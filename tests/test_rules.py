"""Rules regression tests, runnable without third-party test tools."""

import unittest
import random
from nocturne.core.board import Board, START_FEN, perft, parse_square
from nocturne.core.notation import PgnGame, parse_san, read_pgn, san, write_pgn

class RulesTests(unittest.TestCase):

    def test_initial_perft(self):
        for depth, nodes in [(0, 1), (1, 20), (2, 400), (3, 8902), (4, 197281)]:
            with self.subTest(depth=depth, nodes=nodes):
                board = Board()
                assert perft(board, depth) == nodes
                assert board.fen() == START_FEN
                assert board.key == board.compute_key()

    def test_reference_perft(self):
        for fen, counts in [('r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1', [48, 2039, 97862]), ('8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1', [14, 191, 2812, 43238]), ('r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1', [6, 264, 9467]), ('rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8', [44, 1486, 62379]), ('r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10', [46, 2079, 89890])]:
            with self.subTest(fen=fen, counts=counts):
                board = Board(fen)
                for depth, nodes in enumerate(counts, 1):
                    assert perft(board, depth) == nodes
                    assert board.fen() == fen

    def test_castling_restrictions_and_restoration(self):
        b = Board('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1')
        before = (b.fen(), b.key)
        for uci in ('e1g1', 'e1c1'):
            b.play_uci(uci)
            assert b.key == b.compute_key()
            b.pop()
            assert (b.fen(), b.key) == before
        b = Board('4kr2/8/8/8/8/8/8/R3K2R w KQ - 0 1')
        assert 'e1g1' not in {m.uci() for m in b.legal_moves()}
        assert 'e1c1' in {m.uci() for m in b.legal_moves()}
        b = Board('4r1k1/8/8/8/8/8/8/R3K2R w KQ - 0 1')
        assert b.in_check()
        assert not {'e1g1', 'e1c1'} & {m.uci() for m in b.legal_moves()}

    def test_en_passant_discovered_check_and_hash_identity(self):
        fen = '8/8/8/r4pPK/8/8/8/4k3 w - f6 0 1'
        b = Board(fen)
        assert 'g5f6' not in {m.uci() for m in b.legal_moves()}
        assert b.key == Board(fen.replace(' f6 ', ' - ')).key
        b = Board('4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1')
        assert b.key != Board(b.fen().replace(' d6 ', ' - ')).key
        start = (b.fen(), b.key)
        b.play_uci('e5d6')
        assert b.cells[parse_square('d5')] == 0
        assert b.key == b.compute_key()
        b.pop()
        assert (b.fen(), b.key) == start

    def test_all_underpromotions_and_san(self):
        b = Board('4k3/P7/8/8/8/8/8/4K3 w - - 0 1')
        promotions = [m for m in b.legal_moves() if m.from_sq == parse_square('a7')]
        assert {m.uci() for m in promotions} == {'a7a8q', 'a7a8r', 'a7a8b', 'a7a8n'}
        for m in promotions:
            assert parse_san(b, san(b, m)) == m
            start = (b.fen(), b.key)
            b.push(m)
            assert b.key == b.compute_key()
            b.pop()
            assert (b.fen(), b.key) == start

    def test_mate_stalemate_and_75_move_precedence(self):
        b = Board()
        for move in ('f2f3', 'e7e5', 'g2g4'):
            b.play_uci(move)
        m = b.parse_uci('d8h4')
        assert san(b, m) == 'Qh4#'
        b.push(m)
        b.halfmove = 150
        assert b.outcome().reason == 'Checkmate'
        assert b.outcome().winner == -1
        b = Board('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1')
        assert b.outcome().reason == 'Stalemate'

    def test_repetition_and_intended_claims(self):
        b = Board()
        cycle = ('g1f3', 'g8f6', 'f3g1', 'f6g8')
        for move in cycle + cycle[:3]:
            b.play_uci(move)
        assert not b.claimable_draws()
        assert 'Threefold repetition' in b.claimable_draws(b.parse_uci('f6g8'))
        assert b.repetition_count() == 2
        b.play_uci('f6g8')
        assert b.repetition_count() == 3
        assert b.outcome() is None
        for move in cycle * 2:
            b.play_uci(move)
        assert b.outcome().reason == 'Fivefold repetition'

    def test_fifty_and_seventyfive_move_rules(self):
        b = Board('4k3/8/8/8/8/8/8/R3K3 w - - 99 1')
        assert not b.claimable_draws()
        assert b.claimable_draws(b.parse_uci('a1a2')) == ('Fifty-move rule',)
        b.play_uci('a1a2')
        assert b.claimable_draws() == ('Fifty-move rule',)
        assert b.outcome() is None
        b.halfmove = 150
        assert b.outcome().reason == 'Seventy-five-move rule'

    def test_insufficient_material(self):
        for fen, dead in [('4k3/8/8/8/8/8/8/4K3 w - - 0 1', True), ('4k3/8/8/8/8/8/8/2B1K3 w - - 0 1', True), ('4k3/8/8/8/8/8/8/2N1K3 w - - 0 1', True), ('4k3/8/8/8/8/8/6b1/2B1K3 w - - 0 1', False), ('4k3/8/8/8/8/8/5b2/2B1K3 w - - 0 1', True), ('4k3/8/8/8/8/8/8/1NN1K3 w - - 0 1', False)]:
            with self.subTest(fen=fen, dead=dead):
                assert Board(fen).insufficient_material() == dead

    def test_fen_failure_is_atomic(self):
        b = Board()
        for fen in ('invalid', START_FEN.replace(' w ', ' x '), '8/8/8/8/8/8/8/K6k w K - 0 1', '8/8/8/8/8/8/4k3/4K3 w - - 0 1'):
            with self.assertRaises(ValueError):
                b.set_fen(fen)
            assert b.fen() == START_FEN

    def test_random_make_unmake_and_notation(self):
        rng = random.Random(134)
        b = Board()
        snapshots = []
        for _ in range(140):
            legal = list(b.legal_moves())
            if not legal:
                break
            move = rng.choice(legal)
            assert parse_san(b, san(b, move)) == move
            snapshots.append((b.fen(), b.key, b.cells.copy(), b.key_history.copy()))
            b.push(move)
            assert b.key == b.compute_key()
            assert Board(b.fen()).fen() == b.fen()
        while snapshots:
            b.pop()
            fen, key, cells, history = snapshots.pop()
            assert (b.fen(), b.key, b.cells, b.key_history) == (fen, key, cells, history)

    def test_pgn_mainline_comments_variations_and_round_trip(self):
        text = '[White "Ada"]\n[Black "Turing"]\n[Result "*"]\n\n1.e4 {hi} e5 2.Nf3 (2.Bc4 Nc6) Nc6 $1 3.Bb5 a6 *'
        game = read_pgn(text)
        assert len(game.moves) == 6
        parsed = read_pgn(write_pgn(game))
        assert parsed.moves == game.moves
        assert parsed.initial_fen == game.initial_fen
        assert parsed.result == game.result
        assert all(parsed.headers[k] == v for k, v in game.headers.items())
        board = Board()
        for move in game.moves:
            board.push(move)
        assert board.cells[parse_square('b5')] == 3

    def test_pgn_custom_black_to_move_and_escaped_headers(self):
        fen = '4k3/8/8/8/8/8/8/R3K3 b - - 0 19'
        b = Board(fen)
        game = PgnGame({'White': 'A "quoted" name'}, fen, [b.parse_uci('e8f8')])
        text = write_pgn(game)
        assert '19... Kf8' in text
        parsed = read_pgn(text)
        assert parsed.initial_fen == fen
        assert parsed.moves == game.moves
        assert parsed.headers['White'] == game.headers['White']

    def test_bad_pgn(self):
        for text in ['1.e5 *', '1.e4 (1.d4 *', '1.e4 {unfinished', '1.e4 * 1.d4 *']:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    read_pgn(text)
