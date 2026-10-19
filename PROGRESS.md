# Development log — Nocturne Chess

This log records executed work. A written feature or an unexecuted test is not a
passing result. All commands are run from the repository root unless specified.

## 2026-10-16 — Architecture and initial rules implementation

**Created:** `pyproject.toml`, package boundaries under `src/nocturne`,
`docs/ARCHITECTURE.md`, `README.md`, `TODO.md`, `LICENSE`, `.gitignore`.

**Decisions:** Python 3.12 + native PySide6. Independent 0x88 rules core, separate
search and persistence layers. A process boundary will keep CPU search outside
the GUI interpreter. No external engine is required for custom-engine play.

**Implemented:** `core/board.py` (legal moves, reversible state, FEN, incremental
Zobrist hashing, repetition, automatic and claimable draws); `core/notation.py`
(SAN, main-line PGN). Added initial `tests/test_rules.py` and `test_oracle.py`.

**Executed:** created `.venv`; ran the initial-position perft for depths 0–3:
`1, 20, 400, 8902`, all exact. Checked the restored initial hash against full
recomputation: equal.

**Environment blocker:** PySide6, pytest, python-chess and PyInstaller are not
preinstalled. Default pip installation failed with a sandbox proxy connection
denial. Additional-permission and escalated installation requests were
interrupted before execution completed. No dependency install, Qt launch,
pytest run, or Windows build has succeeded or been claimed.

**Next:** add standard-library validation so rules and search can be tested
without downloads; run the reference perft suite and edge cases. Then implement
the native board and verify it if dependencies become available.

**Known limits:** general dead-position proof is deferred (conservative standard
insufficient-material recognition exists). PGN import preserves the main line,
not comments or variation trees. Advanced pruning and strength ratings are gated
on evidence.

## 2026-10-16 — Rules validation and authoritative game model

**Created/modified:** converted the rules tests to standard-library `unittest`;
made the independent oracle optional; added `core/game.py`, `storage.py`, and
`tests/test_game_storage.py`.

**Executed:** `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`.
Latest result: **24 tests run, 23 passed, 1 skipped**, no failures. The skipped
test needs the uninstalled python-chess oracle. The perft subtests matched:

| Position | Exact counts by depth |
| --- | --- |
| Start | 20 / 400 / 8,902 / 197,281 |
| Kiwipete | 48 / 2,039 / 97,862 |
| Rook/pawn endgame | 14 / 191 / 2,812 / 43,238 |
| Castling/promotion | 6 / 264 / 9,467 |
| Tactical promotion | 44 / 1,486 / 62,379 |
| Middlegame | 46 / 2,079 / 89,890 |

**Covered:** pinned en passant and repetition-key normalization, castling transit
attacks, underpromotions, mate precedence, threefold/fivefold and 50/75-move
rules, random make/unmake + hash recomputation, SAN, PGN, history branching,
deterministic clock accounting, timeout with insufficient mating material,
transactional save/resume and corrupted-record reporting.

**Found/fixed:** the first PGN round-trip test failed because it compared sparse
input headers with the required tags added on export. It now checks preserved
headers, moves, starting position and result. This was a test assertion error;
the notation implementation did not need a change.

**Next:** native board painting, real move input, promotion dialog, history and
window layout. Qt runtime validation remains pending dependency installation.

## 2026-10-16 — Native desktop foundation source

**Created:** `gui/board.py`, `gui/theme.py`, `gui/dialogs.py`, `gui/window.py`,
`__main__.py`, original vector icon and 12 original SVG chess pieces.

**Implemented:** resizable vector board, click/drag input, legal/capture/check
highlights, explicit promotion menu, last move, animation, right-button arrows
and marks, coordinates, flipping; two-player game shell, clocks, history,
undo/redo, settings, SQLite library and FEN/PGN interchange.

**Executed:** `PYTHONPATH=src .venv/bin/python -m compileall -q src` passed.
`PYTHONPATH=src .venv/bin/python -m nocturne` exited with the expected missing
PySide6 dependency message. **This is not a successful GUI launch.** A second
installer (`uv`, using a writable workspace cache) also confirmed sandbox network
denial. No further permission-gated installation retry is being used to block
independent development work.

**Status:** M1 rules acceptance is met by the executed core tests. Native runtime
acceptance is still open, so M1 is not marked fully complete. Engine source and
CLI validation can proceed independently while that environment gate is open.

**Next:** tapered evaluation, interruptible alpha-beta search and reproducible
CLI tests. Replace interim engine UI wiring with working process-backed search
before any release.

## 2026-10-16 — Independent engine, UCI and process execution

**Created:** `engine/evaluate.py`, `search.py`, `uci.py`, `external.py`,
`worker.py`, `benchmark.py`, `gui/engine.py`, `gui/widgets.py`, search/protocol/
process tests. Connected the window to the process controller and added sampled
evaluation, principal variation, telemetry, and the benchmark dialog.

**Implemented:** tapered handcrafted evaluation; iterative negamax alpha-beta,
check-aware quiescence, ordered captures, killer/history ordering, distance-to-
mate scores, history-aware Zobrist transposition table, PV, time/node budgets,
legal cancellation fallback, and bounded lower-difficulty move selection. PVS
is experimental and disabled by default. No null move, LMR, SEE, futility or NNUE
claims are made.

**Executed:** full unittest suite: **41 run, 40 passed, 1 optional oracle
skipped**, no failures (8.733 s on this run). This includes a real spawned worker,
cooperative cancellation, UCI search/stop, running Nocturne through its external
UCI adapter, and rejecting a deliberately illegal external best move. Stockfish
itself is not installed and has not been tested here.

**Measured:** `python -m nocturne.engine.benchmark --depth 3 --repeat 3 --variants
default no-tt no-ordering no-killers pvs --output benchmarks/baseline-0.3.0.json`.
Five exact FENs and raw runs are recorded, with environment metadata. The sum of
per-position median times was 10.055 s for default and 10.113 s for PVS; PVS was
faster in Kiwipete and slower in the tactical/middlegame positions. Completed
depth-3 runs agreed on scores. Some disabled-ordering/killer runs hit the 10 s
cap and are explicitly not equal-depth comparisons. **PVS stays off.**

**Self-play smoke:** two games, alternating colors, 25 ms/move, 80-ply cap,
default vs PVS: default won one by checkmate; one was unfinished at the cap.
Raw PGNs/results are in `benchmarks/selfplay-smoke-0.3.0.json`. This sample is far
too small for strength conclusions and is not an Elo estimate.

**Native runtime gate:** GUI code compiles, but PySide6 installation and actual
window execution are still pending. No GUI synchronization tests have passed
yet. The process protocol itself is exercised without Qt.

**Next:** integrated GUI regressions (when dependency access is approved), audit
settings/resume and stale-result paths, deeper perft, and Windows build files.

## 2026-10-16 — Native runtime gate resolved; M1–M3 acceptance

**Environment:** user approved dependency installation. Installed the pinned
PySide6 6.8.3, oracle, pytest, Ruff and PyInstaller dependencies successfully;
installed this package in editable mode without additional downloads. Earlier
missing-dependency notes above describe the earlier state, not the current one.

**Executed:**

* `NOCTURNE_DEEP_TESTS=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_deep_perft.py -v`:
  both tests passed, 54.710 s. Start depth 5 = **4,865,609**; Kiwipete depth 4 =
  **4,085,603**.
* `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`: latest **55 passed,
  2 skipped** in 9.22 s. The two skips are the opt-in deep perft tests just run
  separately. Native GUI and independent python-chess tests now execute.
* `.venv/bin/ruff check src tests scripts`: passed.
* `QT_QPA_PLATFORM=offscreen .venv/bin/python -m nocturne --smoke-test`: exit 0.
  This starts the real window, makes a human move, waits for the process-backed
  AI response, and validates the displayed board hash.

**Native coverage:** click and drag; actual menu-selected knight promotion;
flipped coordinate mapping; annotations; responsive AI with Qt event-loop pulses;
human choosing Black; AI vs AI progression/pause; optional takeback restrictions;
stale-result rejection; saved-game resume; and independent analysis copies.
The oracle compared move sets, FEN, check state, material draws, repetition,
hashes and SAN over 12 seeded games of up to 140 plies.

**Found/fixed:** a duplicate evaluation-bar layout edit caused an import error on
the first Qt run; corrected it and reran. Qt's instance `QMenu.exec` does not
honor the attempted class-method mock, so the promotion test now actually clicks
the knight action in the native menu. Source review also found analysis history
could overwrite the played game's saved record. Analysis now forks to a new ID;
core and GUI regressions prove the original remains intact. Added validated
settings, corrupted-record type checks, future-schema rejection and saved engine
match statistics.

**Visual review:** captured and inspected the real Qt window in
`docs/preview.png` using `scripts/capture_preview.py`. Engine values and the graph
are actual search samples, not fabricated UI data. Compact and light layouts
are being checked separately.

**Milestones:** M1's move-generation/native-play acceptance and M2's custom
engine/native-AI acceptance are met. M3's primary modes, clocks, persistence,
themes and background-processing acceptance are met on Linux/offscreen Qt.
General dead-position proof remains a disclosed rules limitation. Windows-specific
runtime behavior is still pending Windows execution.

**Next:** validate PyInstaller bundles, finish release/readme/known-issue records,
and retain advanced analysis and search work as explicit later milestones.

## 2026-10-16 — Application polish, benchmarks and release configuration

**Created/modified:** `Nocturne.spec`, pinned requirements, Windows PowerShell
builder, Windows CI workflow, icon generator, temporary-data app smoke test,
source archive script, release/readme/build/benchmark documentation, licenses,
and additional Qt/worker regressions.

