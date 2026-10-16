import json
from pathlib import Path
import tempfile
import unittest

from nocturne.core.board import Move, START_FEN
from nocturne.core.game import Game, TimeControl
from nocturne.storage import Store, StorageError


class GameTests(unittest.TestCase):
    def test_legal_boundary_and_history_branch(self):
        game = Game()
        with self.assertRaises(ValueError):
            game.play(Move.from_uci("e2e5"))
        self.assertEqual(game.board.fen(), START_FEN)
        game.play(game.board.parse_uci("e2e4"))
        game.play(game.board.parse_uci("e7e5"))
        final = game.board.fen(), game.board.key_history.copy()
        game.undo()
        game.redo()
        self.assertEqual((game.board.fen(), game.board.key_history), final)
        game.undo()
        game.play(game.board.parse_uci("c7c5"))
        self.assertEqual(game.sans, ["e4", "c5"])
        self.assertFalse(game.redo())

    def test_clock_increment_timeout_and_pause(self):
        game = Game(time_control=TimeControl(10, 1))
        game.start_clock(now=100)
        game.play(game.board.parse_uci("e2e4"), now=102)
        self.assertEqual(game.clock_values(now=104), {1: 9, -1: 8})
        game.pause_clock(now=104)
        self.assertEqual(game.clock_values(now=200), {1: 9, -1: 8})
        game.start_clock(now=200)
        result = game.tick(now=209)
        self.assertEqual(result.winner, 1)
        self.assertEqual(result.reason, "Time forfeit")
        with self.assertRaises(ValueError):
            game.play(game.board.parse_uci("e7e5"), now=209)

    def test_timeout_with_bare_king_is_draw(self):
        game = Game("4k3/8/8/8/8/8/8/R3K3 w - - 0 1", TimeControl(1))
        game.start_clock(now=1)
        self.assertEqual(game.tick(now=3).result, "1/2-1/2")

    def test_draw_claim_without_moving(self):
        game = Game("4k3/8/8/8/8/8/8/R3K3 w - - 99 1")
        with self.assertRaises(ValueError):
            game.claim_draw()
        game.claim_draw(game.board.parse_uci("a1a2"))
        self.assertEqual(game.cursor, 0)
        self.assertEqual(game.outcome.reason, "Fifty-move rule")

    def test_json_roundtrip_preserves_redo_and_repetition(self):
        game = Game(time_control=TimeControl(300, 3))
        for text in ("g1f3", "g8f6", "f3g1", "f6g8", "e2e4"):
            game.play(game.board.parse_uci(text))
        game.undo()
        game.evaluations = {0: 10, 4: 12}
        restored = Game.from_dict(json.loads(json.dumps(game.to_dict())))
        self.assertEqual(restored.board.fen(), game.board.fen())
        self.assertEqual(restored.board.key_history, game.board.key_history)
        self.assertEqual(restored.evaluations, game.evaluations)
        self.assertFalse(restored.running)  # resume is paused until user continues
        self.assertTrue(restored.redo())
        self.assertEqual(restored.sans[-1], "e4")

    def test_corrupted_game_rejected(self):
        data = Game().to_dict()
        data["moves"] = ["e2e5"]
        with self.assertRaises(ValueError):
            Game.from_dict(data)
        for key in ("headers", "metadata", "evaluations", "clock_history", "remaining"):
            data = Game().to_dict()
            data[key] = "broken"
            with self.subTest(key=key), self.assertRaises(ValueError):
                Game.from_dict(data)
        data = Game().to_dict()
        data["remaining"][1] = float("nan")
        with self.assertRaises(ValueError):
            Game.from_dict(data)

    def test_pgn_and_resignation(self):
        game = Game.from_pgn("1.e4 e5 2.Nf3 Nc6 *")
        game.resign()
        self.assertEqual(game.outcome.result, "0-1")
        restored = Game.from_pgn(game.pgn())
        self.assertEqual(restored.board.fen(), game.board.fen())
        self.assertEqual(restored.outcome.result, "0-1")

    def test_analysis_fork_preserves_original_game(self):
        game = Game.from_pgn("1.e4 e5 *")
        fork = game.fork_for_analysis()
        self.assertNotEqual(fork.id, game.id)
        self.assertEqual(fork.metadata["source_id"], game.id)
        fork.undo()
        fork.play(fork.board.parse_uci("c7c5"))
        self.assertEqual(game.sans, ["e4", "e5"])
        self.assertEqual(fork.sans, ["e4", "c5"])


class StorageTests(unittest.TestCase):
    def test_saved_match_stats_exclude_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "games.db")
            game = Game()
            game.metadata["mode"] = "ai_ai"
            game.resign(-1)
            store.save(game)
            store.save(game.fork_for_analysis())
            self.assertEqual(store.match_stats(), {"white_wins": 1, "black_wins": 0, "draws": 0, "unfinished": 0})
            store.close()
    def test_save_resume_multiple_games_and_preferences(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "games.db")
            game = Game()
            game.play(game.board.parse_uci("e2e4"))
            store.save(game)
            self.assertEqual(store.resume().board.fen(), game.board.fen())
            store.save(Game(), autosave=False)
            self.assertEqual(len(store.list_games()), 2)
            store.set("theme", "walnut")
            self.assertEqual(store.get("theme"), "walnut")
            store.close()
            store = Store(Path(tmp) / "games.db")
            self.assertEqual(store.get("theme"), "walnut")
            store.delete(game.id)
            self.assertIsNone(store.resume())
            store.close()

    def test_corruption_is_reported_without_deleting_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "games.db")
            game = Game()
            store.save(game)
            with store.db:
                store.db.execute("UPDATE games SET payload='broken' WHERE id=?", (game.id,))
            with self.assertRaises(StorageError):
                store.load(game.id)
            self.assertEqual(len(store.list_games()), 1)
            store.close()
