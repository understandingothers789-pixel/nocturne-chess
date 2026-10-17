import unittest

from nocturne.settings import DEFAULTS, normalize


class SettingsTests(unittest.TestCase):
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
