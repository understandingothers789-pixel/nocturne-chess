import unittest

from nocturne.settings import DEFAULTS, normalize


class SettingsTests(unittest.TestCase):
    def test_candidate_arrow_loss_preferences_default_and_normalize(self):
        self.assertFalse(DEFAULTS["candidate_loss_arrows"])
        self.assertEqual((DEFAULTS["candidate_arrow_green_cp"],
                          DEFAULTS["candidate_arrow_yellow_cp"]), (20, 50))
        settings = normalize({"candidate_loss_arrows": True,
                              "candidate_arrow_green_cp": 35,
                              "candidate_arrow_yellow_cp": 25})
        self.assertTrue(settings["candidate_loss_arrows"])
        self.assertEqual(settings["candidate_arrow_green_cp"], 35)
        self.assertEqual(settings["candidate_arrow_yellow_cp"], 35)
        self.assertEqual(normalize({"candidate_arrow_green_cp": "20"})[
            "candidate_arrow_green_cp"], 20)

    def test_auto_evaluation_and_navigation_preferences(self):
        self.assertEqual(DEFAULTS["auto_eval_nodes"], 200_000_000)
        self.assertEqual(DEFAULTS["analysis_nodes"], 1_000_000_000)
        self.assertEqual(DEFAULTS["auto_play_nodes"], 10_000_000)
        self.assertEqual(DEFAULTS["auto_eval_limit_version"], 2)
        self.assertEqual(DEFAULTS["analysis_kind"], "nodes")
        self.assertFalse(DEFAULTS["reanalyze_on_navigation"])
        settings = normalize({"auto_eval_nodes": 3_000_000_000, "reanalyze_on_navigation": True})
        self.assertEqual(settings["auto_eval_nodes"], 2_000_000_000)
        self.assertTrue(settings["reanalyze_on_navigation"])
        self.assertFalse(normalize({"reanalyze_on_navigation": "yes"})["reanalyze_on_navigation"])

    def test_new_search_defaults_and_one_time_legacy_upgrade(self):
        defaults = normalize({})
        self.assertEqual(defaults["analysis_kind"], "nodes")
        self.assertEqual(defaults["analysis_nodes"], 1_000_000_000)
        self.assertEqual(defaults["analysis_depth"], 128)
        self.assertEqual(defaults["analysis_seconds"], 600)
        self.assertEqual(defaults["auto_eval_nodes"], 200_000_000)
        old = normalize({"analysis_kind": "infinite", "analysis_nodes": 0,
                         "auto_eval_nodes": 10_000_000})
        self.assertEqual(old["analysis_kind"], "nodes")
        self.assertEqual(old["analysis_nodes"], 1_000_000_000)
        self.assertEqual(old["auto_eval_nodes"], 200_000_000)

    def test_older_auto_evaluation_defaults_upgrade_to_200_million(self):
        for nodes in (10_000_000, 20_000_000):
            migrated = normalize({"auto_eval_nodes": nodes, "auto_eval_limit_version": 1})
            self.assertEqual(migrated["auto_eval_nodes"], 200_000_000)
            self.assertEqual(migrated["auto_eval_limit_version"], 2)
        custom = normalize({"auto_eval_nodes": 75_000_000, "auto_eval_limit_version": 1})
        self.assertEqual(custom["auto_eval_nodes"], 75_000_000)

    def test_corrupt_limit_version_recovers_without_crashing(self):
        for version in (None, "old", [], {}):
            with self.subTest(version=version):
                self.assertEqual(normalize({"auto_eval_limit_version": version})["auto_eval_nodes"],
                                 200_000_000)

    def test_node_defaults_migrate_without_overriding_custom_time_depth_limits(self):
        default_profile = dict(DEFAULTS, analysis_kind="bounded", analysis_limit_version=1)
        self.assertEqual(normalize(default_profile)["analysis_kind"], "nodes")
        custom_profile = dict(default_profile, analysis_depth=20, analysis_seconds=30)
        self.assertEqual(normalize(custom_profile)["analysis_kind"], "bounded")
        self.assertEqual(normalize(dict(DEFAULTS, analysis_nodes=0))["analysis_kind"], "infinite")

    def test_piece_style_migration_keeps_lichess_and_retires_original(self):
        self.assertEqual(normalize({})["piece_set"], "Nibbler")
        lichess = normalize({"piece_set": "Cburnett", "piece_set_version": 1})
        self.assertEqual(lichess["piece_set"], "Lichess")
        self.assertEqual(lichess["piece_set_version"], 2)
        retired = normalize({"piece_set": "Original", "piece_set_version": 1,
                             "theme": "Slate", "multipv": 5,
                             "analysis_menu_version": 1})
        self.assertEqual(retired["piece_set"], "Nibbler")
        self.assertEqual(retired["piece_set_version"], 2)
        self.assertEqual(retired["theme"], "Slate")
        self.assertEqual(retired["multipv"], 5)
        retired["piece_set"] = "Lichess"
        self.assertEqual(normalize(retired)["piece_set"], "Lichess")

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
        self.assertFalse(normalize({"show_raw_pgn": True})["show_raw_pgn"])
        self.assertTrue(normalize({"show_raw_pgn": True, "raw_pgn_version": 1})["show_raw_pgn"])
        self.assertTrue(normalize({"cursor_preview": "true"})["cursor_preview"])
        self.assertTrue(normalize({})["cursor_preview"])
        self.assertTrue(normalize({"cursor_preview": True})["cursor_preview"])
        self.assertTrue(normalize({"cursor_preview": False})["cursor_preview"])
        self.assertFalse(normalize({"cursor_preview": False, "cursor_preview_version": 1})["cursor_preview"])
        self.assertFalse(normalize({"expand_pv": True})["expand_pv"])
        self.assertFalse(normalize({"expand_pv": True, "expand_pv_version": 1})["expand_pv"])
        self.assertTrue(normalize({"expand_pv": True, "expand_pv_version": 2})["expand_pv"])
        self.assertTrue(normalize({"wheel_game_moves": "false"})["wheel_game_moves"])
        self.assertFalse(normalize({"wheel_game_moves": False})["wheel_game_moves"])
        self.assertFalse(normalize({"wheel_analysis_moves": False})["wheel_analysis_moves"])
        self.assertEqual(normalize({"piece_set": "Original", "piece_set_version": 1})["piece_set"], "Nibbler")
        self.assertEqual(normalize({"piece_set": "missing"})["piece_set"], "Nibbler")

    def test_selective_depth_visibility_defaults_off_and_validates_boolean(self):
        self.assertFalse(normalize({})["show_seldepth"])
        self.assertFalse(normalize({"show_seldepth": "true"})["show_seldepth"])
        self.assertTrue(normalize({"show_seldepth": True})["show_seldepth"])

    def test_database_statistics_and_explorer_visibility_are_independent(self):
        self.assertEqual(normalize({})["explorer_source"], "chessdb")
        self.assertFalse(normalize({})["explorer_enabled"])
        # The explorer was previously enabled in some persisted profiles;
        # this version starts them disabled once, then preserves user choice.
        migrated = normalize({"explorer_enabled": True})
        self.assertFalse(migrated["explorer_enabled"])
        opted_in = normalize({"explorer_enabled": True, "explorer_enabled_version": 1})
        self.assertTrue(opted_in["explorer_enabled"])
        self.assertFalse(normalize({})["explorer_statistics"])
        self.assertTrue(normalize({"explorer_source": "masters", "explorer_enabled": False})["explorer_statistics"])
        upgraded = normalize({"explorer_enabled": True})
        self.assertTrue(upgraded["explorer_statistics"])
        upgraded["explorer_enabled"] = False
        self.assertTrue(normalize(upgraded)["explorer_statistics"])
        self.assertFalse(normalize({"explorer_enabled": True, "explorer_statistics": False})["explorer_statistics"])
        self.assertFalse(normalize({"explorer_statistics": "true"})["explorer_statistics"])

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
        self.assertEqual(result["analysis_seconds"], 600.0)
        self.assertIs(result["coordinates"], True)
        self.assertIs(result["light"], True)
        self.assertEqual(result["external_path"], "")
