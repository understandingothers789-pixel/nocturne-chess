import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
import tempfile
from pathlib import Path
import chess
from PySide6.QtWidgets import QApplication
from nocturne.gui.analysis_history import AnalysisHistory, tactic_patterns


def line(move, rank=1, nodes=1_000_000):
    b = chess.Board()
    san = b.san(chess.Move.from_uci(move))
    return dict(pv=[move], san=[san], multipv=rank, nodes=nodes, depth=12,
                score=30, score_type='cp', score_value=30)


class CheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.busy = False
        self.widget = AnalysisHistory(lambda: self.busy)
        self.widget.position('a', chess.STARTING_FEN, 1)

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()
        self.app.processEvents()

    def test_doubling_frozen_snapshot_order_missing_and_new_search(self):
        w = self.widget
        w.observe(1, {1: line('e2e4'), 2: line('d2d4', 2)}, 1_000_000)
        w.observe(1, {1: line('d2d4'), 2: line('e2e4', 2)}, 4_100_000)
        self.assertEqual(list(w.checkpoints), [1_000_000, 2_000_000, 4_000_000])
        w.mode.setCurrentIndex(1)
        w.select(1_000_000)
        self.assertEqual(w.panel.lines[1]['pv'], ['d2d4'])
        w.observe(1, {1: line('c2c4')}, 8_000_000)
        self.assertEqual(w.panel.lines[1]['pv'], ['d2d4'])
        w.select(8_000_000)
        self.assertFalse(w.panel.lines)
        w.observe(2, {1: line('e2e4')}, 1_000_000)
        self.assertEqual(list(w.checkpoints), [1_000_000])
        self.assertIsNone(w.selected)

    def test_navigation_restores_position_and_scan_cancels_on_search(self):
        w = self.widget
        w.observe(1, {1: line('e2e4')}, 1_000_000)
        w.position('b', chess.STARTING_FEN, 1)
        self.assertFalse(w.checkpoints)
        w.position('a', chess.STARTING_FEN, 1)
        w.select(1_000_000)
        w.scan()
        self.assertTrue(w.scanning)
        self.busy = True
        w._availability()
        self.assertFalse(w.scanning)
        w.scan()
        self.assertFalse(w.scanning)

    def test_window_collects_complete_multipv_and_keeps_snapshot_frozen(self):
        from nocturne.gui.window import MainWindow
        with tempfile.TemporaryDirectory() as folder:
            window = MainWindow(Path(folder))
            try:
                window.analysis_history_toggle.setChecked(True)
                job = dict(turn=1, multipv=2, generation=123)
                window._show_info(line('e2e4', 1), job)
                self.assertFalse(window.checkpoint_history.checkpoints)
                window._show_info(line('d2d4', 2), job)
                self.assertEqual(len(window.checkpoint_history.checkpoints), 1)
                window.checkpoint_history.select(1_000_000)
                window._show_info(line('c2c4', 1, 4_000_000), job)
                self.assertEqual(window.checkpoint_history.panel.lines[1]['pv'], ['e2e4'])
                self.assertTrue(window.candidates.isHidden())
                window.analysis_history_toggle.setChecked(False)
                self.assertFalse(window.candidates.isHidden())
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_fork_and_mate_patterns_and_plain_opening(self):
        fen = '4k3/8/3r1q2/8/8/2N5/8/4K3 w - - 0 1'
        self.assertTrue(any('Fork' in text for _, text in tactic_patterns(fen, ['c3e4'])))
        gambit = 'rnbqkbnr/ppp1pppp/8/3p4/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 2'
        self.assertTrue(any('Possible pawn sacrifice' in text for _, text in
                            tactic_patterns(gambit, ['e2e4', 'd5e4', 'g1f3'])))
        self.assertFalse(tactic_patterns(chess.STARTING_FEN, ['e2e4', 'e7e5']))
        board = chess.Board()
        moves = ['f2f3', 'e7e5', 'g2g4', 'd8h4']
        self.assertTrue(any('Mate' in text for _, text in tactic_patterns(board.fen(), moves)))
