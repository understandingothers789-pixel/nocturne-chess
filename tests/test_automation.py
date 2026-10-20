"""Focused engine defaults, live automation and manual interruption checks."""

import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from nocturne.core.game import Game
from nocturne.gui.window import MainWindow
from nocturne.gui.dialogs import SettingsDialog


class AutomationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])


    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.window = MainWindow(Path(self.directory.name))
        self.window.timer.stop()
        self.window.autosave_timer.stop()
        self.window.profiles = [{
            "id": "hold", "path": sys.executable,
            "arguments": [str(Path(__file__).parent / "fixtures" / "uci_simulator.py"), "hold"],
            "name": "Protocol fixture", "values": {}, "options": {"MultiPV": {"maximum": 8}},
        }]
        self.window.config.update(engine_id="hold", multipv=3)
        self.window.analysis_mode = True
        self.window._analysis_enabled = False


    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()


    def wait(self, predicate):
        end = time.monotonic() + 4
        while time.monotonic() < end:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(0.005)
        self.fail("Expected engine/UI update did not arrive")

    def test_limits_persist_independently_and_each_menu_resets_only_its_limit(self):
        window = self.window
        defaults = dict(analysis_nodes=1_000_000_000, auto_eval_nodes=200_000_000,
                        auto_play_nodes=10_000_000)
        for key, value in defaults.items():
            self.assertEqual(window.config[key], value)
        window._set_node_limit("analysis_nodes", 300_000_000)
        window._set_node_limit("auto_play_nodes", 50_000_000)
        reopened = MainWindow(Path(self.directory.name))
        try:
            self.assertEqual(reopened.config["analysis_nodes"], 300_000_000)
            self.assertEqual(reopened.config["auto_eval_nodes"], 200_000_000)
            self.assertEqual(reopened.config["auto_play_nodes"], 50_000_000)
        finally:
            reopened.close()
            reopened.deleteLater()
        menus = (("analysis_nodes", window.normal_limit_menu),
                 ("auto_eval_nodes", window.auto_eval_limit_menu),
                 ("auto_play_nodes", window.auto_play_limit_menu))
        for key, menu in menus:
            previous = {k: window.config[k] for k in defaults if k != key}
            next(a for a in menu.actions() if a.text().startswith("Reset to default")).trigger()
            self.assertEqual(window.config[key], defaults[key])
            self.assertEqual({k: window.config[k] for k in previous}, previous)
        self.assertFalse(hasattr(window, "move_tree"))
        self.assertFalse(hasattr(window, "engine_gear"))

    def test_default_limits_reach_the_engine_as_separate_node_commands(self):
        window = self.window
        window._analysis_enabled = True
        window._schedule_engine()
        self.wait(lambda: "> go nodes 1000000000" in window.engine.connection.log)
        window._halt_analysis()
        window._auto_evaluate_line()
        self.wait(lambda: "> go nodes 200000000" in window.engine.connection.log)
        window._escape()
        window._start_auto_play()
        self.wait(lambda: "> go nodes 10000000" in window.engine.connection.log)
        window._escape()


    def test_f12_streams_current_position_and_manual_navigation_cancels(self):
        window = self.window
        window.game = Game.from_pgn("1.e4 e5 2.Nf3 *")
        window.game.navigate(1)
        window._refresh()
        window._auto_evaluate_line()
        self.wait(lambda: len(window.candidates.lines) == 3)
        self.assertEqual(window.game.cursor, 1)
        self.assertNotEqual(window.eval_label.text(), "—")
        self.assertGreater(window._last_info["nodes"], 0)
        self.assertIn("analyz", window.engine_state.text())
        state = window._review
        window._auto_evaluate_line()
        self.assertTrue(state["paused"])
        self.assertFalse(window.engine.busy)
        window._auto_evaluate_line()
        self.wait(lambda: window.engine.busy and bool(window.engine.lines))
        self.assertIs(window._review, state)
        window._undo()
        self.assertIsNone(window._review)
        self.assertFalse(window.engine.busy)
        self.app.processEvents()
        self.assertEqual(window.game.cursor, 0)


    def test_pv_wheel_stops_self_play_before_previewing(self):
        window = self.window
        window._start_auto_play()
        self.wait(lambda: bool(window.candidates.lines))
        moves = window.candidates.rows[1][2]
        before = window.game.board.fen()
        event = QWheelEvent(QPointF(8, 8), QPointF(8, 8), QPoint(), QPoint(0, -120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(moves.viewport(), event)
        self.assertFalse(window._auto_play_active)
        self.assertFalse(window.engine.busy)
        self.assertEqual(window.game.board.fen(), before)
        self.assertIsNotNone(window.board_view.preview_board)


    def test_escape_cancels_automation_and_rejects_queued_results(self):
        window = self.window
        window._auto_evaluate_line()
        self.wait(lambda: bool(window.candidates.lines))
        generation = window._review["generation"]
        before = window.game.board.fen()
        window.show()
        window.activateWindow()
        self.app.processEvents()
        QTest.keyClick(window, Qt.Key.Key_Escape)
        self.assertIsNone(window._review)
        self.assertFalse(window.engine.busy)
        window._engine_message(generation, "result", {"move": "e2e4", "info": {}})
        self.app.processEvents()
        self.assertEqual(window.game.board.fen(), before)


    def test_function_keys_work_from_pgn_editor_and_escape_stops_through_settings(self):
        window = self.window
        window.show()
        window.activateWindow()
        window.tabs.setCurrentIndex(2)
        window.pgn_editor.setFocus()
        self.app.processEvents()
        QTest.keyClick(window.pgn_editor, Qt.Key.Key_F12)
        self.wait(lambda: window._review is not None and bool(window.candidates.lines))
        self.assertEqual(window.tabs.currentIndex(), 1)
        dialog = SettingsDialog(window.config, window)
        dialog.show()
        dialog.activateWindow()
        self.app.processEvents()
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        self.assertIsNone(window._review)
        self.assertFalse(window.engine.busy)
        dialog.deleteLater()


    def test_unrelated_settings_wheel_keeps_automation_running(self):
        window = self.window
        window._start_auto_play()
        self.wait(lambda: bool(window.engine.lines))
        dialog = SettingsDialog(window.config, window)
        event = QWheelEvent(QPointF(8,8), QPointF(8,8), QPoint(), QPoint(0,-120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(dialog.nodes, event)
        self.assertTrue(window._auto_play_active)
        self.assertTrue(window.engine.busy)
        dialog.deleteLater()
        window._escape()


    def test_pinning_a_row_keeps_global_search_telemetry_live(self):
        window = self.window
        window._auto_evaluate_line()
        self.wait(lambda: len(window.candidates.lines) == 3)
        frozen = dict(window.candidates.lines[1])
        window.candidates._action(1, "pin")
        update = frozen | dict(depth=9, nodes=1200, score=60, score_value=60)
        window._review_message(window._review["generation"], "info", update)
        self.assertEqual(window.candidates.lines[1], frozen)
        self.assertEqual(window._last_info["nodes"], 1200)
        self.assertEqual(window.eval_label.text(), "+0.60")

