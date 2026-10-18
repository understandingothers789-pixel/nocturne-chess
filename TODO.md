# Active roadmap

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
