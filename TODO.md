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