**Executed:** latest `.venv/bin/ruff check src tests scripts` passed.
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`: **59 passed,
2 opt-in deep-perft skips**, 8.78 s. Deep perft was separately executed above.
This includes native mode/clock/history/worker synchronization tests, real
promotion selection, benchmark worker progress/reporting and the independent
oracle. A pure Python wheel was also built offline successfully.

**Found/fixed during visual/runtime review:** the 1024×660 engine panel compressed
its controls. Metrics now scroll while source/analysis controls keep their size;
a regression checks their accessibility. Improved light-theme graph/tab
contrast. A delayed callback could restart search after closing a window; a
closing-state guard and regression prevent it. Custom player names in AI mode
are now honored instead of being overwritten by default display names.

**Visual artifacts:** actual rendered captures at `docs/preview.png`,
`docs/preview-light.png` and `docs/preview-compact.png`; no fabricated scores.

**Packaging executed:** rendered the multi-size ICO; built both Linux executables
using PyInstaller 6.12.0 and the checked-in specification. Ran the packaged GUI
with `--smoke-test`: exit 0. Ran the packaged UCI binary through handshake,
readiness and depth-2 search; validated its returned `b8c6` move after `e2e4`
using the custom rules core. Rebuilding final artifacts after licensing/data
updates is the last release step.

**Windows status:** full build configuration and CI recipe are supplied, including
post-build GUI/UCI checks. Neither Windows execution nor the GitHub workflow has
been run here. This is an explicitly disclosed release gate, not a passing test.

**Remaining scope:** M4 pruning/strength research and M5 advanced analysis stay
open in `TODO.md`. General dead-position proof, Multi-PV, annotation-preserving
variation trees and automated game review are not claimed as implemented.

## 2026-10-16 — Final artifact validation

**Completed:** rebuilt the final GUI and UCI bundles after source/licensing
updates. Packaged GUI `--smoke-test` exited **0**. The final UCI bundle completed
`uci`, `isready`, `position startpos moves e2e4`, `go depth 2`, returned legal
`b8c6`, and exited **0** on `quit`.

**Integrity:** verified the actual runtime's Python license text in both bundles;
verified development `chess` and `pytest` modules are excluded from the Python
application archives. Rebuilt the wheel offline and checked ZIP integrity,
the application ICO, and all 12 vector piece assets. Wheel build succeeded.

**Deliverables:** project source, actual dark/light/compact Qt captures, raw
benchmark and self-play records, a pure Python wheel, tested Linux GUI/UCI
bundles, and complete Windows build configuration. `scripts/package_source.py`
creates a source ZIP containing the code, tests, docs, licenses and benchmark
records, excluding local games, environments and caches. `dist/SHA256SUMS.txt`
records final portable-source/wheel checksums.

**Handoff:** first three application milestones are implemented and exercised;
selected UCI, analysis and measurement tools are also usable. Windows binaries
and the remaining research/advanced-analysis roadmap are explicit follow-up
gates. No unexecuted Windows or strength test is counted as passing.

## 2026-10-16 — Windows launch/distribution constraint

**User preference:** no batch files or launch mechanisms that require bypassing
Windows safety warnings. This supersedes the earlier PowerShell build recipe.

**Changed:** removed `scripts/build_windows.ps1`; added developer-only
`scripts/build_windows.py`; updated `.github/workflows/windows.yml`, source
archiving policy, README, build documentation, TODO and changelog. Player launch
uses the normal Windows application. CI builds/tests internally and no longer
uploads unsigned executable archives.

**Release gate:** a separate packaging step verifies all native `.exe`, `.dll`
and `.pyd` files with Windows SDK SignTool's Authenticode trust policy and
timestamp checking. Failed signatures or smoke checks stop release ZIP creation.
Batch/PowerShell/other Windows script launchers are rejected from distributions.
The builder does not generate/import certificates or change Windows protections.

**Executed so far:** `.venv/bin/ruff check src tests scripts` passed.
`.venv/bin/python -m unittest discover -s tests -p test_windows_packaging.py -v`:
all five packaging-policy tests passed. They cover failed signatures, prohibited
launchers, complete native-file coverage, failed smoke checks and missing entry
points. Signature commands are mocked in these Linux policy tests; actual
Windows certificate trust/signing is not claimed as tested.

**Practical limit:** even valid code signing cannot guarantee no SmartScreen
prompt, because Windows reputation and local policy also apply. No Windows
release is supplied until trusted signing and Windows validation are completed.

**Artifact checks completed:** rebuilt the wheel offline and regenerated the
source ZIP. Both archives passed integrity checks. The source ZIP contains no
batch/PowerShell/other prohibited Windows launcher files, and its active README,
build guide and CI configuration contain no removed build-file reference or
execution-policy bypass command. The wheel's embedded README was refreshed too.
`dist/SHA256SUMS.txt` was regenerated for the updated downloads.

**Remaining gate:** real Windows signing, trust/reputation validation and clean
Windows testing require a Windows release environment and legitimate signing.
The chess/GUI implementation was unchanged by this packaging-only update.

### Windows-build status made explicit

**User need:** obtain a Windows build without batch/PowerShell launchers or
warning-bypass instructions.

**Documentation corrected:** README and `docs/BUILDING.md` now state at the
start that no Windows executable is available, that the existing `dist/Nocturne`
binary is Linux-only, and that the Windows workflow has not run because this
workspace has no GitHub remote. Developer build instructions are explicitly
separated from player instructions. A Windows build, trusted signing identity,
and Windows validation remain prerequisites; SmartScreen reputation cannot be
promised from this environment.

**Verification:** inspected the active docs and repository configuration. No
Git repository/remote is configured in `/workspace`. No Windows build or
signature was produced. The source ZIP is refreshed after these documentation
changes; no chess source or tests changed.

### GitHub repository and first native Windows CI build

**Repository:** https://github.com/understandingothers789-pixel/nocturne-chess

Uploaded the complete 0.3.0 project source, original assets, tests, benchmark
records, licenses, documentation, and Windows workflow. The first GitHub Actions
run completed successfully on a Windows runner:

- Python and pinned dependencies installed successfully.
- Ruff passed.
- Full automated test suite passed.
- PyInstaller built the GUI and UCI Windows executables.
- The builder's packaged GUI and UCI smoke checks passed.

Run: https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/38952576627

**Distribution limit:** the run builds in an ephemeral worker and does not
upload the unsigned executable. There is still no downloadable `.exe`; trusted
code signing, Windows reputation/clean-machine checks, and a deliberate signed
release are outstanding. A valid signature still cannot guarantee no
SmartScreen warning. README and BUILDING.md now reflect the successful run and
the remaining release gate.

### Downloadable Windows executable requested

The user explicitly chose the Windows executable option after being informed
that an unsigned app may show a Windows warning. This supersedes the earlier
restriction on retaining unsigned test builds. No batch/PowerShell launchers
are introduced. The Windows workflow now uploads both complete application
folders as a clearly named unsigned test artifact for 30 days, only after the
existing tests, native build, and smoke checks succeed. PR runs do not upload.
README and BUILDING.md now include download/extract/launch instructions.
Signed-release verification remains separate. Windows CI run 38954107896 completed successfully: Ruff passed; unittest ran
66 tests with OK (skipped=2); PyInstaller built the native GUI/UCI apps; packaged
smoke checks and artifact upload passed. GitHub retained artifact 12070336096
(60,833,471 bytes), named Nocturne-0.3.0-Windows-x64-unsigned, expiring
2026-11-15. The artifact download endpoint also returned the ZIP successfully.
The archive SHA-256 reported by GitHub is
506bb5485415799c541ca55f80b79be85cd36aa6d50b8a6fa4350413636f9056.
README and BUILDING.md now include the direct artifact link. Local source and
wheel archives are refreshed with the documentation; signed-release validation
and manual Windows UI checks remain outstanding.

### 0.3.1 — Nibbler-style menus and PGN text workflow

User requested removal of tooltips, menus closer to Nibbler, and move/PGN
copy/paste without requiring a file. The uploaded nibbler.exe exceeds the
32 MiB transfer limit and was not executed. Instead, inspected the upstream
public menu definitions at https://github.com/rooklift/nibbler (menu translation
template). Implemented menu organization independently; no Nibbler code or
assets are bundled.

Modified window.py, board.py, widgets.py and theme.py: added File, Tree,
Analysis, Display, Engine and Play menus for working features; removed hover
tooltips; added an editable PGN tab with Apply/Copy/Load current controls,
clipboard FEN/PGN import/export, and file-based PGN opening. Text is parsed
before replacing the current game. Dirty PGN drafts survive ordinary refreshes,
and typing/navigation in the editor does not activate board shortcuts.
Updated GUI regression tests, version metadata to 0.3.1, Windows artifact name,
README, BUILDING, TODO and CHANGELOG. No unsupported variation-tree or MultiPV
commands were added. Existing main-line-only PGN limitation remains.

Executed so far: Ruff passed; native offscreen GUI suite: 19 passed in 8.17s.
Full suite, visual inspection and updated native Windows artifact are next.

Visual QA found clipped PGN controls at 1024×660. Fixed the panel spacing,
placed PGN actions in one row, and enforced a readable editor height. Added
regressions for compact control geometry and opening UTF-8/BOM PGN files.
Full suite after the fix: 71 passed, 2 skipped; Ruff passed. Both skipped tests
are optional deep perft checks; rules/search code did not change. Rendered and
inspected updated full-size and compact PGN screenshots using
scripts/capture_preview.py. The PNGs show the real Qt window. Windows CI build
and new executable upload are the remaining verification step.

Also inspected the actual File popup visually and added a mouse-driven menu
opening/clipboard-action regression. Kept explicit menu references in the
window. The final GUI-only rerun passed all 22 tests; Ruff passed. A menu
screenshot helper initially failed when using a temporary QAction list; keeping
the list alive fixed that inspection command. This was not an application
interaction failure.

Final menu review also checked light appearance. Fixed selected-menu text
contrast and visually verified the actual light File popup. This one-line
stylesheet adjustment is included in the final Windows build.

Final native Windows verification completed successfully in run 38960506947
(commit 0ee099158aea3d3056b42fa327b2f2b991fad4cc): Ruff passed; unittest ran
74 tests with OK (skipped=2), meaning 72 passed. The builder repeated the
validation successfully, built both Windows apps and passed packaged GUI/UCI
smoke checks. Artifact 12073040643, Nocturne-0.3.1-Windows-x64-unsigned, uploaded
successfully (60834165 bytes). SHA-256 reported by GitHub:
fed2c5a3e425e8e2744b7913345fc55ea04a67704140377416d93cd75af92fc8.
Download: https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/38960506947/artifacts/12073040643
README and BUILDING now point directly to the verified 0.3.1 artifact. Local
0.3.1 source/wheel archives and their checksums are refreshed. No Windows
launcher scripts are included. The test executable remains unsigned with user
authorization; signing and manual clean-machine UI checks remain outstanding.

### 0.3.2 — Dedicated Analysis layout and reversible hover previews

User requested engine analysis on the left, moves at the bottom, and Nibbler-
style hover previews that restore the current board when the pointer leaves.
Modified window.py, board.py and theme.py; added gui/moves.py for flowing,
linked move text. Analysis hides play-specific chrome and uses horizontal and
vertical splitters: engine left, board right, game moves below. Play retains
its previous layout. History and PV tokens emit hover/click signals. Board
preview state is separate from its authoritative board reference; rendering
uses the preview while the game, clock, history cursor, hashes and search job
are unchanged. History clicks still navigate. Input is blocked during preview.
Leaving, hiding or defocusing the text, replacing a PV or actual position, and
changing workspaces clear previews. PVs remain single-line analysis; MultiPV
and variation trees are still deferred. No tooltips were added.

Executed: existing 22 GUI tests passed before the new regressions. New GUI run
initially had 27 passes/1 failure: the mouse helper needed layout processing
and an off-anchor move before hovering. After fixing the helper, all 28 GUI
tests passed in 10.62s. Ruff passed. Tests cover actual history/PV mouse hover,
restore, current-game/hash/cursor/engine-generation invariants, layout switch,
position and PV replacement, input guards, history clicks and castling/EP/
underpromotion. Inspected full and compact Qt renders; bounded PV text height
keeps the sampled graph visible at full size, with scrolling at compact sizes.
Updated capture script can render a display-only hover and asserts that the
underlying board remains unchanged. Version/docs/build artifact bumped to
0.3.2. Full validation and Windows artifact are next.

Final local full validation: pytest 78 passed, 2 optional deep-perft tests
skipped in 15.93s; Ruff passed. Captured and visually inspected dark, light,
compact and PGN layouts, plus a history hover preview showing a different board
while the real current move remains selected. The capture helper asserts the
actual FEN is unchanged and restored after rendering. Uploading code and
screenshots for native Windows CI/build verification next.

Final native Windows run 38963603278 succeeded for commit
c4161f8ed48e4995fbf85a3721b211beaff0f398. Unittest ran 80 tests with OK
(skipped=2), meaning 78 passed; repeated validation inside the builder also
passed. Ruff, PyInstaller GUI/UCI builds, packaged smoke checks and artifact
upload all passed. Artifact 12073553349: Nocturne-0.3.2-Windows-x64-unsigned,
60881825 bytes, SHA-256 2a2099d4f957f1557c03afeda7e7140b0ab8c0af5f8f8b4400e9190733d5461f.
Verified artifact metadata reports it unexpired. Download:
https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/38963603278/artifacts/12073553349
README and BUILDING point to the new download. Refreshed 0.3.2 source/wheel
archives and checksums; archive integrity and prohibited-launcher exclusions
are checked. The executable remains an explicitly authorized unsigned test
build. Single-PV, main-line PGN and manual clean-Windows UI/signing limitations
remain. No changes to rules/search were needed for this feature.

## 0.4.0 — Variations and Syzygy implementation

Implemented ordered variation nodes, legal validation of every branch, nested
PGN import/export, schema-2 save migration, branch navigation/promotion and
display-only hover on any branch. Existing main-line continuations survive
alternate moves. Added core/GUI regressions. Changed core game/notation, new
core/variation.py, GUI moves/window and tests/test_variations.py.

Added MIT Fathom pinned at c9c6fef0dddc05d2e242c183acf5833149ab676d,
a serialized CPython extension, local folder settings, root WDL/DTZ probes,
worker/UCI/external integration and TB telemetry. Native Windows file opening
uses UTF-8 to CreateFileW. No tablebase or external engine is downloaded by the
application. Build source/licenses/extension are included in packaging; compiled
Linux artifacts and developer tables are excluded from source archives.

Executed: rules/storage 25 passed; initial variation tests 6 passed; existing
GUI 28 passed. Initial full integration found one worker protocol regression
(disabled tablebase message arriving before search info), fixed by emitting
TB messages only when configured. Initial real-table run: 3 passed, 1 failed
because cached directory contents missed newly added DTZ files; fixed by
refreshing native initialization per root probe. GCC native rebuild succeeded
after the environment's missing clang default was overridden.

Full executed command: NOCTURNE_TEST_SYZYGY=/workspace/.tb-test-fixtures
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q: 89 passed, 2 optional
deep-perft skipped in 20.42s. Ruff check src tests scripts passed. Tests include
real WDL/DTZ comparisons against development-only python-chess, Unicode folder,
missing DTZ, corrupt-header diagnostics, cancellation, UCI use, nested branches,
save migration and GUI branch/hover restoration. Fixtures were downloaded only
by an explicit developer script and verified against pinned Git blob checksums.
Only small three-piece tables were available; full five/seven-piece data and
manual Windows interaction remain unverified. Slow native/disk I/O can overrun
the calculation budget before returning; the GUI worker can be terminated.
Windows build/frozen probe validation is next.

Windows attempt 38969963839 failed during native compilation before tests:
MSVC reported C1189, C atomic support not enabled. Added the required
/experimental:c11atomics compiler option alongside /std:c11. No runtime
behavior changed. A second Windows build will validate the correction.
Local unittest also ran 91 tests, OK (skipped=2), 20.276s; source archive
integrity/exclusions and Linux wheel native-reader/license inclusion checked.
Inspected a rendered analysis branch tree showing Bc4 and Nc3 together.

The corrected Windows attempt compiled/installed the native reader, downloaded
verified fixtures, passed Ruff and passed its full test step. Packaging/frozen
smokes remain in progress. Additional executed local differential check used
seed 400 and 120 valid nonterminal KQ/KR/KP three-piece positions: all WDL and
DTZ values matched python-chess's independent Syzygy reader. The Linux native
wheel built successfully and was inspected for reader/license inclusion and
absence of table files.

Windows attempt 38970164641 compiled both apps and passed both full test runs
(91 run, OK skipped=2, 27.973s and 27.706s), but the new frozen tablebase smoke
failed decoding a diagnostic middle dot: redirected Windows UCI stdout used the
legacy code page. Made UCI entry-point stdin/stdout/stderr explicitly UTF-8,
also ensuring non-ASCII Syzygy folder paths survive the transport. The frozen
Syzygy smoke remains the regression check; rebuilding rather than publishing
the failed package.

After the UTF-8 fix: pytest tests/test_tablebase.py tests/test_protocol_worker.py
ran 10 tests, all passed in 0.56s; Ruff passed. A real UCI subprocess with
PYTHONIOENCODING=cp1252 still emitted valid UTF-8 and a tablebase hit. An actual
Qt/background-worker integration probe displayed TB · White wins, produced a
legal PV, and left the analyzed FEN unchanged. Inspected the rendered tablebase
analysis window; labels fit and the board/move layout remains intact.

## 0.4.0 — Verified Windows delivery

Windows run 38970560841 succeeded for commit
882c81f03ffe1d445179bdcd262d74ceff6a2031. Both full unittest runs
ran 91 tests, OK (skipped=2): 89 passed each, in 24.802s and 25.435s.
Ruff, native MSVC compilation, GUI/UCI PyInstaller builds, packaged GUI smoke,
UCI handshake and real frozen Syzygy probe all passed. Upload succeeded.
Artifact 12076786361: Nocturne-0.4.0-Windows-x64-unsigned, 60955462 bytes,
SHA-256 5331154ab441dd9b3d0716e6054630f3eb3ed71b4fc466f743a9d33b03626218.
Metadata reports unexpired, retained until 2026-11-15. Download:
https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/38970560841/artifacts/12076786361

README/BUILDING updated to this verified Windows download. Source archive and
Linux native wheel refreshed locally; source archive integrity and native-source
inclusion checked with generated binaries/table files/script launchers excluded.
Remaining limitations: table fixtures cover three-piece data only; full five/
seven-piece collections and manual Windows desktop interaction are unverified.
PGN comments/NAGs and Multi-PV remain deferred. Native/disk probe I/O is not
hard-interruptible inside the standalone UCI thread; GUI worker processes are
killable. No signed-release claim or playing-strength estimate is made.

## 0.5.0 direction — Stockfish analysis GUI

Read the user's new full specification. It supersedes custom-engine development:
external engines only in the desktop analysis/play path. Inspected Nibbler source
(master 6eb0f066), README, 30 issue entries and 15 pull requests via GitHub.
Created docs/NIBBLER_RESEARCH.md with source evidence, reported vs verified
limitations, license boundary and a justified native Qt migration decision.
Created docs/ANALYSIS_ROADMAP.md with explicit acceptance/deferred checkboxes.
No Nibbler implementation/assets copied. No Stockfish binary is installed here.
Next: persistent asynchronous UCI sessions, engine profiles, MultiPV and Smart Move.

### 0.5 implementation phases — external sessions, rules and study UI

Created engine/uci_types.py (options, score/bound/WDL types, external limits),
gui/uci_connection.py (persistent asynchronous QProcess), engine.py controller,
engine_manager.py (profiles and advertised editors), hardware.py (Hash admission),
candidates.py (interactive MultiPV rows), core/rules.py (python-chess adapter),
and gui/setup_position.py (validated manual editor). Modified window/board/moves/
widgets, game/variation/notation/settings/dialogs, source/build configuration,
license notices and documentation. No custom search algorithm was developed.

Implemented direct Smart Move with selected-piece priority, live-FEN/legal guards,
ranked ambiguous destination and promotion selectors, candidate arrows, hover,
PV insertion/copy/pin and searchmoves. Persistent processes retain a single newest
pending request, stop/bestmove/ready barriers, deadline/error handling, bounded
output/logs and 80ms information batches. Unsupported Chess960 is rejected.
Generic options honor engine bounds; Hash also uses detected memory headroom.

Migrated desktop rules/PGN to python-chess. Original perft-tested engine source
remains historical and excluded from the desktop. Preserved nested branches,
comments/NAGs/tags/evaluations; added multi-game study tabs, manual setup, Chess960,
command search, shortcut editing/import/export, image export, classic/analysis-left
layouts and graph hover/zoom/pan. Full-line review uses bounded normal and targeted
played-move searches with immutable node IDs and preserves completed exact scores.
It stores source scores/depths behind estimated 50/100/200 cp loss thresholds.

Discovered/fixed during executed tests: permissive library PGN structure handling;
intended-move draw claim semantics; executable symlink resolution escaping a Python
venv; root PGN evaluation overwritten during selection; compressed compact controls;
PV hover test attempted before nested Qt layouts settled; Unicode/quoted PGN tag
export; interrupted review/navigation lifecycle. Regression checks cover these.
The earliest migration GUI run had 7 failures (old built-in-engine/default layout
assumptions plus hover). Subsequent runs reduced this to 3, then 1 hover-layout
failure; the mouse helper now waits for layout and scrolls the actual PV into view.
The dedicated external suite progressed from 4 pass/3 failure to 7, then 10 and
12 passes as lifecycle/review/smart ambiguity regressions were added.

Executed: 31 rules/storage/notation/variation tests passed; focused study/packaging
run 31 passed in 2.36s; external suite 12 passed in 4.33s, including crash recovery,
ambiguous Smart Move, underpromotion and review pause/resume. Full pytest run:
95 passed, 5 skipped in 39.47s. Full unittest discovery then ran 103 tests,
OK (skipped=5), 59.894s: 98 passed. Skips are 2 optional deep-perft and 3 optional
legacy native-tablebase cases; current Syzygy probes belong to the supplied engine.
Ruff passed. Source GUI --smoke-test and --smoke-engine fixture both ran successfully.
Inspected real rendered dark/light/compact Qt screens with explicitly labelled
simulated UCI data; no real Stockfish binary was available or bundled.

New distribution terms are GPL-3.0-or-later due to python-chess; original code/assets
retain MIT. COPYING/notice files and rules-library Python source accompany the
source ZIP. PyInstaller produces only the external-analysis GUI, excluding the
custom search/evaluation/UCI worker and native table reader. No Windows script
launchers, external engines or table files are bundled. README/architecture/build
instructions and research comparison reflect implemented/deferred scope.

Remaining: real Stockfish 19/development and large-tablebase integration; manual
Windows/DPI/suspend review; richer tree editing, collections, comparison, persistent
cache/snapshots and flexible saved docking. The release is not full Nibbler parity.
Final code verification and native Windows CI/package checks are next.

Final local release checks: full pytest 98 passed, 5 skipped in 47.03s;
post-lifecycle/toolbar GUI plus external suite 41 passed in 27.12s; Ruff passed.
Additional rules/notation/external run 32 passed in 7.20s after escaping quoted
PGN tags and preserving string-option values with reserved-looking words.
Verified source ZIP integrity, GPL notices and included rules-library source,
with binaries/table files/script launchers excluded. Built 0.5.0 pure-Python
wheel without a compiler. Added an always-visible Analyze/Stop/engine selector
entry to keep engine control accessible at compact window sizes. Native Windows
CI, frozen app/external-fixture smoke and artifact upload are next.

Pre-publish Smart Move review found/fixed another stale-menu edge: after a chooser
opens, recheck the original full FEN, current legality, preview and interaction
state before emitting a move. The regression changes the board while the menu is
open, leaving the old suggested move coincidentally legal, and verifies no move
is emitted. Chess960 king-step/castling shared destinations now use SAN choices
rather than a promotion-only menu. External suite: 12 passed in 4.17s; Ruff passed.
Also reset omitted advertised options to engine defaults when switching profiles
on the same executable; the persistent-process test checks Threads returns to 1
without restarting the process. UCI_AnalyseMode follows the actual GUI mode.

Windows run 38987840942 ran 103 tests with 4 cleanup errors and 5 skips. Test
bodies passed, but four new external-GUI tests removed TemporaryDirectory before
unittest addCleanup closed the window/SQLite connection. Linux permits unlinking
an open DB; Windows correctly rejected it (WinError 32). Replaced that fixture
pattern with a context manager that closes/deletes the window and processes Qt
events before deleting its directory. Product storage behavior was not changed.
The Windows package was not built/published from this failed run.

An added analysis-context regression found that focusing a candidate or changing
engine settings could leave alternative rows from the previous search visible.
Candidate/PV state now resets when engine profile, options, limits, MultiPV or
searchmoves changes; targeted analysis is labelled and uses PV 1. Same-position
pinned rows remain stable during updates within a context. This prevents mixed
old/new candidate sets from implying comparable current analysis.

Position identities also include the variation node ID: transposed branches can
share board/hash/ply while carrying different repetition or halfmove history.
The context regression now builds two such branches and verifies a recommendation
from the other branch cannot execute.

Native Windows run 38993814111 succeeded: validation, PyInstaller GUI build,
packaged study/save smoke, packaged external-UCI fixture smoke, source archive
and upload all passed. Subsequent analysis-context checks add branch node IDs
and board-render revisions to reject stale choices even across transpositions
or a board replacement with identical FEN. External suite 13 passed in 5.03s;
Ruff passed. A final Windows build will validate those additional guards.

## 0.5.0 — Verified Windows delivery

Final run 38994172390 succeeded for commit
0f9040a578ff610231dcc3fc65503a61538a3fa7. Windows unittest discovery ran
104 tests, OK (skipped=5): 99 passed in 52.754s. The builder repeated all
104 tests, again 99 passed/5 skipped in 45.241s. Ruff, dependency installation,
PyInstaller GUI build, frozen study/save smoke, frozen external-UCI fixture
smoke, corresponding source archive and upload all passed. No custom engine
executable or test simulator was bundled in the desktop application.

Artifact 12086018094: Nocturne-0.5.0-Windows-x64-unsigned, 53150138 bytes,
SHA-256 1dd785857e4edd6ca2a77d3eb9507cf37133451658ed6857a084d75f9f95e113.
Metadata reports unexpired, retained until 2026-11-16. Download:
https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/38994172390/artifacts/12086018094

README/BUILDING now link to the verified download. Roadmap marks automated
Windows delivery complete while preserving real-engine/manual verification
as outstanding. Source ZIP and pure-Python wheel are refreshed locally with
GPL notices and rules-library source in the ZIP. Original code/assets retain
MIT. No claim of full Nibbler parity or measured engine strength is made.
Remaining features and the verified/report/recommendation distinctions are
listed in docs/ANALYSIS_ROADMAP.md and docs/NIBBLER_RESEARCH.md.


## 2026-10-17 — 0.5.1 resource-control implementation

Requested: make Threads and Hash prominent, following the Nibbler Engine menu.
Created gui/engine_resources.py; changed gui/window.py, engine_manager.py,
uci_connection.py, hardware.py and theme.py. Direct Engine submenus and matching
quick controls show configured values, checked presets, custom values and engine
defaults. Unsupported options are explicit. Values persist in the selected engine
profile. A ready acknowledgement distinguishes applied settings from saved ones.
Resource changes stop/reconfigure/resume through the persistent UCI process;
halted analysis remains halted and stale candidate output is cleared.

Fixed a discovered transport race: replacing a pending request during the ready
barrier could start the new search with the old request's options. The transport
now checks the prepared request identity and prepares the latest options first.
Memory admission credits the engine's acknowledged, replaceable hash allocation
while still reserving system memory; opening the profile editor uses that budget.
Selected-profile discovery is preferred when profiles share an executable.

Commands executed: Ruff; pytest tests/test_external_analysis.py tests/test_gui.py
(initial 42 passed in 26.89s); pytest tests/test_engine_resources.py
 tests/test_external_analysis.py (18 passed in 6.86s). The first new integration
run had a test-only TypeError: Store is not a context manager; corrected to
explicit try/finally close before the successful rerun. No product failure was
claimed as a passing result. Added actual protocol assertions for custom 768 MB,
latest settings before go, same PID, separate profile defaults, SQLite persistence,
unsupported Threads and engine/memory limits. Two memory/validation unit tests
exercise reserve limits and custom values. Ruff passed.

Rendered and inspected the actual Qt window at 1024×660 with labelled protocol
test data; Threads/Hash and acknowledgement status are visible in compact mode.
Version/build metadata, README, changelog, TODO and acceptance checklist updated.
Next: complete the final regression run, inspect both resource menus, run the full
suite and publish/verify a native Windows artifact. No real Stockfish executable
or table files are installed here; no performance/strength claims are made.

Final local verification: pytest resource/external/GUI suites 47 passed in 32.59s;
full unittest discovery ran 109 tests in 35.596s, OK (5 skipped, 104 passed).
The five skips remain two optional deeper-perft and three optional historical
native-reader tests. Ruff passed. Captured and inspected Engine, Threads and Hash
menus (including checked custom 768 MB), plus updated actual dark/light/compact
Qt previews. Disabled preset colors were made explicit for readability.
Actual popup interaction regression: selecting Threads through the visible Qt
menu (not just QAction.trigger) passed, 1 test in 0.82s. Source ZIP created and
0.5.1 pure-Python wheel built without a compiler; Ruff passed again.


## 0.5.1 — Verified Windows resource-control delivery

Published source commit 9738d99e2cd76213a3f2b34e7e4654d77959f551 to the user's
nocturne-chess repository. Native Windows run 39006678168 / job 117320454714
succeeded. Full unittest discovery ran 109 tests, OK (skipped=5): 104 passed in
59.351s. The build repeated all 109 tests: 104 passed/5 skipped in 50.576s.
Ruff, PyInstaller, frozen study/save smoke, frozen external-UCI protocol-fixture
smoke, corresponding source archive and artifact upload all passed. The builder
runs both frozen smoke commands with checked exit codes before making its archive.

Artifact 12091382461: Nocturne-0.5.1-Windows-x64-unsigned, 53,198,474 bytes,
SHA-256 1a21c02251d5d1da894cd6ee2752f519cc20044388fdaf80ef412c5a8967e39c.
GitHub metadata reports unexpired and retained until 2026-11-16. Download:
https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39006678168/artifacts/12091382461

README and BUILDING link to the verified Windows ZIP; TODO records remaining
real-engine/manual checks. Updated actual Qt previews and resource-menu images
are checked into the repository. Local source ZIP integrity passed, resource
component/tests and rules-library source included, executables and script
launchers excluded. Final source ZIP and pure-Python wheel refreshed.

No engine binary or table files are bundled. Tests used an explicitly labelled
protocol fixture; actual Stockfish resource allocation, manual Windows/DPI,
large Syzygy collections and playing strength remain unverified. No performance
or strength improvement is claimed. No batch/PowerShell launcher or Windows
security-policy change was added. Future work remains in ANALYSIS_ROADMAP.md.

### Final profile-metadata regression

A final static review identified that stopping a search after the source selector
changed could label the old score with the new profile/options. Added an assertion
to the real resource/profile-switch integration test and reproduced the failure:
`second != simulator` (1 failed). This was a product bug, not a fixture error.
Changed gui/window.py to freeze profile ID/configured values in each search/review
context and use that snapshot for every score save, including stop. gui/engine.py
also attaches acknowledged UCI options to info so saved analysis records actual
Threads/Hash, including engine defaults. Extended the regression to check both
profile ownership and actual acknowledged Threads=6, Hash=768. A fresh Windows
build is required before final delivery of this correction.
Post-fix resource/external/GUI run: 47 passed in 33.46s; Ruff passed. No failures.


## 0.5.1 — Final corrected Windows package

Source commit c053f15ed8b6ed692416767ed92b0c297a95b1dc passed native Windows
run 39007159403 / job 117321857514. Each unittest run executed 109 tests, OK
(skipped=5): 104 passed in 52.977s, then 104 passed in 51.485s inside the clean
builder. Ruff, PyInstaller, frozen study/save and external-UCI fixture smoke,
source creation and upload passed. The extended regression confirms saved score
ownership stays with its originating profile and acknowledged Threads/Hash.

Final artifact 12091413076: Nocturne-0.5.1-Windows-x64-unsigned, 53,200,607 bytes.
SHA-256 ee9c8ee2ad6edbc43185a86e72cd1170185e524c6694bd62ceb43024b93d8ed8.
Metadata reports unexpired, retained until 2026-11-16. This supersedes the earlier
0.5.1 test package above. Final download:
https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39007159403/artifacts/12091413076

README/BUILDING now point to this corrected package. Final local source/wheel and
checksums refreshed; source ZIP integrity verified. No further product code was
changed after the passing Windows run. Real Stockfish allocation, manual Windows
interaction/DPI and larger Syzygy collections remain follow-up verification.


## 2026-10-17 — 0.5.2 default PGN archives and resource refinements

Requested: restore default retention/access to prior PGNs, display larger Hash
sizes in GB, and add a 14-thread choice. SQLite games were still retained, but
Analysis hid the sidebar and there were no automatic PGN files. Implemented
Store.archive_pgn/pgn_path and atomic per-study copies in the data directory's
PGNs folder. Store.save commits the SQLite game before writing the file. A failed
replace retains the previous PGN and the DB game, removes temporary files and
reports an error. Unchanged copies keep their timestamps; invalid UTF-8 copies
are repaired on a later save. Filenames sanitize untrusted save IDs. Event names
appear in new library titles.

Modified storage.py and gui/window.py: File → Saved PGNs / game library… and
Open saved PGN folder; folder access in the library; incremental startup export
of older missing PGNs with a 40 ms timer, no resume-ID changes and no deletion of
corrupt records. Import/save failures are reported. Preferences save independently
before the PGN backup attempt; the archive timer stops before closing SQLite.

Modified gui/engine_resources.py, engine_manager.py and window.py: MB below 1,024;
GB from 1,024 MB (including 1.5 GB); exact MB retained for UCI/custom input. Hash
menu/default/bounds/current-memory labels, quick controls and detailed telemetry
share the conversion; generic option editor shows an additional GB readout.
14 threads is offered only within advertised engine limits.

Tests added/extended in test_game_storage.py, test_gui.py,
test_engine_resources.py and test_external_analysis.py. Executed focused pytest
on those four modules: 64 passed in 32.21s; Ruff passed. Coverage includes prior
study retention, comments/branches, atomic failure/retry and UTF-8 repair, startup
export/corrupt-record retention/resume stability, folder action, unit boundaries,
and actual setoption Threads=14 / Hash=2048 while the UI reads 2 GB.
Earlier storage/external run: 27 passed in 7.38s. No test failures in this phase.

Updated version, Windows build metadata/workflow, README, CHANGELOG, TODO and
acceptance checklist. Next: actual Qt menu/library inspection, full regression
suite and native Windows build. Real Stockfish allocation/manual Windows/DPI and
large Syzygy verification remain open; no strength or speed claim is made.

Full local verification: unittest discovery ran 115 tests in 40.012s,
OK (skipped=5): 110 passed. Skips remain two optional deep-perft and three
historical optional native-reader tests. Ruff passed. Rendered and inspected
actual Qt File/Engine/Hash/Threads menus and the saved-PGN library. Confirmed
2 GB and checked 14 threads, clear folder access and titled prior studies.
No failing tests or new implementation blockers. Native Windows CI is next.


## 0.5.2 — Verified Windows delivery

Published source bb12d4b1010a9638d795eb66f6012ff4f35c0c21 to nocturne-chess.
Windows run 39008543023 / job 117325913201 succeeded. Full unittest discovery
executed 115 tests, OK (skipped=5): 110 passed in 57.325s. The clean builder
repeated the suite: 110 passed / 5 skipped in 58.544s. Ruff, PyInstaller,
frozen study/save and external-UCI fixture smoke checks, source archive creation
and upload all passed. Native file tests cover PGN replacement failure/recovery,
UTF-8 repair, full variation retention and old-library background export.
The engine fixture verifies 14 threads and 2,048 MB commands with a 2 GB label.

Artifact 12092370151: Nocturne-0.5.2-Windows-x64-unsigned, 53,268,918 bytes.
SHA-256 8bfe7e11fbde2f9446ffa55659e09c07ac82b1d307725dd6595dc9d6ff22d7e5.
Metadata reports unexpired, retained until 2026-11-16. Download:
https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39008543023/artifacts/12092370151

README and BUILDING link to the verified download; TODO keeps manual Explorer,
real-engine allocation, DPI and large-Syzygy checks open. Actual Qt File, resource
menus and saved-library screenshots are in docs. Source ZIP integrity and pure
Python wheel build passed; no executable or script launcher is in the source
archive. Final local archives/checksums refreshed after this documentation update.
No product code changed after the passing native Windows build. No strength or
speed claims, engine/table downloads, batch launchers or security changes added.


## 2026-10-17 — 0.5.3 spacious analysis and working MultiPV menus

Requested: settings belong in the top Engine menu, with MultiPV available, and
right-side space devoted to analysis like Nibbler. The previous PV spin only
worked in Explore mode, so other modes silently searched one line. Replaced
hidden/view-based engine state with authoritative preferences and menu commands.
Threads/Hash now use a menu-only QObject in gui/engine_resources.py. window.py
owns MultiPV presets/custom values, active-profile selection and continuous/bounded
limits. No source/mode/PV spin/resource widgets or duplicate Analyze button remain
in the analysis pane. MultiPV is independent of search mode; unsupported engines
stay at one PV, first-discovery limits clamp/requeue safely and selecting MultiPV
clears searchmoves focus. Continuous searches ignore bounded node settings.

Layout: wider analysis split, smaller margins, compact move tree below, graph at
the foot of analysis, tab bar hidden during analysis (shown for PGN editing).
Candidates/moves components fit complete PV text to wrapped document height, use
one scrolling list, and move insert/pin/copy/focus into a real context menu.
Primary PV rendering now has one owner, so unchanged lines preserve hover during
depth updates. Its click connection is established once, avoiding accumulated
handlers after context changes. Engine profile resource presets leave MultiPV
unchanged. Existing archives, study tabs, PGN editing and play modes are retained.

Modified gui/window.py, engine_resources.py, candidates.py, moves.py,
engine_manager.py, settings.py, __main__.py and capture_preview.py. Updated tests
and the explicit protocol fixture. Tests cover actual MultiPV popup selection,
custom counts, continuous/bounded searches and node limits, cap discovery,
unsupported engines, focus clearing, stopped-state persistence, settings migration,
full wrapped text, context-menu copy, stable hover and single click dispatch.

Executed focused pytest (external/GUI/resources/settings): initially 52 passed
in 24.01s; extended 55 passed in 25.85s; final 57 passed in 26.51s. Ruff found an
unused SAN import after removing duplicate rendering; removed it, then Ruff passed.
Actual Qt captures inspected at 1920×1040 and 1024×660: wide right analysis,
six candidate rows, no settings controls, moves below. No test failures in this
phase. Version/build metadata and docs updated for 0.5.3. Next: full suite,
refreshed screenshots and native Windows build/package smoke validation. Real
Stockfish/manual Windows/DPI/large-Syzygy checks remain open; no strength claim.

Final local validation: unittest discovery ran 120 tests in 32.297s,
OK (skipped=5): 115 passed. Skips remain two optional deeper-perft and three
historical native-reader tests. Ruff passed. Updated actual dark/light/compact,
PGN-editor and hover screenshots, plus Engine/Threads/Hash/MultiPV menu captures.
Inspected menu placement, checked MultiPV 6, full wrapped moves, compact viewport
and absence of right-side settings. No code changed after this passing full run.
Next: publish source, native Windows tests/package smoke and artifact verification.

Native Windows run 39011077020 caught one failure: after switching Play → Analysis
and resizing to 1024×660, the analysis pane retained the old narrow sidebar split
(347 px versus 654 px for the board). 120 tests ran in 56.844s: 114 passed,
1 failed, 5 skipped; packaging was correctly blocked. Fixed window.py to reapply
the default split with a parent-owned single-shot timer after Qt's posted layout
requests settle. The timer runs only on workspace/layout changes, preserving
subsequent user splitter drags. Added a regression covering both analysis orders,
compact/desktop sizes, repeated mode changes and preservation of custom splits.
Executed GUI pytest: 34 passed in 16.73s; Ruff passed. Next: full local suite and
a new native Windows build. The earlier 0.5.2 download remains until verification.

After the layout fix, full local unittest discovery ran 121 tests in 32.986s:
116 passed, 5 skipped. Both layout regressions also passed with
QT_STYLE_OVERRIDE=windows (2 passed in 0.69s). Captured and inspected a fresh
1024×660 actual Qt screenshot: wider analysis, moves below, no settings widgets.
Published fix commit 2f68528594595b0354ebf43210b71aebe7fd2430; replacement Windows
run 39011345291 is validating it. No further product changes after these tests.

Run 39011345291 still failed both width regressions (121 tests, 41.314s;
114 passed, 2 failed, 5 skipped). Deferred sizing alone is insufficient on native
Windows. Added widget minimum/hint/maximum diagnostics to the existing assertions
to identify the constraint rather than weakening the checks. Corrected the resize
regression setup so its classic and analysis-left cases actually use both orders.
No executable was produced from either failed run.

Diagnostic run 39011529709 reproduced the two width failures (121 tests,
31.433s; 114 passed, 2 failed, 5 skipped). Its widget measurements identify the
actual cause: the single-line board instruction label is 403 px wide with native
Windows font metrics, forcing the board arena minimum to 654 px. Wrapped that
caption in Play and hid it in Analysis; Flip/Copy FEN remain available. Removed
the unnecessary deferred resize timer. The regression now includes a long caption
and checks it is hidden while both layouts retain wider analysis/custom splits.

Caption fix validation: GUI pytest 34 passed in 16.56s; Ruff passed. Full local
unittest discovery ran 121 tests in 34.110s: 116 passed, 5 skipped. Refreshed the
five actual Qt workspace screenshots and inspected the wide capture. Published
commit c89cff16102e323920ec738199b3e13a86cc4861; Windows run 39011710749 is
validating the corrected minimum width and building the portable app.


## 2026-10-17 — 0.5.3 verified Windows package

Windows run 39011710749/job 117335431211 succeeded for code commit
c89cff16102e323920ec738199b3e13a86cc4861. The workflow ran 121 tests in
32.330s: 116 passed, 5 skipped. The isolated build environment repeated all
121 tests in 39.629s with the same passing result. Ruff, PyInstaller and both
frozen GUI smoke checks (study/save and external-UCI protocol fixture) passed.
The Windows regressions now verify the wider analysis pane in both orders and
compact/desktop sizes, mode switching, long instruction text and user splitter
preservation. MultiPV presets/custom/unsupported limits, continuous/bounded UCI
commands, 14 threads and GB hash labels also pass on native Windows.

Artifact 12093112925: Nocturne-0.5.3-Windows-x64-unsigned, 53,376,940 bytes.
SHA-256 1d633e9cf36e3e62c441c1d92ff023bcae2ee45bd17a84ad6756da68627f62d6.
Metadata reports unexpired and retained until 2026-11-16. Download:
https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39011710749/artifacts/12093112925

README/BUILDING link to this verified executable; TODO retains real Stockfish,
manual Windows/DPI and large-Syzygy checks. Refreshed actual Qt screenshots and
source archive/wheel/checksums. Only documentation/images change after the passing
Windows build; no product code changes. The tests use explicit protocol fixtures,
not installed Stockfish, and make no playing-strength or speed claim. No engine
or table files are bundled; no batch/PowerShell launcher or security bypass added.

## 2026-10-17 — 0.5.4 ranked destination moves, phase 1

Requested automatic arrows/lines for MultiPV and destination clicks that choose
the highest-ranked move sharing that square, including lower-ranked candidates.
Modified gui/board.py, gui/window.py and settings.py: removed the top-only gate
and shared-destination popup, sorted/deduplicated legal recommendations, kept
selected-piece priority, stale/preview checks and manual promotion choices.
Recommended promotions execute the engine's exact choice. Display now offers
Lichess-style arrows or Nibbler-style lines with rank badges; a shared destination
shows its best rank. Clearing/changing MultiPV clears old board recommendations.
Updated the ambiguous-destination regression to verify automatic rank selection,
fifth-candidate execution and retained manual promotion/Chess960 choices.
Executed external-analysis/GUI/settings pytest: 55 passed in 25.42s.
Next: asynchronous Lichess Masters/player explorer, cache and navigation tests.
Direct live HTTP is blocked by this execution sandbox despite the environment's
unrestricted network policy; public endpoint checks will run from Windows CI.

## 2026-10-17 — 0.5.4 opening explorer, phase 2

Created explorer.py (validated queries/statistics and isolated bounded SQLite
cache), gui/explorer_client.py (QtNetwork transport), gui/explorer_panel.py
(frequency table/result bars/hover), tests/test_explorer.py and the opt-in live
check scripts/check_explorer_api.py. window.py/settings.py add Database menus,
source/speed/rating filters and a resizable panel beneath PVs. Network is disabled
by default and paused outside the active Analysis/Engine view. Standard positions
only; Chess960 shows an explicit unsupported state. Database clicks preserve
existing game branches and pass the rules boundary; engine and database rankings
remain distinct. Counters are not used as engine evaluations.

Checked current official Lichess API endpoint/filter specifications using its
public GitHub documentation. Both aggregate endpoints now use explorer.lichess.org;
rating groups match its documented 0/1000/1200/.../2500 bins. Requests are paced,
debounced, generation-guarded, size/deadline bounded, and honor 429 cooldown with
no automatic retry loop. A 256-entry, 24-hour cache can display explicitly labelled
saved data during errors. Individual game downloads and Chess960 lookup deferred.

Executed tests: integration run after adding Database had 52 passed / 1 failed
because the old exact menu list lacked Database; updated that expectation.
Initial HTTP fixture tests exposed the sandbox's socket prohibition; corrected
the fixture's socket-enum/probe handling and skip only denied socket creation.
Added cached-data GUI tests independent of sockets. Corrected one test's invalid
Game.from_fen call to the actual Game(fen) constructor. Final explorer-only run:
5 passed, 5 socket-dependent skipped in 0.45s. Earlier combined focused run:
59 passed, 5 socket-dependent skipped in 35.82s. Ruff passed.

Full local unittest discovery: 132 tests in 43.992s, OK (skipped=10): 122 passed.
The ten skips are five HTTP tests blocked by the sandbox plus five existing
optional deeper-perft/native-reader tests. Desktop smoke with cached explorer
also exited 0. Packaged smoke now checks explorer rows as well as study/save;
Windows CI runs deterministic HTTP tests and a separate non-blocking live Qt TLS
check for both public sources. Documentation/version/workflow updated for 0.5.4.
Next: capture/inspect actual UI, publish and validate native Windows package.

Captured and inspected the actual wide explorer and Nibbler-line layouts. Refreshed
dark/light/compact/PGN/hover captures. Explorer screenshots use explicitly labelled
cached test statistics, not live database results. Ruff passed after capture script
changes. Publishing source now for native Windows HTTP and optional live TLS checks.

Published code 40a5480c68fb9828d4847d6a50f2883664c98f9a. Native Windows run
39064485252 executed all five HTTP tests; cancellation/stale results, response
limits/errors/timeouts, live/cache responses and pacing passed. Its 429 test
found a Qt binding type bug: QNetworkReply.rawHeader expects a string header
name, not bytes. Fixed the Retry-After call. The run had 132 tests in 63.210s:
126 passed, 1 failed, 5 skipped; packaging/live checks were correctly blocked.
Source ZIP and wheel built locally and passed integrity checks; source excludes
executables/script launchers. Next: rerun Windows with the header fix.


## 2026-10-17 — 0.5.4 ChessDB and current Lichess authentication

User added ChessDB during Windows validation. Read its official web/API docs and
source format. Added queryall JSON requests with learn=0/showall=0, a distinct
score/note view and no fabricated game counts/WDL. Normal cp scores orient to
White; large mate/tablebase codes are labelled DB and retained raw. Queries keep
the fifty-move clock. Validate all moves/SAN, terminal states and numeric scores;
handle unknown positions and the service's HTTP-200 rate-limit status explicitly.
The same cache, cancellation, preview and variation-preserving click paths apply.
Files: explorer.py, explorer_client.py, explorer_panel.py, window.py, settings.py,
HTTP/data/GUI tests, live-check script, captures, workflow and docs.

Prior header-fix run 39064687693/job 117489747050 succeeded in packaging code
ac65db318cedcb660bbb8cb1b67ec976079c7873. Both native test runs passed 127 tests
with 5 skips (132 total, 76.554s / 54.334s). All HTTP regressions including 429
passed; frozen explorer/study/save and external-UCI smoke checks passed. Its live
API step returned HTTP 401 for Masters. Although continue-on-error marked the
workflow green, that is NOT successful live data verification. No such claim.

Current official Lichess docs declare OAuth authentication, and its first-party
mobile issue #3161 documents this 2026 change. Added a masked Database-menu token
dialog and token-creation link. Credentials remain in memory only, never in
settings/PGN/cache, and go only to HTTPS explorer.lichess.org:443 with same-origin
redirects. ChessDB/test/other hosts never receive them; 401/403 gives a clear
instruction. A real user token is not available here; authenticated live data
remains a manual check. The live script now distinguishes protected endpoints
from data success and continues to independently check ChessDB.

After ChessDB: explorer tests 8 passed / 6 socket-dependent skipped in 0.74s;
full local suite ran 136 tests in 45.021s, OK (11 skipped): 125 passed.
After session-token tests: explorer pytest 9 passed / 6 skipped in 0.98s; Ruff and
desktop smoke passed. Tests cover scoped Authorization, masked entry and absence
from saved data as well as ChessDB schema/scores/cache/branches. Full final suite
and native Windows run follow. Updated docs to remove the obsolete no-token claim.

Final local full suite after ChessDB and token support: 137 tests in 45.150s,
OK (skipped=11): 126 passed. Six HTTP tests are sandbox-skipped; the other five
are existing optional checks. Refreshed/inspected actual wide and compact ChessDB
captures with explicitly labelled fixture scores. No live authenticated Lichess
data is represented in screenshots. Final Windows validation is next.

Final GUI code 762de7aee5ff49d11c6becb91f889d23effaa48a passed native Windows run
39065410510/job 117491914975. Both test runs executed 137 tests: 132 passed,
5 optional skipped (68.692s / 79.129s). All six HTTP tests ran on Windows and
passed, including ChessDB's JSON/semantic rate limit and Lichess 401 guidance.
Ruff, PyInstaller and both frozen explorer/study/save/UCI smoke checks passed.
Artifact 12112334334 is the verified final GUI, 53,960,583 bytes, SHA-256
2b41604bdf51d88c5cf831ebb888910e8bbf5ba12fa13e8f420e6fa237fe10e6,
retained until 2026-11-16:
https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39065410510/artifacts/12112334334

The optional live-check script hit Windows cp1252 encoding on the arrow in its
authentication message, before reaching later sources. Fixed that developer-only
script to print UTF-8 and added a manual connectivity workflow to rerun only these
checks. The desktop GUI is unaffected and no application code changes follow
the passing native package. Authenticated Lichess data still needs a user token.

Desktop CI now ignores documentation/connectivity-only edits; the separate
database workflow can run on probe edits or manual dispatch. This reruns only
the failed diagnostic instead of repeating the already-passing application
build/tests. Download docs point to the verified 0.5.4 GUI artifact.


## 2026-10-17 — 0.5.4 delivery verified

Connectivity-only Windows run 39065979799/job 117493627053 passed for diagnostic
commit 3a53f9c601a1aec57f754ffcc45007c1882c31de. The same Qt HTTPS client queried
both Lichess sources and reported their authentication requirement. It then
successfully queried ChessDB for the fixed 1.e4 e5 position and parsed/validated
29 legal moves. UTF-8 output completed without exceptions. Authenticated live
Lichess data remains explicitly untested because no user token is available;
header scoping/401 behavior/session handling are covered by native tests.

Final desktop artifact remains run 39065410510/artifact 12112334334, built from
unchanged GUI code 762de7aee5ff49d11c6becb91f889d23effaa48a. It passed 132 tests
with 5 optional skips twice, packaged save/explorer/UCI smoke checks and Ruff.
Download is linked in README/BUILDING; Database menu screenshot shows all three
sources and token controls. TODO retains authenticated real-user Lichess data,
manual Windows/DPI/real Stockfish interactions, individual game downloads and
Chess960 database support as open limitations.

Refreshed local source ZIP, wheel and checksums after final docs. ZIP/wheel
integrity checked; source has no executable or batch/PowerShell launcher.
No application code changed after the passing native Windows package. All online
lookups remain optional; no external engine or table files were downloaded/bundled.


## 2026-10-17 — 0.5.5 subtle analysis markers

The requested visual adjustment is confined to gui/board.py: candidate strokes
now use muted colors at 29–37% opacity, 1–2 logical-pixel arrow shafts and 1–1.6
logical-pixel lines. Arrowheads are roughly one third of their previous dimensions;
rank badges become small translucent circles with quiet numerals. Saved continuation
arrows share the subtle geometry. Manual annotations and candidate click/rank/
promotion behavior are unchanged. No new controls or tooltips were added.

Executed real Qt captures via scripts/capture_preview.py --simulate at 1920×1040
(arrows and lines), 1024×660 (arrows), and 1440×1040 (light mode), and visually
inspected all four. Updated docs/preview.png, preview-lines.png, preview-compact.png
and preview-light.png; the simulator is explicitly labelled test data.

Executed QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests
-p test_external_analysis.py -q: all 20 tests passed in 12.612s, including
ranked destination clicks, exact promotion, hover restoration and both marker
styles rendering. Ruff check src tests scripts passed. The offscreen
python -m nocturne --smoke-test exited 0. No functional bugs were found. Fontconfig
cache and offscreen popup capability notices remain environment limitations.

Version metadata and the Windows artifact/source paths are 0.5.5. The full local
suite and native Windows package are next; the prior verified download remains
linked until the new artifact is actually built. Manual Windows/DPI/real Stockfish
verification remains open.

Full local release validation executed: QT_QPA_PLATFORM=offscreen
.venv/bin/python -m unittest discover -s tests -q ran 137 tests in 44.985s:
126 passed, 11 skipped, no failures. Six HTTP tests skip because socket creation
is denied in this cloud sandbox; five other optional historical checks skip.
Malformed-PGN diagnostics are expected negative-test input. Final Ruff passed.
Next: publish the reviewed file changes and run the existing native Windows CI
validation/PyInstaller/package smoke checks before advertising a 0.5.5 download.


## 2026-10-17 — 0.5.5 Windows delivery verified

Published GUI commit c2dc1dcfe33d30d95ef37104576fe6f518e0c41a. Native Windows run
39070057843/job 117505628036 completed successfully. The full suite ran twice:
137 total tests each time, 132 passed and 5 optional skips, in 64.011s and
64.154s. All six HTTP tests executed on Windows. Ruff passed twice; PyInstaller
produced the windowed executable, and packaged study/save/explorer and external-UCI
fixture smoke checks passed. No test failures. The optional live check returned
29 legal ChessDB moves; Lichess reported authentication required, not live data.

Verified artifact 12114389477 is Nocturne-0.5.5-Windows-x64-unsigned, built from the
same commit, 53,971,786 bytes, retained until 2026-11-16. SHA-256:
0b1aa2f5b4535c7dbcade36d97b4a53514ee207682c7a4adbd2b7e8ff40ffbb2.
Download: https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39070057843/artifacts/12114389477

README.md and docs/BUILDING.md now link the verified 0.5.5 ZIP; TODO.md records
completion and remaining manual Windows/DPI checks. Source ZIP and wheel built
locally and passed ZIP integrity checks; source contains no EXE/batch/PowerShell
launcher. Refreshing source/checksums after final documentation changes. These
final changes are documentation only; application code is unchanged after the
passing Windows package. Next verification is user desktop/DPI appearance and
real Stockfish interaction; automated results use a labelled UCI protocol fixture.


## 2026-10-17 — 0.5.6 Backspace branch deletion, implementation

User requested Nibbler-style selected-line deletion with plain Backspace: from
1.e4 e5 (1...Nf6), deleting e5 must display Nf6. Added Game.delete_current_line in
core/game.py and Tree → Delete current line in gui/window.py. Deletes the current
move/subtree; chooses the next sibling, otherwise previous sibling, otherwise
parent. Root and Play mode are protected; shortcut auto-repeat is disabled.
The tree is compacted before saving, preserving child order and surviving
comments/analysis/clocks/evaluations; review node references are remapped and
removed entries discarded. A changed main line clears its previous result.
The GUI cancels active review, stops old search before editing, refreshes board/
history, autosaves, and reschedules only if analysis was enabled.

Added regression coverage in tests/test_variations.py (main/side subtree deletion,
sibling order, parent/root fallback, results and PGN/JSON restore), test_gui.py
(actual Backspace on board/move pane, hover restoration, saved PGN/board sync,
PGN and text-field editing), and test_external_analysis.py (live UCI restart,
stale reply rejection and halted-state preservation). Initial tests exposed two
invalid new fixtures: wrong PGN variation placement and a review record lacking
criteria. Fixed the fixtures; no application bug was found in that run.

Executed focused unittest discovery: variation tests 8 passed (0.076s), GUI tests
36 passed (24.074s), external-analysis tests 21 passed (14.038s). Ruff passed.
One history-text assertion was subsequently added and will run in the full suite.
Version metadata, Windows artifact paths, README and CHANGELOG updated to 0.5.6.
Full local validation and native Windows packaging are next; the prior verified
0.5.5 download stays linked until the new artifact is verified. No new tooltips,
launch scripts or dependencies. Manual Windows/DPI/real Stockfish review remains open.

Full local validation executed: QT_QPA_PLATFORM=offscreen .venv/bin/python
-m unittest discover -s tests -q ran 142 tests in 51.839s: 131 passed,
11 skipped, no failures. Six HTTP tests skip on denied sandbox sockets; five
optional historical checks also skip. The added visible-history assertion passed.
The offscreen python -m nocturne --smoke-test exited 0; final Ruff passed.
Publishing the reviewed changes next for native Windows validation and packaging.


## 2026-10-17 — 0.5.6 Windows Backspace release verified

Published application commit e59980a326306e05080b1a8a55d3255b3e5f3a4c. Windows
run 39076887941/job 117525776947 completed successfully. Full unittest discovery
ran twice: 142 tests each, 137 passed and 5 optional skips, in 68.116s and 67.472s.
The five new deletion/Backspace regressions passed in both runs, including actual
key input, sibling display, save/restore, text-field editing and live UCI
cancellation/restart/stale reply guards. All six HTTP tests executed on Windows.
Ruff passed twice. PyInstaller built the windowed GUI; both frozen study/save/
explorer and external-UCI fixture smoke checks passed. No test failures.
The optional API check returned 29 legal ChessDB moves and explicit Lichess
authentication requirements; authenticated Lichess data is not claimed.

Artifact 12116669238 is Nocturne-0.5.6-Windows-x64-unsigned from the tested commit,
53,978,903 bytes, retained until 2026-11-16. SHA-256:
bd6912922b667292c14cfacef6069de7d1cc058ea195c8cfcd94b4fa941b46c4.
Download: https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39076887941/artifacts/12116669238

README.md, docs/BUILDING.md and TODO.md now point to the verified download and
record completion. Local source ZIP/wheel built and passed archive integrity
checks; source excludes EXE/batch/PowerShell launchers. Refreshed source/checksums
after these final documentation edits. No application code changed after the
passing Windows build. Next is user desktop/DPI/real Stockfish verification;
automated engine interactions use the labelled protocol fixture. Backspace
deletes the selected move and descendants, not earlier ancestors; root/Play
mode remain protected and text fields retain their normal key behavior.


## 2026-10-17 — 0.5.7 optional Game Review, implementation and focused checks

User requested optional chess.com/Lichess-style move review and total percentages
under Analysis. Added independent review.py scoring/evidence module and
gui/review_panel.py. Updated gui/window.py with Analysis → Game Review, a button
above PVs, opt-in review tab, frozen review limits, exact same-root targeted-move
validation, per-node evidence, live progress, pause/resume/cancel and navigation
that preserves the chosen branch and halted analysis. The panel displays White,
Black and overall estimated accuracy, all six quality counts, error filtering,
best moves and score/depth evidence. Empty/partial coverage remains explicit.

Used published numerical score/accuracy curves inspected in Lichess's official
scalachess eval.scala/lila AccuracyPercent.scala; independent Python math with
Nocturne arithmetic-mean aggregation and explicit 3/8/20 pp loss bands. Accuracy
is labelled an estimate, not an official site score or a probability/rating.
Mate outcomes are separate from cp; mate distance is not graded. Full formulas,
limits and references are documented in docs/REVIEW.md and credited in notices.

Updated core/game.py for accuracy PGN annotations and resilient legacy records;
settings.py persists the review budget; gui/theme.py styles progress. Extended
__main__.py smoke checks so the frozen UCI test executes review and checks complete
coverage. capture_preview.py --review uses explicitly labelled deterministic
simulator scores. Created docs/game-review.png, -compact.png and -light.png from
real Qt captures at 1440×1040 (dark/light) and 1024×660; all visually inspected.
Compact height uses a vertical review scroll area; normal analysis is unchanged.

Focused commands executed: unittest discovery for test_review.py: 5 passed
(0.042s), test_external_analysis.py: 23 passed (33.586s), test_gui.py: 36 passed
(36.404s). The new integration initially failed because the simulator preferred
d4 over the intended Nf3 Best example; fixed fixture ordering, then all 23 passed.
Earlier existing 21 external tests also passed (18.409s). Ruff passed.

Full local discovery then ran 149 tests in 84.262s: 138 passed, 11 skipped,
no failures. Both offline and external-UCI app smoke commands exited 0, including
a full two-move review through the actual UI/controller. Later hardened malformed
legacy annotation export, added its regression plus side-variation navigation,
and started a final full run for the final source. Six HTTP skips are sandbox
socket restrictions; five other optional historical checks skip. No GUI freeze,
rule change, new dependency, tooltip or launcher added.

README/CHANGELOG/roadmap/notices and version/Windows paths are 0.5.7. Final local
validation and native Windows package verification are next. Manual Windows/DPI,
actual Stockfish review calibration and large-tree profiling remain open.


## 2026-10-18 — 0.5.7 final local validation

Final full command: QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest
discover -s tests -q. Ran 151 tests in 73.528s: 140 passed, 11 skipped, no
failures. This includes six scoring/evidence tests, 23 external-analysis tests
and 37 GUI tests, with the new malformed-record and selected-branch navigation
regressions. Ruff check src tests scripts passed. Both app smoke commands exited
0; the --smoke-engine path completed actual two-move review with full coverage
through the UI/controller. Fontconfig/offscreen popup notices are environmental.
Six HTTP tests remain sandbox-skipped; native Windows must run them.

Reviewed final dark/light/compact Qt captures. Published method/limitations in
docs/REVIEW.md; documented UI use and synthetic screenshot labelling in README.
Next: publish the source and run Windows CI/PyInstaller and frozen review smoke
checks. Prior verified Windows link remains until the 0.5.7 artifact is verified.


## 2026-10-18 — 0.5.7 Windows Game Review delivery verified

Application commit b00711c9f41c67362d1afab3f176e9a6f81dad1e passed Windows run
39081231579/job 117538394042. Full unittest discovery ran twice: 151 total each,
146 passed and 5 optional skips, in 102.826s and 113.005s. New Game Review grading,
filter/navigation, pause/resume, wrong-target/bound rejection, Black/FEN numbering,
partial coverage, malformed legacy export and branch-preserving navigation tests
passed on Windows. All six HTTP tests executed. Ruff passed twice. PyInstaller
built the windowed GUI. Both frozen smoke commands passed, including a full
two-move external-UCI Game Review with complete graded coverage through the
packaged UI/controller, alongside saved-study/PGN/explorer checks. No test failures.
The optional API probe returned 29 legal ChessDB moves; Lichess required a token,
so authenticated Lichess data is not claimed.

Verified artifact 12118044851: Nocturne-0.5.7-Windows-x64-unsigned from the tested
commit, 54,467,609 bytes, retained until 2026-11-17. SHA-256:
16fc6f5fe3097f9f7f6f88241041ca8601d5f08724c0fa298b4cba88ee4143d2.
Download: https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39081231579/artifacts/12118044851

README, BUILDING and TODO now link the verified package and record completed
checks. Source ZIP/wheel built locally and passed archive integrity checks; source
has no EXE/batch/PowerShell launcher. Refreshed source/checksums after final docs.
Only documentation follows the passing native package; application code is
unchanged. Game Review is opt-in under Analysis; normal PV analysis retains its
space. Actual Stockfish quality calibration, manual Windows/DPI interactions and
large-tree profiling remain open. Percentages are Nocturne estimates, not official
Chess.com/Lichess scores or evidence of engine strength. Next is user desktop
verification with the installed engine and adequate review budgets.


## 2026-10-18 — 0.5.8 Cburnett pieces, clocks and stable MultiPV

Replaced all twelve board SVGs with the exact Lichess Cburnett sources by Colin
M. L. Burnett at lila commit cd2656d2787a766ba743da8da1dd3b24975e6329.
Verified each local Git blob hash against that pinned upstream directory: all
12 match. Only filenames are normalized to lowercase. Official lila COPYING
identifies this set as GPLv2+; included its attribution and GPL-2.0-or-later
license in licenses/, wheel metadata, source archive and existing native bundle
license collection. No Chess.com or Nibbler artwork is copied. board.py uses the
SVGs' own margins for board, drag/animation and promotion rendering.

Added persisted Display → Clocks in settings.py/window.py and a compact White/
Black strip above the analysis board, with theme.py styling. Play retains its
player-card clocks. Visibility does not pause/reset a running game or change its
position/time control; Analysis keeps its existing paused behavior. Untimed games
show infinity. PGN clock-comment import remains unsupported and is documented.

Changed gui/moves.py and candidates.py to reserve three text lines per MultiPV
rank, including waiting ranks, using a cached font/DPI-aware fixed viewport.
Long PVs scroll inside the slot and copy in full. Headers have a fixed one-line
height. The hovered rank retains its visible PV until leaving; newer updates
queue without displacing its move. Fixed an actual preview-loss bug: updates in
another rank previously ended the active rank's preview. A queued replacement
also cannot change the move under a click. Context changes invalidate pending
callbacks. window.py synchronizes arrows and destination clicks to the displayed
snapshot, including after queued updates. No tooltip or script launcher added.

Executed focused GUI discovery: 41 tests passed in 43.930s. External-analysis
suite: 23 passed in 29.738s. Final full command:
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -q
ran 155 tests in 81.774s: 144 passed, 11 skipped, no failures. Six HTTP tests skip
because this sandbox cannot bind loopback sockets; five optional historical
checks skip. New regressions cover fixed heights, out-of-order rank arrival,
other-rank updates during hover, queued own-rank updates, safe clicks, stale
context invalidation, actual SVG/promotion rendering and clock persistence with
running timers. Replaced the old full-height-PV expectation with the requested
three-line viewport behavior. Ruff check src tests scripts passed.

Both python -m nocturne --smoke-test and the --smoke-engine path using the local
UCI simulator exited 0, including full two-move Game Review coverage. Captured
and visually inspected actual Qt dark (1920×1040), compact (1024×660), light
(1440×1040) and clocks-hidden views. Updated the corresponding docs previews;
simulated analysis is explicitly labelled. No measured strength claim is made.

Built the 0.5.8 wheel with pip wheel --no-deps --no-build-isolation; archive
integrity and inclusion of both Cburnett license/credit files plus notices
passed. Version files, Windows workflow paths, README, CHANGELOG, architecture
and roadmap are updated. Next: publish the tested source and verify native
Windows tests, PyInstaller and packaged GUI/UCI smoke checks before updating the
download link. Manual Windows/DPI, real Stockfish hover interaction and very
large MultiPV lists remain to verify on a desktop. Narrow fixed headers may
clip some optional statistics; the main telemetry remains available.


## 2026-10-18 — 0.5.8 native Windows delivery verified

Published application commit b1322d643bb57901a854b398f9b1056f48cc1a25 with GitHub
blob/tree/commit/ref operations and a matching-head lease; no forced update.
Windows run 39083200511/job 117544263988 completed successfully. Full unittest
discovery ran twice: 155 total each, 150 passed and 5 optional skips, in 84.660s
and 106.145s. Both Ruff runs passed. All six loopback HTTP tests ran on native
Windows. New clock/piece/MultiPV/hover/click regressions passed. PyInstaller
built the windowed Nocturne.exe, then the builder launched both frozen smoke
paths successfully (offline and external UCI with complete two-move Game Review).
The check=True builder stops before source packaging/upload if either launch
fails. No test failure. Non-blocking PyInstaller API-set DLL resolution notices
and the existing Actions Node deprecation notice remain in the build log; the
packaged GUI checks succeeded on the native runner.

Verified artifact 12119502466 matches the tested commit and is not expired:
Nocturne-0.5.8-Windows-x64-unsigned, 54,608,168 bytes, retained until 2026-11-17.
SHA-256: 00ff5a5ba65e41d8ba6c6a46aa6f7cbb5acea456529aca71e33c4699001b65e2
Download: https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39083200511/artifacts/12119502466

The separate live API check returned 29 legal ChessDB moves. Lichess endpoints
required a user token, so no authenticated Lichess data claim is made. README
and BUILDING now link the verified package; TODO records completed checks.
The source ZIP passed integrity/license checks and contains no EXE, batch or
PowerShell launcher. Wheel integrity and required credit/license inclusion also
passed. Refreshed local source/checksums after final documentation. Only docs
follow the tested application commit. Next is manual Windows 11/DPI, actual
engine hover/scroll interaction and clock usability verification on a desktop;
PGN clock-comment import and other named limitations remain documented.


## 2026-10-18 — User-reported Smart App Control signing blocker

User reports that Windows Smart App Control blocks the delivered Nocturne EXE
because it is unsigned. This is an unresolved release blocker for their setup;
the earlier passing native tests and packaged smoke checks did not test that
policy or establish publisher trust. The block is user-reported, not reproduced
inside this Linux workspace.

Inspected scripts/build_windows.py, .github/workflows/windows.yml and current
build documentation using rg/sed/cat. The workflow builds/uploads unsigned test
artifacts. The existing --package-signed gate verifies Authenticode signatures
with SignTool but does not perform signing or enroll a publisher. Managed
environment readiness reports no configured secrets, signing identities or
signing capabilities. A trusted signing operation cannot be completed here
without a legitimate certificate/service and publisher enrollment.

Updated README.md and docs/BUILDING.md to identify the current download as a
tested unsigned developer build, explain the actual Smart App Control block and
distinguish test success from signature/trust verification. Added the signing/
Smart App Control acceptance task at the top of TODO.md. No self-signed trust
root, launcher script, security-policy bypass or replacement unsigned EXE was
created. No application code changed; no application tests were rerun for these
documentation-only changes. Next: configure legitimate publisher signing, sign
the native bundle, pass the existing signature gate and test the downloaded
package with Smart App Control enabled before offering a signed release.


## 2026-10-18 — Restore 0.5.7 and isolate the three-line MultiPV patch

User confirms 0.5.7 works on their computer and requests reverting to it with
only the three-reserved-text-lines change. Restored all 35 tracked files that
differed from 0.5.7 commit b69b8d81222117946838ad7a40b864eecd624a9a using the
existing 0.5.7 source archive. Verified every restored Git blob hash against that
remote tree before writing; all 35 matched. Removed the three 0.5.8-only clock
preview/Cburnett license files. Original piece SVGs, board.py, theme.py,
settings.py, THIRD_PARTY_NOTICES, MANIFEST, requirements, build script, PyInstaller
specification and capture script match 0.5.7 exactly. No signing/build-policy
change. Historical log/changelog entries are retained, not represented as active
features. A new unsigned EXE is not guaranteed the same Windows trust decision;
root cause of the user's 0.5.8 block remains unconfirmed.

Applied only the MultiPV change to gui/moves.py, candidates.py and window.py:
three fixed text lines per rank, fixed-height headers, reserved waiting ranks,
internal scrolling for long PVs, owner-aware hover snapshots/latest-update queue,
click-before-flush ordering and displayed-snapshot marker synchronization.
Added the related GUI regressions only, excluding the removed clock/art tests.
Verified that these three runtime files and tests/test_gui.py were the complete
source diff against 0.5.7 before changing version metadata. Labelled this patch
0.5.7.1 in pyproject, __init__, Windows file/product versions and CI artifact paths.

Executed focused GUI command:
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -p test_gui.py -q
39 tests passed in 35.911s, no failures. Ruff check src tests scripts passed twice.
Both offline and external-UCI python -m nocturne --smoke-test commands exited 0,
including complete two-move Game Review via the protocol fixture. Captured and
visually inspected actual Qt dark 1920×1040, compact 1024×660 and light 1440×1040
views with original pieces and no new clock strip; screenshot engine output is
explicitly labelled simulator test data. Updated these docs previews and fixed
obsolete full-height-PV wording in README/architecture. No tooltips/launchers.
Full regression discovery is running; next is source-diff verification and native
Windows packaging. Manual Windows trust/DPI and real-engine checks remain open.


## 2026-10-18 — 0.5.7.1 local validation complete

Final full command QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest
discover -s tests -q ran 153 tests in 79.478s: 142 passed, 11 skipped, no failures.
Six HTTP tests skip due to sandbox socket restrictions; five optional historical
checks skip. Focused GUI: 39 passed in 35.911s. Both app smoke checks exited 0.
Ruff passed. No application code changed after this validation.

Rechecked scoped diff against 0.5.7: exactly three runtime GUI files, their test,
four version/artifact metadata files, docs and three real Qt screenshots.
Twenty-three critical packaging/appearance files (all 12 original pieces,
Nocturne.spec, build_windows.py, capture_preview.py, all requirements, board.py,
theme.py, settings.py, MANIFEST and notices) match the 0.5.7 Git blob hashes.
Built source ZIP via scripts/package_source.py and wheel via pip wheel --no-deps
--no-build-isolation. Both passed ZIP integrity checks, contain byte-identical
restored pieces and no removed Cburnett files or Windows script/EXE launchers.
Pip's unwritable-cache notice and Qt/offscreen/font warnings are environmental;
negative SAN parsing tests emit expected warnings. No test failure discovered.
Next: publish this isolated patch as a new commit without rewriting history and
verify Windows tests/PyInstaller/frozen checks before updating the download.


## 2026-10-18 — 0.5.7.1 Windows validation timeout investigation

Initial Windows run 39088139853/job 117558949162 for application commit
d0c968211a9cb8ce3fb6d2d6c865d806aab383a0: first full run passed 148 tests with
5 optional skips (153 total, 97.027s). Builder's second full run had 147 passed,
5 skipped and one failure (153 total, 116.049s). Failure:
test_external_analysis.QtIntegration.test_review_rejects_bound_scores_and_wrong_targeted_moves,
bounds subtest, timed out waiting for the review's paused state. All new MultiPV
tests passed. Packaging/upload correctly stopped; no patch EXE was delivered.

Reproduced the external suite locally: all 23 passed in 24.140s. Repeated the
original failing test 12 times: all passed in 36.083s. Exact Windows transient
cause is unconfirmed because the original wait lacked protocol diagnostics.
Found a test-budget mismatch: wait_until defaults to four seconds while the
existing transport permits five seconds for an engine handshake. Updated only
this test to allow ten seconds including cold subprocess startup, report phase,
review state and bounded protocol log on timeout, and require the exact intended
score-rejection message and idle transport. A connection timeout also pauses
review and can no longer falsely satisfy the test. Application source, startup
budgets, original packaging/dependencies/pieces/clocks are unchanged. Ruff passed.
Next: execute the revised external suite and repeat native validation; do not
claim Windows packaging passed until it actually completes.

Revised external suite command completed: 23 tests passed in 26.173s, no failures.
Only tests/test_external_analysis.py and this log change after the initial native
attempt. Retrying the unchanged application with stronger test diagnostics.


## 2026-10-18 — 0.5.7.1 Windows patch delivery verified

Final tested source commit 573e329d7882f7bc3cdd9a961b88b2a6d47c4bef passed Windows
run 39088586425/job 117560251408. Full discovery ran twice: 153 total each,
148 passed and 5 optional skips, in 101.585s and 108.900s. All six HTTP tests ran.
Both Ruff runs passed. The revised cold-start/rejection test and all new PV
regressions passed in both runs. PyInstaller built the windowed application;
both frozen smoke commands passed (offline and external UCI, including complete
two-move Game Review). The build's check=True gate completed only after both
launches. The initial failed attempt remains documented above; its timeout was
not counted as a successful build. No application source changes followed the
original successful local application validation; the retry changed test/log only.

Verified artifact 12121976207 belongs to the final tested commit, is not expired,
and is named Nocturne-0.5.7.1-Windows-x64-unsigned. Size 54,465,871 bytes; retention
until 2026-11-17. SHA-256:
bb28a693b772ea71b793822d5c00e457772e274cca2fbcb7be9afef1657ba052.
Download: https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39088586425/artifacts/12121976207

README/BUILDING link the new tested unsigned patch and retain the original 0.5.7
package as a fallback. TODO records completed checks. Source ZIP and wheel passed
integrity checks with the byte-identical original pieces and no removed Cburnett
or Windows launcher files. Refreshed source/checksums after final documentation.
Only docs follow the passing native commit. The optional API check again returned
29 legal ChessDB moves and Lichess token requirements; authenticated Lichess data
is not claimed. User-machine Smart App Control acceptance, manual DPI and actual
engine interaction remain unverified. This patch restores the requested baseline;
it is not claimed to resolve or bypass the unconfirmed Windows trust decision.


## 2026-10-18 — 0.5.7.2 piece artwork only

User confirms 0.5.7.1 works and requests adding only the different pieces.
Verified the complete local tracked manifest matches confirmed working GitHub
commit 40f185ec20e2acd5dbcb464c7d0e848dfbbd800d before editing. Replaced only the
12 assets/pieces/*.svg files with the exact Lichess Cburnett sources at lila
commit cd2656d2787a766ba743da8da1dd3b24975e6329. All twelve local Git blob hashes
match that pinned upstream directory; only filename case is normalized. GPLv2+
art by Colin M. L. Burnett is compatible with this GPL-3.0-or-later distribution.
Added licenses/CBURNETT-GPL-2.0-or-later.txt and CBURNETT-NOTICE.txt and corrected
THIRD_PARTY_NOTICES.md. Using .txt for credits lets existing wheel/source license
patterns collect them, so no packaging-pattern/specification change is needed.

Versioned 0.5.7.2 in pyproject, __init__, Windows version strings and artifact
paths. All GUI/rules/engine/controller/test/settings code, piece sizing, clock
UI, three-line MultiPV behavior, build script, PyInstaller spec, MANIFEST and
requirements remain byte-identical to working 0.5.7.1. No tooltip, launcher,
clock option, dependency or signing change. No new test mirrors the asset swap;
existing GUI coverage includes drag/click/animation/promotion and PV behavior.

Ruff passed. Both python -m nocturne --smoke-test commands exited 0 (offline and
external UCI using the local protocol fixture, including two-move Game Review).
Executed a real Qt renderer/icon check: all twelve QSvgRenderers are valid,
produce nontransparent pixels and provide non-null promotion QIcon pixmaps.
Captured/visually inspected dark 1920×1040, compact 1024×660 and light 1440×1040
actual Qt windows. Pieces are clear at the existing size; rendering code stays
unchanged. Simulator scores are explicitly labelled. Updated docs previews,
README, CHANGELOG and TODO. Focused GUI suite is running; next is archive/license
verification and native Windows full tests/build before changing the download.


Focused command completed:
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -p test_gui.py -q
39 tests passed in 34.387s, no failures. This asset-only patch does not require
re-running unrelated local engine suites; the unchanged Windows workflow runs
full discovery twice before packaging. Both actual app smoke commands exited 0.


Archive checks completed: scripts/package_source.py and pip wheel --no-deps
--no-build-isolation both succeeded. Both archives pass ZIP integrity checks,
include GPL and author-credit texts plus all twelve byte-identical pinned SVGs,
and contain no EXE/batch/PowerShell launcher. Wheel SHA-256:
9ad6c8ca1253e8d516dcef35cfc911b04d55351e2aed815b99b3606c04573269.
Rechecked source diff: all 63 Python files except version-only __init__.py are
byte-identical to working 0.5.7.1; spec, MANIFEST and all requirements also match.
Next: publish the asset-only update and execute native Windows validation.


## 2026-10-18 — 0.5.7.2 piece-only Windows delivery verified

Published source commit 031f389e79e258bd6b9a8023730e063d1eafb5eb from the confirmed
working 0.5.7.1 tree, using GitHub blob/tree/commit/ref operations with a matching-
head lease and no forced update. Remote comparison confirms no behavior/test
code changes; only the 12 SVGs, two license/credit files, version metadata and
documentation/screenshots differ. GUI/engine/rules/settings/build logic is intact.

Windows run 39089980725/job 117564482194 completed successfully. Full unittest
discovery ran twice: 153 total each, 148 passed and 5 optional skips, in 95.171s
and 103.852s. All six loopback HTTP tests ran. Both Ruff checks passed. The
existing GUI tests exercised drag, promotion and stable PV slots with the new
artwork. PyInstaller built the windowed application and both frozen smoke paths
passed (offline and external UCI, including a full two-move Game Review). The
check=True builder completed after both launches; no test/build failure occurred.
The optional API check returned 29 legal ChessDB moves and Lichess token-required
responses. Authenticated Lichess data is not claimed.

Verified artifact metadata/logs: 12122595914 belongs to the passing source commit,
is not expired, and is named Nocturne-0.5.7.2-Windows-x64-unsigned. Size 54,468,748
bytes, retained until 2026-11-17. SHA-256:
938d98832eab83a9ed0b4d5b57e2e44906296b6fc35362c492016e1460d18da9.
Download: https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39089980725/artifacts/12122595914

README and BUILDING now link the new package and retain working 0.5.7.1 as a
fallback. TODO and this log record the completed milestone. Local source ZIP and
wheel integrity, exact pinned pieces, GPL/credit inclusion and launcher checks
passed; refreshed source/checksums after final documentation. Only docs follow
the tested application/assets commit. No extra clock or other feature is added.
Next: user desktop acceptance of the rebuilt unsigned EXE, manual Windows DPI
and piece appearance/drag/promotion checks with their actual installed engine.


## 2026-10-18 — 0.5.7.3 neutral appearance and Display clocks

User confirms 0.5.7.2 works and requests standard square/interface colors plus the
previously requested clock controls. Started from df0de14f3a50499e36eb82d98f6ad0d3e3de94b3.
Changed gui/theme.py to shared neutral charcoal/light palettes, with Classic
brown/cream and Grey boards. settings.py migrates legacy Forest defaults once
(appearance_version=1), preserves other old choices and later explicit selections,
and validates/persists show_clocks. No chess-rule/search/time-control code changes.

Updated board.py frame/coordinates/selection/legal dots and subtly colored hint
markers, moves.py HTML, widgets.py evaluation graphics, explorer_panel.py WDL
bars and review_panel.py quality colors to remove the green UI tint. Marker
geometry/opacity and fixed PV slots stay intact. dialogs.py uses Classic as its
fallback. Original icon.svg is neutral; scripts/make_icon.py regenerated icon.ico.
All twelve licensed Cburnett piece SVGs remain byte-identical to working 0.5.7.2.

window.py adds the White/Black clock strip above the analysis board and the
checkable Display → Clocks action. Existing Play labels follow the same preference.
Both presentations read actual Game.clock_values(); analysis remains paused,
untimed games show infinity, and hidden Play clocks keep running. Preference
changes do not stop/restart engine search or change position/time control. Applied
shared text colors to all candidate rows, including pinned rows, on light changes.
Adjusted player clock geometry and content margin after actual Play capture
showed active styling too tight. No new clock engine or inferred PGN clock times.

Executed Ruff check src tests scripts: passed. Settings discovery: 4 passed
(0.000s), including once-only migration/idempotence/resource preservation and
boolean validation. Focused GUI discovery: 41 passed (38.494s), including new
analysis/untimed/timed visibility + reopen and deterministic hidden-running-clock/
save-restore regressions. Full local discovery then ran 157 tests in 79.731s:
146 passed, 11 skipped, no failures. Six HTTP tests are sandbox socket skips;
five historical optional checks skip. Following final clock/icon styling,
clock-only discovery ran twice: 2 passed in 1.765s and 2 in 1.795s. Final Ruff
passed; both offline and external-UCI app smoke commands exited 0 again, including
a complete two-move Game Review via the protocol fixture. Native full validation
will cover final styling changes before delivery. No claim of a final local
full rerun after the last visual spacing adjustment.

Captured and visually inspected real Qt dark 1920×1040, compact 1024×660,
light 1440×1040, clocks-hidden and Grey views. Also exercised actual human 5+2
creation/e4 play: increment applied to White and Black's clock runs; captured the
native board/clock portion, not a fabricated UI. Analysis/review fixture values
are explicitly labelled simulator test data. scripts/capture_preview.py adds
--hide-clocks and --board-theme. Updated README/CHANGELOG/architecture/TODO and
preview assets. Version/artifact metadata is 0.5.7.3; build spec/script, all
requirements, UCI/rules/game model and piece sources remain unchanged.

Next: verify source/wheel/license contents, publish, run native Windows full tests
and frozen smoke checks, then replace the download link. Manual Windows trust/
DPI and real-engine interactions remain to verify. The Play sidebar can clip
some content at narrower widths; tracked for layout follow-up. This does not
hide either player clock or affect analysis's full-width PV area. PGN clock-
comment import remains unsupported and documented. No tooltips/launcher scripts.


Also captured/inspected dark/light Game Review and Nibbler-style candidate lines
with the neutral palette, and updated their documentation screenshots. Final
Play clock spacing uses a stable QLabel content margin, verified in the actual
running 5+2 view. All app code is now frozen for native validation.


Source ZIP and wheel build commands succeeded. Both archives passed integrity,
Cburnett source-hash/credit/license and no-launcher checks. Wheel SHA-256:
63e9d6464b6ebb91a76d1e42cc69cb20d3c963c44b1a60fb027924f2b467f972.
Critical-file hash checks confirm the build script/spec, MANIFEST, requirements,
CandidatePanel snapshot controller, UCI controller/transport and all piece SVGs
match working 0.5.7.2. No further application changes before native verification.


## 2026-10-18 — 0.5.7.3 neutral appearance/clocks Windows delivery verified

Final application/assets commit e99f58e900285e2646caa3204f90249d709e4d5b passed
Windows run 39095336406/job 117580486769. Full discovery ran twice: 157 total
in each run, 152 passed and 5 optional skips, in 98.932s and 99.584s. All six HTTP
tests executed. Both Ruff runs passed. New tests verify once-only palette
migration with preserved hash/MultiPV/choices, clock boolean validation, analysis
clock values and preference reload, hidden running-time continuity, unchanged
FEN/engine generation and saved remaining-time/time-control integrity. Existing
PV/hover/click, review, rules and persistence checks passed. No test failure.

PyInstaller built windowed Nocturne.exe with the neutral multi-resolution icon;
both frozen smoke paths passed (offline and external UCI with complete two-move
Game Review). The existing check=True build gate completed after both launches.
The optional API check returned 29 legal ChessDB moves and Lichess authentication
requirements; no authenticated Lichess result is claimed. Build spec/script,
requirements, game/rules/UCI code and working Cburnett piece sources are unchanged.

Verified artifact metadata and upload log: 12124810527 is
Nocturne-0.5.7.3-Windows-x64-unsigned, from the tested source commit and not expired.
Size 54,693,152 bytes; retained until 2026-11-17. SHA-256:
f00beba4ee0cbb9136cfff848e7a3510947e371b01938a279d57c623aafe0d3e.
Download: https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39095336406/artifacts/12124810527

README/BUILDING now link the tested package and retain working 0.5.7.2 as fallback.
Updated TODO and this visible development log. Source ZIP/wheel integrity,
Cburnett byte/credit/license and no-launcher checks passed; source/checksums
refreshed after final docs. Only documentation follows the passing build; no
application source changes after final native validation. Next is user desktop
verification of the new appearance and Display clock toggle, including Windows
trust/DPI, real engine interaction and the tracked narrow Play-sidebar layout
limitation. PGN clock-comment import was added in the following 0.5.7.4 phase.
No claim of a signed or Smart App Control-verified executable.

## 2026-10-18 — 0.5.7.4 imported PGN clock display Windows delivery verified

User supplied a PGN with standard `[%clk ...]` and `[%timestamp ...]` comments;
the Display → Clocks strip showed infinity and the move list printed raw tags.
Added tolerant clock parsing, per-position/per-variation latest-known values,
clean per-move clock labels when enabled, em dashes for unrecorded positions in
tagged games, and raw machine-tag hiding while preserving PGN comments for export
and save/restore. Untimed games without clock annotations retain infinity. No live
timer or time-control is inferred from imported clock comments.

Changed core/notation.py and core/game.py for parsing and variation-aware display
data; gui/window.py connects the data to the existing toggle, board strip and
analysis move line. Updated README, CHANGELOG, architecture, build notes, TODO and
this log; version metadata is 0.5.7.4. Regression tests cover hours/minutes and
tenths parsing, invalid clock tags, branch-specific clock values, unrecorded root
positions, the display toggle, preservation on PGN export and game save/restore.
Focused rules and GUI tests passed (1 each). Full local discovery ran 159 tests:
148 passed, 11 skipped, no failures. Ruff passed; offline and absolute-path
external-UCI app smoke checks exited 0. One initial UCI smoke invocation used
relative executable paths and timed out; rerunning with the absolute interpreter
and fixture paths passed.

Windows run 39096484337/job 117583902608 tested source commit
d020afff00f871f23ccea7c390f27865bf85b964. Both native runs completed 159 tests:
154 passed, 5 optional skips (83.309s / 92.496s). Ruff passed twice. PyInstaller,
offline and external-UCI/Game Review packaged smoke checks and artifact upload all
passed. Artifact 12125455189, `Nocturne-0.5.7.4-Windows-x64-unsigned`, is 54,697,193
bytes and retained until 2026-11-17. SHA-256:
`8d4a33a54066c972c0f1dc71b1ac83e55ad74781b27771d5d4c7a7d57de4ca66`.
Download: https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39096484337/artifacts/12125455189

The exact supplied-style inline `[Best]` annotations were accepted alongside
standard clock/timestamp comments. Export and saved-game restoration preserve
the original machine tags; display strips them into readable times. No timer or
time control is inferred, and positions without a recorded clock show an em dash.
Manual Windows Smart App Control acceptance and user-machine interaction remain
unverified. No signing, security-policy or launcher changes were made.

## 2026-10-18 — Download 1 / commit 1: 0.5.7.5 live appearance preview

Requested three cumulative commits/builds. This first change adds reversible
Studio previews for board palette, piece style, light/dark, coordinates and
overlays. dialogs.py shows a sample BoardWidget beside scrolling controls and
emits visual-only changes. window.py keeps the preview separate from config;
Cancel/window-close restores the original appearance without changing saved
preferences, board, clocks or engine generation. Save commits choices normally.
board.py lazily caches SVG renderers for Cburnett and Original, including matching
promotion icons. Restored the twelve original MIT pieces from pinned 0.5.7 source;
updated package-data and notices, settings validation, README/CHANGELOG/TODO.

Executed focused GUI/settings checks: 5 passed in 1.775s. Full local discovery:
160 tests in 99.267s, 149 passed and 11 skipped, no failures. Ruff passed. Both
offline and absolute-path external-UCI/Game Review smoke commands exited 0.
Built the 0.5.7.5 wheel and checked ZIP integrity plus all 24 SVG assets. Captured
and inspected the actual 860x620 Qt dialog (docs/studio-preview.png): preview and
Save/Cancel visible, long form scrolls. No test failure. Six local socket tests
and five optional historical checks skip as before. Native Windows validation
will run on this commit before download delivery. Next: MultiPV reference colors
and numbered destination circles in the second commit. No signing/build-tool or
security-policy change; desktop trust acceptance remains unverified here.

## 2026-10-18 — Download 2 / commit 2: 0.5.7.6 MultiPV presentation

First source commit 3229377b796bba09e6eb7f9beabfc68b7e907d88 is undergoing native
Windows validation in run 39097285528. Its first full Windows test pass succeeded;
packaging is still running as this second source commit is prepared.

Updated theme.py, board.py, candidates.py and moves.py: rank-one hints use teal,
alternatives green; thin lines end in matching numbered circles at destination
centers. The higher-ranked shared-destination marker is drawn above the rest.
Candidate rows have matching round badges, colored first moves and contrasting
White/Black continuation text. Three-line reservations and hover snapshots remain
intact. settings.py upgrades to reference lines once, preserving later explicit
arrow choices. Dialog previews inherit the selected marker style. Added two
behavior regressions and a --multipv option to the real Qt capture tool.

Focused tests passed: 7 in 0.902s, covering five-rank destination execution,
hover/update stability and settings. Full local discovery: 162 tests in 92.236s,
151 passed, 11 skipped, no failures. Ruff and the external-UCI/Game Review smoke
check passed. Captured/inspected actual Qt five-PV UI and board-only reference
views (docs/reference-multipv.png and reference-board.png), explicitly using
fixture suggestions rather than claiming measured engine evaluations. Updated
version/build artifact names, README/CHANGELOG/TODO and this log. Native Windows
validation runs on the versioned commit. Next: hide metadata in Game Moves while
preserving PGN/export data, with an optional read-only developer view.

## 2026-10-18 — Verified Windows downloads 1 and 2

Download 1, source 3229377b796bba09e6eb7f9beabfc68b7e907d88, passed run
39097285528/job 117586249755: both 160-test runs succeeded (155 passed, 5 optional
skips) in 116.719s and 128.484s. Ruff, native packaging and frozen GUI/UCI/Game
Review launch checks passed. Artifact 12125655113 is the matching non-expired
Nocturne-0.5.7.5-Windows-x64-unsigned, 54,781,794 bytes. SHA-256:
49f0ccae9cec311befd7debccb8c23fec0b7618038a8c68340b623e6bac620f9.
https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39097285528/artifacts/12125655113

Download 2, source 7a4169e5fb4119f6cb3b021fbf79fe2e8dadd013, passed run
39097588959/job 117587131716: both 162-test runs succeeded (157 passed, 5 optional
skips) in 105.242s and 105.758s. Ruff, native packaging and frozen GUI/UCI/Game
Review launch checks passed. Artifact 12125422408 is the matching non-expired
Nocturne-0.5.7.6-Windows-x64-unsigned, 54,968,343 bytes. SHA-256:
925d1b778ce3917bbb69de69acc1ab20d23894883d01d533503c7f7449170b30.
https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39097588959/artifacts/12125422408

Both are retained until 2026-11-17. Exact artifact source hashes verified. These
build results establish native tests/packaging, not user-machine signing or trust
acceptance. The third feature commit and download follow separately.

## 2026-10-18 — Download 3 / commit 3: 0.5.7.7 clean moves and optional raw PGN

Changed window.py to render the bottom move strip from numbered SAN/variation
tokens alone. Clocks, timestamps, comments, NAGs and review metadata remain in
the game model, SQLite saves, PGN editor and export. Display → Clocks still
controls the board clock strip. Added Dev → Show raw PGN data, default off via
validated settings, opening a separate read-only tab with a complete-PGN copy
button. The raw text is refreshed from the authoritative game, not an editable
duplicate. Backspace/letter shortcuts in that text view cannot mutate the board.
Updated clock-display regression expectations for the requested clean moves,
added raw-view/export/storage/focus coverage, and updated docs/version metadata.

The first focused run exposed a misplaced old clock assertion in the new test;
corrected its test placement. Seven focused checks then passed in 1.057s, followed
by the final keyboard check (1 passed, 0.302s). The first full run found only an
outdated menu-list expectation (Dev was newly added); updated that expectation.
Final full local discovery: 163 tests in 104.795s, 152 passed, 11 skipped, no
failures. Ruff and both offline/absolute-path external-UCI/Game Review smoke
commands passed. Captured/inspected real Qt normal and optional raw-PGN screens
(docs/clean-game-moves.png, raw-pgn-data.png): metadata is absent from Game Moves,
clock values remain above the board, and the opt-in view retains the full data.

This is the third and final requested feature commit. Windows CI will test this
exact source and create download 3 after native validation. The previous two
verified downloads remain available independently. No build/signing/dependency
or security-policy change; actual desktop trust acceptance is not claimed.

## 2026-10-18 — Download 3 verified; three-commit delivery complete

Third commit 9236c785e9cded1ea7b39e3f2693ac9077ce6db4 passed Windows run
39098023371/job 117588388622. Both full runs completed 163 tests: 158 passed and
5 optional skips each, in 113.465s and 128.494s. Ruff passed twice. Native
PyInstaller packaging and offline/external-UCI/Game Review frozen smoke checks
passed before upload. No Windows test/build failure occurred in this series.

Artifact 12125303892 is Nocturne-0.5.7.7-Windows-x64-unsigned, from the exact
tested source, 55,156,789 bytes, non-expired and retained until 2026-11-17.
SHA-256: 221126c71b044e1b8f5f946af5e1aaf41bf902127db7e83c2d25e58b64644ba0.
https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39098023371/artifacts/12125303892

Verified exactly three published feature commits: 3229377 (previews), 7a4169e
(MultiPV presentation), 9236c78 (clean moves/raw view). All three source-specific
downloads remain independent. Application files match the final tested commit.
Final artifact receipts/download links are recorded in the workspace docs without
adding a fourth commit. Refreshed local source archive/checksums after those docs;
wheel/source integrity, 24-piece inventory and no-launcher checks passed. Desktop
Smart App Control acceptance remains unverified; no signing/security changes.

## 2026-10-18 — 0.5.7.8 subtle analysis-panel text

User approved the board hints but requested no numbered badges/rank colors on
the analysis side and a barely noticeable White/Black move-text distinction.
Changed candidates.py to remove row badges and use neutral gray headings;
moves.py removes the rank-one color override and uses near-neutral warm grays
for Black moves (dark #e5e3e2 versus White #ededed; light #302d2b versus #262626).
Removed the unused rank-text palette helper from theme.py. BoardWidget and its
teal/green connecting lines/numbered circles are unchanged. Fixed three-line PV
slots, hover snapshots and internal candidate ranks remain in place.

Updated the existing five-candidate GUI regression for unnumbered neutral rows,
while retaining destination execution checks. Two focused checks passed in
1.081s; all 45 GUI tests passed in 58.476s. Ruff passed. Offline and absolute-path
external-UCI/Game Review app smoke checks exited 0. Captured and inspected real
Qt five-PV dark/light views (subtle-analysis-dark.png, subtle-analysis-light.png),
explicitly labelled protocol-simulator test data. No test failures. Updated
README/CHANGELOG/TODO and version/artifact metadata to 0.5.7.8. Native full tests
and frozen launch checks will validate the exact Windows build before delivery.

### 0.5.7.8 Windows delivery verified

Source 6e12832ff813f74c4946d0cb018e04e6c698fbf8 passed native run 39099441736/job
117592505281. Both full discoveries ran 163 tests: 158 passed, 5 optional skips
each, in 134.600s and 137.800s. Ruff passed twice; native packaging, offline and
external-UCI/Game Review frozen launch checks passed. No test/build failures.
Verified the artifact's source SHA, versioned name and non-expired status:
12124934909, Nocturne-0.5.7.8-Windows-x64-unsigned, 55,392,327 bytes, retained
until 2026-11-17. SHA-256:
0ca9a00c0e5470b6f068bfcefb9ce3a7114352d3e7df523a935e9b7bd0501ba7.
https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39099441736/artifacts/12124934909

README/BUILDING link the verified build; TODO and this log record the actual
checks. The board.py hash matches approved 0.5.7.7. No application source changes
follow native validation; only these release notes/links are updated. Source ZIP
integrity, 24-piece inventory and no-launcher checks passed. Signing/build tools
and dependencies are unchanged. User-machine trust acceptance remains unverified.


## 2026-10-18 — 0.5.7.9: padded SAN slots and expandable PVs

**Implemented:** `gui/moves.py` uses equal-width nonbreaking SAN anchors with
clickable horizontal padding, larger line spacing and vertical hit padding.
Three-row measurement excludes a clipped fourth line. `gui/candidates.py`
applies fixed/expanded mode to existing and new rows. `gui/window.py` adds
**Dev → Expand analysis beyond three rows**; `settings.py` validates and stores
the preference, off by default. No engine restart or board-style change.

**Validation so far:** original 45 GUI tests passed in 59.547s. Initial new hover
test failed because its separate offscreen top-level window did not receive
mouse moves; switched to the actual application analysis widget. The equal-slot
width/padded click test, full-PV expansion test, and fixed-slot hover stability
test then each passed. Ruff and both offline/external-UCI source smoke commands
passed. Full local suite: **165 run, 154 passed, 11 skipped**, no failures,
118.846s (`QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover
-s tests -q`). Six HTTP-server tests skip under sandbox socket restrictions;
five optional tests also skip. Native Windows packaging is pending.

**Files:** move/candidate/window/settings components, GUI/settings tests, preview
capture helper and real Qt screenshots, version/build metadata, README, changelog,
roadmap and this log. No launcher scripts or signing-policy changes.

**Next:** finish full validation and native Windows build, record the exact test
results and artifact, then deliver its download. Actual Windows trust decisions
and high-DPI appearance still require user-machine verification.


### 0.5.7.9 — Native Windows delivery verified

**Published:** `439b2dc0ccf6a1c97f7e1dbbb32fa2d5b351859d`, run 39100427444,
job 117595398583, overall success. Native `python -m unittest discover -s tests
-v` and the build's second full discovery each ran **165 tests: 160 passed,
5 optional skips**, in 74.675s and 82.054s. Ruff passed twice. The Python Windows
builder completed PyInstaller and both gated packaged launch checks, including
external-UCI/Game Review. No test failures. New integration checks cover equal
SAN widths, padded hover/click activation, full final-PV visibility, preference
storage and reverting to stable three-row slots.

**Artifact:** [Nocturne-0.5.7.9-Windows-x64-unsigned](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39100427444/artifacts/12126700388),
ID 12126700388, 55,631,228 bytes, expires 2026-11-17. SHA-256:
`5d5ed7b16311c46faae08e2e92afe923a29e481a780c51bd356c38e9fed1c3d0`.
Source ZIP integrity check passed, all 24 piece SVGs present, no `.bat`, `.cmd`
or `.ps1` launchers. Real Qt fixed/expanded captures are in `docs/`.

**Remaining limits:** unsigned executable trust and physical Windows high-DPI
appearance require user-machine checks. Expanded mode intentionally allows rows
to change height as PV lengths change; fixed mode remains the default. Live
ChessDB returned 29 legal moves; authenticated Lichess data was not verified
without a user token. No engine, board marker, launcher or signing-policy changes.

**Completed:** requested display phase and Windows delivery. README, BUILDING,
TODO and this log now record actual results; application code is unchanged
after the successful build. Next: user feedback on target sizes and spacing.


## 2026-10-18 — 0.5.7.10: quiet colors, palette-relative highlights and wheel moves

**Phase implemented:** `theme.py` lowers text brightness and supplies separate
White/Black PV, game-history and muted metadata colors for both appearances.
`moves.py` renders those colors. `board.py` makes candidate rods 1–2px and
number circles smaller; last-move squares preserve their own hue/saturation
with +/-0.05 HSV value (darken pale squares, lighten dark ones). Check and manual
annotation colors retain their distinct meaning. Real Qt dark/light captures
are `docs/quiet-studio-*.png`, labelled with UCI simulator data.

**Navigation:** shared `gui/wheel.py` accumulates wheel and trackpad deltas,
respecting Shift for ordinary scrolling. Board and game-history wheel steps use
the existing selected-branch navigation. PV wheel steps preview the frozen
displayed candidate, bound to root/end; leaving restores the real board.
`window.py`, `candidates.py` and `settings.py` add independent persistent Display
toggles (default on), including newly created candidate slots and the Play table.
No position edits or variation insertion during PV preview.

**Executed:** focused GUI tests for game/PV wheel navigation, actual rendered
White/Black/history colors, and last-move pixels across all six board themes:
**4 tests passed**. Ruff passed; both source offline/external-UCI smoke checks
passed. Initial tests/lint caught a missing palette import, fixed before these
passes. Full local suite (`QT_QPA_PLATFORM=offscreen .venv/bin/python -m
unittest discover -s tests -q`) **169 run, 158 passed, 11 skipped**, no failures,
121.629s. Six HTTP tests skip under sandbox socket restrictions; five are optional.
The suite includes partial mouse-wheel and pixel-trackpad accumulation. Native
Windows build pending.

**Modified:** board/move/candidate/window/theme/settings components, new wheel
helper, GUI/settings regression tests, version/build metadata, screenshots and
README/CHANGELOG/TODO/BUILDING/PROGRESS. No batch/PowerShell launchers or changes
to signing/trust policy.

**Next:** finish the full suite and native Windows pipeline, publish its actual
test results and download. Physical trackpad feel, high-DPI contrast and Windows
trust acceptance remain user-machine checks. Expanded PV mode can still change
row heights by design; fixed three-row mode remains the default.


### 0.5.7.10 — Windows delivery verified

**Source:** `2f68a331f6f213ac03b5e9cdf33b11929518aa26`. Windows run 39101008893,
job 117597097215, overall success. `python -m unittest discover -s tests -v`
and the builder's repeated full discovery each ran **169 tests: 164 passed,
5 optional skips**, in 131.223s and 128.822s. Ruff passed twice. The existing
Python Windows builder completed PyInstaller and both gated frozen GUI launch
checks, including external-UCI/Game Review. No failures.

**Download:** [Nocturne-0.5.7.10-Windows-x64-unsigned](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39101008893/artifacts/12126636588),
artifact 12126636588, 55,885,463 bytes, expires 2026-11-17. SHA-256:
`552dd4f800ff646ee850a4597666b6d2bdebd4b2396c6a86bcebf504493a75c7`.
The source ZIP passed integrity checks, includes all 24 piece SVGs and contains
no batch/CMD/PowerShell launchers. README/BUILDING/TODO now contain actual results
and the download. Application code is unchanged after this successful build.

**Completed:** restrained side/history text colors in both appearances, thinner
numbered candidate hints, per-square hue-preserving last-move shading, wheel
game navigation and reversible frozen-PV previews with independent saved Display
toggles and Shift scrolling. Fixed three-row slots and variation trees retained.

**Limits/next:** physical Windows high-DPI contrast, trackpad feel and unsigned
executable acceptance require user-machine feedback. No trust-policy changes.
The live API check returned 29 legal ChessDB moves; authenticated Lichess data
was not tested without a user token. No further implementation is pending for
this request; next is user feedback on the new appearance and navigation.


## 2026-10-18 — 0.5.7.11: analysis metrics and 10% move shading

**Implemented:** `gui/candidates.py` uses full-width rich headers: restrained blue
evaluation/API win/frequency (and separate ChessDB score), neutral depth/WDL/
sample/source information. Uniform width-dependent metadata heights prevent
engine/API updates moving hovered lower candidates. Existing three PV text rows,
equal SAN slots, pins, wheel previews and move text colors are retained.
`gui/theme.py` adds metric/neutral metadata colors in both appearances.

`gui/explorer_panel.py` exposes validated results/provenance; `gui/window.py`
joins them only to the matching current engine position. Headers match the
first candidate UCI move, use total position games for frequency, use actual
side-to-move wins (draws stay in the denominator), label cached/live and source,
and show dashes for absent counts. ChessDB's White-perspective score is distinct
from win/frequency. Disabled/new/stale queries cannot leak old percentages.
Main evaluation is blue; telemetry is neutral. No new automatic network traffic.

**User steering:** increased `board.py`'s per-square HSV value shift from 0.05 to
0.10, keeping hue/saturation, and updated the six-palette rendered-pixel test.

**Executed:** focused GUI tests for blue/neutral actual document formatting,
White/Black API percentages and total-game denominator, API-update hover
stability, stale/source/disabled result rejection, narrow/wide metadata sizing,
10% highlight pixels, plus existing three-row hover regression: **5 tests passed**.
One initial test expected the wrong ChessDB label ordering; display now explicitly
labels `DB White` and the corrected test passed. Ruff passed. Full local and
native Windows validation pending. Real Qt captures use clearly labelled UCI
simulator/database fixture data, not measured engine/live API statistics.

**Files:** candidate/explorer/window/theme/board GUI components, GUI tests, real
Qt captures, version/build metadata, README/CHANGELOG/TODO/BUILDING and this log.
No launcher or signing-policy changes.

**Next:** full tests, frozen offline/external-UCI checks and native Windows build,
then publish the verified artifact/results. Real Windows trust/high-DPI appearance
and authenticated live Lichess data remain user-machine checks.


### 0.5.7.11 — Local full validation

`QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -q`:
**172 tests, 161 passed, 11 skipped**, 138.249s, no failures. Six socket-based
HTTP tests skip in this sandbox; five skips are optional. Both offline and
external-UCI source smoke commands passed. Windows run 39101814543 / job
117599461444 passed its first full suite and is packaging. User added the exact
Nibbler piece request while that build ran; continued cumulatively as 0.5.7.12.

## 2026-10-18 — 0.5.7.12: original Nibbler pieces as default

**Source inspected:** rooklift/nibbler commit
`6eb0f066402c0cf53d08d682dbc394acd9cb5fb9`, `files/src/pieces`. The white knight
visually matches the supplied reference exactly. Downloaded all 12 PNGs via the
GitHub connector, checked each original Git blob SHA-1 and retained original
names/bytes. Nibbler credits Lichess; Lichess lists Merida as Armando Hernandez
Marroquin / GPLv2+. Added artist/provenance notice, GPL2+ text and 12 upstream
editable Merida SVGs from pinned lila commit
`cd2656d2787a766ba743da8da1dd3b24975e6329`. No Nibbler application code copied.

**Implemented:** `board.py` supports cached PNG/QPixmap rendering alongside SVG,
with smooth scaling and upstream transparent padding. Promotion choices resolve
the active set's file. Dialog/window/settings default to Nibbler; normalization
selects it once on upgrade, preserving later explicit alternatives. Wheel, blue
API headers, neutral depth and 10% last-move adjustment retained. Package-data
and manifest include PNGs and source SVGs; spec already recursively includes
assets/licenses. Updated distribution/research notices to remove old no-assets
claims. Added actual dark/light Qt captures, labelled simulator/fixture data.

**Executed:** new all-twelve PNG/default/style-switch GUI test passed; existing
underpromotion test passed with four nonempty PNG icons; Studio live preview/
Cancel/Save test passed. All **6 settings tests passed**, including one-time
migration and retaining later user choices. Ruff passed. Full local tests, wheel
contents/source/frozen launch checks and native Windows build pending.

**Files:** 12 original PNGs and 12 upstream SVGs; board/dialog/window/settings;
GUI/settings tests; pyproject/MANIFEST/version metadata; license/provenance files;
README/CHANGELOG/TODO/BUILDING/research/PROGRESS and real Qt captures.

**Next:** finish full verification and Windows packaging; record actual artifact
results. Native PNG resolution is 240×240; extreme enlargement can soften images.
Physical Windows trust/high-DPI behavior remains a user-machine check. No launcher
or signing-policy changes; all prior requested changes remain included.


### 0.5.7.12 — Local full validation

Full local command: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest
discover -s tests -q`: **174 tests, 163 passed, 11 skipped**, 136.119s, no failures.
Both source smoke commands passed. `pip wheel --no-deps --no-build-isolation`
built 0.5.7.12; archive integrity and presence of all 12 original PNGs/12 editable
Merida SVGs passed. Windows run 39102285548 is validating this piece commit.

