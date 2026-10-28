"""Behavior at the boundaries of the PGN and validated variation caches."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from nocturne.core.rules import Board
from nocturne.gui.engine import EngineController
from nocturne.gui.window import MainWindow


class PerformancePathsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_validation_cache_handles_changed_pvs_positions_and_caller_mutation(self):
        controller = EngineController()
        controller.board = Board()
        info = dict(pv=["e2e4", "e7e5", "g1f3"], nodes=1)
        result = controller._validated_info(info)
        self.assertEqual(result["san"], ["e4", "e5", "Nf3"])
        result["san"].clear()
        result["pv"].clear()
        again = controller._validated_info(info | {"nodes": 9})
        self.assertEqual(again["san"], ["e4", "e5", "Nf3"])
        self.assertEqual(again["nodes"], 9)
        invalid = controller._validated_info(dict(pv=["e2e4", "e7e5", "e2e4"]))
        self.assertEqual(invalid["pv"], ["e2e4", "e7e5"])
        controller.board = Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
        self.assertIsNone(controller._validated_info(info))
        controller.deleteLater()

    def test_pgn_editor_loads_current_game_when_opened_and_preserves_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(Path(directory))
            try:
                window._analysis_enabled = False
                window.analysis_mode = True
                window.config["maia_enabled"] = False
                window.game.play(window.game.board.parse_uci("e2e4"))
                window.tabs.setCurrentIndex(1)
                with patch.object(window.game, "pgn", wraps=window.game.pgn) as export:
                    window._refresh()
                    export.assert_not_called()
                    window.tabs.setCurrentWidget(window.pgn_page)
                    self.assertIn("e4", window.pgn_editor.toPlainText())
                    self.assertEqual(export.call_count, 1)
                window.pgn_editor.setPlainText("1. d4")
                window.pgn_editor.document().setModified(True)
                window.tabs.setCurrentIndex(1)
                window._refresh()
                window.tabs.setCurrentWidget(window.pgn_page)
                self.assertEqual(window.pgn_editor.toPlainText(), "1. d4")
            finally:
                window.close()
                window.deleteLater()

    def test_meter_cache_reuses_results_and_invalidates_changed_policy_and_score(self):
        from nocturne.gui.maia_insights import MaiaInsights
        from nocturne.maia.risk import assess_moves
        widget = MaiaInsights()
        try:
            board = Board()
            policy = {"e2e4": .7, "d2d4": .3}
            lines = {1: dict(pv=["e2e4"], score_type="cp", score_value=20, depth=12, nodes=100)}
            with patch("nocturne.gui.maia_insights.assess_moves", wraps=assess_moves) as assess:
                first = widget.set_analysis(policy, board, lines)
                again = widget.set_analysis(policy, board, lines)
                self.assertEqual(first, again)
                self.assertEqual(assess.call_count, 1)
                widget.set_analysis({"e2e4": .6, "d2d4": .4}, board, lines)
                self.assertEqual(assess.call_count, 2)
                lines[1]["score_value"] = 50
                widget.set_analysis(policy, board, lines)
                self.assertEqual(assess.call_count, 3)
        finally:
            widget.close()
            widget.deleteLater()
