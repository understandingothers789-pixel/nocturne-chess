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
