# Active roadmap

0.5.7.8 removes analysis-panel rank badges and rank coloring, with subtle side-to-
move text tints. Board overlays retain the approved appearance.
All 45 local GUI tests and both native full runs passed (158 passed/5 optional
skips per native run), plus frozen launch checks. Desktop trust/DPI remain manual.

0.5.7.7 (download 3) keeps metadata in the backend/export while Game Moves shows
numbers and SAN. Dev → Show raw PGN data enables a separate read-only view;
default off. Three cumulative feature commits and Windows downloads are retained.
All three native builds passed their full tests twice plus packaged launch checks.
Final version: 158 passed, 5 optional skips per native run; user-machine trust/DPI
and real-engine desktop interactions remain manual checks.

0.5.7.6 (download 2) adds reference-style teal/green candidate lines and numbered
circles, colored MultiPV rows and a once-only default marker migration.

0.5.7.5 (download 1) adds reversible live Studio appearance previews and an
Original piece-style option. Native Windows build receipts are in PROGRESS.md
and the corresponding versioned Actions run.

Nocturne 0.5 changes direction to an external-UCI analysis GUI. Custom-engine
milestones from 0.1–0.4 are historical; no further search development is planned.

The active feature checklist and remaining work are maintained in
[docs/ANALYSIS_ROADMAP.md](docs/ANALYSIS_ROADMAP.md). Executed tests/build evidence
and discovered bugs are recorded in [PROGRESS.md](PROGRESS.md).

Highest-priority remaining checks:

- Real Stockfish 19 and official development-build integration on Windows.
- Manual Windows 11 interaction/DPI/suspend and large Syzygy collections.
- Large-tree profiling, richer branch editing and study collections.
- Persistent cache/snapshots, independent secondary engine and split-board comparison.
- WDL graph, figurines/piece sets and fully saved flexible panel layouts.

0.5.1 automated Windows package checks passed. Verify actual Stockfish resource
allocation and manual Windows/DPI behavior; protocol fixture tests do not measure strength.

0.5.2 native Windows build/tests passed. Manual Explorer access to the PGN folder
and real Stockfish allocation remain to verify on a user desktop.

0.5.3 native Windows tests/build and packaged smoke checks passed. Manual real
Stockfish MultiPV, DPI and desktop interaction verification remains open.

0.5.4 native tests, six HTTP tests and packaged GUI checks passed.
Live ChessDB HTTPS data query passed (29 legal moves); Lichess authentication
requirement verified.
Verify live Lichess data using a user-provided session token. Manual Windows
explorer interactions and real Stockfish marker behavior remain to verify.
Individual database game lists/downloads and Chess960 lookup are deferred.

0.5.5 makes candidate arrows/lines and rank markers much subtler. Four real Qt
views inspected; focused analysis tests and native Windows build checks passed.
132 tests passed with 5 optional skips twice; packaged GUI/UCI smoke checks passed.
Manual desktop/DPI review remains open.

0.5.6 plain Backspace branch deletion passed focused tests, the full local suite
and native Windows tests twice (137 passed, 5 optional skips). Packaged GUI/UCI
smoke checks passed; the new Windows download is verified. Manual desktop/DPI/
real Stockfish interaction review remains open.

0.5.7 optional Game Review, per-side/overall accuracy estimates, filtering and
persisted evidence passed full local/native Windows checks. Native: 146 passed,
5 optional skips twice, plus frozen Game Review/UCI smoke checks. Validate review
judgments with actual Stockfish/user games and manual Windows/DPI; official site
score parity is not claimed.


0.5.7.1 restores the 0.5.7 baseline and adds only three-line MultiPV slots and
hover stability. Focused GUI tests: 39 passed; lint and both app smoke checks
passed. Full local discovery passed: 142 passed, 11 skipped. Native Windows validation
passed twice: 148 passed, 5 optional skips each; packaged GUI/UCI/Game Review
checks passed. The 0.5.7.1 Windows download is verified against the tested commit. Confirm the rebuilt
patch opens on the user's Windows configuration; prior 0.5.7 acceptance does
not establish the new executable's trust status. No 0.5.8 pieces/clock UI remain.


0.5.7.2 adds only exact licensed Lichess Cburnett piece artwork to the user-
confirmed working 0.5.7.1 base. All GUI behavior/sizing/clocks/PV code and build
rules stay unchanged. Source hashes and real Qt SVG/promotion icons verified;
lint and both app launch checks passed. Focused GUI: 39 passed. Native Windows: 148 passed and 5 optional skips, twice;
both frozen GUI/UCI checks passed. Archives include GPL/credits and exact SVGs.
The 0.5.7.2 Windows package is verified against the passing source commit. User desktop trust/DPI remains to verify.


0.5.7.3 neutral appearance and Display → Clocks: settings (4), GUI (41), full
local suite (146 passed/11 skipped), final clock checks (2) and both app launch
checks passed. Native Windows passed twice: 152 passed, 5 optional skips per run; packaging
and both frozen GUI/UCI/Game Review checks passed. Source/wheel/license checks
passed and the 0.5.7.3 Windows download is verified against the tested commit. Verify manual
Windows trust/DPI and saved-default migration. Follow up Play sidebar minimum
width/content clipping; analysis PV space and both player clocks are unaffected.
PGN clock comments now display in the board clock strip and beside annotated
moves. They follow the selected variation; the 0.5.7.4 native Windows regression
and packaged smoke checks passed.
