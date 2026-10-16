"""Create a reviewable source archive without environments, caches or local games."""

from pathlib import Path
import zipfile

from nocturne import __version__

LAUNCHER_SUFFIXES = frozenset((".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".wsf", ".wsh", ".hta", ".scr", ".com"))


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "dist" / f"Nocturne-{__version__}-source.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    files = []
    for name in ("pyproject.toml", "Nocturne.spec", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md",
                 "CHANGELOG.md", "TODO.md", "PROGRESS.md", ".gitignore",
                 "requirements.txt", "requirements-dev.txt", "requirements-build.txt"):
        files.append(root / name)
    for name in ("src/nocturne", "tests", "scripts", "docs", "benchmarks", "licenses", ".github"):
        files.extend(path for path in (root / name).rglob("*") if path.is_file()
                     and "__pycache__" not in path.parts and path.suffix != ".pyc")
    launchers = [p.relative_to(root).as_posix() for p in files if p.suffix.lower() in LAUNCHER_SUFFIXES]
    if launchers:
        raise RuntimeError("Windows script launchers are excluded from the source archive: " + ", ".join(launchers))
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            archive.write(path, f"Nocturne-{__version__}/" + path.relative_to(root).as_posix())
    print(f"Created {output} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
