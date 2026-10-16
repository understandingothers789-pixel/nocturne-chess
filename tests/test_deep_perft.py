"""Optional slower reference counts; opt in with NOCTURNE_DEEP_TESTS=1."""

import os
import unittest

from nocturne.core.board import Board, perft


@unittest.skipUnless(os.environ.get("NOCTURNE_DEEP_TESTS") == "1", "deep perft is opt-in")
class DeepPerftTests(unittest.TestCase):
    def test_initial_depth_five(self):
        self.assertEqual(perft(Board(), 5), 4_865_609)

    def test_kiwipete_depth_four(self):
        board = Board("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
        self.assertEqual(perft(board, 4), 4_085_603)
