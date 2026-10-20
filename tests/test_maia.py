"""Identity and probability integrity at the Maia/Stockfish boundary."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QApplication

from nocturne.maia import percentage
from nocturne.maia.controller import MaiaController
from nocturne.gui.candidates import CandidatePanel
from nocturne.gui.moves import MoveText


class MaiaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_probability_matches_uci_move_when_stockfish_order_differs(self):
        panel = CandidatePanel(MoveText(auto_fit=True))
        panel.set_maia({"d2d4": 0.1, "e2e4": 0.9}, 1800)
        panel.update_line({"multipv": 1, "pv": ["d2d4"], "san": ["d4"], "score": 30, "score_value": 30, "score_type": "cp", "depth": 12, "seldepth": 16}, 1)
        panel.update_line({"multipv": 2, "pv": ["e2e4"], "san": ["e4"], "score": 20, "score_value": 20, "score_type": "cp", "depth": 12, "seldepth": 16}, 1)
        self.assertEqual(panel.maia_labels[1].text(), "10.0%")
        self.assertEqual(panel.maia_labels[2].text(), "90.0%")
        panel.set_maia({"d2d4": 0.000000001})
        self.assertEqual(panel.maia_labels[1].text(), "1e-07%")
        self.assertEqual(panel.maia_labels[2].text(), "—")
        panel.deleteLater()

    def test_stale_worker_result_never_updates_the_selected_position(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = MaiaController(folder)
            controller._serial = 2
            controller._active = (("key", (1800,)), {"id": 2})
            message = json.dumps({"id": 1, "policies": {"1800": {"e2e4": 1}}, "complete": True})
            with patch.object(controller.process, "readAllStandardOutput", return_value=QByteArray((message+"\n").encode())):
                controller._read()
            self.assertEqual(controller.policies, {})
            controller.stop()

    def test_cache_distinguishes_move_history_and_retains_rating_policies(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = MaiaController(folder)
            controller.request("root", ["g1f3"], 1800)
            first = controller._queued[0][0]
            controller.request("root", ["b1c3"], 1800)
            second = controller._queued[0][0]
            self.assertNotEqual(first, second)
            controller.cache[second] = {"1800": {"a2a3": 1}}
            controller._save_cache()
            restored = MaiaController(Path(folder))
            restored.request("root", ["b1c3"], 1800)
            self.assertEqual(restored.policies, {"1800": {"a2a3": 1}})
            self.assertIsNone(restored._queued)
            controller.stop()
            restored.stop()

    def test_probability_format_does_not_round_small_values_into_fake_matches(self):
        self.assertEqual(percentage(None), "—")
        self.assertEqual(percentage(0), "0%")
        self.assertEqual(percentage(0.000001), "0.0001%")
