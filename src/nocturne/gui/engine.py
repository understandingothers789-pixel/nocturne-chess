"""Desktop external-engine controller. No custom engine is used by the GUI."""

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ..core.notation import san
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
        self.connection.completed.connect(self._result)
        self.connection.failed.connect(self._error)
        self.connection.discovered.connect(self.discovered)
        self.connection.status.connect(self.status)
        self._busy = False
        self.board = None
        self.lines = {}

    @property
    def busy(self):
        return self._busy

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
    ):
        if not external:
            raise ValueError("Select your Stockfish or another UCI executable first")
        self.stop()
        self.board = game.board.copy()
        self.lines = {}
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
        go = (
            "go infinite"
            if infinite
            else f"go depth {limits.depth} movetime {max(1, int(limits.seconds * 1000))}"
        )
        if limits.nodes:
            go += " nodes " + str(limits.nodes)
        if searchmoves:
            valid = [self.board.parse_uci(m).uci() for m in searchmoves]
            go += " searchmoves " + " ".join(valid)
        self._busy = True
        self.connection.request(self.generation, position, go, desired, game.id)
        return self.generation

    def _info(self, generation, info):
        if generation != self.generation or not self._busy:
            return
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
            return
        info = dict(
            info, pv=pv, san=texts, engine=self.connection.name,
            applied_options={k: v for k, v in self.connection.confirmed.items() if k != "__study"},
        )
        self.lines[info["multipv"]] = info
        self.message.emit(generation, "info", info)

    def _result(self, generation, bestmove):
        if generation != self.generation or not self._busy:
            return
        self._busy = False
        try:
            if bestmove == "0000" and any(self.board.legal_moves()):
                raise ValueError("No move in a nonterminal position")
            move = self.board.parse_uci(bestmove).uci() if bestmove != "0000" else None
        except ValueError:
            self._error("Engine returned an illegal or outdated move: " + bestmove)
            return
        self.message.emit(
            generation, "result", {"move": move, "info": self.lines.get(1, {}), "stopped": False}
        )

    def _error(self, message):
        self._busy = False
        self.message.emit(self.generation, "error", {"message": message})

    def stop(self):
        self.generation += 1
        self._busy = False
        self.lines = {}
        self.connection.stop()

    def close(self):
        self.stop()
        self.connection.close()