## 2026-10-18 — 0.5.7.13: separate evaluation graph phase

**Implemented:** `gui/widgets.py` adds neutral dotted ±100cp reference lines with
labels and an equality baseline. The transform is linear inside ±100cp and
sign-preserving log2 compression outside; fit uses 12% transformed headroom and
a minimum extent, smoothly adjusting beyond equality. Mate sentinels are placed
at the edge without determining centipawn range. Actual samples/hover values
remain raw. Labels avoid overlap when guides converge. Plotting is clipped;
shared plot geometry retains mouse click, wheel zoom and middle-drag mapping.

**Executed:** two focused native Qt graph tests passed, covering symmetry,
near-zero linearity, large-score compression, adaptive reference location, raw
score preservation, mate independence and zoom/click/reset mapping. Ruff passed.
Capture helper adds explicit `--graph-fixture` values and labels those as test
cp, not engine analysis. Full cumulative/native validation is pending.

**Files:** widgets, GUI tests, preview helper, version/build metadata and
README/CHANGELOG/TODO/PROGRESS. This graph change is a separate version-labelled
commit after the exact-piece commit. User added compact move spacing while it
was being completed; that is the next separate commit. No requested feature
has been dropped. Windows physical display/trust checks remain manual.


### 0.5.7.11 — Native metrics delivery verified

