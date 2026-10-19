"""Durable node checkpoints, paused restoration, and comparison UI."""

import os
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from nocturne.analysis_jobs import restore
from nocturne.core.game import Game
from nocturne.gui.snapshot_dialog import SnapshotDialog
from nocturne.gui.window import MainWindow
from nocturne.settings import normalize
from nocturne.snapshots import milestones, position_key
from nocturne.storage import Store


class SnapshotModelTests(unittest.TestCase):
    def test_milestones_follow_one_two_five_through_and_beyond_ten_billion(self):
        self.assertEqual(list(milestones(0, 10_000_000_000)), [
            1_000_000, 2_000_000, 5_000_000, 10_000_000, 20_000_000, 50_000_000,
            100_000_000, 200_000_000, 500_000_000, 1_000_000_000, 2_000_000_000,
            5_000_000_000, 10_000_000_000,
        ])
        self.assertEqual(list(milestones(10_000_000_000, 50_000_000_000)), [20_000_000_000, 50_000_000_000])
        self.assertFalse(normalize({})["analysis_snapshots"])

    def test_snapshot_storage_is_durable_immutable_and_scoped_to_game_and_position(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "library.db"
            game = Game.from_pgn("1.e4 (1.d4 d5) e5 *")
            game.select_node(0)
            key = position_key(game)
            record = {"milestone": 1_000_000, "observed_nodes": 1_000_083, "lines": [{"score": 35}]}
            store = Store(path)
            store.save(game)
            store.save_snapshot(game.id, key, record)
            store.save_snapshot(game.id, key, record | {"observed_nodes": 2_000_000})
            store.close()
            store = Store(path)
            self.assertEqual(store.snapshots(game.id, key), [record])
            self.assertEqual(store.snapshots("another-pgn", key), [])
            self.assertEqual(store.snapshots(game.id, "another-position"), [])
            store.delete(game.id)
            self.assertEqual(store.snapshots(game.id, key), [])
            store.close()

    def test_corrupt_or_invalidated_saved_queue_is_ignored(self):
        game = Game.from_pgn("1.e4 *")
        game.metadata["auto_eval_job"] = {"version": 1, "kind": "auto_eval", "game_id": game.id,
                                           "line": [0, 999], "index": 0}
        self.assertIsNone(restore(game))


class SnapshotGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.window = MainWindow(Path(self.tmp.name))
        self.window.timer.stop()
        self.window.autosave_timer.stop()
        self.window.profiles = [{"id": "snapshots", "path": sys.executable,
                                 "arguments": [str(Path(__file__).parent / "fixtures" / "uci_simulator.py"), "snapshot-nodes"],
                                 "values": {}, "options": {"MultiPV": {"maximum": 8}}}]
        self.window.config.update(mode="analysis", engine_id="snapshots", multipv=3,
                                  analysis_nodes=10_000_000, auto_eval_nodes=10_000_000)
        self.window.game = Game.from_pgn("1.e4 e5 *")
        self.window.game.metadata["mode"] = "analysis"
        self.window.game.navigate(0)
        self.window.analysis_mode = True
        self.window._analysis_enabled = False
        self.window._apply_settings()
        self.window._refresh()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.tmp.cleanup()

    def wait(self, check, seconds=6):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.app.processEvents()
            if check():
                return
            time.sleep(0.005)
        self.fail(f"Timed out: {self.window._review}")

    def reopen(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.window = MainWindow(Path(self.tmp.name))
        self.window.timer.stop()
        self.window.autosave_timer.stop()
        self.app.processEvents()

    def test_snapshots_and_analysis_reopen_paused_and_only_fresh_analyze_clears_them(self):
        window = self.window
        self.assertFalse(window.snapshot_capture_action.isChecked())
        window._set_snapshot_capture(True)
        window._start_analysis()
        self.wait(lambda: not window.engine.busy and bool(window.game.nodes[0].analysis))
        key = position_key(window.game)
        records = window.store.snapshots(window.game.id, key)
        self.assertEqual([r["milestone"] for r in records], [1_000_000, 2_000_000, 5_000_000, 10_000_000])
        self.assertTrue(all(len(r["lines"]) == 3 for r in records))
        dialog = SnapshotDialog(lambda: records, parent=window)
        self.assertEqual(dialog.selectors[0].currentData(), 1_000_000)
        self.assertEqual(dialog.selectors[1].currentData(), 10_000_000)
        self.assertIn("Depth", dialog.views[0].toPlainText())
        self.assertIn("→", dialog.summary.text())
        dialog.close()
        self.reopen()
        window = self.window
        self.assertFalse(window._analysis_enabled)
        self.assertFalse(window.engine.busy)
        self.assertEqual(len(window.candidates.lines), 3)
        self.assertEqual(window.store.snapshots(window.game.id, key), records)
        window._set_snapshot_capture(False)
        self.assertEqual(window.store.snapshots(window.game.id, key), records)
        window._start_analysis()
        self.assertEqual(window.store.snapshots(window.game.id, key), [])
        self.assertEqual(window.game.nodes[0].analysis, {})
        self.wait(lambda: not window.engine.busy)
        self.assertEqual(window.store.snapshots(window.game.id, key), [])

    def test_f12_reopens_at_unfinished_position_and_resumes_without_repeating_completed_positions(self):
        window = self.window
        window._set_snapshot_capture(True)
        window._auto_evaluate_line()
        self.wait(lambda: window._review is not None and window._review["index"] == 1)
        window._auto_evaluate_line()
        self.assertTrue(window._review["paused"])
        original = json.loads(json.dumps(window.game.nodes[0].analysis))
        key = position_key(window.game, 0)
        records = window.store.snapshots(window.game.id, key)
        self.assertEqual(window.store.load(window.game.id).metadata["auto_eval_job"]["index"], 1)
        self.reopen()
        window = self.window
        self.assertTrue(window._review["paused"])
        self.assertEqual(window._review["index"], 1)
        self.assertFalse(window.engine.busy)
        window._auto_evaluate_line()
        self.wait(lambda: window._review is None)
        self.assertEqual(window.game.nodes[0].analysis, original)
        self.assertEqual(window.store.snapshots(window.game.id, key), records)
        self.assertNotIn("auto_eval_job", window.store.load(window.game.id).metadata)
