"""Single authoritative game model, independent of GUI and engine workers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import time
from typing import Any
from uuid import uuid4

from .rules import Board
from .board import Move, Outcome, START_FEN, SQUARES, KING, PAWN, ROOK, QUEEN, BISHOP, KNIGHT
from .notation import PgnGame, pgn_clock, read_pgn, san, write_pgn
from .variation import Node, build_nodes, mainline, ordered_edges, tree_tokens


@dataclass(frozen=True, slots=True)
class TimeControl:
    seconds: float = 0
    increment: float = 0

    def __post_init__(self):
        if not all(math.isfinite(v) and v >= 0 for v in (self.seconds, self.increment)):
            raise ValueError("Time controls must be finite nonnegative numbers")


class Game:
    def __init__(self, fen: str = START_FEN, time_control: TimeControl | None = None):
        self.id = str(uuid4())
        self.board = Board(fen)
        self.initial_fen = self.board.fen()
        self.moves: list[Move] = []
        self.sans: list[str] = []
        self.cursor = 0
        self.headers = {"White": "You", "Black": "Nocturne", "Date": datetime.now().strftime("%Y.%m.%d")}
        self.time_control = time_control or TimeControl()
        self._remaining = {1: self.time_control.seconds, -1: self.time_control.seconds}
        self._clock_history = [self._remaining.copy()]
        self.running = False
        self._anchor = time.monotonic()
        self.declared: Outcome | None = None
        self.evaluations: dict[int, int] = {}
        self.metadata: dict[str, Any] = {}
        self.has_pgn_clocks = False
        self.nodes = [Node(None, None, clock=self._remaining.copy())]
        self._line_nodes = [0]
        self._main_result = "*"

    @property
    def outcome(self) -> Outcome | None:
        return self.declared or self.board.outcome()

    def clock_values(self, now: float | None = None) -> dict[int, float]:
        values = self._remaining.copy()
        if self.running and self.time_control.seconds:
            elapsed = max(0, (time.monotonic() if now is None else now) - self._anchor)
            values[self.board.turn] = max(0, values[self.board.turn] - elapsed)
        return values

    def start_clock(self, now: float | None = None) -> None:
        if self.time_control.seconds and not self.outcome and not self.running:
            self._anchor = time.monotonic() if now is None else now
            self.running = True

    def pause_clock(self, now: float | None = None) -> None:
        self._remaining = self.clock_values(now)
        self.running = False

    def tick(self, now: float | None = None) -> Outcome | None:
        if self.running and self.clock_values(now)[self.board.turn] <= 0:
            loser = self.board.turn
            self.pause_clock(now)
            if self._can_mate(-loser):
                self.declared = Outcome("0-1" if loser == 1 else "1-0", "Time forfeit", -loser)
            else:
                self.declared = Outcome("1/2-1/2", "Time expired; opponent cannot checkmate")
        return self.declared

    def _can_mate(self, color: int) -> bool:
        """Conservative FIDE timeout material test, including possible helpmates."""
        ours = [abs(self.board.cells[s]) for s in SQUARES if self.board.cells[s] * color > 0]
        if any(p in (PAWN, ROOK, QUEEN) for p in ours):
            return True
        minors = [p for p in ours if p != KING]
        if not minors or self.board.insufficient_material():
            return False
        enemy = [abs(self.board.cells[s]) for s in SQUARES if self.board.cells[s] * color < 0]
        if minors == [KNIGHT] and all(p in (KING, QUEEN) for p in enemy):
            return False
        if all(p == BISHOP for p in minors):
            bishops = [s for s in SQUARES if abs(self.board.cells[s]) == BISHOP]
            if len({((s >> 4) + (s & 7)) % 2 for s in bishops}) == 1 and all(
                p in (KING, BISHOP) for p in enemy
            ):
                return False
        return True

    def play(self, move: Move, now: float | None = None) -> str:
        if self.tick(now) or self.outcome:
            raise ValueError("This game has ended")
        legal = list(self.board.legal_moves())
        if move not in legal:
            raise ValueError(f"Illegal move: {move.uci()}")
        notation = san(self.board, move, legal)
        self._sync_tree_state()
        parent = self.current_node
        existing = next((c for c in self.nodes[parent].children if self.nodes[c].move == move), None)
        if existing is not None:
            running = self.running
            self.select_node(existing)
            if running:
                self.start_clock(now)
            return notation
        if len(self.nodes) > 20_000:
            raise ValueError("Move tree exceeds 20,000 nodes")
        self._remaining = self.clock_values(now)
        if self.time_control.seconds:
            self._remaining[self.board.turn] += self.time_control.increment
        self.moves[self.cursor :] = [move]
        self.sans[self.cursor :] = [notation]
        self._clock_history[self.cursor + 1 :] = [self._remaining.copy()]
        self.evaluations = {k: v for k, v in self.evaluations.items() if k <= self.cursor}
        index = len(self.nodes)
        self.nodes.append(Node(parent, move, notation, self.cursor + 1, clock=self._remaining.copy()))
        self.nodes[parent].children.append(index)
        self._line_nodes[self.cursor + 1 :] = [index]
        self.board.push(move)
        self.cursor += 1
        self._anchor = time.monotonic() if now is None else now
        if self.board.outcome():
            self.pause_clock(now)
        return notation

    @property
    def current_node(self):
        return self._line_nodes[self.cursor]

    def _sync_tree_state(self):
        if self.declared and self.current_node == mainline(self.nodes)[-1]:
            self._main_result = self.declared.result
        for ply, index in enumerate(self._line_nodes):
            self.nodes[index].clock = self._clock_history[ply].copy()
            self.nodes[index].evaluation = self.evaluations.get(ply)

    def node_path(self, index):
        if type(index) is not int or not 0 <= index < len(self.nodes):
            raise ValueError("Unknown variation node")
        path = []
        while index is not None:
            path.append(index)
            index = self.nodes[index].parent
        return list(reversed(path))

    def position_at_node(self, index):
        board = Board(self.initial_fen)
        for child in self.node_path(index)[1:]:
            board.push(self.nodes[child].move)
        return board

    def pgn_clock_values(self, index=None):
        """Clock annotations known at a position, keyed by chess color."""
        values = {1: None, -1: None}
        if not self.has_pgn_clocks:
            return values
        path = self.node_path(self.current_node if index is None else index)
        turn = Board(self.initial_fen).turn
        for child in path[1:]:
            clock = pgn_clock(self.nodes[child].comment)
            if clock is not None:
                values[turn] = clock
            turn = -turn
        return values

    def select_node(self, index):
        path = self.node_path(index)
        self.pause_clock()
        self._sync_tree_state()
        self._line_nodes = path[:-1] + mainline(self.nodes, index)
        self.moves = [self.nodes[i].move for i in self._line_nodes[1:]]
        self.sans = [self.nodes[i].san for i in self._line_nodes[1:]]
        self._clock_history = [self.nodes[i].clock.copy() for i in self._line_nodes]
        self.evaluations = {
            p: self.nodes[i].evaluation
            for p, i in enumerate(self._line_nodes)
            if self.nodes[i].evaluation is not None
        }
        self.board = self.position_at_node(index)
        self.cursor = len(path) - 1
        self._remaining = self._clock_history[self.cursor].copy()
        self.declared = None

    def tree_tokens(self):
        return tree_tokens(self.nodes, self.initial_fen)

    def promote_current_line(self):
        for parent, child in zip(self._line_nodes[: self.cursor], self._line_nodes[1 : self.cursor + 1]):
            children = self.nodes[parent].children
            children.remove(child)
            children.insert(0, child)
        self._main_result = "*"

    def delete_current_line(self) -> bool:
        """Remove this move and its subtree; select the nearest surviving sibling."""
        index = self.current_node
        parent = self.nodes[index].parent
        if parent is None:
            return False
        self.pause_clock()
        self._sync_tree_state()
        changes_mainline = index in mainline(self.nodes)
        removed, stack = set(), [index]
        while stack:
            child = stack.pop()
            removed.add(child)
            stack.extend(self.nodes[child].children)
        siblings = self.nodes[parent].children
        slot = siblings.index(index)
        siblings.remove(index)
        target = siblings[min(slot, len(siblings) - 1)] if siblings else parent
        # First leave the removed path while all old IDs are still valid. Compact
        # afterward so deleted nodes cannot reappear through save/restore.
        self.select_node(parent)
        remap = {old: new for new, old in enumerate(i for i in range(len(self.nodes)) if i not in removed)}
        self.nodes = [node for i, node in enumerate(self.nodes) if i not in removed]
        for node in self.nodes:
            node.parent = remap[node.parent] if node.parent is not None else None
            node.children = [remap[c] for c in node.children]
        self._line_nodes = [remap[i] for i in self._line_nodes]
        review = self.metadata.get("review")
        if isinstance(review, dict):
            keys = {str(old): str(new) for old, new in remap.items()}
            self.metadata["review"] = {keys[key]: value for key, value in review.items() if key in keys}
        if changes_mainline:
            self._main_result = "*"
        self.select_node(remap[target])
        return True

    def mainline_node(self, depth):
        path = mainline(self.nodes)
        return path[min(max(0, depth), len(path) - 1)]

    def undo(self) -> bool:
        if not self.cursor:
            return False
        self._sync_tree_state()
        self.pause_clock()
        self.board.pop()
        self.cursor -= 1
        self.declared = None
        self._remaining = self._clock_history[self.cursor].copy()
        return True

    def redo(self) -> bool:
        if self.cursor >= len(self.moves):
            return False
        self.pause_clock()
        self.board.push(self.moves[self.cursor])
        self.cursor += 1
        self.declared = None
        self._remaining = self._clock_history[self.cursor].copy()
        return True

    def navigate(self, cursor: int) -> None:
        if not 0 <= cursor <= len(self.moves):
            raise ValueError("History index out of range")
        previous = self.cursor
        while self.cursor > cursor:
            self.undo()
        while self.cursor < cursor:
            self.redo()
        # When backing out of a variation onto a shared main-line position,
        # make that position's continuation the active path. Otherwise redo
        # would silently resume the old parenthesized variation.
        if cursor < previous and self.current_node == self.mainline_node(cursor):
            self.select_node(self.current_node)

    def resign(self, color: int | None = None) -> None:
        if self.outcome:
            return
        color = self.board.turn if color is None else color
        self.pause_clock()
        self.declared = Outcome("0-1" if color == 1 else "1-0", "Resignation", -color)

    def agree_draw(self) -> None:
        if not self.outcome:
            self.pause_clock()
            self.declared = Outcome("1/2-1/2", "Draw by agreement")

    def claim_draw(self, intended: Move | None = None) -> None:
        if self.outcome:
            raise ValueError("This game has ended")
        reasons = self.board.claimable_draws(intended)
        if not reasons:
            raise ValueError("No valid draw claim in this position")
        self.pause_clock()
        self.declared = Outcome("1/2-1/2", reasons[0])

    def pgn(self) -> str:
        self._sync_tree_state()
        path = mainline(self.nodes)
        outcome = self.outcome if self.current_node == path[-1] else self.position_at_node(path[-1]).outcome()
        result = outcome.result if outcome else self._main_result
        return write_pgn(
            PgnGame(
                self.headers.copy(),
                self.initial_fen,
                result=result,
                edges=ordered_edges(self.nodes),
                annotations=self._pgn_annotations(),
            )
        )

    def _pgn_annotations(self):
        result = {}
        stack = [0]
        while stack:
            index = stack.pop()
            node = self.nodes[index]
            records = self.metadata.get("review", {})
            review = records.get(str(index)) if isinstance(records, dict) else None
            comment = node.comment
            if isinstance(review, dict) and isinstance(review.get("label"), str):
                comment += " [Nocturne review: " + review["label"]
                if isinstance(review.get("loss_cp"), (int, float)):
                    comment += f"; estimated loss {review['loss_cp'] / 100:.2f} pawns"
                if isinstance(review.get("accuracy"), (int, float)):
                    comment += f"; estimated accuracy {review['accuracy']:.1f}%"
                comment += "; " + str(review.get("criteria", "Legacy review; rerun for current accuracy")) + "]"
            result[len(result)] = {
                "comment": comment,
                "starting_comment": node.starting_comment,
                "nags": node.nags.copy(),
                "evaluation": node.evaluation,
                "analysis": node.analysis.copy(),
            }
            stack.extend(reversed(node.children))
        return result

    def fork_for_analysis(self) -> Game:
        fork = Game.from_dict(self.to_dict())
        fork.id = str(uuid4())
        fork.metadata.update({"mode": "analysis", "source_id": self.id})
        return fork

    @classmethod
    def from_pgn(cls, text: str) -> Game:
        parsed = read_pgn(text)
        game = cls(parsed.initial_fen)
        game.headers.update(parsed.headers)
        game.nodes = build_nodes(parsed.initial_fen, parsed.edges)
        for index, data in parsed.annotations.items():
            node = game.nodes[index]
            node.comment = data.get("comment", "")
            node.starting_comment = data.get("starting_comment", "")
            node.nags = data.get("nags", [])
            import re

            match = re.search(r"\[%eval ([#]?[+-]?\d+(?:\.\d+)?)", node.comment)
            if match:
                value = match[1]
                if value.startswith("#"):
                    mate = int(value[1:])
                    node.evaluation = (30000 - min(abs(mate), 999)) * (1 if mate >= 0 else -1)
                    node.analysis = {"score_type": "mate", "white_value": mate}
                else:
                    node.evaluation = round(float(value) * 100)
        game.has_pgn_clocks = any(pgn_clock(node.comment) is not None for node in game.nodes)
        game.evaluations = {0: game.nodes[0].evaluation} if game.nodes[0].evaluation is not None else {}
        game._line_nodes = [0]
        game.select_node(mainline(game.nodes)[-1])
        game._main_result = parsed.result
        if parsed.result != "*" and not game.outcome:
            winner = 1 if parsed.result == "1-0" else -1 if parsed.result == "0-1" else None
            game.declared = Outcome(parsed.result, "Imported PGN result", winner)
        if game.outcome and parsed.result != "*" and parsed.result != game.outcome.result:
            raise ValueError("PGN result conflicts with the final position")
        return game

    def to_dict(self) -> dict:
        self._sync_tree_state()
        return {
            "schema": 2,
            "id": self.id,
            "initial_fen": self.initial_fen,
            "moves": [m.uci() for m in self.moves],
            "cursor": self.cursor,
            "headers": self.headers.copy(),
            "time_control": [self.time_control.seconds, self.time_control.increment],
            "remaining": self.clock_values(),
            "clock_history": self._clock_history,
            "declared": {
                "result": self.declared.result,
                "reason": self.declared.reason,
                "winner": self.declared.winner,
            }
            if self.declared
            else None,
            "evaluations": self.evaluations.copy(),
            "metadata": self.metadata.copy(),
            "tree": [
                {
                    "parent": n.parent,
                    "move": n.move.uci() if n.move else None,
                    "clock": n.clock.copy(),
                    "evaluation": n.evaluation,
                    "children": n.children.copy(),
                    "comment": n.comment,
                    "starting_comment": n.starting_comment,
                    "nags": n.nags.copy(),
                    "analysis": n.analysis.copy(),
                }
                for n in self.nodes
            ],
            "line": self._line_nodes.copy(),
            "main_result": self._main_result,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Game:
        """Replay and validate every move; never trust saved cached board state."""
        try:
            if not isinstance(data, dict):
                raise ValueError("Saved game must be an object")
            if data["schema"] not in (1, 2):
                raise ValueError("Unsupported game schema")
            for key in ("headers", "metadata", "evaluations"):
                if not isinstance(data.get(key, {}), dict):
                    raise ValueError(f"Invalid saved {key}")
            if not isinstance(data.get("remaining"), dict) or not isinstance(data.get("clock_history"), list):
                raise ValueError("Invalid saved clock data")
            if data.get("declared") is not None and not isinstance(data["declared"], dict):
                raise ValueError("Invalid saved outcome")
            game = cls(data["initial_fen"], TimeControl(*data["time_control"]))
            game.id = str(data["id"])
            if not isinstance(data["moves"], list) or len(data["moves"]) > 20_000:
                raise ValueError("Invalid saved move list")
            for text in data["moves"]:
                game.play(game.board.parse_uci(text))
            cursor = data["cursor"]
            if not isinstance(cursor, int) or not 0 <= cursor <= len(game.moves):
                raise ValueError("Invalid saved history cursor")
            clocks = data.get("clock_history", [])
            if len(clocks) != len(game.moves) + 1:
                raise ValueError("Invalid saved clock history")
            game._clock_history = [_clock_record(c) for c in clocks]
            if data["schema"] == 2:
                raw = data.get("tree")
                if not isinstance(raw, list) or not 1 <= len(raw) <= 20_001:
                    raise ValueError("Invalid saved variation tree")
                if raw[0].get("parent") is not None or raw[0].get("move") is not None:
                    raise ValueError("Invalid saved tree root")
                nodes = build_nodes(
                    game.initial_fen, [(n["parent"], Move.from_uci(n["move"])) for n in raw[1:]]
                )
                for node, record in zip(nodes, raw):
                    children = record.get("children", node.children)
                    if (
                        not isinstance(children, list)
                        or any(type(c) is not int for c in children)
                        or sorted(children) != sorted(node.children)
                    ):
                        raise ValueError("Invalid variation child order")
                    node.children = children.copy()
                    node.clock = _clock_record(record["clock"])
                    value = record.get("evaluation")
                    if value is not None and type(value) is not int:
                        raise ValueError("Invalid variation evaluation")
                    node.evaluation = value
                    for field in ("comment", "starting_comment"):
                        text = record.get(field, "")
                        if not isinstance(text, str) or len(text) > 100_000:
                            raise ValueError("Invalid saved annotation")
                        setattr(node, field, text)
                    nags = record.get("nags", [])
                    if not isinstance(nags, list) or any(
                        type(n) is not int or not 0 <= n <= 65535 for n in nags
                    ):
                        raise ValueError("Invalid saved NAGs")
                    node.nags = nags.copy()
                    analysis = record.get("analysis", {})
                    if not isinstance(analysis, dict):
                        raise ValueError("Invalid analysis data")
                    node.analysis = analysis.copy()
                line = data.get("line")
                if (
                    not isinstance(line, list)
                    or not line
                    or line[0] != 0
                    or any(type(i) is not int or not 0 <= i < len(nodes) for i in line)
                    or any(nodes[c].parent != p for p, c in zip(line, line[1:]))
                    or nodes[line[-1]].children
                    or [nodes[i].move for i in line[1:]] != game.moves
                    or [nodes[i].clock for i in line] != game._clock_history
                ):
                    raise ValueError("Invalid saved selected line")
                game.nodes, game._line_nodes = nodes, line.copy()
                game._main_result = data.get("main_result", "*")
                if game._main_result not in ("*", "1-0", "0-1", "1/2-1/2"):
                    raise ValueError("Invalid main-line result")
            game.navigate(cursor)
            game._remaining = _clock_record(data["remaining"])
            game.headers.update({str(k): str(v) for k, v in data.get("headers", {}).items()})
            if declared := data.get("declared"):
                if declared["result"] not in ("1-0", "0-1", "1/2-1/2"):
                    raise ValueError("Invalid saved result")
                winner = {"1-0": 1, "0-1": -1, "1/2-1/2": None}[declared["result"]]
                game.declared = Outcome(declared["result"], str(declared["reason"]), winner)
            game.evaluations = {
                int(k): int(v)
                for k, v in data.get("evaluations", {}).items()
                if 0 <= int(k) <= len(game.moves)
            }
            game.metadata = dict(data.get("metadata", {}))
            game.has_pgn_clocks = any(pgn_clock(node.comment) is not None for node in game.nodes)
            game._sync_tree_state()
            return game
        except (KeyError, TypeError, IndexError, OverflowError, AttributeError) as exc:
            raise ValueError("Incomplete or corrupted game record") from exc


def _clock_record(data: dict) -> dict[int, float]:
    if not isinstance(data, dict):
        raise ValueError("Invalid saved clock record")
    result = {c: float(data.get(str(c), data.get(c, -1))) for c in (1, -1)}
    if any(not math.isfinite(v) or v < 0 for v in result.values()):
        raise ValueError("Invalid saved clock value")
    return result
