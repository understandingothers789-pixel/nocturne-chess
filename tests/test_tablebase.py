"""Real, offline Syzygy probes against optional checksum-pinned test data."""
import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from nocturne.core.board import Board
from nocturne.engine.tablebase import probe, root_result
from nocturne.engine.uci import UciSession

FIXTURES = os.environ.get('NOCTURNE_TEST_SYZYGY', '')
WIN = '8/8/8/8/8/2K5/4Q3/k7 w - - 0 1'


class TablebaseDiagnostics(unittest.TestCase):
    def test_disabled_castling_and_invalid_folder(self):
        self.assertEqual(probe(Board(WIN), '')['status'], 'disabled')
        self.assertEqual(probe(Board(), 'missing')['status'], 'outside')
        self.assertEqual(probe(Board(WIN), '/nonexistent/nocturne-tables')['status'], 'error')
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'KQvK.rtbw').write_bytes(b'bad')
            self.assertIn('invalid table', probe(Board(WIN), directory)['message'])


@unittest.skipUnless(FIXTURES, 'Set NOCTURNE_TEST_SYZYGY to verified development fixture directory')
class RealTablebaseTests(unittest.TestCase):
    def test_wdl_dtz_and_legal_root_match_independent_reader(self):
        import chess
        import chess.syzygy
        with chess.syzygy.open_tablebase(FIXTURES) as oracle:
            for fen in (WIN, WIN.replace(' w ', ' b '),
                        '8/8/8/8/8/2K5/4P3/k7 w - - 0 1',
                        '8/8/8/8/8/2K5/4R3/k7 b - - 0 1',
                        WIN.replace('0 1', '98 1')):
                with self.subTest(fen=fen):
                    board = Board(fen)
                    result = probe(board, FIXTURES)
                    self.assertEqual(result['status'], 'hit', result)
                    # Raw WDL oracle ignores the halfmove clock; compare at zero.
                    if not board.halfmove:
                        self.assertEqual(result['wdl'], oracle.probe_wdl(chess.Board(fen)))
                        self.assertEqual(result['dtz'], oracle.probe_dtz(chess.Board(fen)))
                    board.parse_uci(result['move'])
                    self.assertIsNotNone(root_result(board, result))

    def test_unicode_path_missing_dtz_and_cancellation(self):
        with tempfile.TemporaryDirectory(prefix='nocturne-é-') as directory:
            shutil.copy(Path(FIXTURES, 'KQvK.rtbw'), directory)
            result = probe(Board(WIN), directory)
            self.assertEqual(result['status'], 'wdl', result)
            self.assertIsNone(root_result(Board(WIN), result))
            shutil.copy(Path(FIXTURES, 'KQvK.rtbz'), directory)
            self.assertEqual(probe(Board(WIN), directory)['status'], 'hit')
            self.assertEqual(probe(Board(WIN), directory, lambda: True)['status'], 'canceled')

    def test_uci_uses_packaged_reader(self):
        output = io.StringIO()
        session = UciSession(output)
        session.command('setoption name SyzygyPath value ' + FIXTURES)
        session.command('position fen ' + WIN)
        session.command('go depth 2')
        session._thread.join(timeout=5)
        session.stop()
        self.assertIn('tbhits 1', output.getvalue())
        best = next(line.split()[1] for line in output.getvalue().splitlines() if line.startswith('bestmove '))
        Board(WIN).parse_uci(best)
