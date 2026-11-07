# Performance follow-up after 0.5.7.139

## Scope

Reviewed navigation and Game Line rendering; engine transport, PV validation,
completion and previews; Maia/Leela update paths; board painting; storage,
PGN serialization and autosave; database request pacing and caching.
The largest measured remaining costs were Game Line HTML layout and repeated
position synchronization while formatting engine variations.

## Implemented changes

- Cursor-only navigation reuses the Game Line document. A Qt extra selection
  highlights the current move. Structural edits, scores, notes, annotations,
  database departure markers, risk markers and theme changes still rebuild it.
  Anchor cursors are rebuilt with the document; variations retain navigation.
- Engine PV validation uses the existing python-chess rules board directly,
  retaining legal UCI validation and SAN formatting while avoiding per-ply GUI
  arrays, FEN generation and hashes. Null moves and invalid tails are rejected.
  The root board is copied without its stack for this formatting-only operation.
- Main analysis previews likewise avoid per-ply drawing-state synchronization.
  Terminal-PV checks retain move history for repetition and draw claims.
- UCI output flushing is now demand-driven. No 80 ms timer wakes while idle;
  subsequent pending output is batched, initial ranks emit immediately, and final
  output flushes before bestmove completion. Stop/replacement cancels the timer.

## Measurements

Local offscreen Qt, deterministic standard-chess fixtures:

| Workload | Before | After |
| --- | ---: | ---: |
| 60 navigation/refresh updates through a 100-ply study, with inference/database requests disabled, under cProfile | 1.642 s | 0.508 s |
| Validate and format a new 48-ply PV, 150 repetitions with the full-PV cache cleared each time | 6.069 ms/line | 0.858 ms/line |

These measure specific GUI/controller workloads, not whole-application speed or
external engine nodes per second. No engine search limits or model coverage
changed. Existing piece caching and unchanged-input UI guards from 139 remain.
Storage durability, database rate limits and inference cache bounds were retained.

## Validation

- Existing isolated suite: 359 tests, 7 skipped, no failed processes.
- After the transport-timer change: all 38 external-analysis tests passed again.
- Three additional regression checks cover document reuse and invalidation;
  standard/Chess960 castling, promotion and invalid/null PV moves against the
  previous validation path; and idle/pending output timer behavior.
- Ruff and whitespace checks passed.

No version bump, build or publication is part of this local optimization pass.