Source `7932bd96be45168673df13f4140d3f26cfdf8c2e`, Windows run 39101814543,
job 117599461444 succeeded. Both full native runs: **172 tests, 167 passed,
5 optional skips**, 153.701s / 152.316s. Ruff passed twice and the gated build/
frozen GUI checks passed. Artifact 12126029735, 56,219,724 bytes, expires
2026-11-17; SHA-256
`dbe690e8658fed08495284150cdd778fbe4f295cbfab16f3c9fee0ab16c23926`.
Later cumulative commits include the additional piece/graph/spacing requests.

## 2026-10-18 — 0.5.7.14: separate compact-spacing phase

**Implemented:** `gui/moves.py` keeps 16px analysis text, reduces a short SAN's
anchor from ten to nine monospace characters and inter-token separators from
three to one. Nonbreaking padded slots remain equal width. Analysis leading is
155% (previously 175%), with three consistently remeasured rows. Game history
keeps 14px text and reduces leading to 140% with single spaces.
`candidates.py` reduces outer PV row gaps. `window.py` reduces bottom-strip
padding, navigation-button height and minimum/default strip height to 90px.

**Executed:** four focused native Qt tests passed: eight short/long SAN columns
fit in 800px, history is tighter than analysis; padded hit-area activation; stable
three-row hover with queued updates; clicking the displayed frozen snapshot.
Ruff passed. Both source offline/external-UCI smoke commands passed. Real Qt
dark/light captures show labelled simulator/database/graph fixtures, not measured
engine/live statistics. Full cumulative suite is running; native build pending.

