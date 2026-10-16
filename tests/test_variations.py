"""Persistent ordered variations and PGN RAV round trips."""
from copy import deepcopy
import io
import json
import unittest

from nocturne.core.game import Game
from nocturne.core.notation import read_pgn


class VariationTests(unittest.TestCase):
    def study(self):
        game = Game.from_pgn("1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.O-O Nf6 *")
        original = game.current_node
        game.navigate(4)
        game.play(game.board.parse_uci("b1c3"))
        return game, original

    def test_alternative_preserves_original_continuation(self):
        game, original = self.study()
        alternative = game.current_node
        self.assertEqual(game.sans[-1], "Nc3")
        self.assertEqual([game.nodes[c].san for c in game.nodes[4].children], ["Bc4", "Nc3"])
        game.select_node(original)
        self.assertEqual(game.sans, ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "O-O", "Nf6"])
        game.select_node(alternative)
        self.assertEqual(game.sans, ["e4", "e5", "Nf3", "Nc6", "Nc3"])

    def test_existing_move_reuses_branch_with_future(self):
        game, _ = self.study()
        game.play(game.board.parse_uci("g8f6"))
        count = len(game.nodes)
        game.navigate(4)
        game.play(game.board.parse_uci("b1c3"))
        self.assertEqual(len(game.nodes), count)
        self.assertEqual(game.cursor, 5)
        self.assertTrue(game.redo())
        self.assertEqual(game.sans[-1], "Nf6")

    def test_pgn_includes_nested_variations_and_reimports(self):
        text = "1.e4 (1.d4 d5 (1...Nf6 2.c4) 2.c4) e5 2.Nf3 (2.Bc4 Nc6) Nc6 *"
        game = Game.from_pgn(text)
        rendered = game.pgn()
        restored = Game.from_pgn(rendered)
        self.assertEqual(restored.tree_tokens(), game.tree_tokens())
        self.assertEqual(len(restored.nodes), len(game.nodes))
        self.assertEqual(read_pgn(text).moves, read_pgn(rendered).moves)
        try:
            import chess.pgn
        except ImportError:
            return
        oracle = chess.pgn.read_game(io.StringIO(rendered))
        self.assertFalse(oracle.errors)
        self.assertEqual(len(oracle.variations), 2)
        self.assertEqual(len(oracle.variations[1].variations), 2)

    def test_json_preserves_branches_selected_cursor_and_promotion_order(self):
        game, original = self.study()
        game.evaluations[game.cursor] = 27
        alternative = game.current_node
        game.promote_current_line()
        data = json.loads(json.dumps(game.to_dict()))
        restored = Game.from_dict(data)
        self.assertEqual(restored.current_node, alternative)
        self.assertEqual(restored.pgn(), game.pgn())
        self.assertEqual(restored.nodes[4].children, game.nodes[4].children)
        self.assertEqual(restored.evaluations[5], 27)
        restored.select_node(original)
        self.assertEqual(restored.sans[-1], "Nf6")
        self.assertEqual(restored.board.key, game.position_at_node(original).key)

    def test_old_schema_migrates_and_invalid_side_branch_rejected(self):
        game, _ = self.study()
        data = game.to_dict()
        legacy = deepcopy(data)
        legacy["schema"] = 1
        for k in ("tree", "line", "main_result"):
            legacy.pop(k)
        restored = Game.from_dict(legacy)
        self.assertEqual(restored.board.fen(), game.board.fen())
        for change in ("move", "cycle", "order"):
            broken = deepcopy(data)
            if change == "move":
                broken["tree"][5]["move"] = "e1e8"
            elif change == "cycle":
                broken["tree"][5]["parent"] = 5
            else:
                broken["tree"][4]["children"] = []
            with self.subTest(change=change), self.assertRaises(ValueError):
                Game.from_dict(broken)

    def test_side_variation_must_be_legal_and_parentheses_balanced(self):
        for text in ("1.e4 (1.e5) *", "1.e4 (1.d4 *", "1.e4 ) *"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                Game.from_pgn(text)
