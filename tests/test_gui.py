"""Native Qt integration tests. Explicitly skipped if the binding is absent."""

import os
import sys
from copy import deepcopy
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from nocturne.core.board import parse_square
from nocturne.core.game import Game
from nocturne.core.notation import san

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QEvent, QPointF, QTimer, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMenu, QScrollArea, QWidget
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
        self.window.analysis_mode = False
        self.window._analysis_enabled = False
        fixture = str(Path(__file__).parent / "fixtures" / "uci_simulator.py")
        self.window.profiles = [
            {
                "id": "test",
                "path": sys.executable,
                "arguments": [fixture],
                "name": "Transport simulator",
                "values": {},
                "options": {},
            }
        ]
        self.window.config["engine_id"] = "test"
        self.window._apply_settings()
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
        QTest.mouseClick(
            board, Qt.MouseButton.LeftButton, pos=board.square_rect(parse_square(name)).center().toPoint()
        )
        self.app.processEvents()

    def test_analysis_alternative_preserves_original_and_hover_restores(self):
        window = self.window
        window.analysis_mode = True
        window.game = Game.from_pgn("1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 *")
        original = window.game.current_node
        window.game.navigate(4)
        window.game.play(window.game.board.parse_uci("b1c3"))
        alternative = window.game.current_node
        window._refresh()
        fen = window.game.board.fen()
        window._preview_history(original)
        self.assertEqual(window.game.board.fen(), fen)
        self.assertIsNotNone(window.board_view.preview_board)
        window._end_preview("history")
        self.assertIsNone(window.board_view.preview_board)
        window._navigate_node(original)
        self.assertEqual(window.game.sans[4:], ["Bc4", "Bc5"])
        window._navigate_node(alternative)
        self.assertEqual(window.game.sans[4:], ["Nc3"])
        self.assertIn("(", window.game.pgn())

    def test_backspace_deletes_current_branch_selects_sibling_and_saves(self):
        self._analysis_game("1.e4 e5 (1...Nf6 2.d4) 2.Nf3 (2.Bc4) *")
        window = self.window
        window._navigate(2)
        window._preview_history(len(window.game.nodes) - 1)
        action = window.menu_actions["Delete current line"]
        self.assertEqual(action.shortcut().toString(), "Backspace")
        self.assertFalse(action.autoRepeat())
        window.board_view.setFocus()
        QTest.keyClick(window.board_view, Qt.Key.Key_Backspace)
        self.app.processEvents()
        self.assertEqual(window.game.cursor, 2)
        self.assertEqual(window.game.sans[:2], ["e4", "Nf6"])
        self.assertIsNone(window.board_view.preview_board)
        self.assertEqual(window.board_view.board.fen(), window.game.board.fen())
        self.assertEqual(window.store.load(window.game.id).pgn(), window.game.pgn())
        self.assertNotIn("e5", window.game.pgn())
        self.assertNotIn("e5", window.analysis_history.toPlainText())
        window.analysis_history.setFocus()
        QTest.keyClick(window.analysis_history, Qt.Key.Key_Backspace)
        self.app.processEvents()
        self.assertEqual(window.game.sans, ["e4"])
        QTest.keyClick(window.analysis_history, Qt.Key.Key_Backspace)
        self.app.processEvents()
        self.assertEqual(window.game.cursor, 0)
        self.assertFalse(action.isEnabled())

    def test_backspace_in_pgn_and_text_fields_does_not_delete_branch(self):
        from PySide6.QtWidgets import QLineEdit

        self._analysis_game()
        window = self.window
        original = window.game.pgn()
        window.tabs.setCurrentIndex(window.tabs.indexOf(window.pgn_editor.parentWidget()))
        window.pgn_editor.setFocus()
        window.pgn_editor.setPlainText("abc")
        window.pgn_editor.moveCursor(window.pgn_editor.textCursor().MoveOperation.End)
        QTest.keyClick(window.pgn_editor, Qt.Key.Key_Backspace)
        self.assertEqual(window.pgn_editor.toPlainText(), "ab")
        edit = QLineEdit(window)
        edit.setText("abc")
        edit.show()
        edit.setFocus()
        QTest.keyClick(edit, Qt.Key.Key_Backspace)
        self.assertEqual(edit.text(), "ab")
        self.assertEqual(window.game.pgn(), original)
        window.analysis_mode = False
        window._refresh()
        self.assertFalse(window.delete_line_action.isEnabled())

    def test_review_navigation_preserves_selected_variation_and_halted_state(self):
        self._analysis_game("1.e4 e5 (1...c5 2.Nf3) 2.Bc4 *")
        window = self.window
        parent = next(i for i, n in enumerate(window.game.nodes) if n.san == "c5")
        window.game.select_node(window.game.nodes[parent].children[0])
        selected = window.game._line_nodes.copy()
        window._show_review()
        window._review_navigate(parent)
        self.assertEqual(window.game._line_nodes, selected)
        self.assertEqual(window.game.cursor, 2)
        window._review_navigate(0)
        self.assertEqual(window.game._line_nodes, selected)
        self.assertFalse(window._analysis_enabled)

    def test_display_clocks_analysis_values_toggle_and_reopen(self):
        from nocturne.core.game import TimeControl

        self._analysis_game()
        window = self.window
        self.assertTrue(window.analysis_clocks.isVisible())
        self.assertEqual(window.analysis_clock_values[1].text(), "∞")
        self.assertEqual(window.analysis_clock_values[-1].text(), "∞")
        window.game = Game(time_control=TimeControl(300, 2))
        window.game.metadata["mode"] = "analysis"
        window.game._remaining = {1: 280, -1: 290}
        window._refresh()
        self.assertEqual(window.analysis_clock_values[1].text(), "04:40")
        self.assertEqual(window.analysis_clock_values[-1].text(), "04:50")
        fen, generation = window.game.board.fen(), window.engine.generation
        action = window.display_actions["show_clocks"]
        action.trigger()
        self.assertFalse(window.analysis_clocks.isVisible())
        self.assertFalse(window.store.get("settings")["show_clocks"])
        self.assertEqual(window.game.board.fen(), fen)
        self.assertEqual(window.engine.generation, generation)
        self.assertFalse(window.game.running)
        action.trigger()
        self.assertTrue(window.analysis_clocks.isVisible())
        action.trigger()
        window.close()
        window.deleteLater()
        self.app.processEvents()
        self.window = MainWindow(Path(self.tmp.name))
        self.window.timer.stop()
        self.window.autosave_timer.stop()
        self.window._analysis_enabled = False
        self.window.show()
        self.app.processEvents()
        self.assertFalse(self.window.display_actions["show_clocks"].isChecked())
        self.assertFalse(self.window.analysis_clocks.isVisible())
        self.assertEqual(self.window.game.time_control, TimeControl(300, 2))
        self.assertEqual(self.window.game.clock_values(), {1: 280, -1: 290})

    def test_studio_appearance_preview_cancel_and_save(self):
        from nocturne.gui.dialogs import SettingsDialog

        window = self.window
        original = deepcopy(window.config)
        state = (window.game.board.fen(), window.engine.generation, window.game.clock_values())
        saved = deepcopy(window.store.get("settings"))

        def cancel(dialog):
            dialog.theme.setCurrentText("Grey")
            dialog.pieces.setCurrentText("Original")
            dialog.checks["light"].setChecked(True)
            dialog.checks["coordinates"].setChecked(False)
            dialog.checks["overlays"].setChecked(False)
            self.assertEqual(window.board_view.theme, "Grey")
            self.assertEqual(dialog.preview.theme, "Grey")
            self.assertEqual(window.board_view.piece_set, "Original")
            self.assertTrue(all(r.isValid() for r in window.board_view._renderers.values()))
            self.assertTrue(window.board_view.light)
            self.assertFalse(window.board_view.coordinates)
            self.assertFalse(window.board_view.overlays)
            self.assertEqual(window.config, original)
            self.assertEqual(window.store.get("settings"), saved)
            self.assertEqual((window.game.board.fen(), window.engine.generation, window.game.clock_values()), state)
            return dialog.DialogCode.Rejected

        with patch.object(SettingsDialog, "exec", new=cancel):
            window._settings()
        self.assertEqual(window.config, original)
        self.assertEqual(window.board_view.theme, original["theme"])
        self.assertEqual(window.board_view.piece_set, original["piece_set"])
        self.assertEqual(window.board_view.light, original["light"])
        self.assertEqual(window.board_view.overlays, original["overlays"])

        def save(dialog):
            dialog.theme.setCurrentText("Grey")
            dialog.pieces.setCurrentText("Original")
            return dialog.DialogCode.Accepted

        with patch.object(SettingsDialog, "exec", new=save):
            window._settings()
        self.assertEqual(window.store.get("settings")["piece_set"], "Original")
        self.assertEqual(window.store.get("settings")["theme"], "Grey")
        self.assertEqual(window.game.board.fen(), state[0])

    def test_imported_pgn_clocks_follow_selected_position_and_display_toggle(self):
        text = (
            '1. e4 {[%clk 0:04:59.3][%timestamp 7]} '
            'e5 {[%clk 0:04:58.9]} (1... c5 {[%clk 0:04:59.1]}) '
            '2. Nf3 {[%clk 0:04:58.4]} *'
        )
        self.assertTrue(self.window._import_text(text))
        self.assertEqual(self.window.analysis_clock_values[1].text(), "0:04:58.4")
        self.assertEqual(self.window.analysis_clock_values[-1].text(), "0:04:58.9")
        visible_moves = self.window.analysis_history.toPlainText()
        self.assertIn("[0:04:59.3]", visible_moves)
        self.assertIn("[0:04:58.9]", visible_moves)
        self.assertNotIn("[%clk", visible_moves)
        self.assertNotIn("[%timestamp", visible_moves)

        self.window.game.select_node(0)
        self.window._refresh()
        self.assertEqual(self.window.analysis_clock_values[1].text(), "—")
        self.assertEqual(self.window.analysis_clock_values[-1].text(), "—")
        self.window.game.select_node(next(i for i, node in enumerate(self.window.game.nodes) if node.san == "Nf3"))
        self.window._refresh()

        c5 = next(i for i, node in enumerate(self.window.game.nodes) if node.san == "c5")
        self.window.game.select_node(c5)
        self.window._refresh()
        self.assertEqual(self.window.analysis_clock_values[1].text(), "0:04:59.3")
        self.assertEqual(self.window.analysis_clock_values[-1].text(), "0:04:59.1")

        self.window.display_actions["show_clocks"].trigger()
        self.assertFalse(self.window.analysis_clocks.isVisible())
        self.assertNotIn("[0:04:59.1]", self.window.analysis_history.toPlainText())
        self.window.display_actions["show_clocks"].trigger()
        self.assertEqual(self.window.analysis_clock_values[-1].text(), "0:04:59.1")

    def test_hiding_play_clocks_keeps_elapsed_time_and_saved_game(self):
        from nocturne.core.game import TimeControl

        window = self.window
        window.game = Game(time_control=TimeControl(60, 2))
        action = window.display_actions["show_clocks"]
        fen, generation = window.game.board.fen(), window.engine.generation
        with patch("nocturne.core.game.time.monotonic", return_value=100.0) as clock:
            window.game.start_clock()
            window._refresh()
            self.assertFalse(window.analysis_clocks.isVisible())
            self.assertTrue(window.bottom_clock.isVisible())
            clock.return_value = 106.0
            action.trigger()
            self.assertTrue(window.game.running)
            self.assertEqual(window.game._anchor, 100.0)
            self.assertEqual(window.game.clock_values(), {1: 54, -1: 60})
            self.assertTrue(window.top_card.isVisible())
            self.assertTrue(window.bottom_card.isVisible())
            self.assertFalse(window.top_clock.isVisible())
            self.assertFalse(window.bottom_clock.isVisible())
            clock.return_value = 110.0
            action.trigger()
            self.assertEqual(window.bottom_clock.text(), "00:50")
            self.assertEqual(window.top_clock.text(), "01:00")
            self.assertEqual(window.bottom_clock.objectName(), "activeClock")
            self.assertEqual(window.game._remaining, {1: 60, -1: 60})
            self.assertEqual(window.game.board.fen(), fen)
            self.assertEqual(window.engine.generation, generation)
            saved = window.store.load(window.game.id)
            self.assertEqual(saved.time_control, TimeControl(60, 2))
            self.assertEqual(saved.clock_values(), {1: 50, -1: 60})
            window.game.pause_clock()

    def _three_pvs(self):
        self._analysis_game("1.e4 e5 *")
        self.window.config["multipv"] = 3
        job = {"turn": 1, "multipv": 3}
        base = {"depth": 6, "seldepth": 10, "score": 15, "nodes": 500}
        # Rank three arrives first; empty ranks still reserve their places.
        self._show_external_info(base | {"multipv": 3, "pv": ["b1c3", "g8f6", "g1f3"]}, job)
        self._show_external_info(base | {"multipv": 1, "pv": ["g1f3"]}, job)
        self._show_external_info(base | {"multipv": 2, "pv": ["f1c4", "g8f6"]}, job)
        self.app.processEvents()
        return base, job

    def test_five_colored_candidates_keep_slots_and_destination_execution(self):
        self._analysis_game("1.e4 e5 *")
        self.window.config["multipv"] = 5
        job = {"turn": 1, "multipv": 5}
        for rank, move in enumerate(["g1f3", "b1c3", "f1c4", "d2d3", "d2d4"], 1):
            self._show_external_info({"depth": 7, "seldepth": 9, "score": 35 - rank * 5,
                                      "nodes": 2000, "multipv": rank, "pv": [move]}, job)
        self.app.processEvents()
        panel = self.window.candidates
        self.assertEqual([panel.badges[r].text() for r in range(1, 6)], ["1", "2", "3", "4", "5"])
        self.assertEqual(len({panel.rows[r][2].height() for r in range(1, 6)}), 1)
        self.assertNotEqual(panel.badges[1].styleSheet(), panel.badges[2].styleSheet())
        self.assertEqual(self.window.board_view.candidate_style, "lines")
        QTest.mouseClick(self.window.board_view, Qt.MouseButton.LeftButton,
                         pos=self.window.board_view.square_rect(parse_square("d4")).center().toPoint())
        self.assertEqual(self.window.game.sans[-1], "d4")

    def test_three_line_pv_slots_preserve_hover_and_apply_latest_update_after_leaving(self):
        base, job = self._three_pvs()
        panel = self.window.candidates
        self.assertEqual(list(panel.rows), [1, 2, 3])
        heights = [widgets[2].height() for widgets in panel.rows.values()]
        self.assertEqual(len(set(heights)), 1)
        third = panel.rows[3][2]
        self._hover_word(third, "Nc3")
        preview = self.window.board_view.display_board.fen()
        position = panel.rows[3][0].mapToGlobal(panel.rows[3][0].rect().topLeft())
        for pv in (["g1f3", "g8f6", "f3g1", "f6g8"] * 8, ["g1f3"]):
            self._show_external_info(base | {"multipv": 1, "pv": pv}, job)
            self._show_external_info(base | {"multipv": 2, "pv": ["f1b5"]}, job)
            self.app.processEvents()
            self.assertEqual(panel.rows[3][0].mapToGlobal(panel.rows[3][0].rect().topLeft()), position)
            self.assertEqual(self.window.board_view.display_board.fen(), preview)
            self.assertEqual(panel.hovered, 3)
        self._show_external_info(base | {"multipv": 3, "pv": ["d2d4", "e5d4"]}, job)
        self.assertEqual(panel.lines[3]["pv"][0], "b1c3")
        self.assertEqual(third._items[0][0], "Nc3")
        QTest.mouseMove(third.viewport(), pos=third.viewport().rect().bottomRight() - QPointF(4, 4).toPoint())
        QTest.qWait(20)
        self.assertEqual(panel.lines[3]["pv"][0], "d2d4")
        self.assertIsNone(self.window.board_view.preview_board)
        self.assertIn("d2d4", [m.uci() for m, rank, _ in self.window.board_view.recommendations if rank == 3])
        self._hover_word(third, "d4")
        self._show_external_info(base | {"multipv": 3, "pv": ["b1c3"]}, job)
        self.window._clear_analysis_output()
        QTest.qWait(20)
        self.assertFalse(panel.lines)
        self.assertFalse(panel.pending)
        self.assertIsNone(self.window.board_view.preview_board)

    def test_clicking_hovered_candidate_uses_displayed_snapshot_not_queued_replacement(self):
        base, job = self._three_pvs()
        panel = self.window.candidates
        third = panel.rows[3][2]
        self._hover_word(third, "Nc3")
        self._show_external_info(base | {"multipv": 3, "pv": ["d2d4"]}, job)
        cursor = third.document().find("Nc3")
        cursor.setPosition(cursor.selectionStart() + 1)
        QTest.mouseClick(third.viewport(), Qt.MouseButton.LeftButton, pos=third.cursorRect(cursor).center())
        self.app.processEvents()
        self.assertEqual(self.window.game.sans, ["e4", "e5", "Nc3"])
        self.assertFalse(panel.pending)

    def test_click_move_updates_model_board_and_san_history(self):
        self._click("e2")
        self.assertEqual(self.window.board_view.selected, parse_square("e2"))
        self._click("e4")
        self.assertEqual(self.window.game.cursor, 1)
        self.assertEqual(self.window.game.sans, ["e4"])
        self.assertEqual(self.window.history.item(0, 1).text(), "e4")
        self.assertEqual(self.window.game.board.cells[parse_square("e4")], 1)
        self.assertIs(self.window.board_view.board, self.window.game.board)

    def test_prior_pgns_are_retained_and_folder_is_accessible(self):
        window = self.window
        window._import_text("1.e4 {prior study} (1.d4 d5) e5 *")
        first_id = window.game.id
        window._import_text("1.Nf3 d5 *")
        second_id = window.game.id
        window._new_study()
        first = window.store.pgn_path(first_id)
        second = window.store.pgn_path(second_id)
        self.assertIn("prior study", first.read_text(encoding="utf-8"))
        self.assertIn("(", first.read_text(encoding="utf-8"))
        self.assertEqual(Game.from_pgn(second.read_text()).sans, ["Nf3", "d5"])
        with patch("nocturne.gui.window.QDesktopServices.openUrl", return_value=True) as opened:
            window.menu_actions["Open saved PGN folder"].trigger()
            self.assertEqual(Path(opened.call_args.args[0].toLocalFile()), window.store.pgn_directory)

    def test_older_library_pgns_backfill_without_changing_resume_or_removing_corrupt_games(self):
        window = self.window
        window._save()
        resume = window.store.get("resume_id")
        old = Game.from_pgn("1.e4 c5 *")
        broken = Game.from_pgn("1.d4 *")
        window.store.save(old, autosave=False)
        window.store.save(broken, autosave=False)
        window.store.pgn_path(old.id).unlink()
        window.store.pgn_path(broken.id).unlink()
        with window.store.db:
            window.store.db.execute("UPDATE games SET payload='broken' WHERE id=?", (broken.id,))
        window._start_pgn_archive_migration()
        deadline = time.monotonic() + 3
        while window.archive_timer.isActive() and time.monotonic() < deadline:
            QTest.qWait(20)
        self.assertFalse(window.archive_timer.isActive())
        self.assertEqual(Game.from_pgn(window.store.pgn_path(old.id).read_text()).sans, ["e4", "c5"])
        self.assertEqual(window.store.get("resume_id"), resume)
        self.assertIn(broken.id, window.store.game_ids())

    def test_nibbler_style_menus_and_no_widget_tooltips(self):
        self.assertEqual(
            [a.text().replace("&", "") for a in self.window.menuBar().actions()],
            ["File", "Tree", "Analysis", "Display", "Engine", "Database", "Play"],
        )
        self.assertTrue(all("custom engine" not in w.toolTip() for w in self.window.findChildren(QWidget)))
        action = self.window.display_actions["coordinates"]
        action.trigger()
        self.assertFalse(self.window.board_view.coordinates)
        action.trigger()
        self.assertTrue(self.window.board_view.coordinates)

    def test_file_menu_opens_by_mouse_and_exposes_clipboard_commands(self):
        bar = self.window.menuBar()
        QTest.mouseClick(
            bar,
            Qt.MouseButton.LeftButton,
            pos=bar.actionGeometry(self.window.menus["File"].menuAction()).center(),
        )
        self.app.processEvents()
        menu = self.window.menus["File"]
        self.assertTrue(menu.isVisible())
        self.assertIn(self.window.menu_actions["load_clipboard"], menu.actions())
        self.assertIn(self.window.menu_actions["copy_pgn"], menu.actions())
        menu.close()

    def _analysis_game(self, text="1. e4 e5 2. Nf3 Nc6 *"):
        self.window._stop_engine()
        self.window.game = Game.from_pgn(text)
        self.window.game.metadata["mode"] = "analysis"
        self.window.config["layout"] = "analysis-left"
        self.window.analysis_mode = True
        self.window._analysis_enabled = False
        self.window._refresh()
        self.app.processEvents()

    def _show_external_info(self, info, job):
        position = self.window.game.board.copy()
        pv = []
        texts = []
        for text in info["pv"]:
            try:
                move = position.parse_uci(text)
                texts.append(san(position, move))
                pv.append(text)
                position.push(move)
            except ValueError:
                break
        data = {
            **info,
            "score_type": "cp",
            "score_value": info["score"],
            "bound": "exact",
            "multipv": info.get("multipv", 1),
            "pv": pv,
            "san": texts,
        }
        self.window._show_info(data, job)

    def _hover_word(self, view, word):
        QTest.qWait(30)
        self.app.processEvents()
        parent = view.parentWidget()
        while parent:
            if isinstance(parent, QScrollArea):
                parent.ensureWidgetVisible(view)
            parent = parent.parentWidget()
        self.app.processEvents()
        QTest.qWait(15)
        cursor = view.document().find(word)
        self.assertFalse(cursor.isNull(), word)
        cursor.setPosition(cursor.selectionStart() + 1)
        QTest.mouseMove(view.viewport(), pos=view.viewport().rect().bottomRight() - QPointF(4, 4).toPoint())
        QTest.mouseMove(view.viewport(), pos=view.cursorRect(cursor).center())
        self.app.processEvents()

    def test_analysis_layout_is_left_with_history_below_and_play_restores(self):
        self.window.config["layout"] = "analysis-left"
        self._analysis_game()
        self.window.resize(1024, 660)
        self.app.processEvents()
        self.assertIs(self.window.main_splitter.widget(0), self.window.panel)
        self.assertIs(self.window.main_splitter.widget(1), self.window.arena)
        self.assertTrue(self.window.analysis_moves_panel.isVisible())
        self.assertFalse(self.window.tabs.isTabVisible(0))
        self.assertEqual(self.window.height(), 660)
        self.assertGreater(self.window.analysis_moves_panel.y(), self.window.main_splitter.y())
        self.window._workspace(False)
        self.assertIs(self.window.main_splitter.widget(0), self.window.arena)
        self.assertFalse(self.window.analysis_moves_panel.isVisible())
        self.assertTrue(self.window.tabs.isTabVisible(0))
        self.assertTrue(self.window.sidebar.isVisible())

    def test_history_mouse_hover_is_display_only_and_blank_space_restores(self):
        self._analysis_game()
        game = self.window.game
        before, key, generation = deepcopy(game.to_dict()), game.board.key, self.window.engine.generation
        self._hover_word(self.window.analysis_history, "e4")
        expected = Game.from_pgn("1.e4 *").board.fen()
        self.assertIs(self.window.board_view.board, game.board)
        self.assertEqual(self.window.board_view.display_board.fen(), expected)
        self.assertEqual(game.to_dict(), before)
        self.assertEqual((game.board.key, self.window.engine.generation), (key, generation))
        view = self.window.analysis_history
        QTest.mouseMove(view.viewport(), pos=view.viewport().rect().bottomRight() - QPointF(4, 4).toPoint())
        self.app.processEvents()
        self.assertIsNone(self.window.board_view.preview_board)
        self.assertIs(self.window.board_view.display_board, game.board)

    def test_pv_mouse_hover_previews_prefix_and_exit_restores(self):
        self._analysis_game("1.e4 e5 *")
        info = {"depth": 3, "seldepth": 4, "score": 15, "nodes": 100, "pv": ["g1f3", "b8c6", "f1b5", "a1a8"]}
        self._show_external_info(info, {"turn": 1})
        self.assertEqual(len(self.window._pv_moves), 3)
        before = deepcopy(self.window.game.to_dict())
        generation = self.window.engine.generation
        self._hover_word(self.window.pv_label, "Nc6")
        self.assertEqual(
            self.window.board_view.display_board.fen(), Game.from_pgn("1.e4 e5 2.Nf3 Nc6 *").board.fen()
        )
        self.assertEqual(self.window.game.to_dict(), before)
        self.assertEqual(self.window.engine.generation, generation)
        self.app.sendEvent(self.window.pv_label.viewport(), QEvent(QEvent.Type.Leave))
        self.assertIsNone(self.window.board_view.preview_board)
        self.assertEqual(self.window.game.to_dict(), before)

    def test_position_change_or_new_pv_cannot_restore_stale_preview(self):
        self._analysis_game("1.e4 e5 *")
        self.window._preview_history(1)
        self.window.game.play(self.window.game.board.parse_uci("g1f3"))
        self.window._refresh()
        actual = self.window.game.board.fen()
        self.window.analysis_history.cancel_preview()
        self.assertEqual(self.window.board_view.display_board.fen(), actual)
        info = {"depth": 2, "seldepth": 3, "score": 0, "nodes": 50, "pv": ["b8c6", "f1b5"]}
        self._show_external_info(info, {"turn": -1})
        self.window._preview_pv(2)
        self.assertIsNotNone(self.window.board_view.preview_board)
        self._show_external_info(info | {"pv": ["g8f6"]}, {"turn": -1})
        self.assertIsNone(self.window.board_view.preview_board)
        self.assertEqual(self.window.board_view.display_board.fen(), actual)

    def test_hover_special_moves_uses_copies_and_preserves_hash_and_cursor(self):
        cases = [
            ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1g1"),
            ("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1", "e5d6"),
            ("4k3/P7/8/8/8/8/8/4K3 w - - 0 1", "a7a8n"),
        ]
        self._analysis_game()
        for fen, uci in cases:
            with self.subTest(uci=uci):
                game = Game(fen)
                game.metadata["mode"] = "analysis"
                game.play(game.board.parse_uci(uci))
                expected = game.board.fen()
                game.navigate(0)
                self.window.game = game
                self.window._refresh()
                before, key = deepcopy(game.to_dict()), game.board.key
                self.window._preview_history(1)
                self.assertEqual(self.window.board_view.display_board.fen(), expected)
                self.assertEqual(game.to_dict(), before)
                self.assertEqual(game.board.key, key)
                self.window._end_preview("history")
                self.assertEqual(self.window.board_view.display_board.fen(), fen)

    def test_preview_blocks_board_input_and_clicking_history_navigates(self):
        self._analysis_game()
        self.window._preview_history(1)
        cursor = self.window.game.cursor
        self._click("d2")
        self._click("d4")
        self.assertEqual(self.window.game.cursor, cursor)
        self.window.analysis_history.cancel_preview()
        self._hover_word(self.window.analysis_history, "Nf3")
        view = self.window.analysis_history
        text_cursor = view.document().find("Nf3")
        text_cursor.setPosition(text_cursor.selectionStart() + 1)
        with patch.object(self.window, "_schedule_engine"):
            QTest.mouseClick(
                view.viewport(), Qt.MouseButton.LeftButton, pos=view.cursorRect(text_cursor).center()
            )
        self.assertEqual(self.window.game.cursor, 3)
        self.assertIsNone(self.window.board_view.preview_board)

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
        QTest.keyClicks(editor, "1. e4 e5 2. Nf3 Nc6 *")
        self.assertEqual(editor.toPlainText(), "1. e4 e5 2. Nf3 Nc6 *")
        QTest.keyClick(editor, Qt.Key.Key_Home)
        QTest.keyClicks(editor, "F")
        self.assertEqual(editor.toPlainText(), "F1. e4 e5 2. Nf3 Nc6 *")
        self.assertEqual((self.window.board_view.flipped, self.window.paused), (flipped, paused))
        self.window._refresh()
        self.assertEqual(editor.toPlainText(), "F1. e4 e5 2. Nf3 Nc6 *")

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
            self.assertTrue(
                self.window.tabs.rect().contains(
                    control.mapTo(self.window.tabs, control.rect().bottomRight())
                )
            )

    def test_open_pgn_file_and_reload_editor(self):
        path = Path(self.tmp.name) / "game.pgn"
        path.write_text("\ufeff1. d4 Nf6 2. c4 e6 *", encoding="utf-8")
        with (
            patch("nocturne.gui.window.QFileDialog.getOpenFileName", return_value=(str(path), "")),
            patch.object(self.window, "_schedule_engine"),
        ):
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
        event = QMouseEvent(
            QEvent.Type.MouseMove,
            dst,
            QPointF(board.mapToGlobal(dst.toPoint())),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
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
        self.window._job = {
            "generation": generation,
            "kind": "play",
            "identity": self.window._position_identity(),
            "turn": 1,
            "external": False,
        }
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

    def test_pv_updates_preserve_hover_and_do_not_accumulate_click_handlers(self):
        self._analysis_game("1.e4 e5 *")
        info = {"depth": 3, "seldepth": 4, "score": 15, "nodes": 100, "pv": ["g1f3", "b8c6", "f1b5"]}
        self._show_external_info(info, {"turn": 1})
        self._hover_word(self.window.pv_label, "Nc6")
        before = self.window.game.board.fen()
        self.assertIsNotNone(self.window.board_view.preview_board)
        self._show_external_info(dict(info, depth=4, nodes=200), {"turn": 1})
        self.assertIsNotNone(self.window.board_view.preview_board)
        self.assertEqual(self.window.game.board.fen(), before)
        self.window._end_preview("pv")
        for _ in range(3):
            self.window._clear_analysis_output()
            self._show_external_info(info, {"turn": 1})
            self.app.processEvents()
        clicks = []
        self.window.candidates.navigate.connect(lambda rank, ply: clicks.append((rank, ply)))
        self.window.pv_label.move_clicked.emit(1)
        self.assertEqual(clicks, [(1, 1)])

    def test_long_pvs_have_three_reserved_lines_scroll_and_copy_from_context_menu(self):
        from PySide6.QtGui import QTextDocument
        self._analysis_game("1.e4 e5 *")
        info = {"depth": 6, "seldepth": 10, "score": 15, "nodes": 500,
                "pv": ["g1f3", "g8f6", "f3g1", "f6g8"] * 10}
        self._show_external_info(info, {"turn": 1})
        self.app.processEvents()
        view = self.window.pv_label
        self.assertEqual(len(view._items), 40)
        last = view.document().find("Ng8", view.document().characterCount() - 1, QTextDocument.FindFlag.FindBackward)
        self.assertGreater(view.verticalScrollBar().maximum(), 0)
        view.setTextCursor(last)
        view.ensureCursorVisible()
        self.assertLessEqual(view.cursorRect(last).bottom(), view.viewport().height())
        from PySide6.QtWidgets import QPushButton
        self.assertFalse(self.window.candidates.rows[1][0].findChildren(QPushButton))

        def copy_line():
            menu = QApplication.activePopupWidget()
            if isinstance(menu, QMenu):
                action = next(a for a in menu.actions() if a.text() == "Copy SAN")
                QTest.mouseClick(menu, Qt.MouseButton.LeftButton, pos=menu.actionGeometry(action).center())

        guard = QTimer(self.window)
        guard.setSingleShot(True)
        guard.timeout.connect(lambda: QApplication.activePopupWidget().close() if QApplication.activePopupWidget() else None)
        guard.start(1000)
        QTimer.singleShot(20, copy_line)
        self.window.candidates._menu(1, self.window.mapToGlobal(self.window.rect().center()))
        guard.stop()
        self.assertTrue(QApplication.clipboard().text().startswith("Nf3 Nf6"))

    def test_analysis_uses_menu_controls_and_keeps_the_right_pane_for_pvs(self):
        self._analysis_game()
        self.window.config["layout"] = "classic"
        self.window._refresh()
        self.window.resize(1024, 660)
        self.app.processEvents()
        self.assertFalse(self.window.tabs.tabBar().isVisible())
        self.assertIs(self.window.main_splitter.widget(1), self.window.panel)
        self.assertGreater(self.window.panel.width(), self.window.arena.width(), self._split_diagnostics())
        self.assertTrue(self.window.quick_analysis_button.isVisible())
        self.assertGreater(self.window.engine_scroll.height(), 250)
        from PySide6.QtWidgets import QComboBox, QSpinBox, QToolButton
        for kind in (QComboBox, QSpinBox, QToolButton):
            self.assertFalse(self.window.tabs.widget(1).findChildren(kind))
        self.assertIn(self.window.resource_controls.menus["Threads"].menuAction(), self.window.menus["Engine"].actions())
        self.assertIn(self.window.multipv_menu.menuAction(), self.window.menus["Engine"].actions())

    def test_delayed_search_cannot_restart_after_window_close(self):
        self.window.config["mode"] = "ai_ai"
        self.window.close()
        self.window._schedule_engine()
        self.assertFalse(self.window.engine.busy)

    def test_analysis_split_settles_after_mode_changes_and_preserves_user_resize(self):
        self.window.board_hint.setText("Instructions " * 12)
        for size in ((1024, 660), (1920, 1040)):
            for layout in ("classic", "analysis-left"):
                self.window._workspace(False)
                self.app.processEvents()
                self._analysis_game()
                self.window.config["layout"] = layout
                self.window._refresh()
                self.window.resize(*size)
                self.app.processEvents()
                QTest.qWait(10)
                self.assertFalse(self.window.board_hint.isVisible())
                self.assertGreater(self.window.panel.width(), self.window.arena.width(), self._split_diagnostics())
                self.window.main_splitter.setSizes([500, 500])
                self.app.processEvents()
                chosen = self.window.main_splitter.sizes()
                self.window._refresh()
                self.app.processEvents()
                self.assertEqual(self.window.main_splitter.sizes(), chosen)

    def _split_diagnostics(self):
        widgets = {"arena": self.window.arena, "panel": self.window.panel,
                   "board": self.window.board_view, "top_card": self.window.top_card,
                   "bottom_card": self.window.bottom_card}
        widgets.update({f"arena_child_{i}": w for i, w in enumerate(self.window.arena.findChildren(QWidget))
                        if w.minimumSizeHint().width() > 400})
        return repr({name: {"width": w.width(), "min": w.minimumWidth(),
                            "min_hint": w.minimumSizeHint().width(), "hint": w.sizeHint().width(),
                            "max": w.maximumWidth(), "visible": w.isVisible()}
                     for name, w in widgets.items()})

    def test_custom_player_names_are_respected_in_ai_mode(self):
        self.window.config.update({"mode": "human_ai", "human_color": 1, "white_name": "Ada"})
        self.window._create_game()
        self.assertEqual(self.window.game.headers["White"], "Ada")
        self.assertEqual(self.window.bottom_name.text(), "Ada")
