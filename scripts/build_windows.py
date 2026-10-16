"""Developer-only Windows builds; release archives require trusted native signatures."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
APPLICATIONS = ("Nocturne", "Nocturne-UCI")
NATIVE_SUFFIXES = frozenset((".exe", ".dll", ".pyd"))
LAUNCHER_SUFFIXES = frozenset((".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".wsf", ".wsh", ".hta", ".scr", ".com"))


class BuildError(RuntimeError):
    pass


def run(arguments, **kwargs):
    return subprocess.run([str(arg) for arg in arguments], cwd=ROOT, check=True, shell=False, **kwargs)


def smoke_test(dist: Path):
    run([dist / "Nocturne" / "Nocturne.exe", "--smoke-test"], timeout=30)
    result = run([dist / "Nocturne-UCI" / "Nocturne-UCI.exe"], input="uci\nisready\nquit\n",
                 capture_output=True, text=True, encoding="utf-8", timeout=15)
    if not {"uciok", "readyok"}.issubset(result.stdout.splitlines()):
        raise BuildError("The packaged UCI handshake failed")


def build_only(skip_tests=False):
    if sys.version_info[:2] != (3, 12):
        raise BuildError("Run this developer build using Python 3.12 x64")
    run([sys.executable, "-m", "venv", ROOT / ".venv-build"])
    python = ROOT / ".venv-build" / "Scripts" / "python.exe"
    run([python, "-m", "pip", "install", "-r", "requirements-build.txt"])
    run([python, "-m", "pip", "install", "--no-deps", "--no-build-isolation", "-e", "."])
    if not skip_tests:
        run([python, "-m", "pip", "install", "-r", "requirements-dev.txt"])
        run([python, "-m", "ruff", "check", "src", "tests", "scripts"])
        run([python, "-m", "unittest", "discover", "-s", "tests", "-v"])
    run([python, "scripts/make_icon.py"])
    run([python, "-m", "PyInstaller", "--noconfirm", "--clean", "Nocturne.spec"])
    smoke_test(ROOT / "dist")
    print("Local validation build completed. A signed release archive requires --package-signed.")


def verify_release_files(dist: Path, signtool: str) -> list[Path]:
    """Use Windows SDK Authenticode verification, including certificate trust."""
    files = []
    for name in APPLICATIONS:
        directory = dist / name
        if not (directory / f"{name}.exe").is_file():
            raise BuildError(f"Missing application executable: {name}")
        if directory.is_symlink():
            raise BuildError("Release directories must not be symbolic links")
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise BuildError(f"Symbolic link in release: {path.name}")
            if not path.is_file():
                continue
            if path.suffix.lower() in LAUNCHER_SUFFIXES:
                raise BuildError(f"Windows script/launcher files are excluded from releases: {path.name}")
            files.append(path)
    for path in files:
        if path.suffix.lower() in NATIVE_SUFFIXES:
            try:
                # /pa selects Authenticode trust policy; /all checks every signature.
                # No certificate is imported and no Windows security setting changes.
                run([signtool, "verify", "/pa", "/all", "/v", "/tw", path],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
            except (OSError, subprocess.SubprocessError) as exc:
                raise BuildError(f"Trusted Authenticode verification failed: {path.relative_to(dist)}") from exc
    return files


def package_signed(dist: Path, version: str, signtool: str) -> Path:
    files = verify_release_files(dist, signtool)
    smoke_test(dist)
    output = dist / f"Nocturne-{version}-win64-signed.zip"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=dist, suffix=".zip", delete=False) as stream:
            temporary = Path(stream.name)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in files:
                archive.write(path, path.relative_to(dist).as_posix())
        temporary.replace(output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build-only", action="store_true", help="Compile/test locally; do not create a release ZIP")
    mode.add_argument("--package-signed", action="store_true", help="Verify signed native files and package them")
    parser.add_argument("--signtool", help="Installed Windows SDK signtool.exe path; otherwise use PATH")
    parser.add_argument("--skip-tests", action="store_true", help="Developer builds only; smoke checks still run")
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        parser.error("Windows builds and Authenticode verification must run on Windows")
    try:
        if args.build_only:
            build_only(args.skip_tests)
        else:
            if args.skip_tests:
                parser.error("--skip-tests is only supported with --build-only")
            signtool = args.signtool or shutil.which("signtool.exe")
            if not signtool:
                raise BuildError("Install Windows SDK SignTool or provide --signtool; signing verification is required")
            with (ROOT / "pyproject.toml").open("rb") as stream:
                version = tomllib.load(stream)["project"]["version"]
            output = package_signed(ROOT / "dist", version, signtool)
            print(f"Trusted signature and smoke checks passed: {output}")
    except (BuildError, OSError, subprocess.SubprocessError) as exc:
        print(f"Build stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
