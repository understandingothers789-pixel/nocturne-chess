# Performance review for 0.5.7.118

Reviewed the desktop board, navigation, Stockfish transport/validation and presentation,
Maia request/cache/prefetch paths, rating and blunder visualizations, database clients,
PGN rendering, and SQLite/PGN persistence. The changes target measured repeated work
on the GUI thread. Engine search parameters and model inference are unchanged.

## Changes

- Board copies retain independent native history, cells and key history while copying
  the already synchronized scalar state. They no longer rebuild the piece map, FEN
  and position hash for an unchanged position.
- When only an analysis evaluation/depth changes, edit the text prefix rather than
  replace the whole rich-text document. Move anchors, colors and hover state survive.
  Changed moves, theme, side, notes and font settings still use full rendering.
- Use Qt's direct anchor lookup before scanning the padding around move links. The
  fallback still supports continuous horizontal and vertical hover previews.
- Reuse the two font metrics objects within each notation-width calculation.
- Skip the 100 ms player-detail refresh when clocks are stopped. Navigation and
  settings continue to refresh those details; running clocks and timeouts still tick.

- Prepare opening-database scans in one forward walk through the selected variation,
  rather than replay every prefix from the starting position. Branches and normalized
  query FENs are preserved, and the live board is not mutated.

## Local measurements

Compared release 0.5.7.117 (`ca9bc6b`) with the optimized code in the same Linux Qt
workspace, using separate runs and the offscreen Qt backend. Each result is the median
of five batches. No real Stockfish process, GPU or Maia model was used. The synthetic
Stockfish workload uses three distinct, legal 12-ply variations and changing scores.
Opening-scan preparation uses a deterministic 60-ply game with HTTP dispatch disabled.

| Operation | Before (ms/call) | After (ms/call) | Ratio |
| --- | ---: | ---: | ---: |
| Board copy (8 plies of history) | 0.08418 | 0.01618 | 5.2× |
| Stockfish score update (3 PV rows) | 1.70986 | 0.89301 | 1.9× |
| Direct move-link hit test | 0.04860 | 0.00232 | 20.9× |
| Stopped-clock timer callback | 0.01555 | 0.00005 | 311.0× |
| Opening scan preparation (60 plies) | 199.54964 | 16.80513 | 11.9× |

The score-update measurement covers the synchronous UI update handler, not complete
screen presentation. Hit-test results cover points on a move link, not the padding
fallback. The stopped-clock callback's absolute saving is small, but removes ten
unnecessary refreshes per second in analysis/paused mode. These figures do not imply
faster Stockfish search or a fixed improvement on every Windows machine.

Reproduce with `QT_QPA_PLATFORM=offscreen PYTHONPATH=src python scripts/benchmark_gui_updates.py`.
Run the same script against each checkout with the same Python/Qt environment.

## Validation and limits

Local regression checks: 143 passed across GUI, independent rules oracle, rules,
candidate history, rendering and performance paths. Ruff passed. New checks cover
board-copy independence and history, plus retained score/depth updates preserving
anchors, hover, text, colors and font size. Opening-coverage tests verify selected-branch
queries match the original replay method without replaying each prefix.

No new persistent cache was added. Existing bounded policy/result caches, foreground
priority, stale-request rejection and deferred persistence remain in place. Database
I/O is asynchronous; Maia inference remains in its worker. Storage and engine work
were inspected without changing their behavior speculatively.
