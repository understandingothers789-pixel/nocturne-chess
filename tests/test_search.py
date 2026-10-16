import time
import unittest

from nocturne.core.board import Board, SQUARES
from nocturne.engine.evaluate import evaluate
from nocturne.engine.search import MATE, SearchLimits, Searcher, difficulty_limits


class EvaluationTests(unittest.TestCase):
    def test_material_and_side_perspective(self):
        w = Board("4k3/8/8/8/8/8/8/Q3K3 w - - 0 1")
        b = Board(w.fen().replace(" w ", " b "))
        self.assertGreater(evaluate(w), 850)
        self.assertLess(evaluate(b), -850)
        self.assertEqual(evaluate(w) + evaluate(b), 20)  # tempo bonus

    def test_color_mirror_symmetry_and_no_mutation(self):
        board = Board()
        for text in ("e2e4", "c7c5", "g1f3", "b8c6", "f1b5", "e7e6"):
            board.play_uci(text)
        mirrored = board.copy(history=False)
        for s in SQUARES:
            mirrored.cells[s ^ 112] = -board.cells[s]
        mirrored.kings = [board.kings[1] ^ 112, board.kings[0] ^ 112]
        mirrored.turn = -board.turn
        original = board.fen(), board.key
        self.assertEqual(evaluate(board), evaluate(mirrored))
        self.assertEqual((board.fen(), board.key), original)


class SearchTests(unittest.TestCase):
    def test_finds_mate_and_encodes_distance(self):
        b = Board("7k/8/5KQ1/8/8/8/8/8 w - - 0 1")
        result = Searcher(SearchLimits(depth=3, seconds=2)).search(b)
        self.assertEqual(result.info.score, MATE - 1)
        b.push(result.best_move)
        self.assertEqual(b.outcome().reason, "Checkmate")

    def test_stalemate_and_checkmate_are_terminal(self):
        for fen, score in (("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", 0),
                           ("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1", -MATE)):
            result = Searcher().search(Board(fen))
            self.assertIsNone(result.best_move)
            self.assertEqual(result.info.score, score)

    def test_wins_free_queen(self):
        b = Board("4k3/8/8/8/8/8/q7/R3K3 w - - 0 1")
        result = Searcher(SearchLimits(depth=2, seconds=2)).search(b)
        self.assertEqual(result.best_move.uci(), "a1a2")

    def test_quiescence_in_check_uses_quiet_evasions(self):
        b = Board("4r1k1/8/8/8/8/8/8/4K3 w - - 0 1")
        result = Searcher(SearchLimits(depth=1, seconds=1)).search(b)
        self.assertIn(result.best_move, list(b.legal_moves()))
        b.push(result.best_move)
        self.assertFalse(b.in_check(1))

    def test_search_preserves_position_and_pv_is_legal(self):
        b = Board()
        original = b.fen(), b.key, b.key_history.copy()
        updates = []
        result = Searcher(SearchLimits(depth=3, seconds=3)).search(b, updates.append)
        self.assertEqual(result.info.depth, 3)
        self.assertEqual((b.fen(), b.key, b.key_history), original)
        self.assertEqual([i.depth for i in updates], [1, 2, 3])
        self.assertEqual(result.info.pv[0], result.best_move)
        for move in result.info.pv:
            self.assertIn(move, list(b.legal_moves()))
            b.push(move)

    def test_immediate_cancellation_returns_legal_fallback(self):
        b = Board()
        result = Searcher(SearchLimits(depth=20, seconds=10), cancel=lambda: True).search(b)
        self.assertTrue(result.stopped)
        self.assertEqual(result.info.depth, 0)
        self.assertIn(result.best_move, list(b.legal_moves()))

    def test_strict_time_and_node_budgets(self):
        started = time.perf_counter()
        result = Searcher(SearchLimits(depth=30, seconds=.06)).search(Board())
        self.assertLess(time.perf_counter() - started, .25)
        self.assertTrue(result.stopped)
        result = Searcher(SearchLimits(depth=30, seconds=5, nodes=128)).search(Board())
        self.assertLessEqual(result.info.nodes, 128)
        self.assertTrue(result.stopped)

    def test_tt_pvs_and_ordering_preserve_fixed_depth_score(self):
        for fen in (Board().fen(), "4k3/8/8/8/3p4/8/4P3/R3K3 w - - 0 1"):
            scores = []
            for options in ({"use_tt": False, "use_ordering": False, "use_killers": False},
                            {}, {"use_pvs": True}):
                result = Searcher(SearchLimits(depth=3, seconds=10, **options)).search(Board(fen))
                self.assertEqual(result.info.depth, 3)
                scores.append(result.info.score)
            self.assertEqual(len(set(scores)), 1, scores)

    def test_claimable_draw_and_clock_allocation(self):
        b = Board("4k3/8/8/8/8/8/8/R3K3 w - - 100 1")
        self.assertTrue(Searcher().search(b).claim_draw)
        limits = difficulty_limits("Maximum", available=.2)
        self.assertLess(limits.seconds, .13)

    def test_weak_levels_still_choose_legal_searched_moves(self):
        b = Board()
        result = Searcher(difficulty_limits("Beginner")).search(b)
        self.assertIn(result.best_move, list(b.legal_moves()))
        self.assertGreater(result.info.nodes, 0)
