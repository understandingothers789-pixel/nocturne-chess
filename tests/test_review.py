"""Review scoring, evidence binding and partial accuracy coverage."""

import json
import unittest

from nocturne.core.game import Game
from nocturne.core.rules import Board
from nocturne.review import chance, classify, rows, summarize


def info(cp, move, kind="cp", **extra):
    return dict(score_type=kind, score_value=cp, bound="exact", pv=[move], depth=12, **extra)


class ReviewTests(unittest.TestCase):
    def test_quality_bands_and_bounded_monotonic_accuracy(self):
        position = Board()
        move = position.parse_uci("e2e3")
        grades = []
        for cp, expected in [(140, "Excellent"), (120, "Good"), (100, "Inaccuracy"), (0, "Mistake"), (-600, "Blunder")]:
            record = classify(position, move, info(150, "e2e4"), info(cp, "e2e3"))
            self.assertEqual(record["label"], expected)
            self.assertTrue(0 <= record["accuracy"] <= 100)
            grades.append(record["accuracy"])
        self.assertEqual(grades, sorted(grades, reverse=True))
        best = classify(position, move, info(150, "e2e3"), info(150, "e2e3"))
        self.assertEqual((best["label"], best["accuracy"]), ("Best", 100))
        self.assertAlmostEqual(chance(info(0, "e2e4")), 50)
        self.assertTrue(0 <= chance(info(10**1000, "e2e4")) <= 100)

    def test_bounds_missing_scores_and_wrong_move_cannot_receive_a_grade(self):
        position = Board()
        move = position.parse_uci("e2e3")
        best = info(150, "e2e4")
        for played in [None, {}, info(35, "e2e4"), info(35, "e2e8"),
                       {**info(35, "e2e3"), "bound": "upperbound"},
                       info(0, "e2e3", "mate")]:
            with self.subTest(played=played):
                self.assertIsNone(classify(position, move, best, played))

    def test_mates_are_outcomes_not_centipawn_arithmetic(self):
        position = Board()
        move = position.parse_uci("e2e3")
        record = classify(position, move, info(3, "e2e4", "mate"), info(0, "e2e3"))
        self.assertEqual(record["label"], "Blunder")
        self.assertEqual(record["loss_percent"], 50)
        self.assertNotIn("loss_cp", record)
        retained = classify(position, move, info(3, "e2e4", "mate"), info(9, "e2e3", "mate"))
        self.assertEqual(retained["accuracy"], 100)

    def test_partial_summary_restore_and_deletion_bind_evidence_to_position(self):
        game = Game.from_pgn("1.e3 e5 (1...Nf6) 2.Nf3 *")
        root = game.position_at_node(0)
        record = classify(root, game.nodes[1].move, info(150, "e2e4"), info(-600, "e2e3"))
        game.metadata["review"] = {"1": record}
        summary = summarize(rows(game))
        self.assertEqual((summary["reviewed"], summary["total"]), (1, 3))
        self.assertAlmostEqual(summary["accuracy"], record["accuracy"])
        self.assertIsNone(summarize(rows(game), -1)["accuracy"])
        restored = Game.from_dict(json.loads(json.dumps(game.to_dict())))
        self.assertEqual(summarize(rows(restored)), summary)
        self.assertIn("estimated accuracy", restored.pgn())
        restored.metadata["review"]["1"]["root_fen"] = "unrelated position"
        self.assertEqual(summarize(rows(restored))["reviewed"], 0)
        game.select_node(1)
        game.delete_current_line()
        self.assertEqual(summarize(rows(game))["reviewed"], 0)

    def test_black_mover_and_fen_move_number_are_not_reversed(self):
        position = Board()
        position.push(position.parse_uci("e2e4"))
        game = Game(position.fen().rsplit(" ", 1)[0] + " 27")
        move = game.board.parse_uci("e7e5")
        record = classify(game.board, move, info(150, "g8f6"), info(0, "e7e5"))
        self.assertEqual(record["label"], "Mistake")
        game.play(move)
        game.metadata["review"] = {str(game.current_node): record}
        entry = rows(game)[0]
        self.assertEqual((entry["color"], entry["number"]), (-1, 27))
        self.assertEqual(summarize(rows(game), -1)["reviewed"], 1)
        self.assertIsNone(summarize(rows(game), 1)["accuracy"])

    def test_malformed_legacy_records_do_not_break_export_or_fabricate_accuracy(self):
        game = Game.from_pgn("1.e4 *")
        for records in [[], None, {"1": {}}, {"1": {"label": "Best"}},
                        {"1": {"label": "Best", "accuracy": "bad", "loss_cp": "bad"}}]:
            with self.subTest(records=records):
                game.metadata["review"] = records
                self.assertEqual(summarize(rows(game))["reviewed"], 0)
                self.assertIsNone(summarize(rows(game))["accuracy"])
                self.assertEqual(Game.from_pgn(game.pgn()).sans, ["e4"])
