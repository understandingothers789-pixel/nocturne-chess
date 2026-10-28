"""Regression checks for aligned controls and panel drag geometry."""
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPlainTextEdit, QAbstractButton
from nocturne.gui.window import MainWindow
from nocturne.gui.notation import FigurineToolButton


class LayoutPolishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = MainWindow(Path(self.tmp.name))
        self.w.timer.stop()
        self.w._analysis_enabled = False
        self.w.analysis_mode = True
        self.w.config.update(mode="analysis", multipv=5)
        self.w._apply_settings()
        self.w._sync_workspace_layout()
        self.w.resize(1900, 1050)
        self.w.show()
        self.app.processEvents()

    def tearDown(self):
        self.w.close()
        self.w.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.tmp.cleanup()

    def test_selected_move_detail_shares_coverage_row(self):
        meter = self.w.maia_insights.blunder
        meter.set_data({"e2e4": {"probability": .684, "category": "best", "loss": 14}}, {"e2e4": "e4"}, "test")
        self.app.processEvents()
        self.assertEqual(meter.coverage.y(), meter.detail.y())
        viewport = self.w.blunder_scroll.viewport()
        self.assertLessEqual(meter.detail.mapTo(viewport, QPoint()).y() + meter.detail.height(), viewport.height())

    def test_note_display_toggle_preserves_notes_and_export(self):
        from nocturne.core.game import Game
        w = self.w
        w.game = Game.from_pgn("1.e4 {An inferred position note.} e5 *")
        w._refresh()
        before = w.game.pgn()
        self.assertIn("An inferred position note.", w.inline_history.toPlainText())
        w.display_actions["show_game_line_notes"].trigger()
        self.assertNotIn("An inferred position note.", w.inline_history.toPlainText())
        self.assertEqual(w.game.pgn(), before)
        w.display_actions["show_game_line_notes"].trigger()
        self.assertIn("An inferred position note.", w.inline_history.toPlainText())
        from nocturne.settings import normalize
        self.assertFalse(normalize({"show_game_line_notes": False})["show_game_line_notes"])

    def test_meter_selector_shares_percentage_strip_row(self):
        meter = self.w.maia_insights.blunder
        self.app.processEvents()
        self.assertLessEqual(abs(meter.move.geometry().center().y() - meter.strip.geometry().center().y()), 3)

    def test_collapsed_moves_click_opens_and_open_click_does_not_collapse(self):
        w = self.w
        w.config["bottom_moves_collapsed"] = True
        w._sync_bottom_moves()
        self.app.processEvents()
        point = w.analysis_moves_panel.mapToGlobal(QPoint(w.analysis_moves_panel.width() // 2, 12))
        target = w.analysis_moves_panel.childAt(w.analysis_moves_panel.mapFromGlobal(point)) or w.analysis_moves_panel
        self.assertNotIsInstance(target, QAbstractButton)
        self.assertTrue(all(control.isHidden() for control in w.bottom_navigation_controls))
        QTest.mouseClick(target, Qt.MouseButton.LeftButton, pos=target.mapFromGlobal(point))
        self.assertFalse(w.config["bottom_moves_collapsed"])
        self.assertFalse(w.analysis_history.isHidden())
        QTest.mouseClick(w.analysis_moves_panel, Qt.MouseButton.LeftButton, pos=QPoint(100, 12))
        self.assertFalse(w.config["bottom_moves_collapsed"])

    def test_pgn_note_editor_updates_game_line_and_export_but_not_bottom_moves(self):
        from nocturne.core.game import Game
        w = self.w
        w.game = Game.from_pgn("1.e4 e5 (1...c5) *")
        w._refresh()
        note = "Keep the center.\nDo not rush <this>."

        def accept_note():
            dialog = QApplication.activeModalWidget()
            self.assertIsInstance(dialog, QDialog)
            dialog.findChild(QPlainTextEdit).setPlainText(note)
            dialog.accept()

        QTimer.singleShot(0, accept_note)
        cursor = w.inline_history.document().find("e4")
        cursor.setPosition(cursor.selectionStart())
        point = w.inline_history.cursorRect(cursor).center() + QPoint(3, 0)
        self.assertEqual(w.inline_history.anchorAt(point), "move:1")
        menu = w._inline_history_context_menu(point)
        next(action for action in menu.actions() if action.text() == "Edit PGN note…").trigger()
        menu.deleteLater()
        self.assertEqual(w.game.nodes[1].comment, note)
        self.assertIn("Keep the center.", w.inline_history.toPlainText())
        self.assertIn("Do not rush <this>.", w.inline_history.toPlainText())
        self.assertNotIn("Keep the center.", w.analysis_history.toPlainText())
        restored = Game.from_pgn(w.game.pgn())
        self.assertEqual(restored.nodes[1].comment, note)
        w.game.nodes[1].comment = "A revised plan."
        w._render_move_history()
        self.assertIn("A revised plan.", w.inline_history.toPlainText())
        self.assertNotIn("Keep the center.", w.inline_history.toPlainText())

    def test_idle_status_space_is_reclaimed(self):
        w = self.w
        w._sync_status_space("Ready · offline")
        self.assertTrue(w.statusBar().isHidden())
        w._sync_status_space("Analyzing next move")
        self.assertFalse(w.statusBar().isHidden())
        self.assertLessEqual(w.statusBar().maximumHeight(), 16)
        self.assertEqual(w.content_layout.contentsMargins().bottom(), 0)

    def test_probability_badges_align_with_mixed_expanders_and_lengths(self):
        panel = self.w.candidates
        panel.set_multipv(5)
        panel.reserve_slots(5)
        panel.set_maia({"e2e4": .000848}, 2200, True)
        for rank in range(1, 6):
            names = ["e4", "e5", "Nf3"] * (30 if rank % 2 else 1)
            panel.update_line(dict(multipv=rank, depth=25, nodes=200000000,
                                   score_type="cp", score_value=20,
                                   pv=["e2e4"], san=names), 1)
        self.app.processEvents()
        badges = list(panel.maia_labels.values())
        self.assertEqual(len({b.mapToGlobal(QPoint()).x() for b in badges}), 1)
        self.assertEqual({b.width() for b in badges}, {84})

    def test_castling_button_reserves_text_width(self):
        short = FigurineToolButton("e4")
        castle = FigurineToolButton("O-O-O")
        try:
            self.assertGreater(castle.minimumSizeHint().width(), short.minimumSizeHint().width())
            self.assertGreaterEqual(castle.minimumSizeHint().width(), 60)
        finally:
            short.deleteLater()
            castle.deleteLater()

    def test_empty_database_shrinks_down_and_gives_game_line_space(self):
        w = self.w
        w.explorer.show()
        w.right_detail_splitter.setSizes([400, 300, 70])
        self.app.processEvents()
        old_height = w.game_line_panel.height()
        old_top = w.explorer.y()
        w.explorer._set_compact_empty(True)
        self.app.processEvents()
        self.assertLessEqual(w.explorer.height(), 88)
        self.assertGreater(w.game_line_panel.height(), old_height)
        self.assertGreater(w.explorer.y(), old_top)
        self.assertEqual(w.right_detail_splitter.widget(2), w.graph)

    def test_dragging_collapsed_bottom_handle_up_reopens_moves(self):
        w = self.w
        w._activate_docked_workspace()
        w._reset_workspace_layout()
        self.app.processEvents()
        w.config["bottom_moves_collapsed"] = True
        w._sync_bottom_moves()
        self.app.processEvents()
        handle = w.workspace_splitter.handle(1)
        start = handle.rect().center()
        global_start = handle.mapToGlobal(start)
        QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=start)
        self.assertGreater(w.analysis_moves_panel.maximumHeight(), 34)
        target = global_start - QPoint(0, 150)
        move = QMouseEvent(QEvent.Type.MouseMove, QPointF(handle.mapFromGlobal(target)), QPointF(target),
                           Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(handle, move)
        QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=handle.mapFromGlobal(target))
        self.app.processEvents()
        self.assertFalse(w.config["bottom_moves_collapsed"])
        self.assertFalse(w.analysis_history.isHidden())
        self.assertGreaterEqual(w.analysis_moves_panel.height(), 90)
