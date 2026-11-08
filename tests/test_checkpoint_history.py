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
        self.assertEqual(list(w.checkpoints), [1_000_000, 4_000_000])
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
                job = dict(turn=1, multipv=2, generation=123, identity=window._position_identity())
                window._job = job
                window.engine.generation = 123
                window.engine._validated_info = lambda info: info.copy()
                window.engine.connection.observation.emit(123, line('e2e4', 1))
                self.assertFalse(window.checkpoint_history.checkpoints)
                window.engine.connection.observation.emit(123, line('d2d4', 2))
                self.assertEqual(len(window.checkpoint_history.checkpoints), 1)
                window.checkpoint_history.select(1_000_000)
                window.engine.connection.observation.emit(123, line('c2c4', 1, 4_000_000))
                self.assertEqual(window.checkpoint_history.panel.lines[1]['pv'], ['e2e4'])
                captured = window.checkpoint_history.checkpoints[4_000_000][1]
                self.assertTrue(captured[3]['historical'])
                self.assertEqual(captured[3]['pv'], ['e2e4'])
                self.assertTrue(window.candidates.isHidden())
                window.analysis_history_toggle.setChecked(False)
                self.assertFalse(window.candidates.isHidden())
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_history_controls_do_not_overlap_maia_heading(self):
        from nocturne.gui.window import MainWindow
        with tempfile.TemporaryDirectory() as folder:
            window = MainWindow(Path(folder))
            try:
                window.resize(1000, 700)
                window.analysis_mode = True
                window.config.update(maia_enabled=True, maia_rating=2200)
                window._refresh()
                window.show()
                self.app.processEvents()
                heading = window.maia_column_title
                toggle = window.analysis_history_toggle
                heading_rect = heading.rect().translated(heading.mapTo(window, heading.rect().topLeft()))
                toggle_rect = toggle.rect().translated(toggle.mapTo(window, toggle.rect().topLeft()))
                self.assertFalse(heading_rect.intersects(toggle_rect))
                self.assertGreaterEqual(heading_rect.left() - toggle_rect.right(), 12)
                self.assertLess(abs(heading_rect.center().y() - toggle_rect.center().y()), 10)
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_capture_preserves_depth_and_grey_candidate(self):
        w = self.widget
        grey = dict(line('d2d4', 2), historical=True, depth=9)
        w.observe(1, {1: line('e2e4'), 2: grey}, 1_000_000)
        w.select(1_000_000)
        self.assertEqual(w.panel.rows[1][2].candidate_depth, 12)
        self.assertEqual(w.panel.rows[2][2].candidate_depth, 9)
        self.assertTrue(w.panel.rows[2][2].candidate_historical)
        grey['depth'] = 30
        self.assertEqual(w.panel.lines[2]['depth'], 9)
        previews = []
        w.preview.connect(lambda pv, ply, name: previews.append(pv))
        w._preview(2, 1)
        self.assertEqual(previews, [['d2d4']])

    def test_history_and_archive_observers_can_be_toggled_independently(self):
        from nocturne.gui.engine import EngineController
        engine = EngineController()
        try:
            engine.set_history_capture(True)
            engine.set_snapshot_capture(True)
            engine.set_snapshot_capture(False)
            self.assertTrue(engine.connection.observe_nodes)
            engine.set_history_capture(False)
            self.assertFalse(engine.connection.observe_nodes)
            engine.set_snapshot_capture(True)
            engine.set_history_capture(True)
            engine.set_history_capture(False)
            self.assertTrue(engine.connection.observe_nodes)
        finally:
            engine.connection.close()

    def test_fork_and_mate_patterns_and_plain_opening(self):
        fen = '4k3/8/3r1q2/8/8/2N5/8/4K3 w - - 0 1'
        self.assertTrue(any('Fork' in text for _, text in tactic_patterns(fen, ['c3e4'], min_ply=1)))
        self.assertFalse(tactic_patterns(fen, ['c3e4']))
        gambit = 'rnbqkbnr/ppp1pppp/8/3p4/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 2'
        self.assertTrue(any('Possible pawn sacrifice' in text for _, text in
                            tactic_patterns(gambit, ['e2e4', 'd5e4', 'g1f3'], min_ply=1)))
        self.assertFalse(tactic_patterns(chess.STARTING_FEN, ['e2e4', 'e7e5']))
        board = chess.Board()
        moves = ['f2f3', 'e7e5', 'g2g4', 'd8h4']
        self.assertTrue(any('Mate' in text for _, text in tactic_patterns(board.fen(), moves)))
