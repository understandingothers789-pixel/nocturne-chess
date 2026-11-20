import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from nocturne.engine.uci_types import parse_option
from nocturne.gui.engine_manager import EngineManager
from nocturne.gui.uci_connection import UciConnection


class EngineManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_select_detects_missing_options_and_preserves_profile_values(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(UciConnection, 'launch') as launch:
            path = Path(folder) / 'stockfish.exe'
            path.write_bytes(b'engine')
            option = parse_option('option name Debug Log File type string default <empty>')
            profiles = [dict(id='old', path=str(path), name='SF old', values={'Debug Log File': 'saved.log'},
                             options={option.name: asdict(option)}, options_detected=True,
                             options_signature=EngineManager._signature(path)),
                        dict(id='new', path=str(path), name='SF new', values={}, options={})]
            dialog = EngineManager(profiles, 'old')
            try:
                self.app.processEvents()
                launch.assert_not_called()
                self.assertEqual(dialog.widgets['Debug Log File'].text(), 'saved.log')
                dialog.selector.setCurrentIndex(1)
                self.app.processEvents()
                launch.assert_called_once_with(str(path))
                dialog.selector.setCurrentIndex(0)
                dialog._discovered(dict(path=str(path), name='Wrong profile', options={}))
                self.assertIn('Debug Log File', dialog.widgets)
                dialog.selector.setCurrentIndex(1)
                self.app.processEvents()
                dialog._discovered(dict(path=str(path), name='New Stockfish', options={option.name: option}))
                self.assertIn('Debug Log File', dialog.widgets)
                self.assertIn('1 advertised options', dialog.status.text())
                dialog.selector.setCurrentIndex(0)
                self.assertEqual(dialog.widgets['Debug Log File'].text(), 'saved.log')
            finally:
                dialog.reject()
                dialog.deleteLater()
                self.app.processEvents()

    def test_replaced_executable_is_redetected_and_failures_are_visible(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(UciConnection, 'launch') as launch:
            path = Path(folder) / 'sf.exe'
            path.write_bytes(b'old')
            signature = EngineManager._signature(path)
            path.write_bytes(b'new engine')
            dialog = EngineManager([dict(id='p', path=str(path), name='SF', values={}, options={},
                                         options_detected=True, options_signature=signature)], 'p')
            try:
                self.app.processEvents()
                launch.assert_called_once_with(str(path))
                dialog._failed('Engine blocked or failed to start')
                self.assertIn('blocked', dialog.status.text())
                dialog._detect()
                dialog._discovered(dict(path=str(path), name='SF', options={}))
                self.assertIn('no configurable options', dialog.status.text())
            finally:
                dialog.reject()
                dialog.deleteLater()
                self.app.processEvents()
