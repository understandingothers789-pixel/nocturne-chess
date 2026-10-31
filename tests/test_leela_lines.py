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
