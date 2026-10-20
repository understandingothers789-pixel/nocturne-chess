"""Interaction regressions for the compact analysis workspace."""

import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QDate, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from unittest.mock import patch

from nocturne.core.game import Game
from nocturne.gui.window import MainWindow
from nocturne.gui.analysis_settings import EngineSettings
from nocturne.gui.database_settings import DatabaseSettings
from nocturne.explorer import ExplorerQuery, query_filters


class AnalysisLayoutTests(unittest.TestCase):
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

    def test_compact_rows_stay_single_line_and_full_pv_opens_separately(self):
        window = self.window
        window._auto_evaluate_line()
        self.wait(lambda: len(window.candidates.lines) == 3)
        window.show()
        window.resize(1024, 660)
        self.app.processEvents()
        panel = window.candidates
        heights = [row[0].height() for row in panel.rows.values()]
        self.assertEqual(heights, [28, 28, 28])
        for _, header, moves in panel.rows.values():
            self.assertNotIn("Depth", header.text())
            self.assertNotIn("API", header.text())
            self.assertEqual(moves.height(), 24)
            self.assertEqual(moves.document().begin().layout().lineCount(), 1)
        panel.reserve_slots(99)
        self.assertEqual(list(panel.rows), [1, 2, 3, 4, 5])
        panel.expand_buttons[1].click()
        self.app.processEvents()
        self.assertTrue(panel._popup.isVisible())
        self.assertEqual([panel.rows[r][0].height() for r in (1, 2, 3)], heights)
        panel._popup.close()

    def test_side_tree_branches_evaluations_and_bottom_pgn_share_selection(self):
        window = self.window
        window.game = Game.from_pgn("1.e4 (1.d4 d5 (1...Nf6 2.c4) 2.c4) e5 2.Nf3 *")
        window.game.nodes[1].evaluation = 22
        window.game.evaluations[1] = 22
        window._refresh()
        tree = window.move_tree
        self.assertIn("+0.22", tree.toPlainText())
        self.assertIn("Nf6", tree.toPlainText())
        branch = window.game.nodes[0].children[1]
        tree._click(QUrl(f"move:{branch}"))
        self.assertEqual(window.game.current_node, branch)
        self.assertEqual(window.analysis_history._current, branch)
        self.assertEqual(tree._selected, branch)
        self.assertEqual(window.board_view.board.fen(), window.game.position_at_node(branch).fen())
        window._navigate_node(0)
        tree._click(QUrl(f"branch:{branch}"))
        self.assertNotIn("Nf6", tree.toPlainText())
        tree._click(QUrl(f"branch:{branch}"))
        self.assertIn("Nf6", tree.toPlainText())

    def test_engine_gear_restores_defaults_and_keeps_independent_limits_after_reopen(self):
        window = self.window
        window.config.update(analysis_nodes=100, auto_eval_nodes=200, auto_play_nodes=300)
        def defaults(dialog):
            dialog.reset_defaults()
            return QDialog.DialogCode.Accepted
        with patch.object(EngineSettings, "exec", defaults):
            window._engine_settings()
        self.assertEqual(window.config["analysis_nodes"], 1_000_000_000)
        self.assertEqual(window.config["auto_eval_nodes"], 200_000_000)
        self.assertEqual(window.config["auto_play_nodes"], 10_000_000)
        window._set_node_limit("auto_play_nodes", 50_000_000)
        self.assertEqual(window.config["analysis_nodes"], 1_000_000_000)
        self.assertEqual(window.config["auto_eval_nodes"], 200_000_000)
        reopened = MainWindow(Path(self.directory.name))
        try:
            self.assertEqual(reopened.config["auto_play_nodes"], 50_000_000)
            self.assertIn("1,000,000,000", reopened.normal_limit_menu.title())
            self.assertIn("200,000,000", reopened.auto_eval_limit_menu.title())
            self.assertIn("50,000,000", reopened.auto_play_limit_menu.title())
        finally:
            reopened.close()
            reopened.deleteLater()

    def test_evaluation_bar_handles_mate_unknown_and_orientation(self):
        bar = self.window.eval_bar
        bar.animations = False
        bar.set_score(29997)
        self.assertEqual(bar._fraction, 1)
        self.assertIn("#3", bar.toolTip())
        bar.set_score(-29998)
        self.assertEqual(bar._fraction, 0)
        bar.flipped = True
        self.assertFalse(bar.grab().isNull())
        bar.set_score(None)
        self.assertEqual(bar._fraction, 0.5)
        self.assertEqual(bar.toolTip(), "No evaluation")

    def test_database_dialog_applies_exact_filters_and_reuses_only_matching_cache(self):
        window = self.window
        desired = dict(window.config, explorer_source="lichess", explorer_speeds=["blitz", "rapid"],
                       explorer_ratings=[1800, 2200], explorer_since="2020-04", explorer_until="2024-12")
        query = ExplorerQuery(window.game.board.fen(), "lichess", **query_filters(desired))
        window.explorer.client.cache.put(query.key, {"white": 7, "draws": 2, "black": 1, "moves": []})
        def choose(dialog):
            dialog._fill(desired)
            dialog._accept()
            return dialog.result()
        with patch.object(DatabaseSettings, "exec", choose):
            window._database_settings()
        self.assertEqual(window.explorer.query.key, query.key)
        self.assertEqual(window.explorer.statistics["total"], 10)
        self.assertIn("blitz, rapid", window.explorer.filter_label.text())
        self.assertIn("2020-04", window.explorer.filter_label.text())
        self.assertEqual(window.store.get("settings")["explorer_ratings"], [1800, 2200])
        self.assertEqual(window.side_stack.currentWidget(), window.explorer)
        self.assertTrue(window.explorer_enabled_action.isChecked())
        dialog = DatabaseSettings(desired)
        dialog.source.setCurrentIndex(dialog.source.findData("player"))
        dialog._accept()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
        self.assertIn("username", dialog.error.text())
        dialog.player.setText("example")
        dialog._accept()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertFalse(dialog.rating_box.isEnabled())
        dialog.deleteLater()

    def test_database_dates_reject_reversed_range(self):
        dialog = DatabaseSettings(self.window.config)
        dialog.source.setCurrentIndex(dialog.source.findData("masters"))
        dialog.since_on.setChecked(True)
        dialog.until_on.setChecked(True)
        dialog.since.setDate(QDate(2024, 1, 1))
        dialog.until.setDate(QDate(2020, 1, 1))
        dialog._accept()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
        self.assertIn("Since", dialog.error.text())
        dialog.deleteLater()

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
        dialog = EngineSettings(window.config, window.profiles, window)
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
        dialog = EngineSettings(window.config, window.profiles, window)
        event = QWheelEvent(QPointF(8,8), QPointF(8,8), QPoint(), QPoint(0,-120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(dialog.normal_nodes, event)
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
