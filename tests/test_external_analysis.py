"""External-only analysis, persistent lifecycle, stale protection and study integration."""

from contextlib import contextmanager
from pathlib import Path
import os
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from nocturne.core.board import parse_square
from nocturne.core.game import Game
from nocturne.core.rules import Board
from nocturne.engine.uci_types import AnalysisLimits, parse_info, parse_option
from nocturne.gui.engine import EngineController
from nocturne.gui.uci_connection import UciConnection
from nocturne.gui.window import MainWindow

SIMULATOR = str(Path(__file__).parent / "fixtures" / "uci_simulator.py")


class UciDataTests(unittest.TestCase):
    def test_advertised_options_and_validation(self):
        option = parse_option(
            "option name Analysis Style type combo default Very Solid var Normal var Very Solid"
        )
        self.assertEqual(option.choices, ["Normal", "Very Solid"])
        self.assertEqual(option.default, "Very Solid")
        self.assertEqual(
            parse_option("option name Path type string default a min b var c").default, "a min b var c"
        )
        self.assertEqual(option.validate("Very Solid"), "Very Solid")
        with self.assertRaises(ValueError):
            option.validate("unknown")
        spin = parse_option("option name Hash type spin default 16 min 1 max 1024")
        self.assertEqual(spin.validate(768), "768")
        with self.assertRaises(ValueError):
            spin.validate(1025)
        with self.assertRaises(ValueError):
            spin.validate("16\nquit")

    def test_scores_bounds_and_real_wdl(self):
        info = parse_info(
            "info depth 30 seldepth 44 score mate -3 upperbound wdl 0 0 1000 multipv 2 nodes 10 pv e2e4"
        )
        self.assertEqual((info["score_type"], info["score_value"], info["bound"]), ("mate", -3, "upperbound"))
        self.assertEqual(info["wdl"], (0, 0, 1000))
        self.assertNotIn("wdl", parse_info("info score cp 18 pv e2e4"))
        self.assertIsNone(parse_info("info score cp broken pv e2e4"))


class QtIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @contextmanager
    def workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(Path(directory))
            try:
                yield window
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def wait_until(self, predicate, seconds=4):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(0.005)
        self.fail("Timed out waiting for asynchronous engine event")

    def profile(self):
        return {
            "id": "simulator",
            "path": sys.executable,
            "arguments": [SIMULATOR],
            "name": "Transport simulator",
            "values": {"Threads": 2, "Hash": 64},
            "options": {},
        }

    def test_persistent_multipv_stop_barrier_and_rapid_positions(self):
        controller = EngineController()
        self.addCleanup(controller.close)
        messages = []
        controller.message.connect(lambda g, k, p: messages.append((g, k, p)))
        game = Game()
        limits = AnalysisLimits(depth=4, seconds=1)
        generation = controller.start(
            game,
            limits,
            sys.executable,
            arguments=[SIMULATOR],
            multipv=3,
            infinite=True,
            options={"Threads": 4},
        )
        self.wait_until(lambda: len(controller.lines) == 3)
        pid = controller.connection.process.processId()
        self.assertEqual(controller.lines[1]["pv"][0], "e2e4")
        game.play(game.board.parse_uci("e2e4"))
        new = controller.start(game, limits, sys.executable, arguments=[SIMULATOR])
        self.wait_until(lambda: any(g == new and k == "result" for g, k, p in messages))
        self.assertEqual(controller.connection.process.processId(), pid)
        self.assertEqual(controller.connection.applied["Threads"], "1")
        self.assertGreater(new, generation)
        self.assertTrue(all("a1a8" not in p.get("pv", []) for g, k, p in messages if g == new))
        log = "\n".join(controller.connection.log)
        self.assertIn("> stop", log)
        self.assertIn("> isready", log)

    def test_handshake_timeout_and_crash_recovery(self):
        connection = UciConnection(timeout_ms=100)
        self.addCleanup(connection.close)
        errors = []
        connection.failed.connect(errors.append)
        connection.launch(sys.executable, [SIMULATOR, "hang"])
        self.wait_until(lambda: bool(errors))
        self.assertIn("did not respond", errors[-1])
        connection.timeout_ms = 2000
        found = []
        connection.discovered.connect(found.append)
        connection.launch(sys.executable, [SIMULATOR])
        self.wait_until(lambda: bool(found))
        self.assertIn("MultiPV", found[0]["options"])
        connection.request(3, "position fen " + Board().fen(), "go depth 2", {}, "study")
        self.wait_until(lambda: connection.phase == "idle")

    def test_resource_change_during_ready_barrier_applies_latest_options(self):
        connection = UciConnection()
        self.addCleanup(connection.close)
        connection.launch(sys.executable, [SIMULATOR])
        self.wait_until(lambda: connection.phase == "idle")
        position = "position fen " + Board().fen()
        connection.request(1, position, "go infinite", {"Threads": 2, "Hash": 64}, "study")
        self.assertEqual(connection.phase, "ready")
        # No event processing: readyok is still outstanding for the old settings.
        connection.request(2, position, "go infinite", {"Threads": 6, "Hash": 768}, "study")
        self.wait_until(lambda: connection.phase == "search")
        self.assertEqual(connection.running[0], 2)
        self.assertEqual(connection.confirmed["Threads"], "6")
        self.assertEqual(connection.confirmed["Hash"], "768")
        log = list(connection.log)
        self.assertEqual(log.count("> go infinite"), 1)
        self.assertLess(log.index("> setoption name Hash value 768"), log.index("> go infinite"))

    def test_resource_menu_changes_reuse_process_and_persist_per_profile(self):
        from unittest.mock import patch
        from nocturne.storage import Store

        with self.workspace() as window:
            window.timer.stop()
            window.autosave_timer.stop()
            window.profiles = [self.profile()]
            window.config.update(engine_id="simulator")
            window._apply_settings()
            window._schedule_engine()
            self.wait_until(lambda: bool(window.candidates.lines))
            pid = window.engine.connection.process.processId()
            resources = window.resource_controls
            self.assertEqual(resources.state.text(), "Applied to engine")
            window.show()
            resources.menus["Threads"].popup(window.mapToGlobal(window.rect().center()))
            self.app.processEvents()
            action = next(a for a in resources.menus["Threads"].actions() if a.data() == 6)
            QTest.mouseClick(
                resources.menus["Threads"], Qt.MouseButton.LeftButton,
                pos=resources.menus["Threads"].actionGeometry(action).center(),
            )
            self.wait_until(lambda: window.engine.connection.confirmed.get("Threads") == "6")
            with patch("PySide6.QtWidgets.QInputDialog.getInt", return_value=(768, True)):
                resources._custom(window._profile(), "Hash")
            self.wait_until(lambda: window.engine.connection.confirmed.get("Hash") == "768")
            self.wait_until(lambda: window._last_info is not None)
            self.assertEqual(window.engine.connection.process.processId(), pid)
            self.assertEqual(window.profiles[0]["values"], {"Threads": 6, "Hash": 768})
            self.assertIn("768 MB", resources.buttons["Hash"].text())
            self.assertTrue(next(a for a in resources.menus["Hash"].actions() if a.data() == 768).isChecked())
            self.assertTrue(all("a1a8" not in info["pv"] for info in window.candidates.lines.values()))
            saved = Store(window.store.path)
            try:
                self.assertEqual(saved.get("engine_profiles")[0]["values"]["Hash"], 768)
            finally:
                saved.close()
            second = dict(self.profile(), id="second", values={}, options=window.profiles[0]["options"])
            window.profiles.append(second)
            window._apply_settings()
            window.analysis_source.setCurrentIndex(1)
            record = window.game.nodes[window.game.current_node].analysis
            self.assertEqual(record["profile"], "simulator")
            self.assertEqual(record["options"], {"Threads": 6, "Hash": 768})
            self.assertEqual(record["applied_options"]["Threads"], "6")
            self.assertEqual(record["applied_options"]["Hash"], "768")
            self.wait_until(lambda: window.engine.connection.confirmed.get("Hash") == "16")
            self.assertEqual(window.engine.connection.confirmed["Threads"], "1")
            self.assertEqual(window.engine.connection.process.processId(), pid)
            self.assertEqual(window.profiles[0]["values"]["Hash"], 768)
            window.analysis_source.setCurrentIndex(0)
            self.wait_until(lambda: window.engine.connection.confirmed.get("Hash") == "768")
            default = next(a for a in resources.menus["Hash"].actions() if a.text().startswith("Engine default"))
            default.trigger()
            self.wait_until(lambda: window.engine.connection.confirmed.get("Hash") == "16")
            self.assertNotIn("Hash", window._profile()["values"])
            window._halt_analysis()
            window._set_engine_resource("Threads", 4)
            self.app.processEvents()
            self.assertFalse(window.engine.busy)
            self.assertIn("next search", resources.state.text())
            window._start_analysis()
            self.wait_until(lambda: window.engine.connection.confirmed.get("Threads") == "4")

    def test_resource_limits_reject_invalid_settings_without_stopping_analysis(self):
        from unittest.mock import patch

        with self.workspace() as window:
            window.timer.stop()
            window.profiles = [self.profile()]
            window.config["engine_id"] = "simulator"
            window._apply_settings()
            window._schedule_engine()
            self.wait_until(lambda: bool(window.candidates.lines))
            generation = window.engine.generation
            with (
                patch("nocturne.gui.engine_resources.hash_budget_mb", return_value=512),
                patch.object(window, "_error") as error,
            ):
                window._set_engine_resource("Hash", 768)
                window._set_engine_resource("Threads", 17)
                self.assertEqual(error.call_count, 2)
                self.assertEqual(window.engine.generation, generation)
                self.assertEqual(window._profile()["values"], {"Threads": 2, "Hash": 64})
                window.resource_controls.refresh()
                action = next(a for a in window.resource_controls.menus["Hash"].actions() if a.data() == 1024)
                self.assertFalse(action.isEnabled())
            window._halt_analysis()
            window._profile()["options"].pop("Threads")
            window.resource_controls.refresh()
            self.assertIn("Not advertised", window.resource_controls.menus["Threads"].actions()[0].text())
            with patch.object(window, "_error") as error:
                window._set_engine_resource("Threads", 4)
                error.assert_called_once()
            self.assertEqual(window._profile()["values"]["Threads"], 2)

    def test_engine_crash_reports_error_and_can_restart(self):
        controller = EngineController()
        self.addCleanup(controller.close)
        messages = []
        controller.message.connect(lambda g, k, p: messages.append((g, k, p)))
        controller.start(Game(), AnalysisLimits(), sys.executable, arguments=[SIMULATOR, "crash"])
        self.wait_until(lambda: any(k == "error" for g, k, p in messages))
        generation = controller.start(Game(), AnalysisLimits(), sys.executable, arguments=[SIMULATOR])
        self.wait_until(lambda: any(g == generation and k == "result" for g, k, p in messages))
        self.assertFalse(controller.busy)

    def test_window_smart_move_candidates_hover_and_disabled_guard(self):
        with self.workspace() as window:
            window.timer.stop()
            window.autosave_timer.stop()
            window.profiles = [self.profile()]
            window.config.update(
                mode="analysis",
                engine_id="simulator",
                analysis_kind="explore",
                smart_move=True,
                smart_all=True,
            )
            window.analysis_mode = True
            window._analysis_enabled = True
            window._apply_settings()
            window.analysis_kind.setCurrentIndex(1)
            window.show()
            window._refresh()
            window._schedule_engine()
            self.wait_until(lambda: len(window.candidates.lines) >= 3)
            fen = window.game.board.fen()
            window._preview_candidate(2, 1)
            self.assertEqual(window.game.board.fen(), fen)
            self.assertIsNotNone(window.board_view.preview_board)
            window._end_preview("candidate")
            target = window.board_view.square_rect(parse_square("d4")).center().toPoint()
            QTest.mouseClick(window.board_view, Qt.MouseButton.LeftButton, pos=target)
            self.assertEqual(window.game.sans, ["d4"])
            window._stop_engine()
            window.config["smart_move"] = False
            window._apply_settings()
            window.board_view.set_recommendations([(window.game.board.parse_uci("d7d5"), 1, "+0.1")])
            QTest.mouseClick(
                window.board_view,
                Qt.MouseButton.LeftButton,
                pos=window.board_view.square_rect(parse_square("d5")).center().toPoint(),
            )
            self.assertEqual(window.game.cursor, 1)

    def test_focus_replaces_candidate_context_instead_of_mixing_old_rows(self):
        with self.workspace() as window:
            window.timer.stop()
            window.autosave_timer.stop()
            window.profiles = [self.profile()]
            window.config.update(engine_id="simulator", analysis_kind="explore")
            window._apply_settings()
            window.analysis_kind.setCurrentIndex(1)
            window.analysis_mode = True
            window._analysis_enabled = True
            window._refresh()
            window._schedule_engine()
            self.wait_until(lambda: len(window.candidates.lines) == 3)
            target = window.candidates.lines[2]["pv"][0]
            window._candidate_action(2, "focus")
            self.assertFalse(window.candidates.lines)
            self.wait_until(lambda: bool(window.candidates.lines))
            self.assertEqual(list(window.candidates.lines), [1])
            self.assertEqual(window.candidates.lines[1]["pv"][0], target)
            self.assertIn("Targeted analysis", window.tradeoff_label.text())
            window._stop_engine()
            window.game = Game.from_pgn("1.Nf3 Nf6 2.g3 g6 *")
            original = window._position_identity()
            window.game.navigate(0)
            for text in ("g2g3", "g7g6", "g1f3", "g8f6"):
                window.game.play(window.game.board.parse_uci(text))
            self.assertEqual(original[2], window.game.board.key)
            self.assertNotEqual(original, window._position_identity())
            window._candidate_identity = original
            cursor = window.game.cursor
            window._execute_rank(1)
            self.assertEqual(window.game.cursor, cursor)

    def test_selected_piece_priority_and_stale_recommendation(self):
        from nocturne.gui.board import BoardWidget

        widget = BoardWidget()
        self.addCleanup(widget.close)
        widget.resize(700, 700)
        widget.show()
        game = Game()
        widget.set_position(game.board)
        widget.smart_move = True
        widget.smart_all = True
        widget.set_recommendations([(game.board.parse_uci("g1f3"), 1, "+0.2")])
        moves = []
        widget.move_requested.connect(moves.append)
        QTest.mouseClick(
            widget, Qt.MouseButton.LeftButton, pos=widget.square_rect(parse_square("b1")).center().toPoint()
        )
        QTest.mouseClick(
            widget, Qt.MouseButton.LeftButton, pos=widget.square_rect(parse_square("f3")).center().toPoint()
        )
        self.assertFalse(moves)
        widget.selected = None
        game.board.play_uci("e2e4")
        QTest.mouseClick(
            widget, Qt.MouseButton.LeftButton, pos=widget.square_rect(parse_square("f3")).center().toPoint()
        )
        self.assertFalse(moves)

    def test_annotated_pgn_and_chess960_roundtrip(self):
        text = "1.e4! {A useful note [%eval 0.35,12]} (1.d4 $5 {Alternative} d5) e5 *"
        game = Game.from_pgn(text)
        game.headers["Event"] = 'Quoted "study" with \\ paths'
        result = game.pgn()
        self.assertEqual(Game.from_pgn(result).headers["Event"], game.headers["Event"])
        restored = Game.from_dict(game.to_dict())
        self.assertIn("A useful note", result)
        self.assertIn("$1", result)
        self.assertIn("Alternative", restored.pgn())
        self.assertEqual(game.evaluations[1], 35)
        board = Board("4k3/8/8/8/8/8/8/RK1R4 w DA - 0 1")
        legal = list(board.legal_moves())
        castles = [
            m
            for m in legal
            if board.native.is_castling(__import__("nocturne.core.rules", fromlist=["native"]).native(m))
        ]
        self.assertTrue(castles)
        for move in castles:
            copy = board.copy()
            copy.push(move)
            self.assertTrue(copy.native.is_valid())
        g = Game(board.fen())
        self.assertTrue(Game.from_dict(g.to_dict()).board.chess960)

    def test_game_review_targeted_moves_and_evaluation_export(self):
        from unittest.mock import patch

        with self.workspace() as window:
            window.timer.stop()
            window.autosave_timer.stop()
            window.profiles = [self.profile()]
            window.config.update(engine_id="simulator", analysis_kind="bounded")
            window._apply_settings()
            window.game = Game.from_pgn("1.e3 e5 2.Nf3 *")
            window.analysis_mode = True
            window._refresh()
            original_fen = window.game.board.fen()
            with patch("PySide6.QtWidgets.QInputDialog.getDouble", return_value=(0.1, True)):
                window._analyze_game()
            self.wait_until(lambda: window._review is None, 8)
            self.assertEqual(window.game.board.fen(), original_fen)
            self.assertGreaterEqual(len(window.game.metadata.get("review", {})), 3)
            self.assertIn("searchmoves e2e3", "\n".join(window.engine.connection.log))
            exported = window.game.pgn()
            self.assertIn("[%eval", exported)
            restored = Game.from_pgn(exported)
            self.assertEqual(len(restored.evaluations), len(window.game.evaluations))

    def test_multiple_games_open_in_tabs_and_preserve_annotations(self):
        with self.workspace() as window:
            window._analysis_enabled = False
            text = '[Event "First"]\n\n1.e4 {note} *\n\n[Event "Second"]\n\n1.d4 d5 *'
            self.assertTrue(window._import_text(text))
            self.assertGreaterEqual(window.study_tabs.count(), 3)
            first = window.game.id
            index = next(
                i for i in range(window.study_tabs.count()) if window.study_tabs.tabText(i) == "Second"
            )
            window._switch_study(index)
            self.assertNotEqual(first, window.game.id)
            self.assertEqual(window.game.sans, ["d4", "d5"])
            self.assertIn("note", window._study_games[first].pgn())

    def test_smart_ambiguous_destination_asks_and_promotion_offers_choice(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QMenu
        from nocturne.gui.board import BoardWidget

        widget = BoardWidget()
        self.addCleanup(widget.close)
        widget.resize(650, 650)
        widget.show()
        widget.set_position(Board("4k3/8/8/8/8/8/3N3N/4K3 w - - 0 1"))
        widget.smart_move = True
        widget.smart_all = True
        widget.set_recommendations(
            [(widget.board.parse_uci("d2f3"), 1, "+0.1"), (widget.board.parse_uci("h2f3"), 2, "0.0")]
        )
        moves = []
        widget.move_requested.connect(moves.append)

        def choose_last():
            menu = QApplication.activePopupWidget()
            if isinstance(menu, QMenu):
                QTest.mouseClick(
                    menu, Qt.MouseButton.LeftButton, pos=menu.actionGeometry(menu.actions()[-1]).center()
                )

        def dismiss():
            menu = QApplication.activePopupWidget()
            if menu:
                menu.close()

        QTimer.singleShot(20, choose_last)
        QTimer.singleShot(500, dismiss)
        QTest.mouseClick(
            widget, Qt.MouseButton.LeftButton, pos=widget.square_rect(parse_square("f3")).center().toPoint()
        )
        self.assertEqual(moves[-1].uci(), "h2f3")
        count = len(moves)

        def change_position_then_choose():
            updated = widget.board.copy()
            updated.play_uci("e1f1")
            updated.play_uci("e8f8")
            widget.set_position(updated)
            choose_last()

        QTimer.singleShot(20, change_position_then_choose)
        QTimer.singleShot(500, dismiss)
        QTest.mouseClick(
            widget, Qt.MouseButton.LeftButton, pos=widget.square_rect(parse_square("f3")).center().toPoint()
        )
        self.assertEqual(len(moves), count)
        widget.set_position(Board("4k3/8/8/8/8/8/8/R4K1R w HA - 0 1"))
        widget.selected = parse_square("f1")
        QTimer.singleShot(20, choose_last)
        QTimer.singleShot(500, dismiss)
        QTest.mouseClick(
            widget, Qt.MouseButton.LeftButton, pos=widget.square_rect(parse_square("g1")).center().toPoint()
        )
        self.assertIn(moves[-1].uci(), ("f1g1", "f1h1"))
        self.assertEqual(len(moves), count + 1)
        widget.set_position(Board("4k3/P7/8/8/8/8/8/4K3 w - - 0 1"))
        widget.set_recommendations([(widget.board.parse_uci("a7a8q"), 1, "#1")])
        QTimer.singleShot(20, choose_last)
        QTimer.singleShot(500, dismiss)
        QTest.mouseClick(
            widget, Qt.MouseButton.LeftButton, pos=widget.square_rect(parse_square("a8")).center().toPoint()
        )
        self.assertEqual(moves[-1].uci(), "a7a8n")

    def test_paused_review_preserves_completed_results_and_resumes(self):
        from unittest.mock import patch

        with self.workspace() as window:
            window.timer.stop()
            window.autosave_timer.stop()
            window.profiles = [self.profile()]
            window.config.update(engine_id="simulator")
            window._apply_settings()
            window.game = Game.from_pgn("1.e3 e5 2.Nf3 Nc6 3.Bc4 *")
            window._refresh()
            with patch("PySide6.QtWidgets.QInputDialog.getDouble", return_value=(0.1, True)):
                window._analyze_game()
            self.wait_until(lambda: window._review and window._review["index"] >= 1)
            window._navigate(0)
            self.assertIsNotNone(window._review)
            window._pause_review()
            self.assertTrue(window._review["paused"])
            self.assertFalse(window.engine.busy)
            self.assertIn("[%eval", window.game.pgn())
            completed = dict(window.game.metadata["review"])
            window._pause_review()
            self.wait_until(lambda: window._review is None, 10)
            self.assertTrue(all(k in window.game.metadata["review"] for k in completed))
