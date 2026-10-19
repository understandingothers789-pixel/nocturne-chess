"""Explicit, cancellable opening coverage scan with real service counts."""

from PySide6.QtCore import QObject, QTimer, Signal

from ..explorer import ExplorerCache, ExplorerQuery
from .explorer_client import ExplorerClient


class OpeningCoverage(QObject):
    changed = Signal()

    def __init__(self, cache_path, parent=None):
        super().__init__(parent)
        self.client = ExplorerClient(ExplorerCache(cache_path), self, interval_ms=1500)
        self.client.result.connect(self._result)
        self.client.status.connect(self._status)
        self.context = None
        self.message = ""
        self.departure = None
        self.running = False
        self._generation = 0

    @staticmethod
    def signature(game, source, speed, rating):
        return game.id, tuple(game._line_nodes), source, speed, rating

    def start(self, game, source="masters", speed="all", rating=0, token=""):
        self.cancel()
        if source == "chessdb":
            return
        self.context = self.signature(game, source, speed, rating)
        self.items = []
        for node_id in game._line_nodes:
            board = game.position_at_node(node_id)
            if board.chess960:
                self.message = "Opening coverage is available for standard chess."
                self.changed.emit()
                return
            self.items.append((node_id, ExplorerQuery(board.fen(), source, speed, rating)))
        self.client.set_lichess_token(token)
        self.index = 0
        self.previous_count = None
        self.departure = None
        self.running = True
        self._next()

    def cancel(self, clear=True):
        self._generation += 1
        self.running = False
        self.client.cancel()
        if clear:
            self.context = None
            self.departure = None
            self.message = ""
        else:
            self.message = "Database scan stopped · coverage incomplete"
        self.changed.emit()

    def _next(self):
        if not self.running:
            return
        if self.index == len(self.items):
            self.running = False
            self.message = f"Every position found · final position: {self.previous_count:,} games"
            self.changed.emit()
            return
        self.message = f"Checking database coverage · position {self.index + 1}/{len(self.items)}"
        self.changed.emit()
        self.client.load(self.items[self.index][1])

    def _result(self, key, data, origin):
        if not self.running or key != self.items[self.index][1].key:
            return
        count = data["total"]
        if count == 0:
            self.running = False
            self.departure = self.items[self.index][0]
            self.message = (f"0 games · previous position: {self.previous_count:,} games"
                            if self.previous_count is not None else "0 games at the starting position")
            self.changed.emit()
            return
        self.previous_count = count
        self.index += 1
        generation = self._generation
        QTimer.singleShot(0, lambda: self._next() if generation == self._generation else None)

    def _status(self, key, message):
        if not self.running or self.index >= len(self.items) or key != self.items[self.index][1].key:
            return
        if message.startswith(("Loading ", "Cached ·", "Live ·")):
            return
        self.running = False
        self.message = message + " · coverage incomplete"
        self.changed.emit()

    def close(self):
        self.cancel()
        self.client.close()