**Files:** move/candidate/window components, GUI tests, real Qt captures,
version/build metadata, README/CHANGELOG/TODO/BUILDING/PROGRESS. This is another
version-labelled feature commit after 0.5.7.13's graph change. No features from
earlier requests were dropped; no signing or launcher changes.

**Next:** complete full/native verification and deliver the newest cumulative
Windows artifact. Physical Windows DPI/trackpad/trust checks remain manual.


### 0.5.7.14 — Local full result and native timing failures

The compact cumulative local suite ran **177 tests: 166 passed, 11 skipped**,
148.638s, no failures. Windows 0.5.7.12 run 39102285548/job 117600840590 passed
its first 174-test suite (169 passed/5 skips, 143.637s), but its repeated suite
failed `test_review_panel_grades_accuracy_navigation_and_saved_restore` at the
fixture's 10-second completion deadline (190.767s full run). No artifact uploaded.
Windows 0.5.7.13 run 39102557054/job 117601614434 failed `test_request_spacing`: 
63ms observed between arrivals versus a 75ms lower bound, 176 tests/84.274s,
5 optional skips. No artifact uploaded. These are recorded failures, not passes.

## 2026-10-18 — 0.5.7.15: labelled timing-regression fix phase

**Implemented:** `gui/explorer_client.py` uses Qt PreciseTimer and checks the
monotonic debounce/last-send interval/Retry-After deadline at dispatch. Early
callbacks rearm instead of sending, enforcing pacing independently of platform
timer precision. `tests/test_explorer.py` adds an offline regression simulating
an early callback and active backoff before any network access.

