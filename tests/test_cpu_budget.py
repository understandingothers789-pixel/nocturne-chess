"""CPU-rate admission and actual Windows job configuration."""
import ctypes
import os
import subprocess
import sys
import unittest
from ctypes import wintypes

from nocturne.gui.cpu_budget import CpuBudget
from nocturne.settings import normalize


class CpuBudgetTests(unittest.TestCase):
    def test_settings_and_rate_validation(self):
        self.assertEqual(normalize({'engine_cpu_budget': 25})['engine_cpu_budget'], 25)
        for invalid in (0, 101, True, '25'):
            self.assertEqual(normalize({'engine_cpu_budget': invalid})['engine_cpu_budget'], 100)
            with self.assertRaises(ValueError):
                CpuBudget().apply(0, invalid)

    @unittest.skipUnless(os.name == 'nt', 'Windows job-object API')
    def test_real_process_budget_can_change_and_be_disabled(self):
        process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        limiter = CpuBudget()
        try:
            query = limiter.api.QueryInformationJobObject
            query.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
            query.restype = wintypes.BOOL
            for budget in (25, 50, 100, 10):
                limiter.apply(process.pid, budget)
                info = (wintypes.DWORD * 2)()
                self.assertTrue(query(limiter.handle, 15, ctypes.byref(info), ctypes.sizeof(info), None))
                self.assertEqual(info[0], 0 if budget == 100 else 5)
                if budget != 100:
                    self.assertEqual(info[1], budget * 100)
            self.assertIsNone(process.poll())
        finally:
            process.terminate()
            process.wait(timeout=10)
            limiter.close()
        self.assertIsNone(limiter.handle)
