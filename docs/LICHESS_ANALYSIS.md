# Compact analysis workspace — 0.5.7.48

The immediate scope follows Part 1 of the supplied development request. It
extends the existing Qt/UCI application and existing `Game.nodes` tree.

## Behavior and controls

- **F11** plays both sides from the selected position, using **10,000,000 nodes
  per move** by default. **F12** evaluates the selected position and subsequent
  positions on the chosen line, using **200,000,000 nodes per position**. Both
  keys pause/resume their own mode. Normal analysis defaults to **1,000,000,000
  nodes** and stays at the same position when it finishes.
- Escape, board input, position navigation and board/history/PV wheel navigation
  stop automation. PV wheel input then explores that variation. Shift+wheel
  scrolls notation; scrolling unrelated settings controls does not stop a job.
  Canceled search generations cannot advance the game or update another position.
- F12 now selects the position it searches and sends live `info` messages through
  the same renderer as normal analysis. Results retain each PV's actual depth,
  bounds and engine metadata. Partial iterations remain valid saved analysis;
  grading a reviewed move still uses exact evidence.
- Each of at most five candidates has one fixed-height row: rank, evaluation,
  then numbered SAN moves. Long rows clip horizontally. Wheel exploration brings
  the inspected move into view; **…** opens the complete variation in a popup.
  Its snapshot remains stable until the inspector closes. Hover previews are
  temporary, and clicking/inserting explicitly commits moves to the game tree.
- **ⓘ** in the header reveals candidate WDL, API win rate, frequency, sample size
  and source. The same metadata is available on evaluation tooltips. Depth,
  nodes, NPS and time remain in engine telemetry; selective depth is optional.
- **Moves** shows paired mainline moves and inline, nested collapsible branches.
  It shares the game model, cursor and saved evaluations with the board and bottom
  PGN. Comments appear in tooltips; NAG punctuation and scores appear by moves.
  **Openings** and **Game info** use the same side area. No empty future panel
  is reserved. The existing custom docking workspace remains supported.
- The right evaluation bar follows the board orientation. Mate scores reach the
  correct endpoint; unknown evaluations use a neutral state. Transitions respect
  the existing animation preference.

## Settings and APIs

The **engine gear** exposes all three independent budgets, normal search mode,
time/depth, MultiPV 1–5, engine selection and advertised Threads/Hash controls.
Unsupported resources are disabled. The additional-options button opens the
existing UCI profile editor. **Restore defaults** restores the requested budgets
and engine resource defaults. Settings persist in the existing local store.
Node-only and Unlimited modes ignore disabled time/depth fields; time-only and
depth-only modes do not add a hidden node limit. Combined mode explicitly stops
at the first configured limit.

**Database → Database settings and filters**, or the explorer gear, offers
Masters, Lichess, Player and ChessDB. Lichess supports multiple API rating bands
and speeds. Player supports username, color, speeds and month boundaries;
Masters uses year boundaries. Unsupported filters are disabled. Apply/Done
validates the range and changes the live query and its cache key together.
The explorer displays the active filters. Existing simple menu presets remain.

Player results arrive as NDJSON during asynchronous indexing. Intermediate
counts are marked provisional and are neither cached as final statistics nor
used as zero-game departure evidence. Only the completed response is cached.
Timeouts, access failures and rate limits remain distinct from empty results.
Coverage records and gold move markers are separated by the actual filters.

The public Lichess endpoints returned **HTTP 401 without a token** during the
2026-10-20 live check for all three Lichess categories. The UI permits anonymous
requests, reports that response honestly, and retains session-only token support.
Authenticated live filtering could not be tested without a supplied token.
ChessDB remains the startup default until a session token is supplied.

## Verification and implementation map

- Stockfish 19 was downloaded from its official release and run outside the
  bundle. The check verified `go nodes 1000000000`, `go nodes 200000000` and
  `go nodes 10000000`, live F12 rows, F11/F12 pause/resume, five saved PVs at two
  continuation positions, and isolated time/depth/Unlimited commands. A smaller
  100,000-node search finished at Stockfish's reported 102,120 nodes; engine
  overshoot is retained.
- Protocol-fixture tests cover stale results, interruption, partial MultiPV
  depths, bounds and durable analysis restoration. Fixtures are not chess engines.
- Qt regressions cover single-row geometry, full-PV inspectors, hover/wheel
  previews, synchronized nested PGN navigation, resource/settings persistence,
  database filters, NDJSON completion and docking/reset.
- HTTP fixture tests run over real loopback sockets, including partial/final
  responses, cancellation, size limits, rate limits and failures. These counts
  are labelled fixtures, not live database measurements.

Affected implementation files:

| Area | Files |
| --- | --- |
| Search modes and orchestration | `gui/window.py`, `gui/engine.py`, `analysis_jobs.py`, `settings.py` |
| Compact rows and previews | `gui/candidates.py`, `gui/moves.py`, `gui/board.py` |
| Shared side move tree | `gui/move_tree.py` |
| Engine gear | `gui/analysis_settings.py`, existing UCI profile/resource modules |
| Database filters and streams | `explorer.py`, `gui/database_settings.py`, `gui/explorer_panel.py`, `gui/explorer_client.py`, `gui/opening_coverage.py` |
| Evaluation bar | `gui/widgets.py` |

The Windows build receipt records the native CI result and artifact checksum.

## Deferred roadmap

Maia inference, Move Map, Blender Meter, Moves by Rating, rating control and the
four-region insights layout were **not implemented**. Future Maia probabilities
must match Stockfish moves by UCI identifier from the same position, retain the
full legal-move distribution, and use real supported model ratings. Stockfish
retains rods/circular endpoints; future Maia uses distinct translucent arrows.
There is no Maia-only extras panel or development-backlog panel in the UI.
