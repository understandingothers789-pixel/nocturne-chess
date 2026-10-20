"""Cancellable, source-specific coverage with durable departure markers."""

import time

from PySide6.QtCore import QObject, QTimer, Signal

from ..explorer import CACHE_AGE, RATINGS, SPEEDS, ExplorerCache, ExplorerQuery
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
        speed, rating = (speed, rating) if source == "lichess" else ("all", 0)
        path = tuple((node, game.nodes[node].move.uci() if game.nodes[node].move else "")
                     for node in game._line_nodes)
        return game.id, game.initial_fen, path, source, speed, rating

    @staticmethod
    def _records(game):
        records = game.metadata.get("database_coverage", [])
        if not isinstance(records, list):
            return []
        now = time.time()
        return [r for r in records[-64:] if isinstance(r, dict)
                and r.get("source") in ("masters", "lichess", "chessdb")
                and r.get("initial_fen") == game.initial_fen
                and r.get("speed") in ("all", *SPEEDS)
                and type(r.get("rating")) is int and r["rating"] in RATINGS
                and isinstance(r.get("line"), list) and len(r["line"]) <= 20000
                and all(isinstance(move, str) and len(move) <= 5 for move in r["line"])
                and "departure" in r and (r["departure"] is None or type(r["departure"]) is int
                     and 0 <= r["departure"] <= len(r["line"]))
                and isinstance(r.get("message"), str) and len(r["message"]) <= 1000
                and type(r.get("stamp")) in (int, float) and 0 <= now - r["stamp"] < CACHE_AGE]

    @classmethod
    def markers(cls, game, *, allow_lichess=True, speed="all", rating=0):
        """Resolve saved UCI paths anew, so editing/reindexing cannot move a marker."""
        markers = {}
        for record in cls._records(game):
            source, ply = record["source"], record["departure"]
            if not ply or (source != "chessdb" and not allow_lichess):
                continue
            if source == "lichess" and (record["speed"], record["rating"]) != (speed, rating):
                continue
            node = 0
            for uci in record["line"][:ply]:
                node = next((child for child in game.nodes[node].children
                             if game.nodes[child].move.uci() == uci), None)
                if node is None:
                    break
            if node is None:
                continue
            query = ExplorerQuery(game.initial_fen, source, record["speed"], record["rating"])
            label = cls._label(query)
            text = (f"{label}: first position with no stored cloud analysis (unknown)"
                    if source == "chessdb" else f"{label}: first position with no games found")
            markers.setdefault(node, set()).add(text)
        return {node: "\n".join(sorted(labels)) for node, labels in markers.items()}

    @staticmethod
    def _label(query):
        if query.source == "chessdb":
            return "ChessDB Cloud Analysis"
        if query.source == "lichess":
            filters = (query.speed if query.speed != "all" else "all speeds",
                       f"{query.rating}+ rating" if query.rating else "all ratings")
            return "Lichess players (" + ", ".join(filters) + ")"
        return query.label

    def start(self, game, source="masters", speed="all", rating=0, token="", *, force=False):
        self.cancel()
        self.context = self.signature(game, source, speed, rating)
        self.game = game
        self.items = []
        for node_id in game._line_nodes:
            board = game.position_at_node(node_id)
            if board.chess960:
                self.message = "Opening coverage is available for standard chess."
                self.changed.emit()
                return
            self.items.append((node_id, ExplorerQuery(board.fen(), source, speed, rating)))
        query = self.items[0][1]
        self.source_label = self._label(query)
        self.record_key = dict(source=source, speed=speed if source == "lichess" else "all",
                               rating=rating if source == "lichess" else 0, initial_fen=game.initial_fen,
                               line=[game.nodes[node].move.uci() for node in game._line_nodes[1:]])
        self.client.set_lichess_token(token)
        self.index = 0
        self.previous_count = None
        self.departure = None
        if not force:
            for record in reversed(self._records(game)):
                if all(record[k] == value for k, value in self.record_key.items()):
                    self.departure = (self.items[record["departure"]][0]
                                      if record["departure"] is not None else None)
                    self.message = record["message"]
                    self.changed.emit()
                    return
        self.running = True
        self._next()

    def _remember(self):
        records = [record for record in self._records(self.game)
                   if any(record[k] != value for k, value in self.record_key.items())]
        ply = next((i for i, (node, _) in enumerate(self.items) if node == self.departure), None)
        records.append(dict(self.record_key, departure=ply, message=self.message, stamp=time.time()))
        self.game.metadata["database_coverage"] = records[-64:]

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
            detail = ("Every position has stored cloud analysis" if self.record_key["source"] == "chessdb"
                      else f"Every position found · final position: {self.previous_count:,} games")
            self.message = f"{self.source_label} · {detail}"
            self._remember()
            self.changed.emit()
            return
        self.message = f"Checking database coverage · position {self.index + 1}/{len(self.items)}"
        self.changed.emit()
        self.client.load(self.items[self.index][1])

    def _result(self, key, data, origin):
        if not self.running or key != self.items[self.index][1].key:
            return
        cloud = self.record_key["source"] == "chessdb"
        count = data.get("total")
        if (cloud and data.get("status") == "unknown") or (not cloud and count == 0):
            self.running = False
            self.departure = self.items[self.index][0]
            detail = ("No stored cloud analysis" if cloud else
                      f"0 games · previous position: {self.previous_count:,} games"
                      if self.previous_count is not None else "0 games at the starting position")
            self.message = f"{self.source_label} · {detail}"
            self._remember()
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
