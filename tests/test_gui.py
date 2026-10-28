"""Native Qt integration tests. Explicitly skipped if the binding is absent."""

import os
import math
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
    from PySide6.QtCore import QEvent, QPoint, QPointF, QTimer, Qt
    from PySide6.QtGui import QMouseEvent, QTextCursor, QTextDocument, QWheelEvent, QColor, QFontMetricsF
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
        # Existing main-board-preview checks cover the optional legacy mode.
        self.window.config.update({"mode": "human", "animations": False, "cursor_preview": False})
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

    def test_authenticated_masters_automatically_marks_first_out_of_book_move(self):
        from nocturne.explorer import ExplorerQuery

        window = self.window
        window.game = Game.from_pgn("1.e4 e5 *")
        window.config.update(explorer_statistics=True, explorer_source="masters")
        for node, count in zip(window.game._line_nodes, [1000, 23, 0]):
            query = ExplorerQuery(window.game.position_at_node(node).fen())
            window.opening_coverage.client.cache.put(
                query.key, {"white": count, "draws": 0, "black": 0, "moves": []})
        window._sync_explorer()
        self.assertIsNone(window.opening_coverage.context)
        window.explorer.client.set_lichess_token("test-token")
        window._sync_explorer()
        for _ in range(5):
            self.app.processEvents()
        self.assertEqual(window.analysis_history._book_departure, window.game.current_node)
        self.assertIn("#c3b07c", window.analysis_history.toHtml())
        block = window.analysis_history.document().begin()
        while block.isValid():
            fragment = block.begin()
            while not fragment.atEnd():
                fmt = fragment.fragment().charFormat()
                if fmt.anchorHref() == f"move:{window.game.current_node}":
                    self.assertFalse(fmt.fontUnderline())
                fragment += 1
            block = block.next()
        self.assertIn("previous position: 23 games", window.opening_coverage_label.text())
        context = window.opening_coverage.context
        window.game.select_node(1)
        window._sync_explorer()
        self.assertEqual(window.opening_coverage.context, context)
        self.assertEqual(window.analysis_history._book_departure, 2)
        window.explorer.client.set_lichess_token("")
        window._sync_explorer()
        self.assertIsNone(window.analysis_history._book_departure)
        self.assertNotIn("#c3b07c", window.analysis_history.toHtml())

    def test_cached_departure_tooltips_keep_all_database_sources(self):
        from nocturne.explorer import ExplorerQuery

        window = self.window
        window.game = Game.from_pgn("1.e4 e5 *")
        window.explorer.client.set_lichess_token("test-token")
        for source, counts in (("masters", [100, 0]), ("lichess", [1000, 20, 0]),
                               ("chessdb", [1, 0])):
            for node, count in zip(window.game._line_nodes, counts):
                query = ExplorerQuery(window.game.position_at_node(node).fen(), source)
                data = ({"status": "ok" if count else "unknown", "moves": []} if source == "chessdb"
                        else {"white": count, "draws": 0, "black": 0, "moves": []})
                window.opening_coverage.client.cache.put(query.key, data)
        with patch.object(window.explorer.client, "load"):
            for source in ("masters", "lichess", "chessdb", "masters"):
                window._choose_explorer(source)
                for _ in range(5):
                    self.app.processEvents()
        markers = window.analysis_history._book_departures
        self.assertIn("Lichess Masters", markers[1])
        self.assertIn("ChessDB Cloud Analysis", markers[1])
        self.assertIn("Lichess players", markers[2])
        cursor = window.analysis_history.document().find("e4")
        cursor.setPosition(cursor.selectionStart())
        QTest.mouseMove(window.analysis_history.viewport(), window.analysis_history.cursorRect(cursor).center())
        self.assertIn("ChessDB Cloud Analysis", window.analysis_history.viewport().toolTip())
        self.assertIn("Lichess Masters", window.analysis_history.viewport().toolTip())

    def test_named_bookmarks_persist_navigate_and_follow_variation_deletion(self):
        window = self.window
        window.game = Game.from_pgn("1.e4 (1.d4 d5) e5 *")
        window.game.select_node(0)
        window._set_bookmark("Start", "Compare the two pawn openings")
        window.game.select_node(3)
        target_fen = window.game.board.fen()
        window._set_bookmark("Queen pawn", "Watch the central break")
        restored = window.store.load(window.game.id)
        self.assertEqual(restored.metadata["bookmarks"]["3"]["note"], "Watch the central break")
        window.game = restored
        window._populate_bookmarks()
        window.bookmarks_menu.actions()[0].trigger()
        self.assertEqual(window.game.current_node, 0)
        window.bookmarks_menu.actions()[1].trigger()
        self.assertEqual(window.game.board.fen(), target_fen)
        # Removing another branch compacts node IDs, but retains the position.
        e4 = next(i for i, node in enumerate(window.game.nodes) if node.san == "e4")
        window.game.select_node(e4)
        window.game.delete_current_line()
        window._populate_bookmarks()
        window.bookmarks_menu.actions()[1].trigger()
        self.assertEqual(window.game.board.fen(), target_fen)
        window._set_bookmark("")
        self.assertEqual(len(window.game.metadata["bookmarks"]), 1)

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

    def test_game_line_context_menu_offers_mainline_actions_on_alternative(self):
        window = self.window
        window.analysis_mode = True
        window.game = Game.from_pgn("1.e4 e5 2.Nf3 Nc6 (2...Nf6 3.d4) *")
        alternative = next(i for i, node in enumerate(window.game.nodes) if node.san == "Nf6")
        window._refresh()

        cursor = QTextCursor(window.inline_history.document())
        block = window.inline_history.document().begin()
        point = None
        while block.isValid() and point is None:
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.charFormat().anchorHref() == f"move:{alternative}":
                    cursor.setPosition(fragment.position() + 1)
                    point = window.inline_history.cursorRect(cursor).center()
                    break
                iterator += 1
            block = block.next()
        self.assertIsNotNone(point)
        self.assertEqual(window.inline_history.anchorAt(point), f"move:{alternative}")

        menu = window._inline_history_context_menu(point)
        labels = [action.text() for action in menu.actions()]
        self.assertIn("Make this variation the mainline", labels)
        self.assertIn("Make this variation the mainline and delete the previous mainline", labels)
        menu.deleteLater()

    def test_full_rating_chart_precedes_compact_scrollable_meter(self):
        w = self.window
        w.analysis_mode = True
        w.config.update(mode="analysis", multipv=5)
        w._apply_settings()
        w._sync_workspace_layout()
        w.resize(1900, 1050)
        w.show()
        policy = {"e2e4": .4, "d2d4": .3, "g1f3": .15, "c2c4": .1, "b1c3": .05}
        w.maia_insights.set_data({str(r): policy for r in range(600, 3001, 200)}, w.game.board, 1800)
        self.app.processEvents()
        w._protect_analysis_chart()
        self.app.processEvents()
        chart = w.maia_insights.trends_card
        self.assertGreaterEqual(chart.height(), chart.minimumSizeHint().height())
        viewport = w.engine_scroll.viewport()
        last_button = list(w.maia_insights.legend_buttons.values())[-1]
        self.assertLessEqual(last_button.mapToGlobal(last_button.rect().bottomRight()).y(),
                             viewport.mapToGlobal(viewport.rect().bottomRight()).y())
        self.assertLessEqual(w.blunder_scroll.height(), 180)
        self.assertIs(w.blunder_scroll.widget(), w.maia_insights.blunder)
        self.assertIs(w.right_detail_splitter.widget(2), w.graph)

    def test_analysis_columns_put_tools_in_middle_and_game_database_on_right(self):
        window = self.window
        window.analysis_mode = True
        window._apply_settings()
        game = window.game
        self.assertIs(window.candidate_splitter.widget(1), window.maia_insights.trends_card)
        self.assertIs(window.analysis_detail_splitter.widget(1), window.blunder_scroll)
        self.assertIs(window.blunder_scroll.widget(), window.maia_insights.blunder)
        self.assertIs(window.right_detail_splitter.widget(2), window.graph)
        self.assertIs(window.right_detail_splitter.widget(0), window.game_line_panel)
        self.assertIs(window.right_detail_splitter.widget(1), window.explorer)
        self.assertFalse(hasattr(window.maia_insights, "map"))
        window._set_display("show_maia_insights", False)
        self.assertTrue(window.maia_insights.trends_card.isHidden())
        self.assertTrue(window.maia_insights.blunder.isHidden())
        self.assertFalse(window.game_line_panel.isHidden())
        window._set_display("show_maia_insights", True)
        self.assertIs(window.game, game)
        with patch("nocturne.gui.window.QMessageBox.information") as guide:
            window._show_board_guide()
        self.assertIn("10%", guide.call_args.args[2])
        self.assertIn("rankings, not probabilities", guide.call_args.args[2])

    def test_maia_range_updates_requests_chart_and_selected_rating(self):
        from nocturne.settings import normalize
        w = self.window
        w.analysis_mode = True
        with patch.object(w.maia, "request") as request:
            w._set_maia_range(1200, 2000)
            self.assertEqual(w.maia.ratings, (1200, 1400, 1600, 1800, 2000))
            self.assertEqual(w.maia_insights.chart.ratings, w.maia.ratings)
            w._set_maia_rating(3000)
            self.assertEqual(w.config["maia_rating"], 2000)
            self.assertEqual(request.call_args.args[2], 2000)
        restored = normalize(w.config)
        self.assertEqual((restored["maia_rating_min"], restored["maia_rating_max"]), (1200, 2000))
        with patch("nocturne.gui.window.QToolTip.showText") as tooltip:
            w.eventFilter(w.board_guide_button, QEvent(QEvent.Type.Enter))
        self.assertIn("Click to learn", tooltip.call_args.args[1])

    def test_dragging_bottom_splitter_to_zero_collapses_moves(self):
        w = self.window
        w.analysis_mode = True
        w._refresh()
        self.app.processEvents()
        self.assertTrue(w.workspace_splitter.isCollapsible(1))
        w.workspace_splitter.setSizes([800, 0])
        w._bottom_splitter_moved(w.workspace_splitter.height(), 1)
        self.assertTrue(w.config["bottom_moves_collapsed"])
        self.assertTrue(w.analysis_history.isHidden())
        w._toggle_bottom_moves()
        self.assertFalse(w.analysis_history.isHidden())
        self.assertGreater(w.workspace_splitter.sizes()[1], 0)
        self.assertEqual(w.maia_controls.move_limit.prefix(), "")

    def test_bottom_moves_can_collapse_and_reopen(self):
        w = self.window
        w._toggle_bottom_moves()
        self.assertTrue(w.analysis_history.isHidden())
        self.assertLessEqual(w.analysis_moves_panel.maximumHeight(), 34)
        self.assertFalse(w.bottom_moves_toggle.isHidden())
        w._toggle_bottom_moves()
        self.assertFalse(w.analysis_history.isHidden())
        self.assertGreater(w.analysis_moves_panel.maximumHeight(), 100)

    def test_history_numbers_for_black_to_move_fen(self):
        game = Game("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 20")
        for move in ("e7e5", "e2e4", "b8c6"):
            game.play(game.board.parse_uci(move))
        self.window.game = game
        self.window._refresh()
        table = self.window.history
        self.assertEqual([table.item(i, 0).text() for i in range(2)], ["20", "21"])
        self.assertEqual(table.item(0, 2).text(), "e5")
        self.assertEqual(table.item(1, 1).text(), "e4")
        self.assertEqual(table.item(1, 2).text(), "Nc6")

    def test_backing_out_of_variation_resumes_mainline_on_forward_navigation(self):
        window = self.window
        window.game = Game.from_pgn("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 (3...Nf6) 4. Ba4 *")
        alternative = next(i for i, node in enumerate(window.game.nodes) if node.san == "Nf6")
        window.game.select_node(alternative)
        window.game.metadata["mode"] = "analysis"
        window.analysis_mode = True
        window._analysis_enabled = False
        window._navigate(5)  # Return to the shared position after 3.Bb5.
        self.assertEqual(window.game.current_node, window.game.mainline_node(5))
        window._navigate(6)
        self.assertEqual(window.game.sans[5], "a6")

    def test_left_arrow_out_of_variation_resumes_mainline(self):
        window = self.window
        window.game = Game.from_pgn("1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 (3...Nf6) 4.Ba4 *")
        branch = next(i for i, node in enumerate(window.game.nodes) if node.san == "Nf6")
        window.game.select_node(branch)
        window.analysis_mode = True
        window._analysis_enabled = False
        window.menu_actions["Backward"].trigger()
        window.menu_actions["Forward"].trigger()
        self.assertEqual(window.game.sans[5], "a6")

    def test_move_navigation_reanalysis_is_opt_in(self):
        window = self.window
        window.game = Game.from_pgn("1.e4 e5 2.Nf3 *")
        window.analysis_mode = True
        window._analysis_enabled = False
        window._navigate(1)
        self.assertFalse(window._analysis_enabled)
        self.assertFalse(window.config["reanalyze_on_navigation"])
        window.config["reanalyze_on_navigation"] = True
        window._navigate(2)
        self.assertTrue(window._analysis_enabled)
        action = window.menu_actions["Automatically analyze when selecting a position"]
        self.assertFalse(action.isChecked())

    def test_auto_evaluation_limit_is_separate_and_selectable_in_engine_menu(self):
        window = self.window
        self.assertEqual(window.normal_limit_menu.title(), "Normal nodes per position · 1,000,000,000")
        self.assertEqual(window.auto_eval_limit_menu.title(), "Auto-evaluation nodes per position · 200,000,000")
        self.assertEqual(window.auto_play_limit_menu.title(), "Auto-play nodes per move · 10,000,000")
        for menu in (window.normal_limit_menu, window.auto_eval_limit_menu, window.auto_play_limit_menu):
            self.assertTrue({f"{n:,}" for n in range(100_000_000, 1_000_000_001, 100_000_000)} <=
                            {action.text() for action in menu.actions()})
        window._set_auto_eval_limit(100_000_000)
        actions = window.auto_eval_limit_menu.actions()
        selected = next(action for action in actions if action.text() == "100,000,000")
        self.assertTrue(selected.isChecked())
        self.assertEqual(window.config["auto_eval_nodes"], 100_000_000)
        self.assertEqual(window.auto_eval_limit_menu.title(), "Auto-evaluation nodes per position · 100,000,000")
        values = {action.text() for action in window.auto_eval_limit_menu.actions()}
        self.assertTrue({f"{n:,}" for n in range(100_000_000, 1_000_000_001, 100_000_000)} <= values)
        self.assertEqual(window.menu_actions["Auto-play engines from this position"].shortcut().toString(), "F11")

    def test_engine_status_uses_full_uci_name_instead_of_profile_short_label(self):
        profile = self.window._profile()
        profile["name"] = "SF 19"
        self.window.engine.connection.path = profile["path"]
        self.window.engine.connection.name = "Stockfish dev-20261013-5c4cef0b"
        self.assertEqual(self.window._active_engine_name(), "Stockfish dev-20261013-5c4cef0b")

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

    def test_nibbler_default_has_twelve_matching_vectors_and_live_style_switching(self):
        from nocturne.gui.dialogs import SettingsDialog
        board = self.window.board_view
        self.assertEqual(self.window.config["piece_set"], "Nibbler")
        self.assertEqual(board.piece_set, "Nibbler")
        self.assertEqual(len(board._renderers), 12)
        for piece, image in board._renderers.items():
            self.assertTrue(image.isValid())
            self.assertFalse(image.viewBoxF().isEmpty())
            self.assertTrue(board.piece_path(piece).is_file())
            self.assertNotIn("<image", board.piece_path(piece).read_text())
        self.assertEqual(board.piece_path(2).name, "wN.svg")
        self.assertEqual(board.piece_path(-2).name, "bN.svg")
        dialog = SettingsDialog(self.window.config, self.window)
        try:
            self.assertEqual(dialog.pieces.itemText(0), "Nibbler")
            self.assertEqual(dialog.preview.piece_set, "Nibbler")
            dialog.pieces.setCurrentText("Cburnett")
            self.assertEqual(dialog.preview.piece_set, "Cburnett")
            dialog.pieces.setCurrentText("Nibbler")
            self.assertEqual(dialog.preview.piece_set, "Nibbler")
            self.assertTrue(dialog.preview._renderers[2].isValid())
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_every_registered_piece_set_paints_as_antialiased_vectors_at_high_dpi(self):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QImage, QPainter
        from nocturne.pieces import PIECE_SET_NAMES
        board = self.window.board_view
        for style in PIECE_SET_NAMES:
            board.set_piece_set(style)
            self.assertEqual(len(board._renderers), 12, style)
            for piece, renderer in board._renderers.items():
                self.assertTrue(renderer.isValid(), (style, piece))
                self.assertTrue(board.piece_path(piece).is_file(), (style, piece))
                self.assertNotIn("<image", board.piece_path(piece).read_text(), (style, piece))
                for scale in (1, 2, 3):
                    image = QImage(256 * scale, 256 * scale, QImage.Format.Format_ARGB32)
                    image.setDevicePixelRatio(scale)
                    image.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(image)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    board._piece(painter, piece, QRectF(0, 0, 256, 256))
                    painter.end()
                    self.assertEqual(image.pixelColor(0, 0).alpha(), 0, (style, piece, scale))
                    self.assertGreater(image.pixelColor(128 * scale, 190 * scale).alpha(), 0,
                                       (style, piece, scale))
                    edge = [image.pixelColor(x, 128 * scale).alpha() for x in range(image.width())]
                    self.assertTrue(any(0 < alpha < 255 for alpha in edge), (style, piece, scale))

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
        self.assertNotIn("[0:04:59.3]", visible_moves)
        self.assertNotIn("[0:04:58.9]", visible_moves)
        self.assertIn("e4", visible_moves)
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

    def test_game_moves_clean_and_optional_raw_pgn_preserves_annotations(self):
        text = '1.e4 {Keep this note [%clk 0:04:59.3][%timestamp 7]} $1 (1.d4 {Branch}) e5 *'
        self.assertTrue(self.window._import_text(text))
        window = self.window
        raw_index = window.tabs.indexOf(window.raw_pgn_page)
        self.assertFalse(window.raw_pgn_action.isChecked())
        self.assertFalse(window.tabs.isTabVisible(raw_index))
        visible = window.analysis_history.toPlainText()
        self.assertIn("e4", visible)
        self.assertIn("d4", visible)
        self.assertNotIn("04:59", visible)
        self.assertNotIn("Keep this note", visible)
        self.assertNotIn("Branch", visible)
        before = window.game.pgn()
        fen, generation = window.game.board.fen(), window.engine.generation
        window.raw_pgn_action.trigger()
        self.assertIs(window.tabs.currentWidget(), window.raw_pgn_page)
        self.assertTrue(window.raw_pgn_text.isReadOnly())
        self.assertEqual(window.raw_pgn_text.toPlainText(), before)
        self.assertIn("[%timestamp 7]", window.raw_pgn_text.toPlainText())
        self.assertIn("[%clk 0:04:59.3]", window.raw_pgn_text.toPlainText())
        flipped = window.board_view.flipped
        window.raw_pgn_text.setFocus()
        QTest.keyClick(window.raw_pgn_text, Qt.Key.Key_Backspace)
        QTest.keyClick(window.raw_pgn_text, Qt.Key.Key_F)
        self.assertEqual(window.board_view.flipped, flipped)
        self.assertEqual(window.game.pgn(), before)
        self.assertEqual(window.game.board.fen(), fen)
        self.assertEqual(window.engine.generation, generation)
        window._copy_pgn()
        exported = QApplication.clipboard().text()
        restored = Game.from_pgn(exported)
        self.assertIn("Keep this note", restored.pgn())
        self.assertIn("Branch", restored.pgn())
        self.assertTrue(restored.has_pgn_clocks)
        self.assertIn("[%timestamp 7]", window.store.load(window.game.id).pgn())
        window.raw_pgn_action.trigger()
        self.assertFalse(window.tabs.isTabVisible(raw_index))
        self.assertFalse(window.store.get("settings")["show_raw_pgn"])
        self.assertEqual(window.game.pgn(), before)

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

    def test_graph_guides_track_one_pawn_on_compressed_symmetric_scale(self):
        graph = self.window.graph
        samples = {0: 0, 1: 50, 2: 100, 3: 200, 4: 400, 5: 800, 6: -800}
        graph.set_samples(samples, 6, 6)
        rect = graph._plot_rect()
        center = graph._point(0, 0).y()
        self.assertAlmostEqual(center, rect.center().y())
        self.assertAlmostEqual(center - graph._point(2, 100).y(),
                               graph._point(2, -100).y() - center)
        self.assertAlmostEqual(center - graph._point(1, 50).y(),
                               (center - graph._point(2, 100).y()) / 2)
        self.assertLess(graph._point(5, 800).y(), graph._point(4, 400).y())
        self.assertGreater(graph._point(5, 800).y(), rect.top())
        self.assertGreater(graph._compressed(200) - graph._compressed(100),
                           graph._compressed(800) - graph._compressed(700))
        self.assertEqual(graph.samples, samples)  # Values stay actual cp, not display coordinates.
        before = graph._point(2, 100).y()
        graph.set_samples(samples | {7: 2000, 8: -2000}, 7, 8)
        self.assertGreater(graph._point(2, 100).y(), before)
        self.assertAlmostEqual(graph._point(2, 100).y() + graph._point(2, -100).y(), 2 * center)

    def test_graph_reveals_history_through_cursor_and_follows_navigation(self):
        graph = self.window.graph
        graph.resize(650, 85)
        samples = {0: 0, 2: 50, 10: 100}
        graph.set_samples(samples, 2, 10)
        rect = graph._plot_rect()
        self.assertAlmostEqual(graph._point(2, 0).x(), rect.right())
        early_position = graph._point(2, 0).x()
        graph.set_samples(samples, 10, 10)
        self.assertAlmostEqual(graph._point(10, 0).x(), rect.right())
        self.assertLess(graph._point(2, 0).x(), early_position)

    def test_graph_mates_do_not_flatten_cp_and_zoom_clicks_keep_ply_mapping(self):
        graph = self.window.graph
        graph.set_samples({0: 0, 1: 100, 2: -100, 3: 400}, 1, 6)
        ordinary = graph._point(1, 100).y()
        graph.set_samples({0: 0, 1: 100, 2: -100, 3: 400, 4: 30000, 6: -30000}, 1, 6)
        self.assertEqual(graph._point(1, 100).y(), ordinary)
        self.assertEqual(graph._point(4, 30000).y(), graph._plot_rect().top())
        self.assertEqual(graph._point(6, -30000).y(), graph._plot_rect().bottom())
        graph.resize(650, 85)
        graph.view_start, graph.view_end = 1.0, 4.0
        selected = []
        graph.position_requested.connect(selected.append)
        # Disconnect normal game navigation while checking graph coordinates.
        graph.position_requested.disconnect()
        graph.position_requested.connect(selected.append)
        QTest.mouseClick(graph, Qt.MouseButton.LeftButton, pos=graph._point(3, 0).toPoint())
        self.assertEqual(selected, [3])
        self._wheel(graph, 120, point=graph._point(2, 0).toPoint())
        self.assertLess(graph.view_end - graph.view_start, 3)
        QTest.mouseDClick(graph, Qt.MouseButton.LeftButton, pos=graph.rect().center())
        self.assertEqual(graph.view_start, 0)
        self.assertIsNone(graph.view_end)

    def test_graph_zoom_preserves_cursor_anchor_on_partial_game(self):
        from nocturne.gui.widgets import EvaluationGraph
        graph = EvaluationGraph()
        self.addCleanup(graph.close)
        graph.resize(650, 85)
        graph.show()
        self.app.processEvents()
        graph.set_samples({0: 0, 2: 50, 10: 100, 100: 2000}, 10, 100)
        anchor = graph._point(5, 0).toPoint()
        self._wheel(graph, 120, point=anchor)
        self.assertLess(graph.view_end - graph.view_start, 10)
        self.assertAlmostEqual(graph._point(5, 0).x(), anchor.x(), delta=1)

    def test_graph_ignores_future_samples_for_scale_and_clicks(self):
        graph = self.window.graph
        graph.resize(650, 85)
        graph.set_samples({0: 0, 1: 100}, 2, 10)
        extent = graph._extent
        graph.set_samples({0: 0, 1: 100, 3: 2500}, 2, 10)
        self.assertEqual(graph._extent, extent)
        selected = []
        graph.position_requested.disconnect()
        graph.position_requested.connect(selected.append)
        QTest.mouseClick(graph, Qt.MouseButton.LeftButton, pos=graph._plot_rect().topRight().toPoint())
        self.assertEqual(selected, [1])

    def test_graph_visibility_is_independent_and_persisted(self):
        self.assertTrue(self.window.display_actions["show_eval_graph"].isChecked())
        self.window.display_actions["show_eval_graph"].trigger()
        self.assertTrue(self.window.graph.isHidden())
        self.assertFalse(self.window.store.get("settings")["show_eval_graph"])
        self.window.display_actions["show_eval_graph"].trigger()
        self.assertFalse(self.window.graph.isHidden())

    def test_graph_resets_zoom_for_same_length_different_game(self):
        graph = self.window.graph
        graph.set_samples({0: 0, 4: 100}, 4, 10, context="first")
        graph.view_start, graph.view_end = 2, 6
        graph.set_samples({0: 0, 4: -100}, 4, 10, context="second")
        self.assertEqual(graph.view_start, 0)
        self.assertIsNone(graph.view_end)

    def test_unanalysed_navigation_clears_previous_evaluation_and_depth(self):
        window = self.window
        window.analysis_mode = True
        window._analysis_enabled = False
        window.game = Game.from_pgn("1.e4 e5 *")
        window._navigate(0)
        self._show_external_info({"depth": 30, "seldepth": 42, "score": 200, "nodes": 500,
                                  "pv": ["e2e4"]}, {"turn": 1, "multipv": 1})
        window._navigate(1)
        self.assertEqual(window.eval_label.text(), "—")
        self.assertNotIn("30", window.telemetry.text())
        self.assertIsNone(window._last_info)

    def _header_document(self, rank):
        document = QTextDocument()
        header = self.window.candidates.rows[rank][1].text()
        document.setHtml(header)
        return document

    def _candidate_header_text(self, rank):
        document = QTextDocument()
        document.setHtml(self.window.candidates.rows[rank][1].text())
        return document.toPlainText()

    def _candidate_footer_text(self, rank):
        # Kept as a helper for status assertions; candidate telemetry now shares
        # the evaluation/depth row so the database sample stays associated.
        return self._candidate_header_text(rank)

    def test_candidate_headers_color_real_api_metrics_and_keep_depth_neutral(self):
        from nocturne.explorer import parse_statistics
        from nocturne.gui.theme import palette
        self._three_pvs()
        self._show_external_info({"depth": 31, "seldepth": 46, "score": 22, "nodes": 10000,
                                  "multipv": 3, "wdl": (100, 200, 700), "pv": ["b1c3", "g8f6"]},
                                 {"turn": 1, "multipv": 3})
        self.window.config.update(explorer_enabled=True, explorer_statistics=True, explorer_source="masters")
        with patch.object(self.window.explorer.client, "load"):
            self.window._sync_explorer()
        explorer = self.window.explorer
        query = explorer.query
        data = parse_statistics({"white": 500, "draws": 200, "black": 300,
                                 "moves": [{"uci": "b1c3", "white": 100, "draws": 100, "black": 200}]}, query)
        explorer._result(query.key, data, "Cached · test data")
        for light in (False, True):
            self.window.config["light"] = light
            self.window._apply_settings()
            document = self._header_document(3)
            text = document.toPlainText().replace("\u00a0", " ")
            headline = self._candidate_header_text(3).replace("\u00a0", " ")
            footer = self._candidate_footer_text(3).replace("\u00a0", " ")
            self.assertIn("Depth 31", headline)
            self.assertTrue(self.window.candidates.rows[3][2].toPlainText().startswith("+0.22"))
            self.assertNotIn("31/46", headline)
            self.assertIn("W/D/L 10.0/20.0/70.0% White", headline)
            self.assertIn("API win (White) 25.0%", headline)
            self.assertIn("Freq 40.0%", headline)
            self.assertIn("W/D/L 10.0/20.0/70.0% White", footer)
            self.assertIn("API win (White) 25.0%", footer)
            self.assertIn("Freq 40.0%", footer)
            self.assertIn("Depth 31", text)
            self.assertNotIn("31/46", text)
            self.assertIn("W/D/L 10.0/20.0/70.0% White", text)
            self.assertIn("API win (White) 25.0%", text)
            self.assertIn("Freq 40.0%", text)  # Uses all 1,000 games, not just returned moves.
            self.assertIn("400 / 1,000 games", text)
            self.assertIn("Lichess Masters · Cached", text)
            for blue_text in ("25.0%", "40.0%"):
                color = document.find(blue_text).charFormat().foreground().color()
                self.assertEqual(color, QColor(palette(light)["metric"]))
            self.assertNotEqual(document.find("Depth").charFormat().foreground().color(),
                                QColor(palette(light)["metric"]))
            header = self.window.candidates.rows[3][1]
            pv = self.window.candidates.rows[3][2]
            self.assertEqual(header.font().pixelSize(), 16)
            self.assertIn("font-size:19px", pv.toHtml().replace(" ", ""))  # Default +20%, rounded by Qt.
            self.assertIn("No games found", self._header_document(1).toPlainText())
        self.window._set_explorer_option("explorer_enabled", False)
        self.assertFalse(explorer.isVisible())
        self.assertIs(explorer.query, query)
        self.assertIs(explorer.statistics, data)
        self.assertIn("25.0%", self._header_document(3).toPlainText())
        self.assertTrue(self.window.explorer_statistics_action.isChecked())
        # API updates still reach headers while the explorer panel is hidden.
        # API updates change metadata without shifting a hovered lower slot.
        third = self.window.candidates.rows[3][2]
        self._hover_word(third, "Nc3")
        before = third.mapToGlobal(third.rect().topLeft())
        data["moves"][0].update(white=200, black=100)
        explorer._result(query.key, data, "Live · Lichess Masters")
        self.assertIn("50.0%", self._header_document(3).toPlainText())
        self.assertEqual(third.mapToGlobal(third.rect().topLeft()), before)
        self.assertEqual(self.window.candidates.hovered, 3)

    def test_selective_depth_is_optional_in_headers_and_highlights_top_metrics(self):
        from PySide6.QtGui import QTextDocument
        from nocturne.gui.theme import palette

        self._analysis_game("1.e4 e5 *")
        self._show_external_info({
            "depth": 18, "seldepth": 38, "score": 24, "nodes": 2_345_678,
            "nps": 12_345, "seconds": 2.5, "hashfull": 420, "tbhits": 3,
            "pv": ["g1f3"],
        }, {"turn": 1, "multipv": 1})
        action = self.window.display_actions["show_seldepth"]
        self.assertEqual(action.text(), "Show selective depth (seldepth)")
        self.assertFalse(action.isChecked())

        document = QTextDocument()
        document.setHtml(self.window.telemetry.text())
        telemetry = document.toPlainText()
        self.assertNotIn("+0.24", telemetry)
        self.assertEqual(self.window.eval_label.text(), "+0.24")
        self.assertTrue(self.window.engine_state.isHidden())
        self.window.maia_controls.details.setChecked(True)
        self.assertFalse(self.window.engine_state.isHidden())
        self.assertFalse(self.window.tablebase_label.isHidden())
        self.window.maia_controls.details.setChecked(False)
        self.assertTrue(self.window.tablebase_label.isHidden())
        self.assertIn("Depth 18", telemetry)
        self.assertNotIn("18/38", telemetry)
        self.assertIn("Nodes 2,345,678", telemetry)
        self.assertIn("Nodes/second 12,345", telemetry)
        self.assertIn("Depth 18", self._candidate_header_text(1))
        self.assertNotIn("18/38", self._candidate_header_text(1))
        self.assertIn("font-size:15px", self.window.telemetry.text())
        self.assertIn(palette(False)["metric"], self.window.telemetry.text())

        action.trigger()
        document.setHtml(self.window.telemetry.text())
        self.assertTrue(self.window.store.get("settings")["show_seldepth"])
        self.assertIn("Depth 18/38", document.toPlainText())
        self.assertIn("Depth 18/38", self._candidate_header_text(1))

    def test_candidate_database_status_distinguishes_loading_errors_and_empty_samples(self):
        from nocturne.explorer import parse_statistics
        self._three_pvs()
        self.window.config.update(explorer_enabled=True, explorer_statistics=True, explorer_source="masters")
        with patch.object(self.window.explorer.client, "load"):
            self.window._sync_explorer()
        explorer = self.window.explorer
        query = explorer.query
        explorer._status(query.key, "Loading Lichess Masters…")
        self.assertIn("Loading", self._candidate_footer_text(1))
        self.assertNotIn("awaiting data", self._candidate_footer_text(1).lower())
        explorer._clear_statistics()
        explorer._status(query.key, "Lichess Masters unavailable (HTTP 503)")
        footer = self._candidate_footer_text(1)
        self.assertIn("unavailable (HTTP 503)", footer)
        self.assertNotIn("No games found", footer)
        empty = parse_statistics({"white": 0, "draws": 0, "black": 0, "moves": []}, query)
        explorer._result(query.key, empty, "Live · Lichess Masters")
        footer = self._candidate_footer_text(1)
        self.assertIn("No games found", footer)
        self.assertNotIn("Loading", footer)

    def test_candidate_api_counts_follow_black_pov_and_reject_stale_results(self):
        from nocturne.explorer import parse_statistics
        self._analysis_game("1.e4 *")
        self._show_external_info({"depth": 9, "seldepth": 12, "score": 30, "nodes": 1000,
                                  "wdl": (100, 200, 700), "pv": ["e7e5"]}, {"turn": -1})
        self.window.config.update(explorer_enabled=True, explorer_statistics=True, explorer_source="lichess")
        with patch.object(self.window.explorer.client, "load"):
            self.window._sync_explorer()
        explorer = self.window.explorer
        old = explorer.query
        data = parse_statistics({"white": 40, "draws": 20, "black": 40,
                                 "moves": [{"uci": "e7e5", "white": 10, "draws": 10, "black": 30}]}, old)
        explorer._result(old.key, data, "Live · test data")
        text = self._header_document(1).toPlainText()
        self.assertIn("API win (Black) 60.0%", text)
        self.assertIn("Freq 50.0%", text)
        self.assertIn("W/D/L 70.0/20.0/10.0% White", text)
        self.window.config["explorer_source"] = "chessdb"
        with patch.object(explorer.client, "load"):
            self.window._sync_explorer()
        current = explorer.query
        explorer._result(old.key, data, "Live · late old response")
        self.assertNotIn("60.0%", self._header_document(1).toPlainText())
        cloud = parse_statistics({"status": "ok", "moves": [{"uci": "e7e5", "score": 20}]}, current)
        explorer._result(current.key, cloud, "Live · ChessDB")
        text = self._header_document(1).toPlainText()
        self.assertIn("DB White -0.20", text)
        self.assertIn("ChessDB · Live", text)
        self.assertIn("API win (Black) —", text)
        self.assertIn("Freq —", text)
        self.window._set_explorer_option("explorer_enabled", False)
        self.assertIn("DB White -0.20", self._header_document(1).toPlainText())
        self.assertFalse(explorer.isVisible())
        self.window._set_explorer_option("explorer_statistics", False)
        self.assertIn("Database off", self._header_document(1).toPlainText())
        explorer._result(current.key, cloud, "Live · disabled response")
        self.assertIsNone(self.window.candidates.database)

    def test_metadata_headers_fit_at_narrow_and_wide_widths_without_pv_height_changes(self):
        self._three_pvs()
        panel = self.window.candidates
        panel.set_detailed(True)
        for width in (1000, 1600):
            self.window.resize(width, 1000)
            self.app.processEvents()
            pv_heights = {row[2].height() for row in panel.rows.values()}
            self.assertEqual(len(pv_heights), 1)
            self.assertEqual(len({row[1].height() for row in panel.rows.values()}), 1)
            self.assertEqual(len({panel.footers[rank].height() for rank in panel.rows}), 1)
            for _, header, _ in panel.rows.values():
                document = QTextDocument()
                document.setDefaultFont(header.font())
                document.setDocumentMargin(0)
                document.setHtml(header.text())
                document.setTextWidth(header.width())
                self.assertLessEqual(document.size().height(), header.height())
            for footer in panel.footers.values():
                document = QTextDocument()
                document.setDefaultFont(footer.font())
                document.setDocumentMargin(0)
                document.setHtml(footer.text())
                document.setTextWidth(footer.width())
                self.assertLessEqual(document.size().height(), footer.height())

    def _wheel(self, widget, delta, *, pixel=0, shift=False, point=None):
        point = point or widget.rect().center()
        event = QWheelEvent(QPointF(point), QPointF(widget.mapToGlobal(point)),
                            QPoint(0, pixel), QPoint(0, delta), Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        self.app.sendEvent(widget, event)
        self.app.processEvents()

    def test_wheel_board_and_history_navigate_selected_branch_with_bounds_and_toggle(self):
        self._analysis_game("1.e4 e5 (1...Nf6 2.Nc3) 2.Nf3 Nc6 *")
        self.window.game.select_node(next(i for i, n in enumerate(self.window.game.nodes) if n.san == "Nc3"))
        self.window._refresh()
        board = self.window.board_view
        point = board.square_rect(parse_square("e4")).center().toPoint()
        original_nodes = len(self.window.game.nodes)
        with patch.object(self.window, "_schedule_engine"):
            self._wheel(board, 120, point=point)
            self.assertEqual(self.window.game.nodes[self.window.game.current_node].san, "Nf6")
            self._wheel(self.window.analysis_history.viewport(), -120)
            self.assertEqual(self.window.game.nodes[self.window.game.current_node].san, "Nc3")
            self._wheel(board, -120, point=point)
            self.assertEqual(self.window.game.cursor, 3)
            self._wheel(board, 60, point=point)
            self.assertEqual(self.window.game.cursor, 3)
            self._wheel(board, 60, point=point)
            self.assertEqual(self.window.game.cursor, 2)
            self.window._set_display("wheel_game_moves", False)
            self._wheel(board, 120, point=point)
            self._wheel(self.window.analysis_history.viewport(), 120)
            self.assertEqual(self.window.game.cursor, 2)
            self.window._set_display("wheel_game_moves", True)
            self._wheel(board, 120, shift=True, point=point)
            self.assertEqual(self.window.game.cursor, 2)
            self._wheel(self.window.history.viewport(), 120)
            self.assertEqual(self.window.game.cursor, 1)
            self._wheel(board, 0, pixel=-20, point=point)
            self.assertEqual(self.window.game.cursor, 1)
            self._wheel(board, 0, pixel=-20, point=point)
            self.assertEqual(self.window.game.cursor, 2)
        self.assertEqual(len(self.window.game.nodes), original_nodes)

    def test_wheel_analysis_previews_frozen_line_without_editing_game(self):
        base, job = self._three_pvs()
        panel = self.window.candidates
        third = panel.rows[3][2]
        self._hover_word(third, "Nc3")
        node, fen, count = self.window.game.current_node, self.window.game.board.fen(), len(self.window.game.nodes)
        root = self.window.game.board.copy()
        root.push(root.parse_uci("b1c3"))
        root.push(root.parse_uci("g8f6"))
        self._wheel(third.viewport(), -120)
        self.assertEqual(self.window.board_view.display_board.fen(), root.fen())
        self._show_external_info(base | {"multipv": 3, "pv": ["d2d4"]}, job)
        self.assertEqual(panel.lines[3]["pv"][0], "d2d4")
        self.assertIsNone(third.wheel_preview_ply)
        self.assertIsNone(self.window.board_view.preview_board)
        self._wheel(third.viewport(), 120)
        self.assertEqual(third._hovered, 0)
        self._wheel(third.viewport(), 120)
        self.assertEqual(self.window.board_view.display_board.fen(), fen)
        self.assertEqual(self.window.game.current_node, node)
        self.assertEqual(len(self.window.game.nodes), count)
        third.cancel_preview()
        QTest.qWait(20)
        self.assertIsNone(self.window.board_view.preview_board)
        self.assertEqual(panel.lines[3]["pv"][0], "d2d4")
        self.window._set_display("wheel_analysis_moves", False)
        self._wheel(third.viewport(), -120)
        self.assertIsNone(self.window.board_view.preview_board)
        panel.reserve_slots(4)
        self.assertFalse(panel.rows[4][2].wheel_navigation)

    def test_wheel_preview_keeps_pv_snapshot_until_candidate_rank_changes(self):
        base, job = self._three_pvs()
        panel = self.window.candidates
        view = panel.rows[3][2]
        original_pv = ["b1c3", "b8c6", "g1f3", "g8f6", "f3g1", "f6g8",
                       "c3b1", "c6b8", "b1c3", "b8c6", "g1f3", "g8f6"]
        self._show_external_info(base | {"multipv": 3, "pv": original_pv}, job)
        old_line = panel.lines[3].copy()
        for _ in range(6):
            self._wheel(view.viewport(), -120)
        self.assertEqual(view.wheel_preview_ply, 6)
        preview_fen = self.window.board_view.display_board.fen()

        # Stockfish extends/revises the same candidate. Keep its displayed
        # snapshot and wheel index stable until the user leaves the preview.
        same_candidate = base | {"multipv": 3, "pv": original_pv[:6] + ["d2d3"]}
        self._show_external_info(same_candidate, job)
        self.assertEqual(panel.lines[3]["pv"], old_line["pv"])
        self.assertEqual(panel.pending[3][0]["pv"][0], old_line["pv"][0])
        self.assertEqual(view.wheel_preview_ply, 6)
        self.assertEqual(view._hovered, 6)
        self.assertEqual(self.window.board_view.display_board.fen(), preview_fen)

        # A new root move means this MultiPV rank now represents another line.
        self._show_external_info(base | {"multipv": 3, "pv": ["d2d4", "e5d4", "g1f3"]}, job)
        self.assertEqual(panel.lines[3]["pv"][0], "d2d4")
        self.assertIsNone(view.wheel_preview_ply)
        self.assertIsNone(view._hovered)
        self.assertIsNone(self.window.board_view.preview_board)
        self.assertNotIn(3, panel.pending)

    def test_small_mouse_motion_within_candidate_move_keeps_wheel_preview(self):
        self._three_pvs()
        view = self.window.candidates.rows[3][2]
        self._hover_word(view, "Nc3")
        nc3 = view.document().find("Nc3")
        nc3.setPosition(nc3.selectionStart() + 1)
        same_move_point = view.cursorRect(nc3).center()

        self._wheel(view.viewport(), -120)
        self.assertEqual(view.wheel_preview_ply, 2)
        preview_fen = self.window.board_view.display_board.fen()
        QTest.mouseMove(view.viewport(), same_move_point + QPoint(1, 0))
        self.app.processEvents()
        self.assertEqual(view.wheel_preview_ply, 2)
        self.assertEqual(view._hovered, 2)
        self.assertEqual(self.window.board_view.display_board.fen(), preview_fen)

        other_move = view.document().find("Nf6")
        other_move.setPosition(other_move.selectionStart() + 1)
        QTest.mouseMove(view.viewport(), view.cursorRect(other_move).center())
        self.app.processEvents()
        self.assertIsNone(view.wheel_preview_ply)
        self.assertEqual(view._hovered, 2)

    def test_cursor_preview_keeps_main_board_and_snapshot_click_with_wheel(self):
        base, job = self._three_pvs()
        window, panel = self.window, self.window.candidates
        self.assertFalse(window.cursor_preview_action.isChecked())
        window.cursor_preview_action.trigger()
        self.assertTrue(window.store.get("settings")["cursor_preview"])
        fen, node = window.game.board.fen(), window.game.current_node
        third = panel.rows[3][2]
        self._hover_word(third, "Nc3")
        popup = window.hover_preview
        expected = window.game.board.copy()
        expected.push(expected.parse_uci("b1c3"))
        self.assertTrue(popup.isVisible())
        self.assertEqual(popup.board.display_board.fen(), expected.fen())
        self.assertEqual(window.board_view.display_board.fen(), fen)
        self.assertIsNone(window.board_view.preview_board)
        self.assertEqual(window.game.current_node, node)
        self.assertTrue(popup.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self._wheel(third.viewport(), -120)
        expected.push(expected.parse_uci("g8f6"))
        self.assertEqual(popup.board.display_board.fen(), expected.fen())
        self.assertEqual(window.board_view.display_board.fen(), fen)
        # A continuation update to the same candidate stays queued while the
        # wheel preview is active, so clicks use the displayed PV snapshot.
        self._show_external_info(base | {"multipv": 3, "pv": ["b1c3", "g8f6", "d2d4"]}, job)
        self.assertEqual(panel.lines[3]["pv"][0], "b1c3")
        cursor = third.document().find("Nc3")
        cursor.setPosition(cursor.selectionStart() + 1)
        QTest.mouseClick(third.viewport(), Qt.MouseButton.LeftButton, pos=third.cursorRect(cursor).center())
        self.app.processEvents()
        self.assertEqual(window.game.sans, ["e4", "e5", "Nc3"])
        self.assertFalse(popup.isVisible())
        self.assertFalse(panel.pending)

    def test_cursor_preview_history_orientation_appearance_bounds_and_toggle(self):
        self._analysis_game()
        window = self.window
        window._set_cursor_preview(True)
        window._set_display("theme", "Slate")
        window._set_display("piece_set", "Original")
        window.board_view.flipped = True
        fen, node = window.game.board.fen(), window.game.current_node
        self._hover_word(window.analysis_history, "e4")
        popup = window.hover_preview
        self.assertTrue(popup.isVisible())
        self.assertEqual(popup.board.display_board.fen(), window.game.position_at_node(1).fen())
        self.assertEqual(popup.board.theme, "Slate")
        self.assertEqual(popup.board.piece_set, "Original")
        self.assertTrue(popup.board.flipped)
        self.assertEqual(window.board_view.display_board.fen(), fen)
        self.assertEqual(window.game.current_node, node)
        for point in (QPoint(8, 8), window.rect().bottomRight() - QPoint(8, 8)):
            global_point = window.mapToGlobal(point)
            popup.move_near(global_point)
            self.assertTrue(window.rect().contains(popup.geometry()))
            self.assertTrue(window.screen().availableGeometry().contains(
                popup.rect().translated(popup.mapToGlobal(QPoint()))))
            self.assertFalse(popup.geometry().contains(point))
        window.analysis_history.cancel_preview()
        self.assertFalse(popup.isVisible())
        window._preview_history(1)
        window.cursor_preview_action.trigger()
        self.assertFalse(popup.isVisible())
        self.assertFalse(window.store.get("settings")["cursor_preview"])
        window._preview_history(1)
        self.assertIsNotNone(window.board_view.preview_board)
        self.assertFalse(popup.isVisible())
        window._end_preview("history")
        self.assertIsNone(window.board_view.preview_board)

    def test_cursor_preview_clears_on_navigation_deactivation_and_hide(self):
        self._three_pvs()
        window = self.window
        window._set_cursor_preview(True)
        window._preview_candidate(3, 1)
        self.assertTrue(window.hover_preview.isVisible())
        window._navigate(1)
        self.assertFalse(window.hover_preview.isVisible())
        window._preview_history(2)
        self.assertTrue(window.hover_preview.isVisible())
        # A real activation change hides all reversible previews.
        window.hide()
        self.app.processEvents()
        self.assertFalse(window.hover_preview.isVisible())
        self.assertIsNone(window.board_view.preview_board)
        self.assertIsNone(window._preview_source)
        window.show()
        window._preview_history(2)
        QTest.mouseMove(window.analysis_history.viewport(), window.analysis_history.viewport().rect().bottomRight())
        self.app.processEvents()
        window._end_preview("history")
        self.assertFalse(window.hover_preview.isVisible())

    def test_text_colors_distinguish_sides_and_history_in_both_appearances(self):
        from nocturne.gui.theme import palette
        self._three_pvs()
        for light in (False, True):
            self.window.config["light"] = light
            self.window._apply_settings()
            view = self.window.candidates.rows[3][2]
            white = view.document().find("Nc3").charFormat().foreground().color()
            black = view.document().find("Nf6").charFormat().foreground().color()
            history = self.window.analysis_history.document().find("e4").charFormat().foreground().color()
            self.assertEqual(white, QColor(palette(light)["analysis_white"]))
            self.assertEqual(black, QColor(palette(light)["analysis_black"]))
            self.assertEqual(history, QColor(palette(light)["history"]))
            self.assertEqual(len({white.name(), black.name(), history.name()}), 3)
            view.candidate_turn = -1
            view.set_moves(view._items, light=light)
            self.assertEqual(view.document().find("Nc3").charFormat().foreground().color(), black)
            view.candidate_turn = 1

    def test_last_move_highlight_follows_each_board_palette(self):
        from nocturne.gui.theme import BOARD_THEMES
        self._analysis_game("1.e4 *")
        board = self.window.board_view
        for theme, (light, dark) in BOARD_THEMES.items():
            board.theme = theme
            self.app.processEvents()
            image = board.grab().toImage()
            point = board.square_rect(parse_square("e2")).topLeft().toPoint() + QPoint(8, 8)
            base = QColor(light)  # e2 is a light square, now empty.
            actual = image.pixelColor(point)
            expected = board.last_move_color(base)
            self.assertEqual(actual.name(), expected.name(), theme)
            self.assertAlmostEqual(abs(expected.valueF() - base.valueF()), 0.10, delta=0.005)
            for square_color in (light, dark):
                source = QColor(square_color)
                target = board.last_move_color(source)
                self.assertAlmostEqual(source.hsvSaturationF(), target.hsvSaturationF(), delta=0.005)
                self.assertEqual(source.hsvHue(), target.hsvHue())

    def test_compact_spacing_fits_eight_font_scaled_columns_and_tighter_history(self):
        from nocturne.gui.moves import MoveText
        analysis = MoveText(auto_fit=True, reserved_lines=3)
        history = MoveText()
        analysis.candidate_rank = 1
        items = [(text, i + 1) for i, text in enumerate(
            ("e4", "Qxe4", "O-O-O+", "Nf3", "Bxe5+", "Rae1", "d8=Q+", "Qh4xe1#"))]
        analysis.set_moves(items)
        # CSS font metrics differ with the native Windows offscreen DPI. Use a
        # fixed 82-character viewport budget rather than assuming 96 DPI. The
        # old 13-character slots need 104 characters for eight columns and fail.
        font = analysis.document().find("e4").charFormat().font()
        width = math.ceil(QFontMetricsF(font).horizontalAdvance("M" * 82)) + 8
        for view in (analysis, history):
            view.resize(width, 100)
            view.set_moves(items)
            view.show()
        self.app.processEvents()
        try:
            self.assertEqual(analysis.document().begin().layout().lineCount(), 1)
            first, last = (analysis.document().find(word) for word in ("e4", "Qh4xe1#"))
            self.assertEqual(analysis.cursorRect(first).y(), analysis.cursorRect(last).y())
            a_line = analysis.document().begin().layout().lineAt(0)
            h_line = history.document().begin().layout().lineAt(0)
            self.assertLess(h_line.naturalTextWidth(), a_line.naturalTextWidth())
            self.assertLess(h_line.height(), a_line.height())
            self.assertEqual(analysis._reserved_lines, 3)
        finally:
            for view in (analysis, history):
                view.close()
                view.deleteLater()

    def test_candidate_moves_have_natural_spacing_and_precise_hit_targets(self):
        self._three_pvs()
        view = self.window.candidates.rows[1][2]
        view.set_moves([("e4", 1), ("Qxe4", 2), ("O-O-O+", 3)])
        self.app.processEvents()
        starts = []
        for word in ("e4", "Qxe4", "O-O-O+"):
            cursor = view.document().find(word)
            cursor.setPosition(cursor.selectionStart())
            starts.append(view.cursorRect(cursor).x())
        self.assertLess(starts[1] - starts[0], starts[2] - starts[1])
        cursor = view.document().find("e4")
        cursor.setPosition(cursor.selectionEnd() - 1)
        point = view.cursorRect(cursor).center()
        hovered, clicked = [], []
        view.move_hovered.connect(hovered.append)
        view.move_clicked.connect(clicked.append)
        QTest.mouseMove(view.viewport(), view.viewport().rect().bottomRight())
        QTest.qWait(20)
        QTest.mouseMove(view.viewport(), point)
        QTest.qWait(20)
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(hovered, [1])
        self.assertEqual(clicked, [1])

    def test_engine_expand_controls_default_off_and_expand_full_lines(self):
        base, job = self._three_pvs()
        panel = self.window.candidates
        from nocturne.settings import normalize

        self.assertFalse(self.window.config["expand_pv"])
        self.assertFalse(normalize({"expand_pv": True})["expand_pv"])
        engine_actions = {action.text(): action for action in self.window.menus["Engine"].actions()}
        dev_actions = {action.text() for action in self.window.menus["Dev"].actions()}
        self.assertIn("Expand all analysis lines", engine_actions)
        self.assertIn("Preview moves on a small board near cursor", engine_actions)
        self.assertNotIn("Expand all analysis lines", dev_actions)
        self.assertNotIn("Preview moves on a small board near cursor", dev_actions)
        self.assertFalse(self.window.expand_pv_action.isChecked())

        long_pv = ["g1f3", "g8f6", "f3g1", "f6g8"] * 12
        self._show_external_info(base | {"multipv": 1, "pv": long_pv}, job)
        self.app.processEvents()
        moves = panel.rows[1][2]
        height_at_one_row = moves.height()
        self.assertEqual(moves._reserved_lines, 1)
        self.assertEqual(moves.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.assertGreater(moves.wrapped_line_count(), 1)

        self.window.expand_pv_action.trigger()
        self.app.processEvents()
        self.assertTrue(self.window.config["expand_pv"])
        self.assertTrue(self.window.store.get("settings", {})["expand_pv"])
        self.assertGreater(moves.height(), height_at_one_row)

        self.window.expand_pv_action.trigger()
        self.app.processEvents()
        self.assertFalse(self.window.config["expand_pv"])
        self.assertEqual(moves.height(), height_at_one_row)

        panel.set_multipv(5)
        panel.reserve_slots(4)
        self.app.processEvents()
        height_at_five_pvs = moves.height()
        self.assertEqual({row[2]._reserved_lines for row in panel.rows.values()}, {1})
        self.assertEqual(height_at_five_pvs, height_at_one_row)

        panel.set_multipv(4)
        self.app.processEvents()
        self.assertEqual({row[2]._reserved_lines for row in panel.rows.values()}, {1})
        self.assertEqual(moves.height(), height_at_one_row)

    def test_candidate_arrow_expands_only_its_pv_and_collapses_to_one_row(self):
        base, job = self._three_pvs()
        panel = self.window.candidates
        self.assertEqual({panel.rows[rank][2]._reserved_lines for rank in (1, 2, 3)}, {1})
        moves = panel.rows[1][2]
        long_pv = ["g1f3", "g8f6", "f3g1", "f6g8"] * 12
        self._show_external_info(base | {"multipv": 1, "pv": long_pv}, job)
        self.app.processEvents()
        fixed_height = moves.height()
        self.assertEqual([panel.rows[rank][2]._reserved_lines for rank in (1, 2, 3)],
                         [1, 1, 1])
        button = panel.expand_buttons[1]
        self.assertTrue(button.isVisible())
        self.assertEqual(button.toolTip(), "")
        self.assertEqual(button.arrowType(), Qt.ArrowType.DownArrow)
        fen, node = self.window.game.board.fen(), self.window.game.current_node

        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(panel.expanded_ranks, {1})
        self.assertEqual(moves._reserved_lines, 0)
        self.assertGreater(moves.height(), fixed_height)
        self.assertEqual(moves.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertEqual(panel.rows[2][2]._reserved_lines, 1)
        self.assertEqual(panel.rows[3][2]._reserved_lines, 1)
        self.assertEqual(button.arrowType(), Qt.ArrowType.UpArrow)
        last = moves.document().find("Ng8", moves.document().characterCount() - 1,
                                    QTextDocument.FindFlag.FindBackward)
        self.assertFalse(last.isNull())
        self.assertLess(moves.cursorRect(last).bottom(), moves.viewport().height())
        self.assertEqual(self.window.game.board.fen(), fen)
        self.assertEqual(self.window.game.current_node, node)

        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertFalse(panel.expanded_ranks)
        self.assertEqual(moves._reserved_lines, 1)
        self.assertEqual(moves.height(), fixed_height)

        # A changed suggested first move is a different candidate variation;
        # its row returns to the compact state rather than inheriting expansion.
        self._show_external_info(base | {"multipv": 1, "pv": ["d2d4", "e5d4"]}, job)
        self.app.processEvents()
        self.assertNotIn(1, panel.expanded_ranks)
        self.assertEqual(moves._reserved_lines, 1)
        self.assertFalse(button.isVisible())

    def test_candidate_default_rows_follow_selected_multipv_count(self):
        base, _ = self._three_pvs()
        panel = self.window.candidates
        self.assertEqual({row[2]._reserved_lines for row in panel.rows.values()}, {1})
        panel.set_multipv(4)
        self.assertEqual({row[2]._reserved_lines for row in panel.rows.values()}, {1})

    def test_compact_candidate_rows_stay_one_line_during_long_pv_updates(self):
        base, job = self._three_pvs()
        panel = self.window.candidates
        panel.set_multipv(4)
        self.app.processEvents()
        fixed_heights = {rank: panel.rows[rank][2].height() for rank in panel.rows}
        next_row_y = panel.rows[2][0].mapToGlobal(panel.rows[2][0].rect().topLeft()).y()
        long_pv = ["g1f3", "g8f6", "f3g1", "f6g8"] * 12

        # A changing, much longer engine line must scroll inside its reserved
        # single-row slot and leave every other candidate in the same place.
        self._show_external_info(base | {"multipv": 1, "pv": long_pv}, job)
        self.app.processEvents()
        moves = panel.rows[1][2]
        self.assertEqual(moves._reserved_lines, 1)
        self.assertEqual(moves.height(), fixed_heights[1])
        self.assertGreater(moves.wrapped_line_count(), 1)
        self.assertTrue(panel.expand_buttons[1].isVisible())
        self.assertEqual(
            panel.rows[2][0].mapToGlobal(panel.rows[2][0].rect().topLeft()).y(), next_row_y
        )

        shorter_pv = long_pv[:8]
        self._show_external_info(base | {"multipv": 1, "pv": shorter_pv}, job)
        self.app.processEvents()
        self.assertEqual(moves.height(), fixed_heights[1])
        self.assertEqual(
            panel.rows[2][0].mapToGlobal(panel.rows[2][0].rect().topLeft()).y(), next_row_y
        )
        panel.set_multipv(5)
        self.assertEqual({row[2]._reserved_lines for row in panel.rows.values()}, {1})
        panel.reserve_slots(5)
        self.assertEqual({row[2]._reserved_lines for row in panel.rows.values()}, {1})
        panel.set_multipv(4)
        self.assertEqual({row[2]._reserved_lines for row in panel.rows.values()}, {1})

    def test_five_colored_candidates_keep_slots_and_destination_execution(self):
        self._analysis_game("1.e4 e5 *")
        self.window.config["multipv"] = 5
        job = {"turn": 1, "multipv": 5}
        for rank, move in enumerate(["g1f3", "b1c3", "f1c4", "d2d3", "d2d4"], 1):
            self._show_external_info({"depth": 7, "seldepth": 9, "score": 35 - rank * 5,
                                      "nodes": 2000, "multipv": rank, "pv": [move]}, job)
        self.app.processEvents()
        panel = self.window.candidates
        self.assertEqual(len(panel.rows), 5)
        self.assertFalse(any(label.text() in {"1", "2", "3", "4", "5"}
                             for label in panel.findChildren(type(panel.rows[1][1]))))
        self.assertEqual(len({panel.rows[r][2].height() for r in range(1, 6)}), 1)
        self.assertEqual(panel.rows[1][1].styleSheet(), panel.rows[2][1].styleSheet())
        self.assertEqual(self.window.board_view.candidate_style, "lines")
        QTest.mouseClick(self.window.board_view, Qt.MouseButton.LeftButton,
                         pos=self.window.board_view.square_rect(parse_square("d4")).center().toPoint())
        self.assertEqual(self.window.game.sans[-1], "d4")

    def test_smart_destination_click_can_play_recorded_move_outside_multipv(self):
        window = self.window
        window.game = Game.from_pgn("1.e4 e5 2.d4 *")
        window.game.navigate(2)
        window.analysis_mode = True
        window.config["multipv"] = 2
        window._refresh()
        board = window.board_view
        board.set_recommendations([
            (window.game.board.parse_uci("g1f3"), 1, "+0.3"),
            (window.game.board.parse_uci("b1c3"), 2, "+0.2"),
        ])
        QTest.mouseClick(
            board, Qt.MouseButton.LeftButton,
            pos=board.square_rect(parse_square("d4")).center().toPoint(),
        )
        self.assertEqual(window.game.sans, ["e4", "e5", "d4"])

    def test_two_line_pv_slots_preserve_hover_and_apply_latest_update_after_leaving(self):
        base, job = self._three_pvs()
        panel = self.window.candidates
        self.assertEqual(list(panel.rows), [1, 2, 3, 4, 5])
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
        QTest.qWait(200)
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

    def test_saved_game_preview_click_wheel_and_blank_reset(self):
        from nocturne.gui.saved_game_preview import SavedGameMoves

        preview = SavedGameMoves()
        preview.setFixedSize(420, 130)
        preview.set_game(Game.from_pgn("1.d4 d5 2.c4 e6 *"))
        preview.show()
        self.app.processEvents()
        self.assertEqual(preview.selected_ply, 4)  # Open at the final position.

        cursor = QTextCursor(preview.document())
        block = preview.document().begin()
        d4_point = None
        while block.isValid():
            fragment = block.begin()
            while not fragment.atEnd():
                current = fragment.fragment()
                if current.charFormat().anchorHref() == "ply:1":
                    cursor.setPosition(current.position() + 2)
                    d4_point = preview.cursorRect(cursor).center()
                    break
                fragment += 1
            if d4_point is not None:
                break
            block = block.next()
        self.assertIsNotNone(d4_point)
        QTest.mouseClick(preview.viewport(), Qt.MouseButton.LeftButton, pos=d4_point)
        self.app.processEvents()
        self.assertEqual(preview.selected_ply, 1)

        self._wheel(preview.viewport(), -120)
        self.assertEqual(preview.selected_ply, 2)
        self._wheel(preview.viewport(), 120)
        self.assertEqual(preview.selected_ply, 1)
        QTest.mouseClick(preview.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(410, 120))
        self.app.processEvents()
        self.assertEqual(preview.selected_ply, 4)
        preview.close()

    def test_autosave_is_rate_limited_and_imported_pgn_is_saved_immediately(self):
        window = self.window
        self.assertEqual(window.autosave_timer.interval(), 60000)
        window._last_save_at = time.monotonic()
        with patch.object(window.store, "save") as save:
            window._save(defer=True)
            save.assert_not_called()
            window._save(force=True)
            save.assert_called_once_with(window.game)
        self.assertTrue(window._import_text("1.e4 c5 *"))
        pgn_path = window.store.pgn_path(window.game.id)
        self.assertTrue(pgn_path.is_file())
        self.assertEqual(Game.from_pgn(pgn_path.read_text(encoding="utf-8")).sans, ["e4", "c5"])

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
            ["File", "Tree", "Analysis", "Display", "Engine", "Database", "Play", "Dev"],
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
        # Windows delivers native pointer moves asynchronously and can coalesce
        # consecutive moves. Deliver the reset before entering the target link.
        QTest.qWait(15)
        QTest.mouseMove(view.viewport(), pos=view.cursorRect(cursor).center(), delay=15)
        QTest.qWait(15)
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

    def test_history_mouse_hover_is_display_only_and_blank_space_preserves(self):
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
        self.assertEqual(self.window.board_view.display_board.fen(), expected)
        self.app.sendEvent(view.viewport(), QEvent(QEvent.Type.Leave))
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
        QTest.qWait(200)
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

    def test_detected_gpu_selects_eight_gigabyte_hash_only_for_default_profiles(self):
        from nocturne.gui.hardware import has_discrete_gpu

        self.assertTrue(has_discrete_gpu("Intel UHD Graphics\nAMD Radeon RX 9070 XT"))
        self.assertTrue(has_discrete_gpu("NVIDIA GeForce"))
        self.assertFalse(has_discrete_gpu("Intel UHD Graphics\nMicrosoft Basic Display Adapter"))
        self.window._gpu_hardware_detected = True
        option = {"kind": "spin", "default": "16", "minimum": 1, "maximum": 65536}
        default_profile = {
            "id": "gpu-default", "path": "stockfish", "values": {"Hash": "16"},
            "options": {"Hash": option}, "options_detected": True,
        }
        custom_profile = {
            "id": "gpu-custom", "path": "stockfish", "values": {"Hash": "4096"},
            "options": {"Hash": option}, "options_detected": True,
        }
        self.window.profiles.extend((default_profile, custom_profile))
        with patch("nocturne.gui.hardware.hash_budget_mb", return_value=16384):
            self.window._maybe_apply_gpu_hash_default(default_profile)
            self.window._maybe_apply_gpu_hash_default(custom_profile)
        self.assertEqual(default_profile["values"]["Hash"], 8192)
        self.assertEqual(default_profile["gpu_hash_defaulted"], 8192)
        self.assertEqual(custom_profile["values"]["Hash"], "4096")

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
            self.assertEqual(self.window.tabs.currentIndex(), 1)
            self.assertFalse(self.window.raw_pgn_action.isChecked())
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

        icons = []

        def choose_knight():
            menu = QApplication.activePopupWidget()
            if isinstance(menu, QMenu):
                icons.extend(not action.icon().pixmap(48, 48).isNull() for action in menu.actions())
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
        self.assertEqual(icons, [True] * 4)

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
            searched_node = self.window.game.nodes[self.window.game._line_nodes[1]]
            self.assertEqual(searched_node.analysis["score_type"], "cp")
            # The score belongs to the position before the engine's reply;
            # do not leave it displayed as the new position's evaluation.
            self.assertIsNone(self.window._last_info)
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
                action = next(a for a in menu.actions() if a.text() == "Copy SAN (this line)")
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
        self.assertGreaterEqual(sum(self.window.main_splitter.sizes()),
                                        self.window.main_splitter.width() - 20, self._split_diagnostics())
        self.assertLessEqual(self.window.board_view.width(), self.window.board_view.height() + 2)
        self.assertTrue(self.window.quick_analysis_button.isVisible())
        self.assertGreater(self.window.engine_scroll.height(), 250)
        from PySide6.QtWidgets import QComboBox, QSpinBox, QToolButton
        for kind in (QComboBox, QSpinBox, QToolButton):
            controls = [control for control in self.window.tabs.widget(1).findChildren(kind)
                        if control not in self.window.candidates.expand_buttons.values()]
            expected = ([self.window.maia_controls.rating, self.window.maia_controls.range_min, self.window.maia_controls.range_max, self.window.maia_insights.blunder.move] if kind is QComboBox
                        else [self.window.maia_controls.move_limit] if kind is QSpinBox else [])
            self.assertEqual(controls, expected)
        self.assertTrue(self.window.maia_controls.move_limit.isHidden())
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
                self.assertGreaterEqual(sum(self.window.main_splitter.sizes()),
                                        self.window.main_splitter.width() - 20, self._split_diagnostics())
                self.assertLessEqual(self.window.board_view.width(), self.window.board_view.height() + 2)
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
