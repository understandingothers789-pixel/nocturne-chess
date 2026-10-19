"""Coverage distinguishes returned zero counts from incomplete requests."""

import os
from pathlib import Path
import tempfile
import unittest

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

    def cache(self, counts):
        for node, count in zip(self.game._line_nodes, counts):
            query = ExplorerQuery(self.game.position_at_node(node).fen())
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
        self.coverage.start(self.game)
        self.assertEqual(self.coverage.departure, 0)
        self.assertIn("starting position", self.coverage.message)
