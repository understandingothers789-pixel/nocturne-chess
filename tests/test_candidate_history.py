"""Earlier best-move rows are presentation snapshots, never live engine scores."""
import unittest

from PySide6.QtWidgets import QApplication
from nocturne.gui.candidates import CandidatePanel
from nocturne.gui.moves import MoveText


def line(root, depth=20, rank=1):
    return dict(multipv=rank, depth=depth, seldepth=depth + 2, nodes=1000,
                score_type="cp", score_value=32, score=32, pv=[root], san=[root])


class CandidateHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = CandidatePanel(MoveText(auto_fit=True))
        self.addCleanup(self.panel.deleteLater)

    def test_previous_best_keeps_depth_and_is_not_live(self):
        self.panel.update_line(line("e2e4", 16), 1)
        self.panel.update_line(line("d2d4", 25), 1)
        self.assertEqual(set(self.panel.lines), {1})
        self.assertEqual(self.panel.display_line(2)["pv"], ["e2e4"])
        view = self.panel.rows[2][2]
        self.assertIn("+0.32 d16", view.toPlainText())
        self.assertTrue(view.candidate_historical)
        self.assertFalse(self.panel.rows[1][2].candidate_historical)
        previews = []
        self.panel.preview.connect(lambda rank, ply: previews.append((rank, ply)))
        self.panel._hover(2, 1)
        self.assertEqual(previews, [(2, 1)])

    def test_history_is_unique_and_fills_only_five_minus_live_count(self):
        self.panel.set_multipv(2)
        self.panel.update_line(line("a2a3", rank=2), 1)
        for root in ("e2e4", "d2d4", "g1f3", "c2c4", "b2b3", "e2e4"):
            self.panel.update_line(line(root), 1)
        self.assertEqual(set(self.panel.retained_lines), {3, 4, 5})
        roots = [self.panel.display_line(rank)["pv"][0] for rank in range(1, 6)]
        self.assertEqual(len(set(roots)), 5)
        self.assertEqual(roots[:2], ["e2e4", "a2a3"])

    def test_same_root_updates_do_not_create_history_and_clear_drops_it(self):
        for depth in (10, 20, 30):
            self.panel.update_line(line("e2e4", depth), 1)
        self.assertFalse(self.panel.retained_lines)
        self.panel.update_line(line("d2d4"), 1)
        self.panel.clear()
        self.assertFalse(self.panel.best_history)
        self.assertFalse(self.panel.retained_lines)
        self.assertIsNone(self.panel.display_line(2))

    def test_five_live_lines_never_add_history(self):
        self.panel.set_multipv(5)
        self.panel.update_line(line("e2e4"), 1)
        self.panel.update_line(line("d2d4"), 1)
        self.assertFalse(self.panel.retained_lines)
        self.assertFalse(self.panel.best_history)

    def test_history_preview_stays_stable_until_mouse_leaves(self):
        self.panel.update_line(line("e2e4"), 1)
        self.panel.update_line(line("d2d4"), 1)
        self.panel._hover(2, 1)
        self.panel.update_line(line("c2c4"), 1)
        self.assertEqual(self.panel.display_line(2)["pv"], ["e2e4"])
        self.panel._end_hover(2)
        self.assertEqual(self.panel.display_line(2)["pv"], ["d2d4"])

    def test_thread_menu_offers_fifteen_when_supported(self):
        from dataclasses import asdict
        from nocturne.engine.uci_types import parse_option
        from nocturne.gui.engine_resources import EngineResources
        selected = []
        profile = dict(path="engine", values={}, options={"Threads": asdict(parse_option(
            "option name Threads type spin default 1 min 1 max 16"))})
        resources = EngineResources(lambda: profile, lambda: None,
                                    lambda name, value: selected.append((name, value)), lambda: None)
        resources.refresh()
        action = next(item for item in resources.menus["Threads"].actions() if item.data() == 15)
        self.assertTrue(action.isEnabled())
        action.trigger()
        self.assertEqual(selected, [("Threads", 15)])
        for menu in resources.menus.values():
            menu.deleteLater()

    def test_three_pv_keeps_displaced_lower_ranked_moves(self):
        self.panel.set_multipv(3)
        for rank, root in enumerate(("e2e4", "d2d4", "g1f3"), 1):
            self.panel.update_line(line(root, 18, rank), 1)
        self.panel.update_line(line("c2c4", 22, 2), 1)
        self.panel.update_line(line("b2b3", 23, 3), 1)
        self.assertEqual(set(self.panel.retained_lines), {4, 5})
        self.assertEqual({self.panel.display_line(rank)["pv"][0] for rank in (4, 5)},
                         {"d2d4", "g1f3"})
        self.assertEqual(set(self.panel.lines), {1, 2, 3})

    def test_all_small_multipv_counts_reserve_five_and_show_depth_after_eval(self):
        for count in (1, 2, 3, 4):
            with self.subTest(multipv=count):
                self.panel.set_multipv(count)
                self.panel.clear()
                self.panel.update_line(line("e2e4", 17), 1)
                self.assertEqual(set(self.panel.rows), set(range(1, 6)))
                self.panel.update_line(line("d2d4", 25), 1)
                view = self.panel.rows[count + 1][2]
                self.assertTrue(view.candidate_historical)
                self.assertTrue(view.toPlainText().startswith("+0.32 d17"))
