"""Keep secondary analysis work out of the board/Stockfish update path."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from nocturne.gui.window import MainWindow


class AnalysisPriorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.window = MainWindow(Path(self.folder.name))
        self.window._analysis_enabled = False

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.folder.cleanup()

    def test_repeated_stockfish_clicks_defer_panels_and_disk_writes(self):
        w = self.window
        w.analysis_mode = True
        w.config.update(mode="analysis", maia_enabled=False, multipv=1)
        w._refresh()
        w._last_save_at = None
        moves = ("e2e4", "e7e5", "g1f3")
        with patch.object(w, "_render_move_history") as history, \
                patch.object(w, "_sync_explorer") as explorer, \
                patch.object(w, "_schedule_engine") as schedule, \
                patch.object(w.store, "save") as save:
            for text in moves:
                board = w.game.board
                from nocturne.core.notation import san
                name = san(board, board.parse_uci(text))
                info = dict(pv=[text], san=[name], score=20, score_type="cp", score_value=20,
                            depth=12, seldepth=14, nodes=100)
                w._show_info(info, dict(turn=board.turn, multipv=1), store=False)
                self.assertEqual(w.board_view.recommendations[0][0].uci(), text)
                w._insert_candidate(1, 1)
                self.assertEqual(w.board_view.board.fen(), w.game.board.fen())
                self.assertTrue(w.board_view.interactive)
                self.assertTrue(w._navigation_refresh_timer.isActive())
            self.assertEqual(w.game.sans, ["e4", "e5", "Nf3"])
            history.assert_not_called()
            explorer.assert_not_called()
            save.assert_not_called()
            self.assertEqual(schedule.call_count, 3)
            w._navigation_refresh_timer.stop()
            w._flush_navigation_refresh()
            history.assert_called_once()
            explorer.assert_called_once()

    def test_deferred_navigation_refresh_ignores_stale_position_and_close(self):
        w = self.window
        w.analysis_mode = True
        w.config["maia_enabled"] = False
        w._refresh(defer_secondary=True)
        w.game.play(w.game.board.parse_uci("e2e4"))
        with patch.object(w, "_refresh") as refresh:
            w._flush_navigation_refresh()
            refresh.assert_not_called()
        w.close()
        self.assertFalse(w._navigation_refresh_timer.isActive())

    def test_burst_updates_targets_immediately_and_coalesces_secondary_work(self):
        w = self.window
        w._candidate_identity = w._position_identity()
        w.candidates.lines = {1: dict(pv=['e2e4'], score=20, score_type='cp', score_value=20)}
        with patch.object(w, '_sync_blunder') as secondary:
            for _ in range(30):
                w._sync_candidate_markers()
            self.assertEqual(w.board_view.recommendations[0][0].uci(), 'e2e4')
            secondary.assert_not_called()
            self.assertTrue(w._secondary_timer.isActive())
            w._secondary_timer.stop()
            w._flush_secondary_analysis()
            secondary.assert_called_once()

    def test_old_position_and_closed_window_callbacks_do_no_work(self):
        w = self.window
        w._queue_secondary_analysis()
        w.game.play(w.game.board.parse_uci('e2e4'))
        with patch.object(w, '_sync_blunder') as secondary:
            w._flush_secondary_analysis()
            secondary.assert_not_called()
            w._queue_secondary_analysis()
            w._secondary_timer.stop()
            w._flush_secondary_analysis()
            secondary.assert_called_once()
            w.close()
            after_close = secondary.call_count
            w._flush_secondary_analysis()
            self.assertEqual(secondary.call_count, after_close)
            self.assertFalse(w._secondary_timer.isActive())

    def test_identical_pv_reuses_parsed_moves_and_changed_pv_refreshes(self):
        w = self.window
        info = dict(pv=['e2e4', 'e7e5'], san=['e4', 'e5'], score=20,
                    score_type='cp', score_value=20, depth=12, seldepth=14, nodes=100)
        job = dict(turn=1, multipv=1)
        w._show_info(info, job, store=False)
        moves = w._pv_moves
        w._show_info(info | dict(nodes=200), job, store=False)
        self.assertIs(w._pv_moves, moves)
        w._show_info(info | dict(pv=['d2d4', 'd7d5'], san=['d4', 'd5']), job, store=False)
        self.assertEqual(w._pv_moves[0].uci(), 'd2d4')
        self.assertEqual(w.board_view.best_move.uci(), 'd2d4')
        w._clear_analysis_output()
        w._show_info(info, job, store=False)
        self.assertEqual(w._pv_moves[0].uci(), 'e2e4')
