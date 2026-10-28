"""Regression checks for aligned controls and panel drag geometry."""
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
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
        w.config["bottom_moves_collapsed"] = True
        w._sync_bottom_moves()
        self.app.processEvents()
        handle = w.bottom_moves_handle
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