`tests/test_external_analysis.py` gives the six-move review fixture 20 seconds
for two permitted five-second cold handshakes, bounded searches and disk/UI work.
All six labels, completion, accuracy, navigation and saved-restore assertions
remain; failures now include connection phase/review state/recent protocol log.
**Real Game Review is still per-position, without a total 10/20-second cap.**
User explicitly confirmed longer games should take longer; no production
review limit was added or shortened.

**Executed:** the offline early-timer regression passed (1 test, 0.006s); the
full review-panel grading/restore integration passed (1 test, 1.484s). Ruff
passed. Both source launch checks completed successfully. Full cumulative suite
is running; a new native Windows build follows this separate version-labelled
fix commit. No appearance changes from the reviewed compact/piece/graph builds.

**Files:** explorer client, explorer/external integration tests, version/build
metadata and README/CHANGELOG/TODO/BUILDING/PROGRESS.

**Next:** verify full/local/native results and frozen launches before providing
the latest download. Earlier timing failures remain documented. Windows trust,
physical DPI/trackpad feel and authenticated Lichess access remain manual checks.


### 0.5.7.15 — Windows DPI validation follow-up

0.5.7.14 Windows run 39102726551/job 117602120950 failed the new spacing test:
eight SAN columns occupied two lines at the fixture's hard-coded 800px width
(177 tests/125.782s, 5 optional skips). Other tests passed; no artifact uploaded.
The assertion assumed the Linux 96-DPI font metrics. Replaced it with a native
font-scaled 82-character viewport budget: eight new slots fit, while the previous
13-character pitches require 104 characters and fail. History must still be
tighter; actual text sizes and product spacing are unchanged. README now avoids
promising a fixed column count independent of platform DPI.

