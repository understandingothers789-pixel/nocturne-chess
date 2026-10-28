"""Maia destination clicks and avoiding redundant GUI work during analysis."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from nocturne.core.board import Board, parse_square
from nocturne.gui.board import BoardWidget
from nocturne.gui.maia_insights import BlunderMeter
from nocturne.gui.window import MainWindow

FEN = "4r1k1/p1qb1pp1/1b5p/3p4/3N2nB/2P2N2/PP2PPPP/R2Q1RK1 b - - 0 1"


class MaiaDestinationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.view = BoardWidget()
        self.view.resize(700, 700)
        self.view.set_position(Board(FEN))
        self.view.smart_move = True
        self.played = []
        self.view.move_requested.connect(lambda move: self.played.append(move.uci()))
        self.addCleanup(self.view.deleteLater)

    def recommend(self):
        board = self.view.board
        self.view.set_maia_recommendations([
            (board.parse_uci("f7f5"), .65, "unknown"),
            (board.parse_uci("b6d4"), .2, "best"),
            (board.parse_uci("a7a5"), .1, "unknown"),
        ])

    def click(self, square):
        QTest.mouseClick(self.view, Qt.MouseButton.LeftButton,
                        pos=self.view.square_rect(parse_square(square)).center().toPoint())

    def test_maia_only_destinations_play_without_stockfish(self):
        self.recommend()
        self.click("f5")
        self.click("d4")
        self.assertEqual(self.played, ["f7f5", "b6d4"])

    def test_shared_destination_prioritizes_stockfish(self):
        self.recommend()
        self.view.set_recommendations([(self.view.board.parse_uci("d7f5"), 1, "+0.1")])
        self.click("f5")
        self.assertEqual(self.played, ["d7f5"])
        # Choosing a piece first remains an explicit way to play another move.
        self.click("d7")
        self.click("f5")
        self.assertEqual(self.played[-1], "d7f5")

    def test_disabled_markers_low_probability_and_preview_do_not_play(self):
        self.recommend()
        self.click("a5")
        self.assertFalse(self.played)
        self.view.set_maia_recommendations(self.view.maia_recommendations, enabled=False)
        self.click("f5")
        self.assertFalse(self.played)
        self.recommend()
        self.view.show_preview(self.view.board.copy())
        self.click("f5")
        self.assertFalse(self.played)
        self.view.clear_preview()
        self.view.overlays = False
        self.click("f5")
        self.assertFalse(self.played)
        self.view.overlays = True
        self.view.interactive = False
        self.click("f5")
        self.assertFalse(self.played)
        self.view.interactive = True
        self.view.smart_move = False
        self.click("f5")
        self.assertFalse(self.played)

    def test_position_change_clears_targets_and_flipped_click_works(self):
        self.recommend()
        self.view.set_position(Board(FEN))
        self.click("f5")
        self.assertFalse(self.played)
        self.recommend()
        self.view.flipped = True
        self.click("d4")
        self.assertEqual(self.played, ["b6d4"])

    def test_circle_uses_most_likely_maia_move_over_different_recorded_move(self):
        self.recommend()
        pawn = self.view.board.parse_uci("f7f5")
        bishop = self.view.board.parse_uci("d7f5")
        self.view.set_maia_recommendations([(bishop, .3, "best"), (pawn, .7, "unknown")])
        self.view.set_game_move(bishop)
        self.click("f5")
        self.assertEqual(self.played, ["f7f5"])

    def test_window_publishes_clickable_maia_targets_and_commits_move(self):
        from nocturne.core.game import Game
        with tempfile.TemporaryDirectory() as folder:
            window = MainWindow(Path(folder))
            try:
                window._analysis_enabled = False
                window.analysis_mode = True
                window.config.update(maia_enabled=True, smart_move=True)
                window.game = Game(FEN)
                with patch.object(window, "_request_maia"), patch.object(window, "_schedule_engine"):
                    window._refresh()
                    window.maia.policies = {str(window.config["maia_rating"]): {"f7f5": .7, "b6d4": .3}}
                    window._sync_blunder()
                    view = window.board_view
                    view.smart_move = True
                    QTest.mouseClick(view, Qt.MouseButton.LeftButton,
                                     pos=view.square_rect(parse_square("f5")).center().toPoint())
                    self.assertEqual(window.game.sans, ["f5"])
                    self.assertFalse(view.maia_recommendations)
            finally:
                window.close()
                window.deleteLater()

    def test_meter_skips_identical_data_but_updates_changed_loss_and_theme(self):
        meter = BlunderMeter()
        self.addCleanup(meter.deleteLater)
        data = {"f7f5": dict(probability=.7, category="best", loss=0)}
        names = {"f7f5": "f5"}
        meter.set_data(data, names, FEN)
        with patch.object(meter.strip, "update", wraps=meter.strip.update) as repaint:
            meter.set_data(data, names, FEN)
            repaint.assert_not_called()
            data["f7f5"]["loss"] = 75
            data["f7f5"]["category"] = "ok"
            meter.set_data(data, names, FEN)
            self.assertIn("0.75 pawns loss", meter.detail.text())
            self.assertEqual(repaint.call_count, 1)
            original = self.app.property("nocturneLightAppearance")
            try:
                self.app.setProperty("nocturneLightAppearance", not bool(original))
                meter.set_data(data, names, FEN)
                self.assertEqual(repaint.call_count, 2)
            finally:
                self.app.setProperty("nocturneLightAppearance", original)

    def test_unchanged_board_recommendations_do_not_request_extra_repaints(self):
        self.recommend()
        entries = [(self.view.board.parse_uci("d7f5"), 1, "+0.1")]
        self.view.set_recommendations(entries)
        with patch.object(self.view, "update", wraps=self.view.update) as repaint:
            self.recommend()
            self.view.set_recommendations(entries)
            repaint.assert_not_called()
            self.view.set_maia_recommendations(self.view.maia_recommendations, enabled=False)
            self.assertEqual(repaint.call_count, 1)

    def test_blank_header_click_collapses_and_reopens_game_moves(self):
        from PySide6.QtCore import QPoint
        with tempfile.TemporaryDirectory() as folder:
            window = MainWindow(Path(folder))
            try:
                window.analysis_mode = True
                window.config["bottom_moves_collapsed"] = False
                window._sync_bottom_moves()
                panel = window.analysis_moves_panel
                window.show()
                self.app.processEvents()
                point = QPoint(100, window.bottom_moves_title.geometry().center().y())
                QTest.mouseClick(panel, Qt.MouseButton.LeftButton, pos=point)
                self.assertTrue(window.config["bottom_moves_collapsed"])
                QTest.mouseClick(panel, Qt.MouseButton.LeftButton, pos=point)
                self.assertFalse(window.config["bottom_moves_collapsed"])
            finally:
                window.close()
                window.deleteLater()
