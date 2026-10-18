# Windows 11 desktop builds · 0.5.7.10

0.5.7.10 native build/validation is pending. It adds softer distinct move colors,
quieter board highlights and wheel navigation. The prior verified download is below.

[Download Windows 0.5.7.9](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39100427444/artifacts/12126700388). Extract All and open **Nocturne/Nocturne.exe**.
This build adds equal-width padded SAN targets and Dev → Expand analysis beyond
three rows. Source `439b2dc0ccf6a1c97f7e1dbbb32fa2d5b351859d` passed run
39100427444/job 117595398583: both native suites ran 165 tests, **160 passed /
5 optional skips**, in 74.675s and 82.054s. Ruff passed twice, PyInstaller and
both frozen launch checks passed. Artifact 12126700388: 55,631,228 bytes,
retained until 2026-11-17. SHA-256:
`5d5ed7b16311c46faae08e2e92afe923a29e481a780c51bd356c38e9fed1c3d0`.
Only documentation changed after this tested application commit.

[Previous Windows 0.5.7.8 download](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39099441736/artifacts/12124934909).
This version removes analysis-panel badges/rank colors and softens White/Black
text tints, preserving the approved board renderer exactly. Source commit
6e12832ff813f74c4946d0cb018e04e6c698fbf8 passed Windows run 39099441736/job
117592505281: 163 tests twice, 158 passed/5 optional skips each, in 134.600s and
137.800s. Ruff passed twice; packaging and both frozen launch checks passed.
Artifact 12124934909 is 55,392,327 bytes, retained until 2026-11-17. SHA-256:
`0ca9a00c0e5470b6f068bfcefb9ce3a7114352d3e7df523a935e9b7bd0501ba7`.

## Earlier fallback builds

Three cumulative feature commits have separate Windows artifacts:

1. [0.5.7.5: live Studio previews](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39097285528/artifacts/12125655113).
2. [0.5.7.6: previews and MultiPV circles/colors](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39097588959/artifacts/12125422408).
3. [0.5.7.7: all above plus clean Game Moves/raw PGN](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39098023371/artifacts/12125303892).

Select the matching versioned artifact after the workflow succeeds. The 0.5.7.5
run passed both 160-test Windows runs (155 passed/5 skipped each), and 0.5.7.6
passed both 162-test runs (157 passed/5 skipped each). Both passed packaged launch
checks. The last run passed 163 tests twice (158 passed/5 optional skips each),
Ruff and both frozen launch checks for source 9236c785e9cded1ea7b39e3f2693ac9077ce6db4.
Final run 39098023371/job 117588388622 took 113.465s / 128.494s for the suites.
Artifact 12125303892 is 55,156,789 bytes; SHA-256:
`221126c71b044e1b8f5f946af5e1aaf41bf902127db7e83c2d25e58b64644ba0`.
The existing unsigned packaging/build tools are retained for all three downloads;
Windows Smart App Control acceptance cannot be established by CI.

## Previously verified baseline

[Download the tested, unsigned **Nocturne-0.5.7.4 Windows ZIP**](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39096484337/artifacts/12125455189).
Sign into GitHub, download, Extract All, then open **Nocturne/Nocturne.exe**.
Keep the full folder. No Python, compiler or batch launcher is needed to play/analyze.
You select your own Stockfish executable from the Engine menu.

The previous 0.5.7.4 Windows run 39096484337 succeeded for source commit
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
- `dist/Nocturne-0.5.7.10-source.zip`: source, tests, documentation, rules-library source.

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
