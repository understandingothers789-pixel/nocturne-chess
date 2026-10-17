"""Packaging policy tests; real Authenticode trust is verified only on Windows."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import build_windows


class WindowsPackagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dist = Path(self.tmp.name)
        for name in build_windows.APPLICATIONS:
            directory = self.dist / name
            directory.mkdir()
            (directory / f"{name}.exe").write_bytes(b"test fixture; not a real executable")
        (self.dist / "Nocturne" / "runtime.dll").write_bytes(b"native library fixture")

    def test_failed_signature_does_not_create_a_release(self):
        error = subprocess.CalledProcessError(1, "signtool")
        with patch.object(build_windows, "run", side_effect=error):
            with self.assertRaisesRegex(build_windows.BuildError, "Authenticode verification failed"):
                build_windows.package_signed(self.dist, "0.3.0", "signtool.exe")
        self.assertEqual(list(self.dist.glob("*.zip")), [])

    def test_script_launchers_are_rejected_before_native_verification(self):
        for suffix in (".BAT", ".cmd", ".ps1", ".vbs"):
            launcher = self.dist / "Nocturne" / ("launcher" + suffix)
            launcher.write_text("test fixture")
            with self.subTest(suffix=suffix), patch.object(build_windows, "run") as run:
                with self.assertRaisesRegex(build_windows.BuildError, "excluded"):
                    build_windows.package_signed(self.dist, "0.3.0", "signtool.exe")
                run.assert_not_called()
            launcher.unlink()

    def test_all_native_files_must_verify_before_packaging(self):
        with patch.object(build_windows, "run") as run, patch.object(build_windows, "smoke_test") as smoke:
            output = build_windows.package_signed(self.dist, "0.3.0", "signtool.exe")
        checked = {call.args[0][-1].name for call in run.call_args_list}
        self.assertEqual(checked, {"Nocturne.exe", "runtime.dll"})
        self.assertTrue(all(call.args[0][1:5] == ["verify", "/pa", "/all", "/v"] for call in run.call_args_list))
        self.assertTrue(all("/tw" in call.args[0] for call in run.call_args_list))
        smoke.assert_called_once_with(self.dist)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(len(archive.namelist()), 2)
            self.assertIsNone(archive.testzip())

    def test_failed_smoke_check_prevents_release_archive(self):
        with patch.object(build_windows, "run"), patch.object(build_windows, "smoke_test", side_effect=build_windows.BuildError("smoke failed")):
            with self.assertRaisesRegex(build_windows.BuildError, "smoke failed"):
                build_windows.package_signed(self.dist, "0.3.0", "signtool.exe")
        self.assertEqual(list(self.dist.glob("*.zip")), [])

    def test_missing_entry_point_prevents_release(self):
        (self.dist / "Nocturne" / "Nocturne.exe").unlink()
        with self.assertRaisesRegex(build_windows.BuildError, "Missing application executable"):
            build_windows.verify_release_files(self.dist, "signtool.exe")
