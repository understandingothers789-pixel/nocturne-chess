"""Development-only differential checks; never imported by the application."""

import random

try:
    import chess
except ImportError:
    chess = None

import unittest

from nocturne.core.board import Board
from nocturne.core.notation import san


@unittest.skipIf(chess is None, "optional python-chess oracle is not installed")
class OracleTests(unittest.TestCase):
    def test_seeded_games_against_independent_oracle(self):
        rng = random.Random(20261016)
        for _ in range(12):
            ours, reference = Board(), chess.Board()
            for ply in range(140):
                legal = {m.uci(): m for m in ours.legal_moves()}
                assert set(legal) == {m.uci() for m in reference.legal_moves}, (ply, ours.fen())
                assert ours.fen() == reference.fen(en_passant="fen")
                assert ours.in_check() == reference.is_check()
                assert ours.insufficient_material() == reference.is_insufficient_material()
                assert (ours.repetition_count() >= 3) == reference.is_repetition(3)
                assert ours.key == ours.compute_key()
                if not legal:
                    break
                uci = rng.choice(sorted(legal))
                assert san(ours, legal[uci]) == reference.san(chess.Move.from_uci(uci))
                ours.push(legal[uci])
                reference.push_uci(uci)
