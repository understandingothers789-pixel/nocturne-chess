"""Native Qt integration tests. Explicitly skipped if the binding is absent."""

import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from nocturne.core.board import parse_square
from nocturne.core.game import Game

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QEvent, QPointF, QTimer, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMenu, QWidget
    from nocturne.gui.window import MainWindow
    HAS_QT = True
except ImportError:
    HAS_QT = False

@unittest.skipUnless(HAS_QT, "PySide6 is not installed; native GUI validation not executed")
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.window = MainWindow(Path(self.tmp.name))
        self.window.config.update({"mode": "human", "animations": False})
        self.window.game.metadata["mode"] = "human"
        self.window.board_view.animations = False
        self.window.timer.stop()
        self.window.autosave_timer.stop()
        self.window._refresh()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.tmp.cleanup()

    def _click(self, name):
        board = self.window.board_view
        QTest.mouseClick(board, Qt.MouseButton.LeftButton,
                         pos=board.square_rect(parse_square(name)).center().toPoint())
        self.app.processEvents()

    def test_click_move_updates_model_board_and_san_history(self):
        self._click("e2")
        self.assertEqual(self.window.board_view.selected, parse_square("e2"))
        self._click("e4")
        self.assertEqual(self.window.game.cursor, 1)
        self.assertEqual(self.window.game.sans, ["e4"])
        self.assertEqual(self.window.history.item(0, 1).text(), "e4")
        self.assertEqual(self.window.game.board.cells[parse_square("e4")], 1)
        self.assertIs(self.window.board_view.board, self.window.game.board)

    def test_nibbler_style_menus_and_no_widget_tooltips(self):
        self.assertEqual([a.text().replace("&", "") for a in self.window.menuBar().actions()],
                         ["File", "Tree", "Analysis", "Display", "Engine", "Play"])
        self.assertTrue(all(not w.toolTip() for w in self.window.findChildren(QWidget)))
        action = self.window.display_actions["coordinates"]
        action.trigger()
        self.assertFalse(self.window.board_view.coordinates)
        action.trigger()
        self.assertTrue(self.window.board_view.coordinates)

    def test_file_menu_opens_by_mouse_and_exposes_clipboard_commands(self):
        bar = self.window.menuBar()
        QTest.mouseClick(bar, Qt.MouseButton.LeftButton,
                         pos=bar.actionGeometry(self.window.menus["File"].menuAction()).center())
        self.app.processEvents()
        menu = self.window.menus["File"]
        self.assertTrue(menu.isVisible())
        self.assertIn(self.window.menu_actions["load_clipboard"], menu.actions())
        self.assertIn(self.window.menu_actions["copy_pgn"], menu.actions())
        menu.close()

    def test_paste_plain_moves_apply_and_copy_pgn_without_file(self):
        self.window._show_pgn()
        editor = self.window.pgn_editor
        QApplication.clipboard().setText("1. e4 e5 2. Nf3 Nc6 *")
        editor.selectAll()
        QTest.keyClick(editor, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        with patch.object(self.window, "_schedule_engine"):
            QTest.mouseClick(self.window.apply_pgn_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.game.sans, ["e4", "e5", "Nf3", "Nc6"])
        self.assertTrue(self.window.analysis_mode)
        self.window.menu_actions["copy_pgn"].trigger()
        restored = Game.from_pgn(QApplication.clipboard().text())
        self.assertEqual(restored.board.fen(), self.window.game.board.fen())
        self.assertEqual(restored.sans, self.window.game.sans)

    def test_pgn_typing_does_not_trigger_play_or_flip_shortcuts(self):
        self.window._show_pgn()
        editor = self.window.pgn_editor
        editor.selectAll()
        flipped, paused = self.window.board_view.flipped, self.window.paused
        QTest.keyClicks(editor, '1. e4 e5 2. Nf3 Nc6 *')
        self.assertEqual(editor.toPlainText(), '1. e4 e5 2. Nf3 Nc6 *')
        QTest.keyClick(editor, Qt.Key.Key_Home)
        QTest.keyClicks(editor, 'F')
        self.assertEqual(editor.toPlainText(), 'F1. e4 e5 2. Nf3 Nc6 *')
        self.assertEqual((self.window.board_view.flipped, self.window.paused), (flipped, paused))
        self.window._refresh()
        self.assertEqual(editor.toPlainText(), 'F1. e4 e5 2. Nf3 Nc6 *')

    def test_bad_pgn_preserves_current_game_and_editor(self):
        game = self.window.game
        self.window.pgn_editor.setPlainText("1. e4 e5 2. Ke3")
        self.window.pgn_editor.document().setModified(True)
        with patch.object(self.window, "_error") as error:
            self.window._apply_pgn()
        error.assert_called_once()
        self.assertIs(self.window.game, game)
        self.assertEqual(game.sans, [])
        self.assertEqual(self.window.pgn_editor.toPlainText(), "1. e4 e5 2. Ke3")

    def test_compact_pgn_controls_remain_readable(self):
        self.window.resize(1024, 660)
        self.window._show_pgn()
        self.app.processEvents()
        self.assertEqual(self.window.height(), 660)
        self.assertGreaterEqual(self.window.pgn_editor.height(), 100)
        for control in (self.window.apply_pgn_button, self.window.load_pgn_button):
            self.assertGreaterEqual(control.height(), 30)
            self.assertTrue(self.window.tabs.rect().contains(control.mapTo(self.window.tabs, control.rect().bottomRight())))

    def test_open_pgn_file_and_reload_editor(self):
        path = Path(self.tmp.name) / "game.pgn"
        path.write_text("\ufeff1. d4 Nf6 2. c4 e6 *", encoding="utf-8")
        with patch("nocturne.gui.window.QFileDialog.getOpenFileName", return_value=(str(path), "")), \
                patch.object(self.window, "_schedule_engine"):
            self.window.menu_actions["Open PGN…"].trigger()
        self.assertEqual(self.window.game.sans, ["d4", "Nf6", "c4", "e6"])
        self.window.pgn_editor.setPlainText("temporary draft")
        self.window._load_current_pgn()
        self.assertEqual(self.window.pgn_editor.toPlainText(), self.window.game.pgn())
        self.assertFalse(self.window.pgn_editor.document().isModified())

    def test_clipboard_load_pgn_fen_and_empty_clipboard(self):
        with patch.object(self.window, "_schedule_engine"):
            QApplication.clipboard().setText("1.d4 d5 2.c4 *")
            self.window.menu_actions["load_clipboard"].trigger()
            self.assertEqual(self.window.game.sans, ["d4", "d5", "c4"])
            fen = self.window.game.board.fen()
            QApplication.clipboard().setText(fen)
            self.window._load_clipboard()
            self.assertEqual(self.window.game.board.fen(), fen)
        game = self.window.game
        QApplication.clipboard().clear()
        with patch.object(self.window, "_error") as error:
            self.window._load_clipboard()
        error.assert_called_once()
        self.assertIs(self.window.game, game)

    def test_drag_move(self):
        board = self.window.board_view
        src = board.square_rect(parse_square("d2")).center()
        dst = board.square_rect(parse_square("d4")).center()
        QTest.mousePress(board, Qt.MouseButton.LeftButton, pos=src.toPoint())
        event = QMouseEvent(QEvent.Type.MouseMove, dst,
                            QPointF(board.mapToGlobal(dst.toPoint())), Qt.MouseButton.NoButton,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.app.sendEvent(board, event)
        QTest.mouseRelease(board, Qt.MouseButton.LeftButton, pos=dst.toPoint())
        self.assertEqual(self.window.game.sans, ["d4"])

    def test_flip_geometry_and_right_click_annotations(self):
        board = self.window.board_view
        for flipped in (False, True):
            board.flipped = flipped
            for name in ("a1", "h1", "e4", "a8", "h8"):
                square = parse_square(name)
                self.assertEqual(board.square_at(board.square_rect(square).center()), square)
        e4 = parse_square("e4")
        QTest.mouseClick(board, Qt.MouseButton.RightButton, pos=board.square_rect(e4).center().toPoint())
        self.assertIn(e4, board.marks)

    def test_explicit_underpromotion_choice(self):
        self.window.game = Game("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
        self.window._refresh()
        def choose_knight():
            menu = QApplication.activePopupWidget()
            if isinstance(menu, QMenu):
                target = menu.actionGeometry(menu.actions()[-1]).center()
                QTest.mouseClick(menu, Qt.MouseButton.LeftButton, pos=target)

        def dismiss_if_stuck():
            menu = QApplication.activePopupWidget()
            if menu:
                menu.close()

        self._click("a7")
        QTimer.singleShot(20, choose_knight)
        QTimer.singleShot(1500, dismiss_if_stuck)
        self._click("a8")
        self.assertEqual(self.window.game.board.cells[parse_square("a8")], 2)
        self.assertEqual(self.window.game.sans, ["a8=N"])

    def test_stale_position_result_cannot_commit_a_move(self):
        generation = self.window.engine.generation
        self.window._job = {"generation": generation, "kind": "play",
                            "identity": self.window._position_identity(), "turn": 1, "external": False}
        self.window.game.play(self.window.game.board.parse_uci("e2e4"))
        self.window._engine_message(generation, "result", {"move": "d2d4", "info": {}})
        self.assertEqual(self.window.game.cursor, 1)
        self.assertIsNone(self.window._job)

    def test_human_ai_search_is_responsive_and_synchronized(self):
        self.window.config.update({"mode": "human_ai", "human_color": 1, "difficulty": "Casual"})
        ticks = []
        pulse = QTimer()
        pulse.setInterval(10)
        pulse.timeout.connect(lambda: ticks.append(time.monotonic()))
        pulse.start()
        try:
            self._click("e2")
            self._click("e4")
            deadline = time.monotonic() + 4
            while self.window.game.cursor < 2 and time.monotonic() < deadline:
                QTest.qWait(20)
            self.assertEqual(self.window.game.cursor, 2)
            self.assertGreater(len(ticks), 3)
            self.assertEqual(self.window.game.board.key, self.window.game.board.compute_key())
            self.assertIs(self.window.board_view.board, self.window.game.board)
            self.assertIsNotNone(self.window._last_info)
        finally:
            pulse.stop()

    def test_save_and_reopen_resumes_paused(self):
        self._click("e2")
        self._click("e4")
        self.window.close()
        self.window = MainWindow(Path(self.tmp.name))
        self.window.timer.stop()
        self.window.autosave_timer.stop()
        self.assertEqual(self.window.game.sans, ["e4"])
        self.assertTrue(self.window.paused)
        self.assertFalse(self.window.game.running)

    def test_human_can_choose_black_and_engine_opens(self):
        self.window.config.update({"mode": "human_ai", "human_color": -1, "difficulty": "Casual"})
        self.window._create_game()
        deadline = time.monotonic() + 4
        while self.window.game.cursor < 1 and time.monotonic() < deadline:
            QTest.qWait(20)
        self.assertEqual(self.window.game.cursor, 1)
        self.assertEqual(self.window.game.board.turn, -1)
        self.assertTrue(self.window.board_view.flipped)
        self.assertTrue(self.window.board_view.interactive)

    def test_ai_vs_ai_progresses_and_pause_cancels_search(self):
        self.window.config.update({"mode": "ai_ai", "difficulty": "Beginner", "watch_delay_ms": 0})
        self.window._create_game()
        deadline = time.monotonic() + 5
        while self.window.game.cursor < 4 and time.monotonic() < deadline:
            QTest.qWait(20)
        self.window._pause()
        cursor = self.window.game.cursor
        self.assertGreaterEqual(cursor, 4)
        self.assertFalse(self.window.engine.busy)
        QTest.qWait(150)
        self.assertEqual(self.window.game.cursor, cursor)
        self.assertTrue(self.window.paused)

    def test_disabling_takebacks_blocks_history_mutation(self):
        self.window.config["takebacks"] = False
        self._click("e2")
        self._click("e4")
        self.window._undo()
        self.window._navigate(0)
        self.assertEqual(self.window.game.cursor, 1)
        self.assertFalse(self.window.undo_button.isEnabled())

    def test_analysis_navigation_saves_an_independent_copy(self):
        self._click("e2")
        self._click("e4")
        original_id = self.window.game.id
        self.window._navigate(0)
        self.assertNotEqual(self.window.game.id, original_id)
        original = self.window.store.load(original_id)
        self.assertEqual(original.sans, ["e4"])
        self.assertEqual(original.cursor, 1)
        self.assertEqual(self.window.game.cursor, 0)

    def test_compact_engine_controls_remain_accessible(self):
        self.window.resize(1024, 660)
        self.window.tabs.setCurrentIndex(1)
        self.app.processEvents()
        page = self.window.tabs.widget(1)
        for control in (self.window.analysis_source, self.window.analyze_button):
            self.assertGreaterEqual(control.height(), 30)
            self.assertTrue(page.rect().contains(control.geometry()))

    def test_delayed_search_cannot_restart_after_window_close(self):
        self.window.config["mode"] = "ai_ai"
        self.window.close()
        self.window._schedule_engine()
        self.assertFalse(self.window.engine.busy)

    def test_custom_player_names_are_respected_in_ai_mode(self):
        self.window.config.update({"mode": "human_ai", "human_color": 1, "white_name": "Ada"})
        self.window._create_game()
        self.assertEqual(self.window.game.headers["White"], "Ada")
        self.assertEqual(self.window.bottom_name.text(), "Ada")
