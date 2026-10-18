import unittest

from nocturne.settings import DEFAULTS, normalize


class SettingsTests(unittest.TestCase):
    def test_reference_markers_upgrade_once_then_keep_explicit_arrow_choice(self):
        self.assertEqual(normalize({"candidate_style": "arrows"})["candidate_style"], "lines")
        self.assertEqual(normalize({"candidate_style": "arrows", "candidate_marker_version": 1})["candidate_style"], "arrows")
        self.assertEqual(normalize(normalize({"candidate_style": "arrows"}))["candidate_style"], "lines")

    def test_classic_migration_is_once_only_and_keeps_other_preferences(self):
        upgraded = normalize({"theme": "Forest", "hash_mb": 1024, "analysis_menu_version": 1,
                              "multipv": 6, "show_clocks": False})
        self.assertEqual(upgraded["theme"], "Classic")
        self.assertEqual(upgraded["appearance_version"], 1)
        self.assertEqual(upgraded["hash_mb"], 1024)
        self.assertEqual(upgraded["multipv"], 6)
        self.assertFalse(upgraded["show_clocks"])
        self.assertEqual(normalize(upgraded), upgraded)
        self.assertEqual(normalize({"theme": "Walnut"})["theme"], "Walnut")
        self.assertEqual(normalize({"theme": "Slate"})["theme"], "Slate")
        self.assertEqual(normalize({"theme": "Forest", "appearance_version": 1})["theme"], "Forest")

    def test_clock_visibility_is_a_validated_boolean(self):
        self.assertTrue(normalize({"show_clocks": "false"})["show_clocks"])
        self.assertTrue(normalize({"show_clocks": 0})["show_clocks"])
        self.assertFalse(normalize({"show_clocks": False})["show_clocks"])
        self.assertFalse(normalize({"show_raw_pgn": "yes"})["show_raw_pgn"])
        self.assertTrue(normalize({"show_raw_pgn": True})["show_raw_pgn"])
        self.assertFalse(normalize({"expand_pv": "true"})["expand_pv"])
        self.assertTrue(normalize({"expand_pv": True})["expand_pv"])
        self.assertTrue(normalize({"wheel_game_moves": "false"})["wheel_game_moves"])
        self.assertFalse(normalize({"wheel_game_moves": False})["wheel_game_moves"])
        self.assertFalse(normalize({"wheel_analysis_moves": False})["wheel_analysis_moves"])
        self.assertEqual(normalize({"piece_set": "Original"})["piece_set"], "Original")
        self.assertEqual(normalize({"piece_set": "missing"})["piece_set"], "Cburnett")

    def test_menu_migration_preserves_effective_line_count(self):
        self.assertEqual(normalize({"analysis_kind": "infinite", "multipv": 3})["multipv"], 1)
        self.assertEqual(normalize({"analysis_kind": "explore", "multipv": 6})["multipv"], 6)
        self.assertEqual(normalize({"analysis_kind": "bounded", "multipv": 6, "analysis_menu_version": 1})["multipv"], 6)
    def test_corrupt_preferences_recover_with_bounded_limits(self):
        self.assertEqual(normalize(None), DEFAULTS)
        result = normalize({"mode": "broken", "hash_mb": 100000, "analysis_depth": -5,
                            "analysis_seconds": float("nan"), "coordinates": "yes", "light": True,
                            "external_path": ["not a string"]})
        self.assertEqual(result["mode"], "analysis")
        self.assertEqual(result["hash_mb"], 65536)
        self.assertEqual(result["analysis_depth"], 1)
        self.assertEqual(result["analysis_seconds"], 3.0)
        self.assertIs(result["coordinates"], True)
        self.assertIs(result["light"], True)
        self.assertEqual(result["external_path"], "")
