from dataclasses import asdict
import io
import multiprocessing
from pathlib import Path
import sys
import tempfile
import time
import unittest

from nocturne.core.board import Board
from nocturne.engine.external import ExternalEngineError, run_external
from nocturne.engine.search import SearchLimits
from nocturne.engine.uci import UciSession
from nocturne.engine.worker import run_worker


class UciTests(unittest.TestCase):
    def test_handshake_position_and_search(self):
        output = io.StringIO()
        session = UciSession(output)
        session.command("uci")
        session.command("isready")
        session.command("position startpos moves e2e4 e7e5")
        self.assertIn("uciok", output.getvalue())
        self.assertIn("readyok", output.getvalue())
        session.command("go depth 2")
        session._thread.join(timeout=3)
        session.stop()
        best = [line.split()[1] for line in output.getvalue().splitlines() if line.startswith("bestmove ")][-1]
        session.board.parse_uci(best)
        self.assertIn("info depth 2", output.getvalue())

    def test_invalid_position_is_atomic_and_stop_is_prompt(self):
        output = io.StringIO()
        session = UciSession(output)
        before = session.board.fen()
        session.command("position startpos moves e2e5")
        self.assertEqual(session.board.fen(), before)
        session.command("go infinite")
        started = time.perf_counter()
        session.command("stop")
        self.assertLess(time.perf_counter() - started, .3)
        self.assertIn("bestmove ", output.getvalue())


class ProcessTests(unittest.TestCase):
    def test_benchmark_worker_reports_all_reference_positions(self):
        context = multiprocessing.get_context("spawn")
        output, child_output = context.Pipe(duplex=False)
        child_control, control = context.Pipe(duplex=False)
        request = {"kind": "benchmark", "limits": asdict(SearchLimits(depth=1, seconds=.02))}
        proc = context.Process(target=run_worker, args=(request, child_output, child_control))
        try:
            proc.start()
            child_output.close()
            child_control.close()
            rows = []
            deadline = time.monotonic() + 5
            report = None
            while time.monotonic() < deadline and output.poll(2):
                kind, payload = output.recv()
                self.assertNotEqual(kind, "error", payload)
                if kind == "benchmark_progress":
                    rows.append(payload)
                elif kind == "benchmark":
                    report = payload
                    break
            self.assertIsNotNone(report)
            self.assertEqual(len(rows), 5)
            self.assertEqual(report["results"], rows)
            self.assertIn("python", report["metadata"])
            proc.join(timeout=1)
            self.assertEqual(proc.exitcode, 0)
        finally:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=1)
            output.close()
            control.close()

    def test_spawned_search_and_cooperative_cancellation(self):
        context = multiprocessing.get_context("spawn")
        output, child_output = context.Pipe(duplex=False)
        child_control, control = context.Pipe(duplex=False)
        request = {"initial_fen": Board().fen(), "moves": ["e2e4"],
                   "limits": asdict(SearchLimits(depth=30, seconds=10))}
        proc = context.Process(target=run_worker, args=(request, child_output, child_control))
        try:
            proc.start()
            child_output.close()
            child_control.close()
            self.assertTrue(output.poll(4), "worker did not report an iteration")
            kind, payload = output.recv()
            self.assertEqual(kind, "info", payload)
            started = time.perf_counter()
            control.send("stop")
            while output.poll(2):
                kind, payload = output.recv()
                if kind == "result":
                    break
                self.assertNotEqual(kind, "error", payload)
            self.assertEqual(kind, "result")
            self.assertTrue(payload["stopped"])
            b = Board()
            b.play_uci("e2e4")
            b.parse_uci(payload["move"])
            proc.join(timeout=1)
            self.assertFalse(proc.is_alive())
            self.assertLess(time.perf_counter() - started, 1)
        finally:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=1)
            output.close()
            control.close()


class ExternalTests(unittest.TestCase):
    def test_our_uci_engine_as_external_process(self):
        result = run_external([sys.executable, "-m", "nocturne.engine.uci"], Board().fen(), [],
                              SearchLimits(depth=2, seconds=.2), lambda: False, lambda info: None)
        self.assertIn(result.best_move, list(Board().legal_moves()))
        self.assertGreater(result.info.nodes, 0)

    def test_illegal_external_move_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "fake.py"
            script.write_text("import sys\nfor line in sys.stdin:\n"
                              " if line.strip()=='uci': print('uciok',flush=True)\n"
                              " elif line.strip()=='isready': print('readyok',flush=True)\n"
                              " elif line.startswith('go '): print('bestmove e2e5',flush=True)\n"
                              " elif line.strip()=='quit': break\n")
            with self.assertRaisesRegex(ExternalEngineError, "illegal move"):
                run_external([sys.executable, str(script)], Board().fen(), [], SearchLimits(), lambda: False, lambda i: None)
