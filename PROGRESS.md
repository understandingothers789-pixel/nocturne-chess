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
