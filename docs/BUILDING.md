# Windows 11 desktop builds · 0.5.7.4

[Download the tested, unsigned **Nocturne-0.5.7.4 Windows ZIP**](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39096484337/artifacts/12125455189).
Sign into GitHub, download, Extract All, then open **Nocturne/Nocturne.exe**.
Keep the full folder. No Python, compiler or batch launcher is needed to play/analyze.
You select your own Stockfish executable from the Engine menu.

Windows run 39096484337 succeeded for source commit
d020afff00f871f23ccea7c390f27865bf85b964. Both native runs passed 154 tests with
5 optional skips (83.309s / 92.496s). Ruff passed twice. PyInstaller and both
packaged smoke checks passed, including external-UCI review. The artifact is
54,697,193 bytes, retained until 2026-11-17. SHA-256:
`8d4a33a54066c972c0f1dc71b1ac83e55ad74781b27771d5d4c7a7d57de4ca66`.

Live authenticated Lichess data requires a user session token. Separate live
connectivity checks distinguish protected responses from actual returned data;
a green workflow alone is not evidence of successful API data retrieval.
The current build also queried live ChessDB successfully (29 legal moves);
Lichess reported its authentication requirement. No desktop application code
changed after the passing build.

## Appearance, clocks and Windows trust status

0.5.7.3 adds neutral charcoal/light styling, Classic brown/cream and Grey boards,
a one-time legacy-default migration, and saved Display → Clocks visibility.
The working Cburnett pieces, three-line PV slots, UCI/rules/game model, build
script/specification and dependencies are retained. Timed Play clocks continue
when hidden; Analysis pauses them and untimed games show infinity. Configure a
time control in File → New game in a playing mode. 0.5.7.4 reads standard PGN
`[%clk]` annotations and shows the last recorded time for each side at the selected
mainline or variation position. Missing values use an em dash; annotations remain
read-only and do not create a running clock. See the workflow result for current
native Windows validation evidence.

[Working Windows 0.5.7.3 download](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39095336406/artifacts/12124810527) remains available as a fallback.
These are unsigned test builds. The user confirms 0.5.7.2 runs on their computer;
acceptance of the new executable on that setup is unverified here. No signing,
certificate, launcher or security-policy change is included. Manual Windows DPI
and narrow Play-sidebar layout checks remain open; see TODO/PROGRESS.

## Reproducible Windows build

Install Python 3.12 x64 with its Python launcher. In a source checkout:

```text
py -3.12 scripts/build_windows.py --build-only
```

The Python build creates `.venv-build`, installs pinned runtime/build/validation
dependencies, installs the project, runs Ruff and full unittest discovery,
renders the icon, runs PyInstaller and launches the packaged app for smoke checks.
A second smoke connects the packaged GUI, completes a two-move Game Review and
checks full accuracy coverage using the development-only protocol fixture
using the build environment's Python. Neither that interpreter nor the fixture
is a bundled chess engine. A failing check stops the build. The source ZIP includes
the installed python-chess Python source and notices.

Outputs:

- `dist/Nocturne/Nocturne.exe`: windowed native GUI plus `_internal` shared libraries.
- `dist/Nocturne-0.5.7.4-source.zip`: source, tests, documentation, rules-library source.

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

### Standalone database connectivity check

Run `python scripts/check_explorer_api.py` from a source install, or use the
manual **Live database connectivity** workflow. It queries one fixed opening
position, reports Lichess authentication requirements without a user token, and
checks ChessDB independently. It never accepts or logs tokens.

Connectivity-only run 39065979799/job 117493627053 passed on Windows for
3a53f9c601a1aec57f754ffcc45007c1882c31de. Masters/player endpoints returned
authentication-required responses; no authenticated data claim is made. ChessDB
returned valid JSON containing 29 locally validated legal moves for 1.e4 e5.
The UTF-8 diagnostic completed without callback errors.
