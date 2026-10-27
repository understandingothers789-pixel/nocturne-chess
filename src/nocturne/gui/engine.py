"""Desktop external-engine controller. No custom engine is used by the GUI."""

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from ..core.notation import san
from ..snapshots import milestones
from .uci_connection import UciConnection


class EngineController(QObject):
    message = Signal(int, str, object)
    discovered = Signal(object)
    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.generation = 0
        self.connection = UciConnection(self)
        self.connection.information.connect(self._info)
        self.connection.observation.connect(self._observe)
        self.connection.completed.connect(self._result)
        self.connection.failed.connect(self._error)
        self.connection.discovered.connect(self.discovered)
        self.connection.status.connect(self.status)
        self._busy = False
        self.board = None
        self.lines = {}
        self.exact_lines = {}
        self._snapshot_lines = {}
        self._snapshot_nodes = 0
        self._snapshot_pending = []
        self._snapshot_required = 1
        self._pv_recovery = None
        self._extending_pvs = False
        self._pv_stop_sent = False

    @property
    def busy(self):
        return self._busy

    def set_snapshot_capture(self, enabled):
        if self.connection.observe_nodes == bool(enabled):
            return
        self.connection.observe_nodes = bool(enabled)
        self._snapshot_pending = []
        self._snapshot_lines = {rank: dict(info) for rank, info in self.lines.items()}
        self._snapshot_nodes = max((info.get("nodes", 0) for info in self.lines.values()), default=0)

    def connect_engine(self, path, arguments=None):
        self.stop()
        self.connection.launch(path, arguments)

    def start(
        self,
        game,
        limits,
        external="",
        kind="search",
        tablebase_path="",
        options=None,
        infinite=False,
        multipv=1,
        searchmoves=None,
        arguments=None,
        nodes_only=False,
        ensure_pv_length=False,
    ):
        if not external:
            raise ValueError("Select your Stockfish or another UCI executable first")
        self.stop()
        self.board = game.board.copy()
        self.lines = {}
        self.exact_lines = {}
        self._snapshot_lines = {}
        self._snapshot_nodes = 0
        self._snapshot_pending = []
        legal_count = sum(1 for _ in self.board.legal_moves())
        self._snapshot_required = min(multipv, len(searchmoves) if searchmoves else legal_count)
        desired = dict(options or {})
        desired["MultiPV"] = multipv
        desired["UCI_AnalyseMode"] = kind == "analysis" or infinite
        if tablebase_path:
            desired["SyzygyPath"] = tablebase_path
        desired["UCI_Chess960"] = bool(getattr(self.board, "chess960", False))
        if self.connection.path != str(Path(external).absolute()) or not self.connection.alive:
            self.connection.launch(external, arguments)
        position = "position fen " + game.initial_fen
        if game.cursor:
            position += " moves " + " ".join(m.uci() for m in game.moves[: game.cursor])
        if infinite:
            go = "go infinite"
        elif nodes_only and limits.nodes:
            go = f"go nodes {limits.nodes}"
        else:
            go = f"go depth {limits.depth} movetime {max(1, int(limits.seconds * 1000))}"
        if limits.nodes and not nodes_only and not infinite:
            go += " nodes " + str(limits.nodes)
        if searchmoves:
            valid = [self.board.parse_uci(m).uci() for m in searchmoves]
            go += " searchmoves " + " ".join(valid)
        self._pv_recovery = (position, "go infinite" + (
            " searchmoves " + " ".join(valid) if searchmoves else ""
        ), desired, game.id) if ensure_pv_length and not infinite else None
        self._busy = True
        self.connection.request(self.generation, position, go, desired, game.id)
        return self.generation

    def _validated_info(self, info):
        position = self.board.copy()
        pv, texts = [], []
        for text in info["pv"][:128]:
            try:
                move = position.parse_uci(text)
                texts.append(san(position, move))
                position.push(move)
                pv.append(text)
            except ValueError:
                break
        if not pv:
            return None
        return dict(
            info, pv=pv, san=texts, engine=self.connection.name,
            applied_options={k: v for k, v in self.connection.confirmed.items() if k != "__study"},
        )

    def _observe(self, generation, info):
        if generation != self.generation or not self._busy:
            return
        self._snapshot_lines[info["multipv"]] = dict(info)
        nodes = info.get("nodes", 0)
        self._snapshot_pending.extend(milestones(self._snapshot_nodes, nodes))
        self._snapshot_nodes = max(self._snapshot_nodes, nodes)
        if len(self._snapshot_lines) >= self._snapshot_required:
            self._flush_snapshot()

    def _flush_snapshot(self):
        if not self._snapshot_pending:
            return
        lines = [self._validated_info(self._snapshot_lines[rank]) for rank in sorted(self._snapshot_lines)]
        lines = [line for line in lines if line]
        if lines:
            targets, self._snapshot_pending = self._snapshot_pending, []
            self.message.emit(self.generation, "snapshot", {
                "milestones": targets, "observed_nodes": self._snapshot_nodes, "lines": lines,
            })

    def _info(self, generation, info):
        if generation != self.generation or not self._busy or self._pv_stop_sent:
            return
        info = self._validated_info(info)
        if info is None:
            return
        self.lines[info["multipv"]] = info
        if info.get("bound", "exact") == "exact":
            self.exact_lines[info["multipv"]] = info.copy()
        self.message.emit(generation, "info", info)
        if self._extending_pvs and not self._pv_stop_sent and self._pvs_complete():
            self._pv_stop_sent = True
            # Retain the active generation so bestmove completes normally.
            self.connection.send("stop")

    def _pvs_complete(self):
        for rank in range(1, self._snapshot_required + 1):
            pv = self.lines.get(rank, {}).get("pv", [])
            if len(pv) >= 3:
                continue
            position = self.board.copy()
            for text in pv:
                position.push(position.parse_uci(text))
            if not pv or not position.native.is_game_over(claim_draw=True):
                return False
        return True

    def _continue_pvs(self, generation):
        if generation == self.generation and self._busy and self._pv_recovery:
            self.connection.request(generation, *self._pv_recovery)
            self.status.emit(self.connection.name + " · extending short variations")

    def _result(self, generation, bestmove):
        if generation != self.generation or not self._busy:
            return
        if self._pv_recovery and not self._extending_pvs and not self._pvs_complete():
            self._extending_pvs = True
            QTimer.singleShot(0, lambda: self._continue_pvs(generation))
            return
        self._flush_snapshot()
        self._busy = False
        try:
            if bestmove == "0000" and any(self.board.legal_moves()):
                raise ValueError("No move in a nonterminal position")
            move = self.board.parse_uci(bestmove).uci() if bestmove != "0000" else None
        except ValueError:
            self._error("Engine returned an illegal or outdated move: " + bestmove)
            return
        self.message.emit(
            generation, "result", {
                "move": move,
                "info": self.lines.get(1, {}),
                "lines": {rank: info.copy() for rank, info in self.lines.items()},
                "exact_lines": {rank: info.copy() for rank, info in self.exact_lines.items()},
                "stopped": False,
            }
        )

    def _error(self, message):
        self._busy = False
        self.message.emit(self.generation, "error", {"message": message})

    def stop(self):
        if self._busy and self.connection.observe_nodes:
            self._flush_snapshot()
        self._pv_recovery = None
        self._extending_pvs = False
        self._pv_stop_sent = False
        self.generation += 1
        self._busy = False
        self.lines = {}
        self.exact_lines = {}
        self.connection.stop()

    def close(self):
        self.stop()
        self.connection.close()
