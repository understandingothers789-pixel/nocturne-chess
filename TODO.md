# Milestone record and roadmap

Completed checks are supported by executed results in `PROGRESS.md`.

## M1 — Foundation: accepted, with disclosed dead-position limitation

- [x] Separate rules, notation, engine, GUI, persistence and test modules.
- [x] Complete standard legal move generation, FEN and reversible state.
- [x] SAN/UCI notation, main-line PGN, automatic/claimable draw separation.
- [x] Six reference perft positions, deep start/Kiwipete counts, hash integrity.
- [x] Independently compared seeded games using development-only python-chess.
- [x] Native two-player board; click, drag and explicit underpromotion verified.
- [ ] General FIDE dead-position proof beyond conservative material detection.

## M2 — Working engine: accepted

- [x] Independent tapered evaluation and negamax alpha-beta.
- [x] Iterative deepening, check-aware quiescence, PV and mate distance.
- [x] Move ordering, history/killer heuristics, contextual Zobrist TT.
- [x] Real time/node budgets, cancellation and legal fallback.
- [x] Human vs AI; both human colors; meaningful bounded difficulty profiles.
- [x] Native event-loop responsiveness and stale-result synchronization tests.

## M3 — Polished application: accepted on Linux/Qt

- [x] Original vector pieces/icon, dark/light mode, four board palettes.
- [x] Legal/capture/check/last-move highlights, annotations, flip, animation.
- [x] Primary game modes, increment clocks, pause, resign, draws and takebacks.
- [x] SAN history, save/resume, multiple games, preferences, FEN/PGN interchange.
- [x] Nibbler-style native menus, PGN editor and direct clipboard interchange; no tooltips.
- [x] Isolated analysis copies preserve the played game's saved record.
- [x] Configurable hash budget; explicit one-thread limitation.
- [x] Compact engine-panel scrolling and light-theme contrast review.
- [ ] Windows 11 manual interaction, DPI and suspend/resume validation.
- [ ] Optional sound assets and alternate piece sets.

## M4 — Engine development: baseline and measurement tools complete

- [x] Standard console UCI support, including readiness/search/stop/options.
- [x] Explicit local UCI executable integration; no external dependency for AI.
- [x] Fixed-FEN benchmark, ablation variants, JSON records and match harness.
- [x] Actual default/PVS/ordering/TT/killer measurements recorded.
- [x] PVS tested as an opt-in experiment; stays off after mixed timing results.
- [ ] Large, diverse, paired opening matches with objective strength statistics.
- [ ] Test a user-installed Stockfish executable specifically (protocol adapter tested).
- [ ] Measured SEE, aspiration windows, null move with safeguards, LMR,
  selective extensions, futility and incremental evaluation experiments.
- [ ] Profile-driven native acceleration; optional NNUE research.

## M5 — Analysis: usable baseline, advanced tools deferred

- [x] Legal FEN/PGN setup/import, history navigation and alternative main lines.
- [x] Evaluation bar, best-move arrow, single PV, adjustable analysis limits.
- [x] Actual sampled evaluation graph and developer performance dashboard.
- [x] Saved engine-game results and aggregate white/black/draw counts.
- [ ] Graphical unrestricted position-placement editor.
- [ ] Full variation trees and preserving PGN annotations/variations.
- [ ] Multi-PV with independently scored lines.
- [ ] Defensible depth-aware move classification and automated blunder review.
- [ ] Reliable licensed opening database/identification.

## M6 — Release: configuration and Linux bundle verified; Windows gate open

- [x] Pinned dependencies, README, changelog, visible progress and license record.
- [x] Multi-resolution icon generator and PyInstaller GUI/UCI specification.
- [x] Developer-only Python Windows builder and CI validation configuration.
- [x] Windows release ZIP gate: trusted native signatures, timestamps and smoke checks.
- [x] Exclude batch/PowerShell launchers and security-bypass instructions from distribution.
- [x] Linux GUI/UCI bundles built and exercised with packaged smoke checks.
- [x] Native Windows CI builds, packaged smoke checks and downloadable unsigned test artifact.
- [ ] Inspect downloaded artifacts and interact manually on a clean Windows 11 system.
- [ ] Obtain legitimate trusted signing, sign binaries and verify Windows/SmartScreen behavior.
- [ ] Optional installer; full platform/license distribution audit.

## Known practical limits

Search has a 20-ply quiescence safety cap and 96-ply total safety cap. The TT
includes reversible-history context so history-dependent draw scores are not
reused across different game paths. Python hash memory is approximate. Worker
startup consumes game-clock time in addition to the calculation budget.

PGN import accepts one game and retains only the main line/tags. FEN cannot
reconstruct repetition history. Analysis graphs contain sampled positions;
unsearched moves have no invented score or classification. There is no Elo
claim, no secret Stockfish use, and no downloaded/bundled external engine.
