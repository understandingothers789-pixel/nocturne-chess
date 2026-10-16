# Changelog

## Unreleased — Windows distribution constraint

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
