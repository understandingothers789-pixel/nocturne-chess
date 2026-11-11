"""Leela's line renderer preserves engine scores and matchup perspective."""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from nocturne.core.game import Game
from nocturne.settings import DEFAULTS
from nocturne.gui.leela import LeelaPanel, workload_limits


class LeelaLineTests(unittest.TestCase):
    def test_workload_presets_bound_batch_threads_and_speed(self):
        cfg = dict(DEFAULTS, leela_batch_size=128, leela_nps_limit=0)
        self.assertEqual(workload_limits(dict(cfg, leela_workload='minimal')), (1, 1, 100))
        self.assertEqual(workload_limits(dict(cfg, leela_workload='low')), (4, 1, 500))
        self.assertEqual(workload_limits(dict(cfg, leela_workload='normal')), (128, 2, 0))
        self.assertEqual(workload_limits(dict(cfg, leela_workload='minimal', leela_nps_limit=25)), (1, 1, 25))

    def test_on_demand_and_stop_do_not_restart_on_navigation(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            panel = LeelaPanel(Path(folder), dict(DEFAULTS, leela_on_demand=True))
            try:
                panel.active = True
                game = Game()
                panel.request(game)
                self.assertFalse(panel.timer.isActive())
                panel.request(game, force=True)
                self.assertTrue(panel.timer.isActive())
                panel.pause_search()
                self.assertFalse(panel.timer.isActive())
                game.play(game.board.parse_uci('e2e4'))
                panel.request(game)
                self.assertFalse(panel.timer.isActive())
                panel._message(panel.engine.generation - 1, 'info', {'multipv': 1})
                self.assertFalse(panel.lines)
            finally:
                panel.shutdown()
                panel.deleteLater()
                app.processEvents()

    def test_follow_board_flip_can_be_disabled_and_saved(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            config = dict(DEFAULTS)
            panel = LeelaPanel(Path(folder), config)
            try:
                panel.follow_board_flip(False)
                self.assertEqual(config['leela_side'], 'white')
                panel.follow_board_flip(True)
                self.assertEqual(config['leela_side'], 'black')
                panel.follow_board.setChecked(False)
                self.assertFalse(config['leela_follow_board'])
                panel.follow_board_flip(False)
                self.assertEqual(config['leela_side'], 'black')
                panel.side.setCurrentIndex(0)
                self.assertEqual(config['leela_side'], 'white')
                app.processEvents()
            finally:
                panel.shutdown()
                panel.deleteLater()

    def test_render_score_depth_wdl_and_hover_without_starting_engine(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            panel = LeelaPanel(Path(folder), dict(DEFAULTS))
            try:
                panel.active = True
                panel.game = Game()
                panel.identity = (panel.game.board.fen(),)
                panel.lines = {1: dict(multipv=1, score_type='cp', score_value=25,
                                      depth=12, seldepth=19, nodes=12345, nps=2000,
                                      pv=['e2e4', 'e7e5'], san=['e4', 'e5'],
                                      wdl=(600, 300, 100))}
                previews = []
                panel.preview.connect(lambda pv, ply: previews.append((pv, ply)))
                panel._render()
                app.processEvents()
                moves, badge, _ = panel.rows[1]
                self.assertIn('+0.25', moves.toPlainText())
                self.assertIn('d12', moves.toPlainText())
                self.assertEqual(badge.text(), '10.0 / 30.0 / 60.0')
                self.assertIn('12,345', panel.telemetry.text())
                self.assertIn('19', panel.telemetry.text())
                moves.move_hovered.emit(2)
                self.assertEqual(previews, [(['e2e4', 'e7e5'], 2)])
                self.assertIsNone(panel.installer)
            finally:
                panel.shutdown()
                panel.close()
                panel.deleteLater()

    def test_gpu_selection_prefers_discrete_radeon_over_integrated_and_software(self):
        from nocturne.gui.leela_gpu import preferred_adapter
        integrated = dict(index=0, name='AMD Radeon Graphics', memory_mb=512, vendor=0x1002)
        discrete = dict(index=1, name='AMD Radeon RX 9070 XT', memory_mb=16384, vendor=0x1002)
        software = dict(index=2, name='Software', memory_mb=32768, software=True)
        self.assertEqual(preferred_adapter([integrated, discrete, software]), discrete)
        self.assertIsNone(preferred_adapter([software]))

    def test_node_and_unlimited_modes_do_not_send_time_or_depth_limits(self):
        from unittest.mock import Mock, PropertyMock, patch
        from nocturne.gui.uci_connection import UciConnection
        from nocturne.settings import normalize
        app = QApplication.instance() or QApplication([])
        config = normalize(dict(DEFAULTS, leela_limit='nodes', leela_nodes=125000,
                                leela_gpu_auto=False, leela_device=1))
        with tempfile.TemporaryDirectory() as folder:
            panel = LeelaPanel(Path(folder), config)
            try:
                panel.active = True
                panel.game = Game()
                panel.exe = str(Path(folder) / 'lc0.exe')
                panel.weights = 'network.pb.gz'
                panel._launched_device = 1
                panel._launched_batch = 8
                panel.engine.connection.path = panel.exe
                panel.engine.connection.request = Mock()
                with patch.object(UciConnection, 'alive', new_callable=PropertyMock, return_value=True):
                    panel._start()
                    sent = panel.engine.connection.request.call_args.args
                    self.assertEqual(sent[2], 'go nodes 125000')
                    self.assertEqual(sent[3]['Backend'], 'onnx-dml')
                    self.assertEqual(sent[3]['BackendOptions'], 'gpu=1')
                    self.assertEqual(sent[3]['MinibatchSize'], 8)
                    config['leela_limit'] = 'time'
                    panel._start()
                    self.assertEqual(panel.engine.connection.request.call_args.args[2], 'go movetime 20000')
                    config['leela_limit'] = 'both'
                    panel._start()
                    self.assertEqual(panel.engine.connection.request.call_args.args[2], 'go movetime 20000 nodes 125000')
                    config['leela_limit'] = 'infinite'
                    panel._start()
                    self.assertEqual(panel.engine.connection.request.call_args.args[2], 'go infinite')
                    self.assertEqual(panel.speed_limit.value(), 256)
                    panel.speed_limit.setValue(6000)
                    panel.timer.stop()
                    panel._start()
                    self.assertEqual(panel.engine.connection.request.call_args.args[3]['NodesPerSecondLimit'], 6000)
                    panel.speed_limit.setValue(1000)
                    self.assertEqual(config['leela_nps_limit'], 1000)
                    panel.timer.stop()
                    panel._start()
                    self.assertEqual(panel.engine.connection.request.call_args.args[3]['NodesPerSecondLimit'], 1000)
                    panel.speed_limit.setValue(0)
                    panel.timer.stop()
                    panel._start()
                    self.assertEqual(panel.engine.connection.request.call_args.args[3]['NodesPerSecondLimit'], 0)
                    panel.workload.setCurrentIndex(panel.workload.findData('minimal'))
                    panel.timer.stop()
                    panel._start()
                    limited = panel.engine.connection.request.call_args.args[3]
                    self.assertEqual((limited['MinibatchSize'], limited['Threads'], limited['NodesPerSecondLimit']), (1, 1, 100))
                self.assertIsNone(panel.installer)
            finally:
                panel.shutdown()
                panel.close()
                panel.deleteLater()
                app.processEvents()

    @unittest.skipUnless(os.name == 'nt', 'DXGI adapter enumeration is Windows-specific')
    def test_native_dxgi_adapter_indices_and_names(self):
        from nocturne.gui.leela_gpu import directml_adapters
        try:
            devices = directml_adapters()
        except OSError as exc:
            self.skipTest(f'DXGI unavailable in this session: {exc}')
        self.assertEqual(len({device['index'] for device in devices}), len(devices))
        for device in devices:
            self.assertIsInstance(device['name'], str)
            self.assertGreaterEqual(device['memory_mb'], 0)

    def test_stockfish_managed_limits_can_disable_time_without_disabling_nodes(self):
        from unittest.mock import Mock, PropertyMock, patch
        from nocturne.engine.uci_types import AnalysisLimits
        from nocturne.gui.engine import EngineController
        from nocturne.gui.uci_connection import UciConnection
        app = QApplication.instance() or QApplication([])
        engine = EngineController()
        try:
            engine.connection.path = str(Path('stockfish').absolute())
            engine.connection.request = Mock()
            with patch.object(UciConnection, 'alive', new_callable=PropertyMock, return_value=True):
                engine.start(Game(), AnalysisLimits(depth=80, seconds=7, nodes=500000),
                             external=engine.connection.path, kind='analysis',
                             ensure_pv_length=True, time_enabled=False)
                self.assertEqual(engine._managed_limits, (500000, 80, 0))
                self.assertEqual(engine.connection.request.call_args.args[2], 'go infinite')
                engine.start(Game(), AnalysisLimits(depth=80, seconds=7, nodes=500000),
                             external=engine.connection.path, kind='analysis',
                             ensure_pv_length=True, time_enabled=True)
                self.assertEqual(engine._managed_limits, (500000, 80, 7))
        finally:
            engine.close()
            app.processEvents()

    def test_limit_checkboxes_keep_modes_and_fields_in_sync(self):
        from nocturne.settings import normalize
        app = QApplication.instance() or QApplication([])
        config = normalize(dict(DEFAULTS, leela_limit='nodes'))
        with tempfile.TemporaryDirectory() as folder:
            panel = LeelaPanel(Path(folder), config)
            try:
                self.assertFalse(panel.seconds.isEnabled())
                self.assertTrue(panel.nodes.isEnabled())
                panel.time_enabled.setChecked(True)
                self.assertEqual(config['leela_limit'], 'both')
                self.assertTrue(panel.seconds.isEnabled())
                panel.nodes_enabled.setChecked(False)
                self.assertEqual(config['leela_limit'], 'time')
                self.assertFalse(panel.nodes.isEnabled())
                panel.time_enabled.setChecked(False)
                self.assertEqual(config['leela_limit'], 'infinite')
            finally:
                panel.shutdown()
                panel.close()
                panel.deleteLater()
                app.processEvents()

    def test_late_update_and_redraw_are_ignored_after_position_changes(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            panel = LeelaPanel(Path(folder), dict(DEFAULTS))
            try:
                panel.active = True
                panel.game = Game()
                panel.identity = (panel.game.board.fen(),)
                panel.lines = {1: dict(multipv=1, score_type='cp', score_value=25,
                                      depth=12, seldepth=19, nodes=12345, nps=2000,
                                      pv=['e2e4'], san=['e4'], wdl=(600, 300, 100))}
                panel.game.play(panel.game.board.parse_uci('d2d4'))
                panel._message(0, 'info', dict(multipv=2))
                self.assertNotIn(2, panel.lines)
                panel._render()
                self.assertFalse(panel.rows)
            finally:
                panel.shutdown()
                panel.close()
                panel.deleteLater()
                app.processEvents()
