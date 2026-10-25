# Practical traps: proposal only

No trap engine, automatic probes, or extra searches are implemented in 0.5.7.71.
Move Map retains its current behavior. Its card is now third, after Blunder Meter.

## Proposed trigger and UI

```text
on stable position/rating with usable Maia + Stockfish results:
    if Maia's highest-probability move == Stockfish's best move:
        show Move Map
    elif matching trap results are cached:
        show cached Practical Traps results
    elif no check has been attempted for this position/rating/candidate:
        queue one bounded background check
        keep Move Map visible while it runs
```

Disagreement only triggers a check. Equally strong alternative moves are not
traps. Results must identify a likely opponent mistake and its actual engine
loss/refutation; incomplete evidence remains unknown. If no convincing trap is
found, retain Move Map rather than manufacturing a result.

## Proposed resource budget

- Examine one sound candidate (initially Stockfish's best), not every legal move.
- Ask the already-loaded Maia worker once for opponent replies after that move.
  Use the actual game history and selected rating; reuse cached policies.
- Examine at most three likely replies plus the best defensive reply from the
  existing engine PV as a comparison. Reuse engine analysis where available.
- If necessary, use one low-priority Stockfish helper: one thread, 64 MB hash,
  **one million nodes total**, with a two-second time ceiling. These limits
  apply to the entire probe, not to each reply. Primary analysis is untouched.
- Cancel on navigation or rating change, and reject stale results using job IDs.
  Background Maia replies must not replace the current-position policy in the UI.
- Cache by position/history, rating, candidate, engine/model identity and budget
  version. Do not repeat work for every depth update or hover event.

The caps are starting proposals, not measured performance guarantees. A later
user-controlled deeper check could refine a promising result without making
routine navigation expensive.
