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
            # Policy-only caches must backfill the newly exposed outcome head.
            self.assertIsNotNone(restored._queued)
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

    def test_scatter_map_keeps_promotion_identity_and_click_inspects_without_playing(self):
        from nocturne.core.rules import Board
        from nocturne.gui.maia_insights import MaiaInsights
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        board = Board("7k/P7/8/8/8/8/8/7K w - - 0 1")
        original = board.fen()
        tools = MaiaInsights()
        tools.resize(340, 950)
        policy = {"a7a8q": .6, "a7a8n": .3, "h1h2": .1}
        lines = {1: {"pv": ["a7a8q"], "score_type": "cp", "score_value": 400},
                 2: {"pv": ["a7a8n"], "score_type": "cp", "score_value": 200}}
        tools.set_analysis(policy, board, lines)
        tools.show()
        self.app.processEvents()
        tools.map.grab()
        points = {uci: point for point, uci in tools.map.points}
        self.assertEqual(set(points), {"a7a8q", "a7a8n"})
        self.assertGreater(points["a7a8q"].x(), points["a7a8n"].x())
        self.assertLess(points["a7a8q"].y(), points["a7a8n"].y())
        QTest.mouseClick(tools.map, Qt.MouseButton.LeftButton, pos=points["a7a8n"].toPoint())
        self.assertEqual(tools.blunder.move.currentData(), "a7a8n")
        self.assertEqual(board.fen(), original)
        self.assertAlmostEqual(tools.blunder.strip.totals["blunder"], .3)
        self.assertAlmostEqual(tools.blunder.strip.totals["unknown"], .1)
        tools.set_analysis({}, Board(), {})
        self.assertEqual(tools.map.points, [])
        self.assertEqual(tools.blunder.move.count(), 0)
        tools.close()
        tools.deleteLater()

    def test_blunder_buckets_preserve_unknown_mass_and_exact_thresholds(self):
        from nocturne.maia.risk import assess_moves
        policy = {"e2e4": .2, "d2d4": .2, "g1f3": .2, "b1c3": .1, "c2c4": .2, "a2a3": .1}
        lines = {i: {"pv": [uci], "score_type": "cp", "score_value": cp}
                 for i, (uci, cp) in enumerate(zip(policy, (200, 150, 50, 49, 0)), 1)}
        lines[5]["bound"] = "upperbound"
        result = assess_moves(policy, lines)
        self.assertEqual([d["category"] for d in result.values()],
                         ["best", "best", "ok", "blunder", "unknown", "unknown"])
        self.assertAlmostEqual(sum(d["probability"] for d in result.values() if d["category"] == "unknown"), .3)
        self.assertEqual(result["g1f3"]["loss"], 150)
        lines[1] = {"pv": ["e2e4"], "score_type": "mate", "score_value": 3}
        self.assertTrue(all(d["category"] == "unknown" for d in assess_moves(policy, lines).values()))

    def test_black_risk_uses_raw_uci_scores_and_duplicate_roots_count_once(self):
        from nocturne.maia.risk import assess_moves
        lines = {1: {"pv": ["e7e5"], "score_type": "cp", "score_value": -50, "depth": 22},
                 2: {"pv": ["d7d5"], "score_type": "cp", "score_value": -210},
                 3: {"pv": ["e7e5"], "score_type": "cp", "score_value": 100, "depth": 20}}
        result = assess_moves({"e7e5": .7, "d7d5": .3}, lines)
        self.assertEqual(result["e7e5"]["category"], "best")
        self.assertEqual(result["d7d5"]["loss"], 160)
        self.assertEqual(result["d7d5"]["category"], "blunder")
        self.assertEqual(sum(d["probability"] for d in result.values()), 1)

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

    def test_chess960_retains_stockfish_without_unsupported_maia_predictions(self):
        import chess
        from nocturne.core.game import Game
        from nocturne.gui.window import MainWindow
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(Path(directory))
            window.timer.stop()
            window.autosave_timer.stop()
            window._analysis_enabled = False
            window.maia.policies = {"1800": {"e2e4": 1}}
            window.game = Game(chess.Board.from_chess960_pos(0).shredder_fen())
            window.analysis_mode = True
            generation = window.engine.generation
            window._request_maia()
            self.assertEqual(window.maia.policies, {})
            self.assertIn("standard chess only", window.maia_controls.status.text())
            self.assertEqual(window.engine.generation, generation)
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_leaving_analysis_clears_maia_overlays_and_hidden_tools_skip_sweeps(self):
        from nocturne.gui.window import MainWindow
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(Path(directory))
            window.timer.stop()
            window.autosave_timer.stop()
            window._analysis_enabled = False
            window.analysis_mode = True
            window.maia.policies = {"1800": {"e2e4": 1}}
            window._maia_changed(window.maia.policies)
            self.assertTrue(window.board_view.maia_recommendations)
            window.analysis_mode = False
            window._maia_changed(window.maia.policies)
            self.assertEqual(window.board_view.maia_recommendations, [])
            window.analysis_mode = True
            window.config["show_maia_insights"] = False
            with patch.object(window.maia, "request") as request:
                window._request_maia()
                self.assertFalse(request.call_args.kwargs["sweep"])
                window.config["show_maia_insights"] = True
                window._request_maia()
                self.assertTrue(request.call_args.kwargs["sweep"])
            window.close()
            window.deleteLater()
            self.app.processEvents()
