"""Resource admission, including replacement of an existing large hash table."""

from dataclasses import asdict
import unittest
from unittest.mock import patch

from nocturne.engine.uci_types import parse_option
from nocturne.gui.engine_resources import validate_resource
from nocturne.gui.hardware import hash_budget_mb


class ResourceTests(unittest.TestCase):
    def test_custom_hash_uses_engine_bounds_and_memory_budget(self):
        option = parse_option("option name Hash type spin default 16 min 1 max 8192")
        profile = {"options": {"Hash": asdict(option)}, "values": {}}
        with patch("nocturne.gui.engine_resources.hash_budget_mb", return_value=1024):
            self.assertEqual(validate_resource(profile, "Hash", 768), 768)
            self.assertEqual(validate_resource(profile, "Hash", None), 16)
            for invalid in (0, 1025, 8193, "64\nquit"):
                with self.assertRaises(ValueError):
                    validate_resource(profile, "Hash", invalid)
        with self.assertRaises(ValueError):
            validate_resource(profile, "Threads", 2)

    def test_existing_hash_credit_still_reserves_system_memory(self):
        pages_per_mb = 1048576 // 4096
        values = {"SC_PAGE_SIZE": 4096, "SC_PHYS_PAGES": 32768 * pages_per_mb,
                  "SC_AVPHYS_PAGES": 6144 * pages_per_mb}
        with patch("nocturne.gui.hardware.os.name", "posix"), patch(
            "nocturne.gui.hardware.os.sysconf", side_effect=values.__getitem__, create=True
        ):
            self.assertEqual(hash_budget_mb(), 5120)
            self.assertEqual(hash_budget_mb(4096), 9216)
            self.assertEqual(hash_budget_mb(32768), 28672)