The timing-fix local suite ran **178 tests: 167 passed, 11 skipped**, 142.659s.
No failures. This further validation commit retains version 0.5.7.15 and uses a
descriptive version-prefixed title, following the user's commit-labelling request.
Native validation of the final follow-up is required before delivery.


### 0.5.7.15 — Final cumulative Windows delivery verified

**Source:** `4ff370ea4b2d0961e8ee4b6f4903faaeb165331d`. Windows run 39107769865,
job 117617227322, overall success. `python -m unittest discover -s tests -v`
and the builder's repeated full discovery each ran **178 tests: 173 passed,
5 optional skips**, in 159.879s and 157.084s. Ruff passed twice. PyInstaller and
both gated frozen launch checks passed (offline GUI and external-UCI/Game Review).
No failures in either final run. The exact prior failures are covered: real HTTP
request spacing, simulated early callback/backoff, native-font compact density,
and full review grading/navigation/restore all passed twice.

**Artifact:** [Nocturne-0.5.7.15-Windows-x64-unsigned](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39107769865/artifacts/12129033459),
ID 12129033459, 57,235,802 bytes, expires 2026-11-17. SHA-256:
`57079d9db689df64a1313734d25fe6fd8a556a954e7532285dfce940351eb05a`.
Final source ZIP integrity passed; 12 exact Nibbler PNGs and preferred/reference
SVG sources included, no batch/CMD/PowerShell launchers. The 0.5.7.12 wheel
archive also verified all original PNGs and upstream SVGs. No application code
changed after this successful final build; documentation-only receipt update.

