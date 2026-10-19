"""Coverage distinguishes returned zero counts from incomplete requests."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from nocturne.core.game import Game
from nocturne.explorer import ExplorerQuery
from nocturne.gui.opening_coverage import OpeningCoverage


class CoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.coverage = OpeningCoverage(Path(self.tmp.name) / "cache.db")
        self.game = Game.from_pgn("1.e4 e5 *")

    def tearDown(self):
        self.coverage.close()
        self.tmp.cleanup()

    def cache(self, counts, source="masters", speed="all", rating=0):
        for node, count in zip(self.game._line_nodes, counts):
            query = ExplorerQuery(self.game.position_at_node(node).fen(), source, speed, rating)
            self.coverage.client.cache.put(query.key, {"white": count, "draws": 0, "black": 0, "moves": []})

    def test_first_zero_is_a_jump_target_with_previous_sample_count(self):
        self.cache([1000, 23, 0])
        self.coverage.start(self.game)
        for _ in range(5):
            self.app.processEvents()
        self.assertFalse(self.coverage.running)
        self.assertEqual(self.coverage.departure, self.game.current_node)
        self.assertIn("previous position: 23 games", self.coverage.message)

    def test_failure_and_cancellation_never_mean_zero_games(self):
        self.coverage.start(self.game)
        key = self.coverage.items[0][1].key
        self.coverage._status(key, "Lichess Masters access token required")
        self.assertIsNone(self.coverage.departure)
        self.assertIn("coverage incomplete", self.coverage.message)
        self.coverage.cancel()
        self.assertIsNone(self.coverage.context)
        self.assertEqual(self.coverage.message, "")

    def test_all_positive_and_starting_zero_are_distinct(self):
        self.cache([100, 20, 3])
        self.coverage.start(self.game)
        for _ in range(5):
            self.app.processEvents()
        self.assertIsNone(self.coverage.departure)
        self.assertIn("final position: 3 games", self.coverage.message)
        self.cache([0])
        self.coverage.start(self.game, force=True)
        self.assertEqual(self.coverage.departure, 0)
        self.assertIn("starting position", self.coverage.message)

    def test_source_departures_persist_and_restore_without_requests(self):
        self.cache([100, 0], "masters")
        self.cache([1000, 200, 0], "lichess", "rapid", 1800)
        for source in ("masters", "lichess"):
            self.coverage.start(self.game, source, "rapid", 1800)
            for _ in range(5):
                self.app.processEvents()
        markers = self.coverage.markers(self.game, speed="rapid", rating=1800)
        self.assertIn("Lichess Masters", markers[1])
        self.assertIn("Lichess players", markers[2])
        self.assertIn("1800+", markers[2])
        self.assertNotIn(2, self.coverage.markers(self.game, speed="blitz", rating=1800))
        # Store/load uses the same JSON game serialization as an application restart.
        import json
        restored = Game.from_dict(json.loads(json.dumps(self.game.to_dict())))
        self.assertEqual(self.coverage.markers(restored, speed="rapid", rating=1800), markers)
        with patch.object(self.coverage.client, "load") as load:
            self.coverage.start(restored, "masters")
            load.assert_not_called()
        self.assertEqual(self.coverage.departure, 1)
        # An edit/reindex cannot attach the old marker to an unrelated move.
        restored.select_node(1)
        restored.delete_current_line()
        self.assertEqual(self.coverage.markers(restored, speed="rapid", rating=1800), {})

    def test_chessdb_unknown_is_distinct_from_unscored_and_terminal_positions(self):
        for node, status in zip(self.game._line_nodes, ("ok", "ok", "unknown")):
            query = ExplorerQuery(self.game.position_at_node(node).fen(), "chessdb")
            board = self.game.position_at_node(node)
            move = next(iter(board.legal_moves())).uci()
            self.coverage.client.cache.put(query.key, {"status": status, "moves": [
                {"uci": move, "score": "??", "note": ""}] if status == "ok" else []})
        self.coverage.start(self.game, "chessdb")
        for _ in range(5):
            self.app.processEvents()
        self.assertEqual(self.coverage.departure, 2)
        self.assertIn("No stored cloud analysis", self.coverage.message)
        self.assertNotIn("games", self.coverage.message)
        tooltip = self.coverage.markers(self.game, allow_lichess=False)[2]
        self.assertIn("ChessDB Cloud Analysis", tooltip)
        for fen, status in (("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1", "checkmate"),
                            ("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", "stalemate")):
            terminal = Game(fen)
            query = ExplorerQuery(fen, "chessdb")
            self.coverage.client.cache.put(query.key, {"status": status, "moves": []})
            self.coverage.start(terminal, "chessdb")
            for _ in range(3):
                self.app.processEvents()
            self.assertIsNone(self.coverage.departure)
            self.assertIn("Every position", self.coverage.message)

    def test_shared_departure_lists_both_sources_and_failures_are_not_cached(self):
        for source in ("masters", "lichess"):
            self.cache([50, 0], source)
            self.coverage.start(self.game, source)
            for _ in range(3):
                self.app.processEvents()
        tooltip = self.coverage.markers(self.game)[1]
        self.assertIn("Lichess Masters", tooltip)
        self.assertIn("Lichess players", tooltip)
        self.coverage.start(self.game, "chessdb")
        self.coverage._status(self.coverage.items[0][1].key, "ChessDB request timed out")
        self.assertIsNone(self.coverage.departure)
        self.assertNotIn("ChessDB", self.coverage.markers(self.game)[1])
        self.game.metadata["database_coverage"].append({"source": "chessdb"})
        self.assertIn(1, self.coverage.markers(self.game))
