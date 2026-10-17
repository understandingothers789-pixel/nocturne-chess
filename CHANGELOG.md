# Changelog

## 0.5.1 — Accessible engine resources

- Direct Engine → Threads / Hash submenus and visible quick controls, with presets,
  custom integer values, engine-default choices and per-profile persistence.
- Engine-reported limits and conservative memory admission, crediting the running
  engine's acknowledged hash allocation when it is replaced.
- Distinguish saved settings from engine-acknowledged settings; changing resources
  preserves a stopped analysis state and clears stale candidate output.
- Fix a UCI ready-barrier race: a request replaced during option preparation must
  apply its latest options before the new position/search commands are sent.
- Regression coverage for process reuse, profile independence, memory limits,
  unsupported options and settings changed while waiting for readyok.

## 0.5.0 — External-engine analysis studio

- Product direction changes to a user-supplied Stockfish/UCI GUI. Custom search,
  evaluation, UCI executable and native table reader are excluded from the desktop.
- Persistent asynchronous UCI sessions, advertised option profiles, stop/ready
  barriers, deadlines, bounded diagnostics and restart handling.
- Actual MultiPV scores/bounds/WDL, candidate arrows and guarded Smart Move,
  PV hover/click/insert/pin/copy/targeted-search interactions.
- Runtime python-chess rules/PGN with Chess960, comments, NAGs and evaluation
  annotations; multi-game study tabs and manual position setup.
- Full-line review with targeted played-move searches, pause/resume/cancel,
  node-associated exact scores and reliable evaluation export.
- Classic/analysis-left split layouts, graph zoom/pan/hover, command palette,
  shortcut editing/import/export and PNG board export.
- Combined application distribution is GPL-3.0-or-later; original code/assets
  retain MIT. Corresponding rules-library source accompanies release source ZIP.
- Real Stockfish/Windows interaction and advanced comparison/cache/snapshots remain
  explicit follow-up work. No playing-strength or performance improvement claim.

## 0.4.0 — Persistent variations and offline Syzygy

- Alternate moves preserve the main continuation as ordered branches. Nested
  PGN variations, autosaves, branch navigation and main-line promotion round-trip.
- Syzygy folder selection, WDL/DTZ diagnostics and legal root move selection via
  MIT Fathom; up to seven-piece reader support, no table downloads in the app.
- External UCI SyzygyPath forwarding, custom UCI option, TB-hit telemetry.
- Native extension packaging and real tablebase fixture/oracle regression tests.
- Comments/NAGs, full five/seven-piece validation and Multi-PV remain pending.

## 0.3.2 — 2026-10-16

* Dedicated Analysis layout: engine panel left, board right, resizable game
  moves strip across the bottom; Play retains its layout.
* Hover history or suggested PV moves for display-only board previews. Leaving
  the move restores the actual position; clicks on history still navigate.
* Preview rendering preserves game state, clocks, engine jobs, selection and
  annotations. Position/PV updates and focus or workspace changes clear stale
  previews. No hover tooltips are introduced.
* Regression checks cover mouse hover/leave, layout switching, engine/game
  invariants, stale PV replacement, input guards and all special moves.

## 0.3.1 — 2026-10-16

* Added a native File / Tree / Analysis / Display / Engine / Play menu bar,
  organized around supported Nibbler-style commands.
* Added an editable PGN tab, direct clipboard FEN/PGN load and PGN copy, and
  file-based PGN opening. Plain SAN move text is accepted without a file.
* Preserve the board and draft on invalid PGN; keep text editing shortcuts
  independent of board navigation and play shortcuts.
* Removed hover tooltips and retained accessible names for navigation buttons.
* With explicit user authorization, successful Windows CI builds now retain
  unsigned executable downloads for 30 days. Windows may show a warning.

### Earlier Windows distribution changes

* Replaced the PowerShell builder with a developer-only Python tool; removed
  the execution-policy bypass instruction.
* Excluded Windows script launchers from source/release archives and removed
  unsigned binary uploads from CI.
* Require successful trusted Authenticode/timestamp verification and packaged
  smoke checks before creating Windows release ZIPs. Actual signing and Windows
  reputation validation remain pending; no warning-free claim is made.

## 0.3.0 — 2026-10-16

Initial native application and independently implemented engine.

* Reversible 0x88 rules, incremental Zobrist keys, legal special moves, draw
  claims/automatic endings, FEN, SAN, main-line PGN and exact reference perft.
* Tapered handcrafted evaluation, iterative alpha-beta/quiescence, ordered
  moves, killer/history heuristics, contextual transposition table, PV, mate
  distance, deadlines/cancellation and six bounded search profiles.
* Native vector board with click/drag, underpromotion, highlights, annotations,
  animations, palette/appearance settings and a resizable studio layout.
* Human/AI, local two-player, engine-watch and independent analysis games;
  clocks, history, takebacks, transactional autosave/resume and saved library.
* Spawned engine workers with generation/position checks; UCI CLI and optional
  explicitly selected external executables, with illegal-move rejection.
* Single-PV analysis, evaluation samples/graph, benchmark dashboard, JSON
  experiments and saved engine-game statistics.
* Windows PyInstaller configuration, icon, portable build script, CI recipe,
  licensing notices, measured benchmarks and regression suite.

Validated in Linux with Qt 6.8.3. Windows execution remains to be performed.
General dead-position proof and the advanced analysis roadmap remain open in
`TODO.md`. No verified Elo rating is assigned.
