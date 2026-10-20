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

    def test_node_only_and_infinite_commands_ignore_other_caps(self):
        controller = EngineController()
        self.addCleanup(controller.close)
        limits = AnalysisLimits(depth=1, seconds=0.001, nodes=123)
        controller.start(Game(), limits, sys.executable, arguments=[SIMULATOR], nodes_only=True)
        self.wait_until(lambda: "> go nodes 123" in controller.connection.log)
        self.wait_until(lambda: not controller.busy)
        controller.start(Game(), limits, sys.executable, arguments=[SIMULATOR], infinite=True)
        self.wait_until(lambda: "> go infinite" in controller.connection.log)
        self.assertNotIn("> go infinite nodes 123", controller.connection.log)

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
            self.assertEqual(resources.summary, "Applied to engine")
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
            self.assertIn("768 MB", resources.menus["Hash"].title())
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
            window._select_profile("second")
            record = window.game.nodes[window.game.current_node].analysis
            self.assertEqual(record["profile"], "simulator")
            self.assertEqual(record["options"], {"Threads": 6, "Hash": 768, "UCI_ShowWDL": True})
            self.assertEqual(record["applied_options"]["Threads"], "6")
            self.assertEqual(record["applied_options"]["Hash"], "768")
            self.wait_until(lambda: window.engine.connection.confirmed.get("Hash") == "16")
            self.assertEqual(window.engine.connection.confirmed["Threads"], "1")
            self.assertEqual(window.engine.connection.process.processId(), pid)
            self.assertEqual(window.profiles[0]["values"]["Hash"], 768)
            window._select_profile("simulator")
            self.wait_until(lambda: window.engine.connection.confirmed.get("Hash") == "768")
            default = next(a for a in resources.menus["Hash"].actions() if a.text().startswith("Engine default"))
            default.trigger()
            self.wait_until(lambda: window.engine.connection.confirmed.get("Hash") == "16")
            self.assertNotIn("Hash", window._profile()["values"])
            window._halt_analysis()
            window._set_engine_resource("Threads", 4)
            self.app.processEvents()
            self.assertFalse(window.engine.busy)
            self.assertIn("next search", resources.summary)
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

    def test_fourteen_threads_and_gb_labels_send_exact_uci_mb(self):
        with self.workspace() as window:
            window.timer.stop()
            window.profiles = [self.profile()]
            window.config["engine_id"] = "simulator"
            window._apply_settings()
            window._schedule_engine()
            self.wait_until(lambda: bool(window.candidates.lines))
            resources = window.resource_controls
            threads = next(a for a in resources.menus["Threads"].actions() if a.data() == 14)
            threads.trigger()
            self.wait_until(lambda: window.engine.connection.confirmed.get("Threads") == "14")
            hash_action = next(a for a in resources.menus["Hash"].actions() if a.data() == 2048)
            self.assertEqual(hash_action.text(), "2 GB")
            hash_action.trigger()
            self.wait_until(lambda: window.engine.connection.confirmed.get("Hash") == "2048")
            self.assertEqual(resources.menus["Hash"].title(), "Hash (2 GB)")
            log = "\n".join(window.engine.connection.log)
            self.assertIn("> setoption name Threads value 14", log)
            self.assertIn("> setoption name Hash value 2048", log)
            self.assertNotIn("setoption name Hash value 2 GB", log)

    def test_multipv_menu_controls_live_and_bounded_search_without_explore_mode(self):
        with self.workspace() as window:
            window.timer.stop()
            window.profiles = [self.profile()]
            window.config.update(engine_id="simulator", analysis_kind="infinite", multipv=1, analysis_nodes=500)
            window._apply_settings()
            window._schedule_engine()
            self.wait_until(lambda: bool(window.candidates.lines))
            window._refresh_engine_menus()
            window.show()
            pid = window.engine.connection.process.processId()
            menu = window.multipv_menu
            menu.popup(window.mapToGlobal(window.rect().center()))
            self.app.processEvents()
            choice = next(a for a in menu.actions() if a.data() == 3)
            QTest.mouseClick(menu, Qt.MouseButton.LeftButton, pos=menu.actionGeometry(choice).center())
            self.wait_until(lambda: len(window.candidates.lines) == 3)
            self.assertEqual(len(window.board_view.recommendations), 3)
            self.assertEqual(window.config["analysis_kind"], "infinite")
            self.assertEqual(window.engine.connection.confirmed["MultiPV"], "3")
            self.assertNotIn("nodes", window.engine.connection.running[2])
            window._candidate_action(2, "focus")
            self.wait_until(lambda: len(window.candidates.lines) == 1)
            self.assertTrue(window.config.get("searchmoves"))
            window._set_multipv(3)
            self.wait_until(lambda: len(window.candidates.lines) == 3)
            self.assertFalse(window.config.get("searchmoves"))
            window.config.update(analysis_seconds=0.1, analysis_depth=4)
            window._set_analysis_limit("bounded")
            self.wait_until(lambda: not window.engine.busy and len(window.candidates.lines) == 3)
            self.assertEqual(window.engine.connection.process.processId(), pid)
            self.assertIn("> go depth 4 movetime 100 nodes 500", "\n".join(window.engine.connection.log))
            from unittest.mock import patch
            with patch("PySide6.QtWidgets.QInputDialog.getInt", return_value=(5, True)) as chooser:
                next(a for a in window.multipv_menu.actions() if a.text() == "Custom…").trigger()
                self.assertEqual(chooser.call_args.args[-1], 5)
            self.wait_until(lambda: not window.engine.busy and len(window.candidates.lines) == 5)
            self.assertEqual(len(window.board_view.recommendations), 5)
            window._halt_analysis()
            window._set_multipv(2)
            self.assertFalse(window.board_view.recommendations)
            self.assertIsNone(window.board_view.best_move)
            self.assertFalse(window.engine.busy)
            self.assertEqual(window.config["multipv"], 2)
            self.assertEqual(window.store.get("settings")["multipv"], 2)

    def test_multipv_discovery_clamps_and_unsupported_engine_stays_single_pv(self):
        from unittest.mock import patch

        with self.workspace() as window:
            window.timer.stop()
            window.profiles = [self.profile()]
            window.config.update(engine_id="simulator", multipv=32)
            window._apply_settings()
            window._schedule_engine()
            self.wait_until(lambda: len(window.candidates.lines) == 5)
            self.assertEqual(window.config["multipv"], 5)
            self.assertEqual(window.engine.connection.confirmed["MultiPV"], "5")
            window._halt_analysis()
            window.engine.close()
            window._profile()["arguments"] = [SIMULATOR, "single-pv"]
            window._profile()["options"] = {}
            window._profile()["options_detected"] = False
            window.config["multipv"] = 4
            window._start_analysis()
            self.wait_until(lambda: bool(window.candidates.lines))
            self.assertEqual(window.config["multipv"], 1)
            self.assertEqual(list(window.candidates.lines), [1])
            window._refresh_engine_menus()
            self.assertFalse(window.multipv_menu.actions()[0].isEnabled())
            with patch.object(window, "_error") as error:
                window._set_multipv(3)
                error.assert_called_once()
            self.assertEqual(window.config["multipv"], 1)

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
                multipv=3,
                smart_move=True,
            )
            window.analysis_mode = True
            window._analysis_enabled = True
            window._apply_settings()
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

    def test_backspace_during_live_analysis_restarts_on_surviving_sibling(self):
        with self.workspace() as window:
            window.timer.stop()
            window.autosave_timer.stop()
            window.profiles = [self.profile()]
            window.config.update(mode="analysis", engine_id="simulator", analysis_kind="explore", multipv=3)
            window.analysis_mode = window._analysis_enabled = True
            window.game = Game.from_pgn("1.e4 e5 (1...Nf6) 2.Nf3 *")
            window.game.navigate(2)
            window._apply_settings()
            window.show()
            window._refresh()
            window._schedule_engine()
            self.wait_until(lambda: bool(window.board_view.recommendations))
            old_generation = window._job["generation"]
            window.board_view.setFocus()
            QTest.keyClick(window.board_view, Qt.Key.Key_Backspace)
            self.assertEqual(window.game.sans, ["e4", "Nf6"])
            self.wait_until(lambda: window._job is not None and window._job["generation"] > old_generation
                            and bool(window.board_view.recommendations))
            self.assertEqual(window._job["identity"], window._position_identity())
            self.assertEqual(window.board_view.recommendation_fen, window.game.board.fen())
            self.assertTrue(all(m in list(window.game.board.legal_moves())
                                for m, _, _ in window.board_view.recommendations))
            saved = window.game.to_dict()
            window._engine_message(old_generation, "info", {"score": 9999, "pv": ["a1a8"]})
            self.assertEqual(window.game.to_dict(), saved)
            window._halt_analysis()
            QTest.keyClick(window.board_view, Qt.Key.Key_Backspace)
            self.assertEqual(window.game.sans, ["e4"])
            self.assertFalse(window._analysis_enabled)
            self.assertIsNone(window._job)

    def test_focus_replaces_candidate_context_instead_of_mixing_old_rows(self):
        with self.workspace() as window:
            window.timer.stop()
            window.autosave_timer.stop()
            window.profiles = [self.profile()]
            window.config.update(engine_id="simulator", analysis_kind="explore", multipv=3)
            window._apply_settings()
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
            self.assertIn("Targeted analysis", window.analysis_scope)
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

    def test_auto_evaluate_line_uses_multipv_node_caps_and_saves_lines(self):
        with self.workspace() as window:
            window.timer.stop()
            window.autosave_timer.stop()
            profile = self.profile()
            profile["options"] = {"MultiPV": {"maximum": 8}}
            window.profiles = [profile]
            window.config.update(
                engine_id="simulator", multipv=3, auto_eval_nodes=100, analysis_kind="infinite"
            )
            window._apply_settings()
            window.game = Game.from_pgn("1.e3 e5 *")
            window._refresh()
            window.game.navigate(0)
            window._auto_evaluate_line()
            self.wait_until(lambda: window._review is None, 8)
            self.assertIn("> go nodes 100", window.engine.connection.log)
            self.assertEqual(len(window.game.nodes[0].analysis["multipv_lines"]), 3)

            self.assertEqual(len(window.game.nodes[1].analysis["multipv_lines"]), 3)
            saved = window.store.load(window.game.id)
            generation = window.engine.generation
            window.game = saved
            window._navigate(1)
            self.assertEqual(len(window.candidates.lines), 3)
            self.assertEqual(window.eval_label.text(), "-0.35")
            window._navigate(0)
            self.assertEqual(len(window.candidates.lines), 3)
            self.assertEqual(window.eval_label.text(), "+0.35")
            self.assertFalse(window.engine.busy)
            self.assertGreaterEqual(window.engine.generation, generation)
            self.assertEqual(len(window.game.nodes[0].analysis["multipv_lines"]), 3)

    def test_auto_evaluation_keeps_latest_bound_when_node_cap_interrupts_iteration(self):
        with self.workspace() as window:
            window.timer.stop()
            profile = self.profile()
            profile["arguments"] = [SIMULATOR, "bound-at-limit"]
            profile["options"] = {"MultiPV": {"maximum": 8}}
            window.profiles = [profile]
            window.config.update(engine_id="simulator", multipv=3, auto_eval_nodes=400)
            window.game = Game.from_pgn("1.e4 e5 *")
            window.game.navigate(0)
            window._auto_evaluate_line()
            self.wait_until(lambda: window._review is None, 8)
            for node in window.game.nodes:
                self.assertEqual(node.analysis["bound"], "upperbound")
                self.assertEqual(node.analysis["depth"], 4)
                self.assertEqual(len(node.analysis["multipv_lines"]), 3)
            self.assertNotIn("[%eval", window.game.pgn())

    def test_auto_evaluation_keeps_individual_depths_in_partial_multipv_iteration(self):
        with self.workspace() as window:
            window.timer.stop()
            profile = self.profile()
            profile["arguments"] = [SIMULATOR, "partial-pvs"]
            profile["options"] = {"MultiPV": {"maximum": 8}}
            window.profiles = [profile]
            window.config.update(engine_id="simulator", multipv=5, auto_eval_nodes=400)
            window.game = Game.from_pgn("1.e4 *")
            window.game.navigate(0)
            window._auto_evaluate_line()
            self.wait_until(lambda: window._review is None, 8)
            for node in window.game.nodes:
                self.assertEqual([info["depth"] for info in node.analysis["multipv_lines"]], [3, 3, 4, 4, 4])
            restored = Game.from_dict(window.game.to_dict())
            self.assertEqual(restored.nodes[0].analysis["multipv_lines"], window.game.nodes[0].analysis["multipv_lines"])

    def test_deeper_confirmation_can_replace_an_initial_blunder_label(self):
        from nocturne.review import rows

        with self.workspace() as window:
            window.timer.stop()
            profile = self.profile()
            profile["arguments"] = [SIMULATOR, "review-confirm"]
            window.profiles = [profile]
            window.config.update(engine_id="simulator", review_confirm=True)
            window.game = Game.from_pgn("1.e3 *")
            window._begin_review(0.05)
            self.wait_until(lambda: window._review is None, 8)
            record = rows(window.game)[0]["record"]
            self.assertEqual(record["label"], "Excellent")
            self.assertEqual(record["context"]["confirmation"]["initial_label"], "Blunder")
            self.assertEqual(record["context"]["nodes"], 10_000_000)
            self.assertIsNone(record["context"]["seconds"])

    def test_normal_node_menu_switches_from_continuous_and_unlimited_really_is_unlimited(self):
        with self.workspace() as window:
            window.timer.stop()
            window.profiles = [self.profile()]
            window.config.update(engine_id="simulator", analysis_kind="infinite")
            window._apply_settings()
            window._set_node_limit("analysis_nodes", 100)
            self.wait_until(lambda: bool(window.engine.connection.log) and
                            "> go nodes 100" in window.engine.connection.log)
            self.wait_until(lambda: not window.engine.busy)
            self.assertEqual(window.game.cursor, 0)
            window._set_node_limit("analysis_nodes", 0)
            self.wait_until(lambda: "> go infinite" in window.engine.connection.log)
            self.assertTrue(window.engine.busy)
            window._halt_analysis()
            window._set_node_limit("analysis_nodes", 200_000_000)
            self.assertFalse(window.engine.busy)
            self.assertEqual(window.config["auto_eval_nodes"], 200_000_000)
            self.assertEqual(window.config["auto_play_nodes"], 10_000_000)

    def test_live_multipv_cache_restores_after_navigation_without_reanalysis(self):
        with self.workspace() as window:
            window.timer.stop()
            profile = self.profile()
            profile["options"] = {"MultiPV": {"maximum": 8}}
            window.profiles = [profile]
            window.config.update(engine_id="simulator", multipv=3, analysis_nodes=100)
            window.game = Game.from_pgn("1.e4 e5 *")
            window.game.navigate(0)
            window._apply_settings()
            window._schedule_engine()
            self.wait_until(lambda: not window.engine.busy and len(window.candidates.lines) == 3)
            window._halt_analysis()
            window._navigate(1)
            self.assertFalse(window.candidates.lines)
            window._navigate(0)
            self.assertEqual(len(window.candidates.lines), 3)
            self.assertEqual(len(window.board_view.recommendations), 3)
            timestamp = window.game.nodes[0].analysis["timestamp"]
            window._refresh()
            self.assertEqual(len(window.board_view.recommendations), 3)
            self.assertEqual(window.game.nodes[0].analysis["timestamp"], timestamp)
            self.assertFalse(window.engine.busy)

    def test_live_bound_finish_keeps_latest_candidates_in_saved_cache(self):
        with self.workspace() as window:
            window.timer.stop()
            profile = self.profile()
            profile["arguments"] = [SIMULATOR, "bound-at-limit"]
            profile["options"] = {"MultiPV": {"maximum": 8}}
            window.profiles = [profile]
            window.config.update(engine_id="simulator", multipv=3, analysis_nodes=400)
            window.game = Game.from_pgn("1.e4 *")
            window.game.navigate(0)
            window._apply_settings()
            window._schedule_engine()
            self.wait_until(lambda: not window.engine.busy and len(window.candidates.lines) == 3)
            self.assertEqual(len(window.game.nodes[0].analysis["multipv_lines"]), 3)
            self.assertEqual(window.game.nodes[0].analysis["depth"], 4)
            self.assertEqual(window.game.nodes[0].analysis["bound"], "upperbound")

    def test_f11_and_f12_keys_toggle_without_moving_or_restarting_the_line(self):
        with self.workspace() as window:
            window.timer.stop()
            window.autosave_timer.stop()
            profile = self.profile()
            profile["arguments"] = [SIMULATOR, "hold"]
            window.profiles = [profile]
            window.config.update(engine_id="simulator", auto_eval_nodes=100, auto_play_nodes=100)
            window.game = Game.from_pgn("1.e4 e5 *")
            window.game.navigate(1)
            window.analysis_mode = True
            window._analysis_enabled = False
            window._refresh()
            window.show()
            window.activateWindow()
            self.app.processEvents()
            engine_actions = window.menus["Engine"].actions()
            for title in ("Auto-play engines from this position", "Auto-evaluate entire line"):
                action = window.menu_actions[title]
                self.assertIn(action, engine_actions)
                self.assertFalse(action.autoRepeat())
            fen = window.game.board.fen()
            window.config["searchmoves"] = ["e7e5"]
            QTest.keyClick(window, Qt.Key.Key_F11)
            self.wait_until(lambda: bool(window.engine.lines))
            self.assertTrue(window._auto_play_active)
            self.assertNotIn("searchmoves", window.engine.connection.running[2])
            QTest.keyClick(window, Qt.Key.Key_F11)
            self.assertFalse(window.engine.busy)
            self.assertEqual(window.quick_analysis_button.text(), "Resume auto-play")
            QTest.keyClick(window, Qt.Key.Key_F11)
            self.wait_until(lambda: bool(window.engine.lines))
            self.assertEqual(window.game.board.fen(), fen)
            # Switching modes must clear the other mode's pause state.
            QTest.keyClick(window, Qt.Key.Key_F12)
            self.wait_until(lambda: bool(window.engine.lines))
            self.assertFalse(window._auto_play_active)
            state = window._review
            state["index"] = 1
            QTest.keyClick(window, Qt.Key.Key_F12)
            self.assertTrue(state["paused"])
            self.assertFalse(window.engine.busy)
            QTest.keyClick(window, Qt.Key.Key_F12)
            self.wait_until(lambda: bool(window.engine.lines))
            self.assertIs(window._review, state)
            self.assertEqual(state["index"], 1)
            self.assertFalse(state["paused"])
            self.assertEqual(window.game.board.fen(), fen)
            window._pause_review()
            QTest.keyClick(window, Qt.Key.Key_F11)
            self.wait_until(lambda: bool(window.engine.lines))
            self.assertIsNone(window._review)
            self.assertTrue(window._auto_play_active)
            window._halt_analysis()

    def test_f11_auto_play_runs_both_sides_with_ten_million_nodes_per_move(self):
        with self.workspace() as window:
            window.timer.stop()
            window.autosave_timer.stop()
            window.profiles = [self.profile()]
            window.config.update(mode="analysis", engine_id="simulator", auto_play_nodes=10_000_000)
            window.analysis_mode = True
            window._analysis_enabled = False
            window.game = Game.from_pgn("1.e4 *")
            window.game.metadata["mode"] = "analysis"
            window._refresh()
            window._start_auto_play()
            self.wait_until(lambda: len(window.game.moves) >= 2)
            window._halt_analysis()
            self.assertIn("> go nodes 10000000", window.engine.connection.log)
            self.assertEqual(window.game.sans[0], "e4")
            self.assertGreaterEqual(len(window.game.moves), 2)

    def test_review_panel_grades_accuracy_navigation_and_saved_restore(self):
        from nocturne.review import rows, summarize

        with self.workspace() as window:
            window.timer.stop()
            window.autosave_timer.stop()
            profile = self.profile()
            profile["arguments"] = [SIMULATOR, "review-grades"]
            window.profiles = [profile]
            window.config.update(mode="analysis", engine_id="simulator")
            window.game = Game.from_pgn("1.e3 e5 2.Nf3 Nc6 3.Bc4 Nf6 *")
            window.analysis_mode = True
            window._analysis_enabled = False
            window._apply_settings()
            window._refresh()
            window.show()
            window.menu_actions["Game Review…"].trigger()
            panel = window.review_panel
            self.assertIs(window.tabs.currentWidget(), panel)
            self.assertIsNone(window._review)
            self.assertEqual(panel.scores[None][0].text(), "—")
            original = window.game.board.fen()
            panel.seconds.setValue(0.1)
            QTest.mouseClick(panel.run, Qt.MouseButton.LeftButton)
            # Allow both five-second cold UCI/ready handshakes plus the full
            # sequence of bounded searches and disk/UI work on slower CI hosts.
            # Completion, all six grades and restored evidence are still required.
            try:
                self.wait_until(lambda: window._review is None and summarize(rows(window.game))["reviewed"] == 6, 20)
            except AssertionError as exc:
                self.fail(f"{exc}; phase={window.engine.connection.phase}; review={window._review}\n"
                          + "\n".join(list(window.engine.connection.log)[-40:]))
            self.assertEqual(window.game.board.fen(), original)
            summary = summarize(rows(window.game))
            self.assertTrue(all(count == 1 for count in summary["counts"].values()))
            for entry in rows(window.game):
                evidence = entry["record"]["context"].get("confirmation")
                if entry["record"]["label"] in ("Mistake", "Blunder"):
                    self.assertEqual(evidence["nodes_per_search"], 10_000_000)
                else:
                    self.assertIsNone(evidence)
            self.assertEqual(sum(command.startswith("> go nodes 10000000")
                                 for command in window.engine.connection.log), 4)
            self.assertEqual(panel.scores[None][0].text(), f"{summary['accuracy']:.1f}%")
            self.assertEqual(panel.progress.value(), 6)
            panel.errors_only.setChecked(True)
            self.assertEqual(panel.table.rowCount(), 3)
            QTest.mouseClick(panel.table.viewport(), Qt.MouseButton.LeftButton,
                            pos=panel.table.visualItemRect(panel.table.item(0, 0)).center())
            self.assertEqual(window.game.cursor, 1)
            self.assertIn("Blunder", panel.detail.toPlainText())
            self.assertFalse(window._analysis_enabled)
            self.assertIsNone(window._job)
            QTest.mouseClick(panel.before, Qt.MouseButton.LeftButton)
            self.assertEqual(window.game.cursor, 0)
            restored = window.store.load(window.game.id)
            self.assertEqual(summarize(rows(restored)), summary)

    def test_review_rejects_bound_scores_and_wrong_targeted_moves(self):
        from nocturne.review import rows, summarize

        for mode in ("bounds", "ignore-searchmoves"):
            with self.subTest(mode=mode), self.workspace() as window:
                window.timer.stop()
                window.autosave_timer.stop()
                profile = self.profile()
                profile["arguments"] = [SIMULATOR, mode]
                window.profiles = [profile]
                window.config.update(engine_id="simulator")
                window.game = Game.from_pgn("1.e3 *")
                window._show_review()
                window._begin_review(0.1)
                # Include cold subprocess startup: the transport itself permits
                # five seconds per handshake, longer than the helper's default.
                try:
                    self.wait_until(lambda: window._review and window._review["paused"], 10)
                except AssertionError as exc:
                    self.fail(
                        f"{exc}; phase={window.engine.connection.phase}; review={window._review}\n"
                        + "\n".join(window.engine.connection.log)
                    )
                # An engine timeout also pauses review; it must not satisfy this
                # test. Require the intended rejection, after a completed search.
                self.assertEqual(window.engine.connection.phase, "idle")
                self.assertEqual(window._review["message"],
                                 "No exact score for the requested move; review paused.")
                self.assertEqual(summarize(rows(window.game))["reviewed"], 0)
                self.assertEqual(window.review_panel.scores[None][0].text(), "—")
                self.assertIn("paused", window.review_panel.status.text())
                window.review_panel.cancel.click()
                self.assertIsNone(window._review)

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

    def test_smart_shared_destination_uses_highest_rank_and_manual_promotion_asks(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QMenu
        from nocturne.gui.board import BoardWidget

        widget = BoardWidget()
        self.addCleanup(widget.close)
        widget.resize(650, 650)
        widget.show()
        widget.set_position(Board("4k3/8/8/8/8/8/3B4/1N2K3 w - - 0 1"))
        widget.smart_move = True
        widget.set_recommendations(
            [(widget.board.parse_uci("d2c3"), 2, "0.0"), (widget.board.parse_uci("b1c3"), 1, "+0.1"),
             (widget.board.parse_uci("e1f1"), 5, "-0.3")]
        )
        moves = []
        widget.move_requested.connect(moves.append)
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton,
                        pos=widget.square_rect(parse_square("c3")).center().toPoint())
        self.assertEqual(moves[-1].uci(), "b1c3")
        self.assertIsNone(QApplication.activePopupWidget())
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton,
                        pos=widget.square_rect(parse_square("f1")).center().toPoint())
        self.assertEqual(moves[-1].uci(), "e1f1")
        count = len(moves)

        def choose_last():
            menu = QApplication.activePopupWidget()
            if isinstance(menu, QMenu):
                QTest.mouseClick(menu, Qt.MouseButton.LeftButton,
                                pos=menu.actionGeometry(menu.actions()[-1]).center())

        def dismiss():
            menu = QApplication.activePopupWidget()
            if menu:
                menu.close()

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
        widget.selected = parse_square("a7")
        QTimer.singleShot(20, choose_last)
        QTimer.singleShot(500, dismiss)
        QTest.mouseClick(
            widget, Qt.MouseButton.LeftButton, pos=widget.square_rect(parse_square("a8")).center().toPoint()
        )
        self.assertEqual(moves[-1].uci(), "a7a8n")

    def test_recommended_promotion_uses_exact_engine_choice_and_both_marker_styles_render(self):
        from nocturne.gui.board import BoardWidget
        widget = BoardWidget()
        self.addCleanup(widget.close)
        widget.resize(650, 650)
        widget.show()
        widget.set_position(Board("4k3/P7/8/8/8/8/8/4K3 w - - 0 1"))
        widget.smart_move = True
        widget.set_recommendations([(widget.board.parse_uci("a7a8n"), 1, "0.0"),
                                    (widget.board.parse_uci("a7a8q"), 2, "-0.2")])
        before = widget.grab().toImage()
        widget.candidate_style = "lines"
        widget.update()
        self.app.processEvents()
        self.assertNotEqual(before, widget.grab().toImage())
        moves = []
        widget.move_requested.connect(moves.append)
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton,
                        pos=widget.square_rect(parse_square("a8")).center().toPoint())
        self.assertEqual(moves[0].uci(), "a7a8n")
        self.assertIsNone(QApplication.activePopupWidget())

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
            window._pause_review()
            window._navigate(0)
            self.assertIsNotNone(window._review)
            self.assertTrue(window._review["paused"])
            self.assertFalse(window.engine.busy)
            self.assertEqual(window.review_panel.pause.text(), "Resume")
            self.assertGreater(window.review_panel.progress.value(), 0)
            self.assertIn("[%eval", window.game.pgn())
            completed = dict(window.game.metadata["review"])
            window._pause_review()
            self.wait_until(lambda: window._review is None, 10)
            self.assertTrue(all(k in window.game.metadata["review"] for k in completed))
