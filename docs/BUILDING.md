# Windows 11 desktop builds · 0.5.8

[Download the tested, unsigned 0.5.8 Windows ZIP](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39083200511/artifacts/12119502466).

**This unsigned developer build has been blocked by Windows Smart App Control.**
Automated build/test success is separate from publisher trust. No trusted signed
Nocturne release is currently available. See the signing status below before
using this download on a computer with Smart App Control enabled.

Alternatively, select the successful **Nocturne-0.5.8-Windows-x64-unsigned** artifact from
[Windows Actions](https://github.com/understandingothers789-pixel/nocturne-chess/actions/workflows/windows.yml).
Sign into GitHub, download, Extract All, then open **Nocturne/Nocturne.exe**.
Keep the full folder. No Python, compiler or batch launcher is needed to play/analyze.
You select your own Stockfish executable from the Engine menu.

Windows run 39083200511 succeeded for GUI commit b1322d643bb57901a854b398f9b1056f48cc1a25.
Both test runs passed 150 tests with 5 skips (84.660s / 106.145s). Ruff,
PyInstaller and both packaged explorer/study/save/UCI/Game Review smoke checks passed.
All six loopback HTTP tests ran on native Windows. The unsigned artifact is
54,608,168 bytes, retained until 2026-11-17. SHA-256:
`00ff5a5ba65e41d8ba6c6a46aa6f7cbb5acea456529aca71e33c4699001b65e2`.

Live authenticated Lichess data requires a user session token. Separate live
connectivity checks distinguish protected responses from actual returned data;
a green workflow alone is not evidence of successful API data retrieval.
The current build also queried live ChessDB successfully (29 legal moves);
Lichess reported its authentication requirement. No desktop application code
changed after the passing build.

## Smart App Control and signing status

A user reported that Smart App Control blocked Nocturne because it was unsigned.
This is a release blocker for that Windows configuration, not evidence of a
chess-rule or GUI-test failure. The CI runners' successful smoke checks do not
test the user's Smart App Control policy.

The Windows workflow currently produces an explicitly unsigned test artifact.
No code-signing certificate, signing service identity or signing credentials are
configured in this workspace. The existing `--package-signed` mode verifies
Authenticode signatures using SignTool; it does not sign files, create a
certificate or enroll a publisher.

For a distributable signed release, the publisher must first obtain access to a
legitimate code-signing certificate/service with the required identity checks.
Sign the executable and any shipped native dependencies requiring signatures,
use `--package-signed` to verify and package them, then validate the download on
Windows 11 with Smart App Control enabled. A signature alone is not a guarantee
that every Windows trust/reputation policy will accept the application.

Rebuilding, renaming or re-zipping the unsigned files does not supply a trusted
publisher signature. A self-signed certificate is not equivalent to a publicly
trusted publisher identity. Do not disable Smart App Control, import a new trust
root or change execution/security policies to use this developer build. A signed
download will be linked only after signing and acceptance checks actually run.

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
- `dist/Nocturne-0.5.8-source.zip`: source, tests, documentation, rules-library source.

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
