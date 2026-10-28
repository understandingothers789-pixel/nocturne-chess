"""Run every test module in a fresh process to isolate native Qt lifetimes."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pattern", default="test_*.py")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    modules = sorted((root / "tests").glob(args.pattern))
    if not modules:
        parser.error("No test modules matched")
    total = skipped = failures = 0
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    for module in modules:
        print(f"Running {module.name} in an isolated process", flush=True)
        result = subprocess.run(
            [sys.executable, "-X", "faulthandler", "-m", "unittest", "discover",
             "-s", "tests", "-p", module.name, "-v"],
            cwd=root, env=env, capture_output=True, encoding="utf-8", errors="replace",
        )
        output = result.stdout + result.stderr
        print(output, end="", flush=True)
        counts = re.findall(r"Ran (\d+) tests? in", output)
        total += int(counts[-1]) if counts else 0
        skips = re.findall(r"OK \(skipped=(\d+)\)", output)
        skipped += int(skips[-1]) if skips else 0
        if result.returncode or not counts:
            failures += 1
    print(f"Isolated suite: {total} tests, {skipped} skipped; {failures} failed modules", flush=True)
    return int(failures != 0)


if __name__ == "__main__":
    sys.exit(main())
