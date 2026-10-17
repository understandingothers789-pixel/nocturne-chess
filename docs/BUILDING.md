# Windows 11 desktop builds · 0.5.1

[Download the verified 0.5.1 Windows ZIP](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39007159403/artifacts/12091413076).

Alternatively, select the successful **Nocturne-0.5.1-Windows-x64-unsigned** artifact from
[Windows Actions](https://github.com/understandingothers789-pixel/nocturne-chess/actions/workflows/windows.yml).
Sign into GitHub, download, Extract All, then open **Nocturne/Nocturne.exe**.
Keep the full folder. No Python, compiler or batch launcher is needed to play/analyze.
You select your own Stockfish executable from the Engine menu.

Windows run 39007159403 succeeded for commit c053f15ed8b6ed692416767ed92b0c297a95b1dc.
Both test runs passed 104 tests with 5 skips; Ruff, PyInstaller and both packaged
smoke checks passed. The unsigned artifact is 53,200,607 bytes, retained until
2026-11-16. SHA-256:
`ee9c8ee2ad6edbc43185a86e72cd1170185e524c6694bd62ceb43024b93d8ed8`.

## Reproducible Windows build

Install Python 3.12 x64 with its Python launcher. In a source checkout:

```text
py -3.12 scripts/build_windows.py --build-only
```

The Python build creates `.venv-build`, installs pinned runtime/build/validation
dependencies, installs the project, runs Ruff and full unittest discovery,
renders the icon, runs PyInstaller and launches the packaged app for smoke checks.
A second smoke connects the packaged GUI to the development-only protocol fixture
using the build environment's Python. Neither that interpreter nor the fixture
is a bundled chess engine. A failing check stops the build. The source ZIP includes
the installed python-chess Python source and notices.

Outputs:

- `dist/Nocturne/Nocturne.exe`: windowed native GUI plus `_internal` shared libraries.
- `dist/Nocturne-0.5.1-source.zip`: source, tests, documentation, rules-library source.

No C compiler is required for the new external-only GUI. The prior custom UCI
executable/native table reader are not part of this distribution. Source installation
also supports `python -m nocturne` after installing runtime requirements.

Build dependencies need network access once unless a matching wheelhouse is prepared.
The application uses local data and local UCI processes during normal operation.
No Stockfish executable or table file is downloaded by the application/build.

## CI and release status

The checked-in Windows workflow performs validation, builds the actual Windows
executable, runs the packaged smoke checks and uploads the portable directory plus
source archive for 30 days. Creating a workflow file is not evidence it ran: actual
run IDs/results are recorded in PROGRESS.md and the README download link.
Unsigned test builds are explicitly authorized for this project; they may trigger
Windows publisher/reputation prompts. No bypass or Windows policy change is supplied.

For a separately signed release, sign the native files using your legitimate
certificate, then run the Python builder's `--package-signed --signtool PATH` mode.
It verifies signatures with the Windows SDK before making a signed-release ZIP.
Signing credentials/certificates are not bundled. Never copy the EXE alone.

## Linux development checks

```sh
QT_QPA_PLATFORM=offscreen python -m pytest -q
python -m ruff check src tests scripts
QT_QPA_PLATFORM=offscreen python scripts/capture_preview.py --simulate
```

`--simulate` explicitly labels screenshots as UCI transport test data, not measured
Stockfish analysis. `--engine /path/to/engine` uses a supplied actual engine instead.
The Linux environment cannot produce a Windows executable; native Windows CI does.
