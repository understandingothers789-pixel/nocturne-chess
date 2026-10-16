"""Single authoritative game model, independent of GUI and engine workers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import time
from typing import Any
from uuid import uuid4

from .board import Board, Move, Outcome, START_FEN, SQUARES, KING, PAWN, ROOK, QUEEN, BISHOP, KNIGHT
from .notation import PgnGame, read_pgn, san, write_pgn


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
            if len({((s >> 4) + (s & 7)) % 2 for s in bishops}) == 1 and all(p in (KING, BISHOP) for p in enemy):
                return False
        return True

    def play(self, move: Move, now: float | None = None) -> str:
        if self.tick(now) or self.outcome:
            raise ValueError("This game has ended")
        legal = list(self.board.legal_moves())
        if move not in legal:
            raise ValueError(f"Illegal move: {move.uci()}")
        notation = san(self.board, move, legal)
        self._remaining = self.clock_values(now)
        if self.time_control.seconds:
            self._remaining[self.board.turn] += self.time_control.increment
        self.moves[self.cursor:] = [move]
        self.sans[self.cursor:] = [notation]
        self._clock_history[self.cursor + 1:] = [self._remaining.copy()]
        self.evaluations = {k: v for k, v in self.evaluations.items() if k <= self.cursor}
        self.board.push(move)
        self.cursor += 1
        self._anchor = time.monotonic() if now is None else now
        if self.board.outcome():
            self.pause_clock(now)
        return notation

    def undo(self) -> bool:
        if not self.cursor:
            return False
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
        while self.cursor > cursor:
            self.undo()
        while self.cursor < cursor:
            self.redo()

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
        outcome = self.outcome
        return write_pgn(PgnGame(self.headers.copy(), self.initial_fen,
                                 self.moves[:self.cursor], outcome.result if outcome else "*"))

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
        for move in parsed.moves:
            game.play(move)
        if parsed.result != "*" and not game.outcome:
            winner = 1 if parsed.result == "1-0" else -1 if parsed.result == "0-1" else None
            game.declared = Outcome(parsed.result, "Imported PGN result", winner)
        if game.outcome and parsed.result != "*" and parsed.result != game.outcome.result:
            raise ValueError("PGN result conflicts with the final position")
        return game

    def to_dict(self) -> dict:
        return {"schema": 1, "id": self.id, "initial_fen": self.initial_fen,
                "moves": [m.uci() for m in self.moves], "cursor": self.cursor,
                "headers": self.headers.copy(), "time_control": [self.time_control.seconds, self.time_control.increment],
                "remaining": self.clock_values(), "clock_history": self._clock_history,
                "declared": {"result": self.declared.result, "reason": self.declared.reason,
                             "winner": self.declared.winner} if self.declared else None,
                "evaluations": self.evaluations, "metadata": self.metadata}

    @classmethod
    def from_dict(cls, data: dict) -> Game:
        """Replay and validate every move; never trust saved cached board state."""
        try:
            if not isinstance(data, dict):
                raise ValueError("Saved game must be an object")
            if data["schema"] != 1:
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
            game.navigate(cursor)
            game._remaining = _clock_record(data["remaining"])
            game.headers.update({str(k): str(v) for k, v in data.get("headers", {}).items()})
            if declared := data.get("declared"):
                if declared["result"] not in ("1-0", "0-1", "1/2-1/2"):
                    raise ValueError("Invalid saved result")
                winner = {"1-0": 1, "0-1": -1, "1/2-1/2": None}[declared["result"]]
                game.declared = Outcome(declared["result"], str(declared["reason"]), winner)
            game.evaluations = {int(k): int(v) for k, v in data.get("evaluations", {}).items()
                                if 0 <= int(k) <= len(game.moves)}
            game.metadata = dict(data.get("metadata", {}))
            return game
        except (KeyError, TypeError, IndexError, OverflowError) as exc:
            raise ValueError("Incomplete or corrupted game record") from exc


def _clock_record(data: dict) -> dict[int, float]:
    if not isinstance(data, dict):
        raise ValueError("Invalid saved clock record")
    result = {c: float(data.get(str(c), data.get(c, -1))) for c in (1, -1)}
    if any(not math.isfinite(v) or v < 0 for v in result.values()):
        raise ValueError("Invalid saved clock value")
    return result
