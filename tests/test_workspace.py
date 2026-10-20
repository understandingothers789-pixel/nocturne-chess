"""Docking must preserve the live widgets, preferences and saved arrangement."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDockWidget, QPushButton

from nocturne.gui.window import MainWindow


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.window = MainWindow(Path(self.directory.name))
        self.window._analysis_enabled = False
        self.window.timer.stop()
        self.window.autosave_timer.stop()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def arrange(self):
        self.window.arrange_panels_action.trigger()
        self.app.processEvents()
        return self.window._dock_workspace

    def test_arrange_and_done_preserve_widgets_and_lock_the_live_layout(self):
        window = self.window
        board, candidates, fen = window.board_view, window.candidates, window.game.board.fen()
        host = self.arrange()
        self.assertEqual(set(host.docks), {"board", "analysis", "moves", "database", "graph", "insights"})
        self.assertEqual(host.docks["board"].widget(), window.arena)
        self.assertEqual(host.docks["analysis"].widget(), window.panel)
        self.assertTrue(host.docks["board"].features() & QDockWidget.DockWidgetFeature.DockWidgetMovable)
        done = next(b for b in host.toolbar.findChildren(QPushButton) if b.text() == "Done")
        done.click()
        self.assertIs(window._dock_workspace, host)
        self.assertFalse(window.arrange_panels_action.isChecked())
        self.assertFalse(host.docks["board"].features() & QDockWidget.DockWidgetFeature.DockWidgetMovable)
        window._refresh()
        self.assertIs(host.docks["analysis"].widget(), window.panel)
        self.assertIs(window.board_view, board)
        self.assertIs(window.candidates, candidates)
        self.assertEqual(window.game.board.fen(), fen)

    def test_old_wide_dock_layout_fits_board_and_keeps_columns_adjacent(self):
        window = self.window
        window.analysis_mode = True
        window._refresh()
        window.resize(1908, 900)
        host = self.arrange()
        # Reproduce the pre-.56 layout saved with opposite dock areas.
        host.surface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, host.docks["analysis"])
        host.surface.splitDockWidget(host.docks["analysis"], host.docks["database"], Qt.Orientation.Vertical)
        host.surface.splitDockWidget(host.docks["database"], host.docks["graph"], Qt.Orientation.Vertical)
        self.assertTrue(host.restore(host.state()))
        for _ in range(5):
            self.app.processEvents()
        board, analysis = host.docks["board"], host.docks["analysis"]
        self.assertLessEqual(window.board_view.width(), window.board_view.height() + 2)
        self.assertLessEqual(analysis.width(), 560)
        self.assertLess(abs(analysis.x() - board.geometry().right()), 12)
        self.assertGreater(host.docks["moves"].width(), board.width() + analysis.width())

    def test_detached_and_rearranged_panels_restore_locked_after_reopening(self):
        window = self.window
        host = self.arrange()
        host.surface.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, host.docks["moves"])
        host.surface.tabifyDockWidget(host.docks["analysis"], host.docks["graph"])
        host.docks["board"].setFloating(True)
        host.docks["board"].resize(530, 510)
        host.docks["board"].move(100000, 100000)
        self.app.processEvents()
        rect, _ = window.board_view._geometry()
        self.assertEqual(rect.width(), rect.height())
        window._save()
        window.close()
        self.assertFalse(host.docks["board"].isVisible())
        window.deleteLater()
        self.app.processEvents()
        self.window = MainWindow(Path(self.directory.name))
        self.window.timer.stop()
        self.window.autosave_timer.stop()
        self.window.show()
        self.app.processEvents()
        restored = self.window._dock_workspace
        self.assertIsNotNone(restored)
        self.assertTrue(restored.docks["board"].isFloating())
        self.assertIn(restored.docks["graph"], restored.surface.tabifiedDockWidgets(restored.docks["analysis"]))
        self.assertTrue(any(screen.availableGeometry().intersects(restored.docks["board"].frameGeometry())
                            for screen in self.app.screens()))
        self.assertEqual(restored.surface.dockWidgetArea(restored.docks["moves"]),
                         Qt.DockWidgetArea.LeftDockWidgetArea)
        self.assertFalse(self.window.arrange_panels_action.isChecked())
        self.assertFalse(restored.docks["board"].features() & QDockWidget.DockWidgetFeature.DockWidgetMovable)

    def test_reset_returns_floating_panels_to_classic_without_replacing_the_game(self):
        window = self.window
        fen = window.game.board.fen()
        host = self.arrange()
        host.docks["board"].setFloating(True)
        window._reset_workspace_layout()
        self.app.processEvents()
        self.assertIsNone(window._dock_workspace)
        self.assertEqual(window.config["layout"], "classic")
        self.assertIs(window.main_splitter.widget(0), window.arena)
        self.assertIs(window.main_splitter.widget(1), window.panel)
        self.assertIs(window.workspace_splitter.widget(1), window.analysis_moves_panel)
        self.assertIs(window.analysis_detail_splitter.widget(1), window.explorer)
        self.assertGreaterEqual(window.engine_page_layout.indexOf(window.graph), 0)
        self.assertEqual(window.graph.maximumHeight(), 85)
        self.assertEqual(window.game.board.fen(), fen)
        self.assertIsNone(window.store.get("workspace_layout"))
        self.assertTrue(window.board_view.isVisible())
        self.assertTrue(window.analysis_history.isVisible())

    def test_optional_docks_follow_display_and_database_preferences(self):
        window = self.window
        host = self.arrange()
        host.docks["graph"].close()
        self.assertFalse(window.config["show_eval_graph"])
        self.assertTrue(host.docks["graph"].isHidden())
        window._set_display("show_eval_graph", True)
        self.assertFalse(host.docks["graph"].isHidden())
        with patch.object(window.explorer.client, "load"), patch.object(window.opening_coverage.client, "load"):
            window._set_explorer_option("explorer_enabled", True)
            self.assertFalse(host.docks["database"].isHidden())
            window.tabs.setCurrentIndex(2)
            self.assertFalse(host.docks["database"].isHidden())
            host.docks["database"].close()
        self.assertFalse(window.config["explorer_enabled"])
        self.assertTrue(host.docks["database"].isHidden())

    def test_play_mode_and_presets_do_not_steal_or_lose_custom_panels(self):
        window = self.window
        host = self.arrange()
        window._workspace(False)
        self.assertTrue(host.docks["moves"].isHidden())
        self.assertIs(host.docks["board"].widget(), window.arena)
        self.assertIs(host.docks["analysis"].widget(), window.panel)
        window._workspace(True)
        self.assertFalse(host.docks["moves"].isHidden())
        window._set_layout("analysis-left")
        self.assertIsNone(window._dock_workspace)
        self.assertIs(window.main_splitter.widget(0), window.panel)
        self.assertTrue(window.board_view.isVisible())

    def test_corrupt_saved_arrangement_recovers_to_the_classic_layout(self):
        self.window.store.set("workspace_layout", {"version": 1, "docks": "not base64!"})
        self.window._restore_workspace_layout()
        self.assertIsNone(self.window._dock_workspace)
        self.assertTrue(self.window.workspace_splitter.isVisible())
        self.assertIsNone(self.window.store.get("workspace_layout"))
