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
            w._flush_secondary_analysis()
            self.assertEqual(secondary.call_count, 1)
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
