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
