"""Small rendering checks, also runnable with QT_SCALE_FACTOR=1.25 or 2."""

import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea

from nocturne.gui.board import BoardWidget
from nocturne.gui.candidates import CandidatePanel
from nocturne.gui.moves import MoveText
from nocturne.gui.study_tabs import StudyTabBar
from nocturne.gui.theme import stylesheet


class RenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_tabs_keep_live_text_and_native_reordering_during_drag(self):
        class ObservedTabs(StudyTabBar):
            live_paints = 0

            def eventFilter(self, watched, event):
                handled = super().eventFilter(watched, event)
                if event.type() == QEvent.Type.Paint and handled:
                    self.live_paints += 1
                return handled

        bar = ObservedTabs()
        self.addCleanup(bar.close)
        bar.setStyleSheet(stylesheet(False))
        bar.setMovable(True)
        bar.setTabsClosable(True)
        bar.setExpanding(False)
        for title in ("Study — sharp text", "Recorded chess game", "Third PGN"):
            bar.addTab(title)
        bar.resize(700, 45)
        bar.show()
        self.app.processEvents()
        before = bar.grab().toImage()
        start = bar.tabRect(0).center()
        QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=start)
        self.app.processEvents()
        self.assertEqual(before, bar.grab().toImage())
        end = bar.tabRect(1).center()
        event = QMouseEvent(QEvent.Type.MouseMove, QPointF(end), QPointF(bar.mapToGlobal(end)),
                            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(bar, event)
        self.app.processEvents()
        self.assertGreater(bar.live_paints, 0)
        self.assertEqual(bar.tabText(1), "Study — sharp text")
        QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=end)
        QTest.qWait(260)
        self.assertEqual(bar._drag_index, -1)
        self.assertEqual(bar.tabText(1), "Study — sharp text")
        self.assertTrue(bar.isMovable())

    def test_rank_labels_are_on_right_in_both_orientations(self):
        board = BoardWidget()
        self.addCleanup(board.close)
        board.resize(650, 650)
        board.show()
        self.app.processEvents()
        for flipped in (False, True):
            board.flipped = flipped
            board.coordinates = False
            bare = board.grab().toImage()
            board.coordinates = True
            labelled = board.grab().toImage()
            rect, unit = board._geometry()
            ratio = board.devicePixelRatioF()
            y, height = int(rect.top() * ratio), int(unit * 7 * ratio)
            width = int(unit * 0.25 * ratio)
            left = int(rect.left() * ratio)
            right = int((rect.right() - unit * 0.25) * ratio)
            self.assertEqual(bare.copy(left, y, width, height), labelled.copy(left, y, width, height))
            self.assertNotEqual(bare.copy(right, y, width, height), labelled.copy(right, y, width, height))

    def test_first_move_follows_evaluation_on_same_visual_line(self):
        panel = CandidatePanel(MoveText(auto_fit=True))
        self.addCleanup(panel.close)
        panel.resize(800, 250)
        panel.update_line(dict(depth=18, seldepth=25, score_type="cp", score_value=22,
                               score=22, nodes=1000, pv=["e2e4", "e7e5"], san=["e4", "e5"]), 1)
        panel.show()
        self.app.processEvents()
        _, header, moves = panel.rows[1]
        self.assertTrue(" ".join(moves.toPlainText().split()).startswith("+0.22 e4 e5"))
        score = moves.document().find("+0.22")
        move = moves.document().find("e4")
        layout = move.block().layout()
        self.assertEqual(layout.lineForTextPosition(score.selectionStart()).y(),
                         layout.lineForTextPosition(move.selectionStart()).y())
        self.assertTrue(header.isHidden())

        panel.set_detailed(True)
        self.app.processEvents()
        self.assertGreater(header.mapTo(panel, QPoint()).y(), moves.mapTo(panel, QPoint()).y())
        panel.set_detailed(False)
        self.assertTrue(header.isHidden())

    def test_arrow_receives_real_pointer_click_and_expands_only_its_variation(self):
        panel = CandidatePanel(MoveText(auto_fit=True))
        area = QScrollArea()
        self.addCleanup(area.close)
        area.setWidgetResizable(True)
        area.setWidget(panel)
        available = self.app.primaryScreen().availableGeometry()
        area.resize(min(480, available.width() - 20), min(300, available.height() - 20))
        panel.set_multipv(2)
        info = dict(depth=18, seldepth=25, score_type="cp", score_value=22, score=22,
                    nodes=1000, pv=["g1f3", "g8f6", "f3g1", "f6g8"] * 12,
                    san=["Nf3", "Nf6", "Ng1", "Ng8"] * 12)
        for rank in (1, 2):
            panel.update_line(info | {"multipv": rank}, 1)
        area.show()
        self.app.processEvents()
        arrow = panel.expand_buttons[1]
        self.assertTrue(arrow.isVisible())
        for expected in (0, 1):
            center = arrow.mapToGlobal(arrow.rect().center())
            self.assertIs(QApplication.widgetAt(center), arrow)
            QTest.mouseClick(area.windowHandle(), Qt.MouseButton.LeftButton,
                             pos=area.mapFromGlobal(center))
            self.app.processEvents()
            self.assertEqual(panel.rows[1][2]._reserved_lines, expected)
            self.assertEqual(panel.rows[2][2]._reserved_lines, 1)

    def test_fresh_profile_previews_on_cursor_board_and_keeps_opt_out(self):
        from nocturne.gui.window import MainWindow

        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(Path(directory))
            try:
                window.show()
                self.app.processEvents()
                self.assertTrue(window.cursor_preview_action.isChecked())
                before = window.game.board.fen()
                position = window.game.board.copy()
                move = position.parse_uci("e2e4")
                position.push(move)
                window._show_move_preview("candidate", position, move, "Candidate preview")
                self.assertTrue(window.hover_preview.isVisible())
                self.assertGreaterEqual(window.hover_preview.board.width(), 320)
                self.assertEqual(window.board_view.display_board.fen(), before)
                self.assertEqual(window.hover_preview.board.display_board.fen(), position.fen())
                window._set_cursor_preview(False)
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()
            reopened = MainWindow(Path(directory))
            try:
                self.assertFalse(reopened.cursor_preview_action.isChecked())
            finally:
                reopened.close()
                reopened.deleteLater()
                self.app.processEvents()
