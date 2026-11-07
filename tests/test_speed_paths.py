"""Correctness checks for optimized variation validation and cursor updates."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from nocturne.core.game import Game
from nocturne.core.rules import Board
from nocturne.core.notation import san
from nocturne.gui.engine import EngineController
from nocturne.gui.game_line import GameLine


class SpeedPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_output_timer_is_idle_without_pending_information(self):
        from PySide6.QtTest import QTest
        from nocturne.gui.uci_connection import UciConnection
        connection = UciConnection()
        received = []
        connection.information.connect(lambda generation, info: received.append(info))
        self.assertFalse(connection._flush.isActive())
        connection.phase = "search"
        connection.running = (1, "position startpos", "go infinite", {}, "study")
        connection._line("info depth 1 score cp 10 nodes 1 pv e2e4")
        self.assertEqual(len(received), 1)
        connection._line("info depth 2 score cp 20 nodes 2 pv e2e4")
        self.assertTrue(connection._flush.isActive())
        QTest.qWait(120)
        self.assertEqual(received[-1]["depth"], 2)
        self.assertFalse(connection._flush.isActive())
        connection.close()
        connection.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_fast_pvs_match_rules_wrapper_and_leave_root_unchanged(self):
        cases = [
            (Board(), ['e2e4', 'e7e5', 'g1f3', 'illegal']),
            (Board(), ['0000', 'e2e4']),
            (Board('4k3/P7/8/8/8/8/8/4K3 w - - 0 1'), ['a7a8q', 'e8e7']),
            (Board('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1'), ['e1g1', 'e8c8']),
            (Board('r3k2r/8/8/8/8/8/8/R3K2R w HAha - 0 1'), ['e1h1', 'e8a8']),
        ]
        engine = EngineController()
        for board, pv in cases:
            before = board.fen()
            reference = board.copy()
            expected_pv, expected_san = [], []
            for text in pv:
                try:
                    move = reference.parse_uci(text)
                    if move not in reference.legal_moves():
                        break
                    expected_san.append(san(reference, move))
                    reference.push(move)
                    expected_pv.append(text)
                except ValueError:
                    break
            engine.board = board
            result = engine._validated_info({'pv': pv})
            if expected_pv:
                self.assertEqual(result['pv'], expected_pv)
                self.assertEqual(result['san'], expected_san)
            else:
                self.assertIsNone(result)
            self.assertEqual(board.fen(), before)
        engine.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_cursor_navigation_reuses_document_but_comment_edit_rebuilds(self):
        game = Game.from_pgn('1. e4 e5 (1... c5) 2. Nf3 Nc6 *')
        view = GameLine()
        view.set_game(game)
        with patch.object(view, 'setHtml', wraps=view.setHtml) as rebuild:
            for node_id in range(1, len(game.nodes)):
                game.select_node(node_id)
                view.set_game(game)
                selections = view.extraSelections()
                self.assertEqual(len(selections), 1)
                self.assertEqual(selections[0].cursor.selectionStart(),
                                 view._node_cursors[node_id].selectionStart())
            rebuild.assert_not_called()
            game.nodes[game.current_node].comment = 'New comment'
            view.set_game(game)
            rebuild.assert_called_once()
            self.assertIn('New comment', view.toPlainText())
        view.close()
        view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
