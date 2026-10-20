"""Identity and probability integrity at the Maia/Stockfish boundary."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QApplication

from nocturne.maia import percentage
from nocturne.maia.controller import MaiaController
from nocturne.gui.candidates import CandidatePanel
from nocturne.gui.moves import MoveText


class MaiaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_probability_matches_uci_move_when_stockfish_order_differs(self):
        panel = CandidatePanel(MoveText(auto_fit=True))
        panel.set_maia({"d2d4": 0.1, "e2e4": 0.9}, 1800)
        panel.update_line({"multipv": 1, "pv": ["d2d4"], "san": ["d4"], "score": 30, "score_value": 30, "score_type": "cp", "depth": 12, "seldepth": 16}, 1)
        panel.update_line({"multipv": 2, "pv": ["e2e4"], "san": ["e4"], "score": 20, "score_value": 20, "score_type": "cp", "depth": 12, "seldepth": 16}, 1)
        self.assertEqual(panel.maia_labels[1].text(), "10.0%")
        self.assertEqual(panel.maia_labels[2].text(), "90.0%")
        panel.set_maia({"d2d4": 0.000000001})
        self.assertEqual(panel.maia_labels[1].text(), "1e-07%")
        self.assertEqual(panel.maia_labels[2].text(), "—")
        panel.deleteLater()

    def test_stale_worker_result_never_updates_the_selected_position(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = MaiaController(folder)
            controller._serial = 2
            controller._active = (("key", (1800,)), {"id": 2})
            message = json.dumps({"id": 1, "policies": {"1800": {"e2e4": 1}}, "complete": True})
            with patch.object(controller.process, "readAllStandardOutput", return_value=QByteArray((message+"\n").encode())):
                controller._read()
            self.assertEqual(controller.policies, {})
            controller.stop()

    def test_cache_distinguishes_move_history_and_retains_rating_policies(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = MaiaController(folder)
            controller.request("root", ["g1f3"], 1800)
            first = controller._queued[0][0]
            controller.request("root", ["b1c3"], 1800)
            second = controller._queued[0][0]
            self.assertNotEqual(first, second)
            controller.cache[second] = {"1800": {"a2a3": 1}}
            controller._save_cache()
            restored = MaiaController(Path(folder))
            restored.request("root", ["b1c3"], 1800)
            self.assertEqual(restored.policies, {"1800": {"a2a3": 1}})
            self.assertIsNone(restored._queued)
            controller.stop()
            restored.stop()

    def test_probability_format_does_not_round_small_values_into_fake_matches(self):
        self.assertEqual(percentage(None), "—")
        self.assertEqual(percentage(0), "0%")
        self.assertEqual(percentage(0.000001), "0.0001%")

    def test_rating_chart_uses_exact_points_and_legend_toggle(self):
        from nocturne.core.rules import Board
        from nocturne.gui.maia_insights import MaiaInsights
        tools = MaiaInsights()
        tools.resize(340, 700)
        data = {"400": {"e2e4": 0.3, "d2d4": 0.7}, "1800": {"e2e4": 0.6, "d2d4": 0.4}}
        tools.set_data(data, Board(), 1800)
        tools.show()
        self.app.processEvents()
        tools.grab()
        points = [(move, rating, probability) for _, move, rating, probability in tools.chart.points]
        self.assertIn(("e2e4", 400, 0.3), points)
        self.assertIn(("e2e4", 1800, 0.6), points)
        self.assertNotIn(600, [rating for _, rating, _ in points])
        tools.legend_buttons["e2e4"].click()
        self.assertIn("e2e4", tools.chart.hidden_moves)
        tools.close()
        tools.deleteLater()

    def test_move_map_aggregates_promotions_on_the_same_destination(self):
        from nocturne.core.rules import Board
        from nocturne.core.board import parse_square
        from nocturne.gui.maia_insights import MoveMap
        view = MoveMap()
        view.set_policy(Board("7k/P7/8/8/8/8/8/7K w - - 0 1"), {"a7a8q": 0.6, "a7a8n": 0.4})
        self.assertEqual(view.destinations[parse_square("a8")], 1)
        self.assertFalse(view.interactive)
        self.assertFalse(view.wheel_navigation)
        view.deleteLater()

    def test_blend_reports_unknown_for_unsearched_bound_and_mate_scores(self):
        from nocturne.maia.blend import move_quality, blend_score
        lines = {1: {"pv": ["e2e4"], "score_type": "cp", "score_value": 50},
                 2: {"pv": ["d2d4"], "score_type": "cp", "score_value": -50}}
        quality, loss = move_quality(lines, "d2d4")
        self.assertEqual(loss, 100)
        self.assertAlmostEqual(quality, 0.367879441)
        self.assertEqual(blend_score(0.2, quality, 0), 0.2)
        self.assertEqual(blend_score(0.2, quality, 1), quality)
        self.assertIsNone(blend_score(0.2, None, 0.5))
        self.assertEqual(move_quality(lines, "c2c4"), (None, None))
        lines[1]["bound"] = "lowerbound"
        self.assertEqual(move_quality(lines, "d2d4"), (None, None))
        lines[1] = {"pv": ["e2e4"], "score_type": "mate", "score_value": 3}
        self.assertEqual(move_quality(lines, "d2d4"), (None, None))
