# Architecture and acceptance plan

Nocturne is a Python 3.12 / PySide6 desktop application. All normal operation is
offline. The custom rules and search packages do not import Qt, python-chess, or
an external engine. python-chess is a development-only differential test oracle.

## Boundaries

* `core/board.py`: 0x88 representation, reversible moves, incremental Zobrist
  keys, legal moves, draw rules and FEN. A1 = 0, H8 = 119; White = +1.
* `core/notation.py`: SAN and PGN; validation occurs at the rules boundary.
* `core/game.py`: selected-line history, clocks, outcomes, undo/redo and draw claims.
* `core/variation.py`: ordered validated move tree; child zero is the main line.
  PGN and schema-2 saves preserve all branches, clocks and evaluation samples.
* `engine/`: tapered evaluation, bounded search, UCI transport and benchmarks.
* `storage.py`: versioned SQLite records and preferences, no GUI dependency.
* `gui/`: Qt painting, input, dialogs and process-backed engine coordination.

Only the GUI thread mutates the displayed game. Engine workers receive immutable
position snapshots (FEN plus replayable history); results carry a generation ID.
Canceled or outdated results cannot be committed to a changed game. Engines run
in separate processes so the Python GIL cannot freeze the interface.

## Ordered milestones

1. **Foundation**: exact start-position and established tricky-position perft;
   special moves and discovered-check regressions; make/unmake and hash
   integrity; notation round trips; playable two-human Qt window.
2. **Working engine**: legal deterministic negamax, alpha-beta, iterative
   deepening, check-aware quiescence, tapered evaluation, measured timing and
   cancellation; human vs AI.
3. **Application**: polished native board, all primary play modes, clocks,
   autosave/resume, library, settings and robust background search.
4. **Engine development**: UCI, optional local external UCI engine, reproducible
   benchmark. Advanced pruning is gated on measured improvements, not feature
   count.
5. **Analysis**: position import, history exploration, graph and engine telemetry;
   persistent variation trees are implemented; Multi-PV and automated full-game
   review remain deferred.
6. **Release**: comprehensive integrated checks, Windows build configuration,
   licenses and honest known limitations. A Linux build is not a Windows build.

## Rules and safety contracts

`Board.push()` is an internal fast operation for generated pseudo-legal moves.
Public moves go through `parse_uci`, SAN parsing, or `Game.play`, all of which
validate legality. Legal generation filters king exposure after make/unmake;
castling separately checks origin, transit and destination attacks. En passant
is included in repetition keys only if a legal en passant capture exists.

Automatic endings and claimable draws are distinct. Checkmate has precedence
over the 75-move rule. Claims can include an intended legal move. Insufficient
material is detected conservatively: bare kings, king plus a single minor,
and positions with only bishops all on one color. General dead-position proof
(including blocked-pawn fortresses) is an explicitly deferred rules limitation.

Search scores are centipawns from the side to move internally; UI and UCI
conversions are explicit. Mate scores encode distance. Search draws depend on
history, so transposition scores must not bypass repetition adjudication.

## Syzygy boundary

`engine/tablebase.py` maps the custom board to bitboards and probes only at the
root via the MIT Fathom CPython wrapper (`native/`). Legal move validation stays
in the custom core. Native initialization/probing is serialized and releases
the GIL. GUI probes are isolated in killable worker processes. Local files are
header/size checked; missing tables produce diagnostics and normal search.
Exact DTZ root selection is disabled for repetition-sensitive/claimable positions.
No table-derived results automatically terminate games. Source and binary
distributions retain Fathom's license; table files are user supplied.
