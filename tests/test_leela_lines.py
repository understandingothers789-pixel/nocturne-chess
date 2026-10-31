"""Leela's line renderer preserves engine scores and matchup perspective."""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from nocturne.core.game import Game
from nocturne.settings import DEFAULTS
from nocturne.gui.leela import LeelaPanel


class LeelaLineTests(unittest.TestCase):
    def test_render_score_depth_wdl_and_hover_without_starting_engine(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            panel = LeelaPanel(Path(folder), dict(DEFAULTS))
            try:
                panel.active = True
                panel.game = Game()
                panel.identity = ('fixture',)
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
                panel.engine.connection.path = panel.exe
                panel.engine.connection.request = Mock()
                with patch.object(UciConnection, 'alive', new_callable=PropertyMock, return_value=True):
                    panel._start()
                    sent = panel.engine.connection.request.call_args.args
                    self.assertEqual(sent[2], 'go nodes 125000')
                    self.assertEqual(sent[3]['Backend'], 'onnx-dml')
                    self.assertEqual(sent[3]['BackendOptions'], 'gpu=1')
                    config['leela_limit'] = 'infinite'
                    panel._start()
                    self.assertEqual(panel.engine.connection.request.call_args.args[2], 'go infinite')
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
