"""Small rendering checks, also runnable with QT_SCALE_FACTOR=1.25 or 2."""

import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QMouseEvent, QWheelEvent
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

    def test_vertical_candidate_transition_keeps_preview_until_real_exit(self):
        panel = CandidatePanel(MoveText(auto_fit=True))
        self.addCleanup(panel.close)
        for rank in (1, 2):
            panel.update_line(dict(multipv=rank, depth=18, score_type="cp", score_value=22,
                                   score=22, pv=["e2e4"], san=["e4"]), 1)
        endings = []
        panel.preview_end.connect(lambda: endings.append(True))
        panel._hover(1, 1)
        panel._defer_end_hover(1)
        panel._hover(2, 1)
        QTest.qWait(180)
        self.assertFalse(endings)
        self.assertEqual(panel.hovered, 2)
        panel._defer_end_hover(2)
        QTest.qWait(180)
        self.assertEqual(len(endings), 1)

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
        gap = moves.document().find("e4")
        gap.setPosition(gap.selectionEnd())
        point = moves.cursorRect(gap).center() + QPoint(3, 0)
        self.assertEqual(moves._move_at(point).toString(), "move:1")
        end = moves.document().find("e5")
        end.setPosition(end.selectionEnd())
        self.assertTrue(moves._move_at(moves.cursorRect(end).center() + QPoint(12, 0)).isEmpty())

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

    def test_wheel_keeps_score_visible_and_switching_candidates_resets_progress(self):
        panel = CandidatePanel(MoveText(auto_fit=True))
        self.addCleanup(panel.close)
        panel.resize(320, 200)
        panel.set_multipv(2)
        info = dict(depth=18, seldepth=25, score_type="cp", score_value=22, score=22,
                    nodes=1000, pv=["g1f3", "g8f6", "f3g1", "f6g8"] * 12,
                    san=["Nf3", "Nf6", "Ng1", "Ng8"] * 12)
        for rank in (1, 2):
            panel.update_line(info | {"multipv": rank}, 1)
        panel.show()
        self.app.processEvents()
        moves = panel.rows[1][2]
        for _ in range(10):
            event = QWheelEvent(QPointF(8, 8), QPointF(8, 8), QPoint(), QPoint(0, -120),
                                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                Qt.ScrollPhase.NoScrollPhase, False)
            QApplication.sendEvent(moves.viewport(), event)
        self.assertEqual(moves.wheel_preview_ply, 10)
        self.assertEqual(moves.verticalScrollBar().value(), 0)
        self.assertGreaterEqual(moves.cursorRect(moves.document().find("+0.22")).top(), 0)
        # Exercise a candidate change even if a platform misses viewport Leave.
        panel.rows[2][2]._highlight(QUrl("move:1"))
        self.assertIsNone(moves.wheel_preview_ply)
        self.assertIsNone(moves._hovered)
        moves._highlight(QUrl("move:1"))
        self.assertEqual(moves._hovered, 1)
        self.assertIsNone(moves.wheel_preview_ply)

    def test_narrow_engine_page_keeps_controls_and_maia_percentages_in_view(self):
        from nocturne.gui.window import MainWindow

        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(Path(directory))
            try:
                window.timer.stop()
                window.autosave_timer.stop()
                window._analysis_enabled = False
                window.analysis_mode = True
                window.resize(1024, 660)
                window.show()
                window._refresh()
                info = dict(depth=18, seldepth=25, score_type="cp", score_value=22, score=22,
                            nodes=1000, pv=["g1f3"], san=["Nf3"])
                window.candidates.update_line(info, 1)
                window._maia_changed({"1800": {"g1f3": 0.4}})
                for light in (False, True):
                    window.config["light"] = light
                    window._apply_settings()
                    window.engine_state.setText("Stockfish dev-20261017-effdc3fd · saved analysis")
                    QTest.qWait(60)
                    viewport = window.panel.viewport()
                    self.assertEqual(window.panel_body.width(), viewport.width())
                    for widget in (window.maia_controls.settings_button, window.maia_controls.rating,
                                   window.eval_label, window.candidates.maia_labels[1]):
                        left = widget.mapTo(viewport, QPoint(0, 0)).x()
                        self.assertGreaterEqual(left, 0)
                        self.assertLessEqual(left + widget.width(), viewport.width())
                    self.assertIn("dev-20261017-effdc3fd", window.engine_state.text())
                    status = window.maia_controls.status
                    status.setText("Ready")
                    self.app.processEvents()
                    row_y = window.candidates.mapTo(viewport, QPoint(0, 0)).y()
                    message = "Maia is waiting for this position's complete local human-move prediction policy."
                    status.setText(message)
                    self.app.processEvents()
                    self.assertEqual(window.candidates.mapTo(viewport, QPoint(0, 0)).y(), row_y)
                    self.assertEqual(status.toolTip(), message)
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()