**Feature commits preserved and labelled:**

| Version | Source commit | Change |
| --- | --- | --- |
| 0.5.7.11 | 7932bd96be45168673df13f4140d3f26cfdf8c2e | Blue API/evaluation metrics, neutral depth, 10% shading |
| 0.5.7.12 | 049ed72c3e19ecc1242cce4f4672909dba6213e6 | Exact Nibbler PNGs as default, preview/promotion integration |
| 0.5.7.13 | 8b024d508a971aeb62a9c3ca17b86e10342c8bc0 | Dotted ±1-pawn guides and compressed graph scale |
| 0.5.7.14 | 439e320e27e935b91cafd98320fc901fc4558661 | Tight game history and comfortable compact analysis slots |
| 0.5.7.15 | 9c0bf6b87a278ba817b02e24aca401e7c24c7408 | Database pacing and review fixture cold-start allowance |
| 0.5.7.15 | 4ff370ea4b2d0961e8ee4b6f4903faaeb165331d | Native-font DPI validation follow-up; final verified source |

**Completed:** every requested change remains in the cumulative download. Real
Game Review has per-position budgets and no 10/20-second whole-game cap. Local
full suite: 178 run, 167 passed/11 skips (six sandbox socket tests plus five
optional tests); final native suites exercise those HTTP tests successfully.
Real Qt previews explicitly label UCI/database/graph fixtures as test data.

**Limits/next:** exact runtime PNGs are 240×240, so extreme enlargement can soften
them. Physical Windows DPI/trackpad feel and executable trust still require
user-machine checks. Live ChessDB returned 29 legal moves; authenticated Masters/
Lichess data was not tested without a user token. Earlier failed runs remain
recorded above. README/BUILDING/TODO/CHANGELOG now reflect actual final results.
Next is user feedback; no requested implementation remains pending.

## 2026-10-18 — 0.5.7.16: independent database statistics and panel visibility

**Changed:** `gui/window.py`, `settings.py`, GUI/explorer/settings regressions,
`capture_preview.py`, version/build metadata and README/CHANGELOG/TODO.
The explorer visibility checkbox now affects only the lower table. Selecting a
source activates lookups without opening it; hidden lookups follow navigation and
filters and keep updating API win/frequency. A separate lookup toggle preserves
explicit offline operation, including cancellation and late-response rejection.
Existing enabled lookups migrate; fresh installations remain opt-in.

**Executed:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests
-p test_gui.py -k candidate_api -v` and `-k candidate_headers_color -v`: one passed
each. `-p test_explorer.py -k CachedGuiTests -q`: five passed (2.005 s), including
hidden-panel cache/navigation/source/close/persistence/disable coverage.
`-p test_settings.py -q`: seven passed. `.venv/bin/ruff check src tests scripts`: passed.
No failed checks in this phase; native cumulative validation is pending.

**Next:** Dev cursor-board hover experiment, then vector piece rendering. Hidden
lookups still require internet/authentication for uncached service data; no
statistics or database results are invented.

## 2026-10-18 — 0.5.7.17: experimental cursor preview board

**Created/modified:** `gui/hover_preview.py`, `window.py`, `moves.py`,
`candidates.py`, settings, GUI/settings/explorer regressions, capture helper,
`docs/cursor-hover-preview.png`, version metadata and documentation. Added a
remembered, default-off Dev option for a mouse-transparent miniature board near
the pointer. It copies board style/orientation, clamps to window/screen bounds,
and never changes the selected study board. History, PV and database hover all
use it; snapshot clicks, queued engine updates and wheel previews are retained.
Leaving/navigation/deactivation/hide/close/toggle clear it. Closing the explorer
explicitly dismisses its preview while statistics remain available.

**Executed:** focused `test_gui.py -k cursor_preview -v`: three passed (2.276 s).
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -p
test_gui.py -q`: all **61 passed** (115.183 s). Settings suite: seven passed.
Ruff passed. Native Qt capture command: `scripts/capture_preview.py --simulate
--explorer-fixture --hide-explorer --cursor-preview --lines --multipv 5 --layout
analysis-left --width 1440 --height 1040 --output docs/cursor-hover-preview.png`.
The image is an actual application capture with explicitly labelled fixture
statistics and UCI simulator moves; no measured engine-strength claim.

**Known limits/next:** physical Windows DPI/multi-monitor interaction is a manual
check; cumulative native tests/build still pending. The mini board is an experiment
and the prior main-board hover remains the default. Compared all twelve Nibbler
PNGs against the included shaded Merida vectors using Qt rendering; same style.
Switch to those vectors next to remove the fixed bitmap resolution ceiling.
Follow-up cached GUI checks: five passed (1.904 s), including explicit close-preview
dismissal. Ruff and the labelled capture regeneration passed.

## 2026-10-18 — 0.5.7.18: native-resolution shaded Nibbler pieces

**Changed:** `gui/board.py` now renders the matching shaded Merida SVGs directly
at device resolution, retaining the Nibbler default, silhouettes, gradients and
padding. Board, dragging/animation, preview dialogs, promotion icons and cursor
boards share that path. All original PNGs remain byte-for-byte archival assets.
Updated artwork notices, rendering tests, screenshots, build/version metadata
and documentation. Corrected an older ambiguous Cburnett-only notice.

**Integration fixes:** upgrades preserve saved source selections even when the
old explorer panel was hidden; the new explicit lookup opt-out is respected and
fresh installations stay offline. The source/frozen launch fixture now enables
the independent statistics flag. It additionally validates collected SVGs and
the cursor board without changing the real board.

**Executed:** focused `test_gui.py -k nibbler -v`: three passed (2.683 s), including
all twelve vectors with transparent margins/antialiased edges at 1×, 2× and 3×.
Full `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v`:
**184 run, 173 passed / 11 skipped**, 157.584 s; no failures. Six loopback HTTP
cases skip because this execution sandbox denies sockets; Windows runs them.
Following the migration/fixture integration updates, settings suite: seven passed;
`.venv/bin/ruff check src tests scripts`: passed. Both individually executed
`python -m nocturne --smoke-test` and the same command with `--smoke-engine
/workspace/.venv/bin/python /workspace/tests/fixtures/uci_simulator.py`: exit 0.
The latter uses a protocol fixture, not a real playing-strength measurement.

`pip wheel --no-deps --no-build-isolation --wheel-dir /tmp/nocturne-wheel .`
completed. ZIP integrity and contents verified: twelve SVGs, twelve original
PNGs and the new hover module. All twelve PNG Git-blob checksums match the pinned
Nibbler reference notice. Real Qt dark/light/hover captures were generated and
visually inspected; fixture counts and simulated UCI moves are explicitly labelled.

**Next/limits:** publish this cumulative build to native Windows CI, inspect
both full runs and frozen launch gates, then provide the actual Windows download.
User-machine DPI/multi-monitor interaction and unsigned Windows trust remain
manual checks. No new launch scripts or security-policy bypasses were introduced.

## 2026-10-18 — 0.5.7.18: verified cumulative Windows delivery

**Labelled feature commits:**

- `edd89b8ae167c1973d49c200f3bdf8507b33ccf4` — 0.5.7.16: independent database visibility/statistics.
- `8123c54bb7c279c13af2e15bc8798731f1c812b7` — 0.5.7.17: opt-in cursor hover board.
- `6339a03daf29939c69628164449bc26616ea6489` — 0.5.7.18: matching shaded vectors and cumulative checks.

The first two feature pushes intentionally skipped CI; the final cumulative push
built all changes. Run **39110217241**, job **117624541482**: **success**.
Actual job logs show `python -m unittest discover -s tests -v` twice, **184 tests
per run: 179 passed / 5 optional skips**, 142.631 s and 148.320 s. Ruff passed
twice. PyInstaller completed; both subprocess-gated frozen launch checks passed.
The packaged checks exercise all twelve SVGs, hidden-panel cached results and
non-mutating cursor previews, plus external-UCI/Game Review completion.

Verified twice in the logs: hidden lookup navigation/source behavior, blue API
headers, cursor snapshot/wheel/click handling, cursor appearance/bounds, 1×/2×/3×
vector drawing, and real HTTP request spacing. No failed test or build gate.
Live service check: Masters/Lichess reported the expected token requirement;
ChessDB returned 29 validated legal moves. No live Lichess percentages claimed.

[Windows download](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39110217241/artifacts/12130256462) —
artifact **12130256462**, `Nocturne-0.5.7.18-Windows-x64-unsigned`, **57,794,796 bytes**;
SHA-256 `c4473d4d59285be889e6cdf7d2707ba37e5ed6b9c0d268f0dfc279123b57abeb`,
expires 2026-11-17. Extract All; open `Nocturne/Nocturne.exe`.

**Documentation:** README, CHANGELOG, TODO, BUILDING, ARCHITECTURE and this log
updated with final behavior and receipt. No application code changed after the
verified source. Local source ZIP integrity/assets/launcher exclusion checks
passed; rebuilt after this receipt.

**Remaining limits:** physical Windows DPI/multi-monitor interaction and local
unsigned trust remain manual checks. New mini hover mode is experimental and off
by default; prior main-board preview remains selectable. Lichess needs a session
token for uncached service access. All requested implementation is complete.

## 2026-10-18 — 0.5.7.19: Cburnett high-DPI vectors

**Phase:** extend the sharp SVG rendering used by default Nibbler pieces to
Cburnett (Lichess's familiar set) and provide the same rendering automatically
for every registered SVG style. The artwork remains vector; Qt antialiases it at
the screen's device-pixel ratio. Its own SVG viewBox sets piece spacing, with no
extra renderer inset.

**Files changed:** added `src/nocturne/pieces.py` as a path/casing registry;
updated board, settings and Studio preview to use it; generalized the Qt test to
all 36 pieces in Nibbler, Cburnett and Original; added `--piece-set` to the
capture tool and a real Cburnett screenshot; updated versions, workflow artifact
name and README/CHANGELOG/TODO/BUILDING/ARCHITECTURE.

**Issue found and fixed:** the first test run showed Cburnett's existing files
use lowercase piece letters, unlike Nibbler's uppercase filenames. The registry
now maps each correctly; rerunning the focused all-style test passed.

**Commands/results:**

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest tests.test_gui.GuiTests.test_every_registered_piece_set_paints_as_antialiased_vectors_at_high_dpi -v` — passed for all 36 vectors at 1×/2×/3×.
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v` — **184 tests, 173 passed / 11 skipped**, no failures. Six loopback HTTP tests are skipped by the local sandbox; five tablebase fixture tests need a local Syzygy fixture; Windows CI runs the HTTP tests.
- `.venv/bin/ruff check src tests scripts` — passed.
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m nocturne --smoke-test` and the same command with `--smoke-engine /workspace/.venv/bin/python /workspace/tests/fixtures/uci_simulator.py` — both exited 0.
- `scripts/capture_preview.py --piece-set Cburnett` produced the real Qt capture `docs/cburnett-vector.png`; visually checked. The offscreen environment reports a missing writable Fontconfig cache, but rendering succeeds.
- `scripts/package_source.py` — created `dist/Nocturne-0.5.7.19-source.zip` (5,468,308 bytes). ZIP integrity passed; 209 entries, all 36 SVGs and the registry included, no `.bat`, `.cmd` or `.ps1` files. SHA-256: `1c9cb1db6d76b2d2522fe82eb8a59c838b19c8c3d1b8810393dd873dd879de76`.

**At feature-commit time:** native Windows validation was pending; the completed
build result and artifact are recorded below.

### 0.5.7.19 — Windows build verified

Source commit `7e87722d699f6515592624b62c2b371393202715` passed run
**39157138583**, job **117762569570**. The workflow ran the full 184-test suite
twice: **179 passed / 5 optional skips** in 96.046s and 96.660s. Ruff passed
twice. The Windows PyInstaller build and both frozen launch gates passed; the
all-piece vector-rendering regression passed in each run. The live API check
reported the existing Lichess session-token requirement and ChessDB returned
29 legal moves.

Windows artifact **12147706406**, `Nocturne-0.5.7.19-Windows-x64-unsigned`,
57,885,440 bytes, expires 2026-11-17. SHA-256:
`8133e254d93a6911f9480232afb5b263ea877182bf2fff180157e196cc960e86`.
[Download the Windows ZIP](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39157138583/artifacts/12147706406);
extract it and open `Nocturne/Nocturne.exe`. The build is unsigned. The source
archive was regenerated by Windows CI and includes the new registry, tests,
documentation and Cburnett capture.

Updated README, CHANGELOG, TODO, BUILDING, ARCHITECTURE and this log with the
final results. No runtime files changed after the tested feature commit. Remaining
manual validation is on the user's own Windows screen scaling and trust settings.

## 2026-10-18 — 0.5.7.20: evaluation and depth lead each MultiPV row

**Phase:** apply the selected combination of mockups A and B: keep the eval and
search depth as the first, prominent items in each candidate, place them close
together, keep the three reserved PV lines in a fixed middle block, and put
W/D/L, API win rate, frequency, sample and source in a fixed footer.

**Files changed:** `src/nocturne/gui/candidates.py` splits each candidate's
existing header and metadata into a compact eval/depth header and a footer.
The existing move slots remain three lines high. Header and footer font styles
are applied before measuring their reserved heights. `tests/test_gui.py` now
checks field ordering, colors, font sizing and fixed geometry at two widths.
Version metadata and release notes are labeled 0.5.7.20.

**Commands/results:**

- Focused candidate rendering and width tests — passed.
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v` —
  **184 tests, passed (11 optional skips)** in 161.136 s.
- `.venv/bin/ruff check src tests scripts` — passed.
- Offline and external-UCI smoke tests — both exited 0.
- Source ZIP `dist/Nocturne-0.5.7.20-source.zip` — integrity passed, 209 entries,
  no `.bat`, `.cmd` or `.ps1` launcher files; SHA-256
  `122af3baffb637e37efa61a3cc9b3cf323a799bc8cda275f3010021c3643ddab`.

**Windows CI:** feature commit `4e4b04456ca108547e774b1e0c3c0127370bb854`
passed run **39161047849**, job **117774243507**. Native Windows validation:
**184 tests, 179 passed / 5 optional skips**; Ruff, PyInstaller, and packaged
launch checks all passed. Artifact **12149276470** (`Nocturne-0.5.7.20-Windows-
x64-unsigned`) is **57,888,497 bytes**, expires 2026-11-17, SHA-256
`91a6a0683a862a652a647668b3b435813c3baf6e1eeb685c4340f165613d9cc1`.
[Download the Windows ZIP](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39161047849/artifacts/12149276470);
extract it and open `Nocturne/Nocturne.exe`. The build is unsigned. Lichess
Masters/Players live API checks require a session access token; ChessDB returned
29 legal moves.

## 2026-10-18 — 0.5.7.21: two-row PVs with a per-candidate expand arrow

**Phase:** reserve two move rows for each MultiPV candidate. Put a small
expand/collapse arrow at the end of its second row. Expanding shows the full PV
reported for only that candidate; other candidate rows stay compact. Collapse
returns it to two rows. If the candidate's suggested first move changes, clear
that row's expansion so it does not carry over to a different variation. Keep
the existing developer setting for expanding every line.

**Files changed:** `candidates.py` now owns an independent expansion state and
arrow for each rank, keeps a narrow control area clear, and recalculates whether
the arrow is needed from the current wrapped PV length. `moves.py` measures
wrapped lines at the visible width. `window.py` renames the developer option to
**Expand all analysis lines**. `explorer_panel.py` passes live loading and
terminal error state to candidate footers; completed empty Lichess results say
**No games found**. GUI tests cover two-row default, per-row toggling, full PV
visibility, unaffected ranks, line replacement and board state, plus loading,
empty-result and service-error wording. Version metadata and build labels are
0.5.7.21.

**Validation:** 186 tests passed overall (175 passed, 11 optional skips).
Focused GUI regressions passed and Ruff passed. The 209-entry source archive
passed ZIP integrity checks and contains no script launchers. Windows run
39165248055 passed **186 tests (181 passed / 5 optional skips)** in 205.575
seconds; Ruff, PyInstaller, packaged launch checks and the live database check
passed. Artifact **12150402048** is 57,894,483 bytes, expires 2026-11-17, and
has SHA-256 `87f3dae9f32423bda6c92aeb89fd436e9f46c732316f272517c580c99ea79212`.
The build is unsigned. The published two-row PV feature commit is
`fbdccac4817f61fc1ba694c93d667d4cb08ab08d`; database-status follow-up is
`d1c1b019ec931a0559a10b1e6016d6b246d146c7`.

## 2026-10-19 — 0.5.7.22: keep MultiPV wheel previews steady

**Phase:** Preserve the selected ply and the displayed PV snapshot while
scroll-browsing a candidate that retains the same root move. Queue newer engine
continuations until the preview ends. If a different root move occupies that
candidate rank, end the old preview and display the new line.

**Files changed:** `moves.py` records the wheel-selected ply until actual pointer
movement or preview cancellation. `candidates.py` keeps same-root engine updates
queued and resets the wheel preview when that rank's root move changes. GUI
regression coverage checks the selected ply and board position through same-root
updates, then verifies reset after the rank changes. Version and Windows artifact
labels are 0.5.7.22.

**Validation:** 187 tests passed overall (176 passed, 11 optional skips).
Focused wheel-preview tests and Ruff passed. The 209-entry source archive
passed ZIP integrity checks and contains no script launchers. Windows build
and packaged smoke checks are pending.
