# Changelog

## 0.5.7.5 — Download 1: live Studio appearance preview

- Preview board palette, Cburnett/Original pieces, light/dark appearance,
  coordinates and overlays before saving. Cancel restores the saved appearance.
- Show a sample board and keep Save/Cancel visible with a scrolling settings form.
- Keep live previews separate from saved preferences, position, clocks and engine
  jobs; include original MIT SVGs and matching promotion icons in distributions.

## 0.5.7.4 — Show imported PGN clock annotations

- Read standard `[%clk …]` comments for each move and variation, display the
  latest recorded White/Black times at the selected position, and show clean
  per-move clock values when Display → Clocks is enabled.
- Hide raw clock/timestamp directives in move text while preserving them in PGN
  import/export and saved games. Untagged positions display an em dash in a game
  that contains clock annotations; ordinary untimed games continue to show ∞.
- Add regression coverage for clock parsing/formatting, variation navigation,
  save/restore, PGN preservation and the Display toggle.

## 0.5.7.3 — Neutral appearance and optional chess clocks

- Replace the green interface with charcoal/neutral light palettes, classic
  brown-and-cream squares and a Grey option; migrate the old default once.
- Apply consistent colors to menus, move text, graphs, highlights, database bars,
  review labels and the original application icon; preserve Cburnett artwork.
- Add saved Display → Clocks, with an analysis clock strip and Play clock labels.
  Hiding clocks leaves running timers, positions and time controls intact.
- Verify clock preference reload, elapsed time/save integrity and settings
  migration. Keep three-line PV slots, hover snapshots and engine behavior.

## 0.5.7.2 — Cburnett pieces on the working 0.5.7.1 base

- Replace the twelve original SVGs with the exact Lichess Cburnett set by Colin
  M. L. Burnett, with GPL-2.0-or-later license text, credits and pinned source.
- Keep all board rendering, sizing, drag/promotion logic, clocks, fixed three-line
  MultiPV slots and dependencies unchanged. No runtime feature code is modified.
- Include the artwork's notices through existing native/wheel/source collection.

## 0.5.7.1 — 0.5.7 baseline with stable three-line MultiPV

- Restore the original 0.5.7 pieces, clock display, dependencies and packaging.
- Reserve three text lines and a fixed header per MultiPV rank; scroll long PVs
  within their slot without changing lower rows' positions.
- Preserve hovered moves during engine updates and use their displayed snapshot
  for clicks; clear queued updates after position changes.
- Exclude the 0.5.8 Cburnett artwork, extra clock strip and Display clock toggle.
- Retain Game Review and all other 0.5.7 behavior. No signing or Windows security
  policy change is included; trust acceptance still needs desktop verification.

## 0.5.8 — Familiar pieces, optional clocks and steady MultiPV slots

- Use the exact Lichess Cburnett SVG set, with upstream attribution, GPLv2+
  license and preferred modifiable sources included in distributions.
- Add persistent Display → Clocks; show a compact analysis strip and toggle
  existing Play clocks without changing the time control or pausing a game.
- Reserve three move-text lines plus a fixed metrics header for every requested
  PV rank before results arrive. Long PVs scroll within their fixed viewport.
- Keep hovered PV data stable, apply the newest queued update after leaving,
  and prevent other ranks' updates from ending the current preview.
- Execute clicks against the displayed snapshot; discard queued data on position
  changes and synchronize candidate markers when pending data is applied.

## 0.5.7 — Optional Game Review and accuracy estimates

- Add Analysis → Game Review and a button above PVs, with White/Black/overall
  accuracy estimates, six move-quality counts, review progress and error filtering.
- Click results for board navigation and engine evidence; return to the previous
  position without changing the selected branch or restarting halted analysis.
- Grade exact same-root best/played comparisons using published score curves and
  explicit loss bands. Exclude missing, stale, bound, legacy or wrong-move evidence.
- Keep partial coverage explicit; persist results and export labelled PGN comments.
  No official Chess.com/Lichess score, brilliant/book label or strength claim.
- Preserve pause/resume/cancel; harden legacy review export and freeze review limits.
- Extend frozen executable smoke checks to run an actual external-UCI review.

## 0.5.6 — Backspace deletes the current analysis line

- Add Tree → Delete current line with plain Backspace. Delete the selected move
  and descendants, display a surviving sibling, or return to its parent.
- Preserve sibling order, annotations, saved analysis and review records while
  removing deleted nodes from saved games/PGNs. Reset a changed main-line result.
- Stop old analysis/review before editing; resume live analysis on the surviving
  position and keep halted analysis halted. Text fields retain normal Backspace.
- Disable deletion at the root and during play; ignore shortcut auto-repeat.

## 0.5.5 — Subtle analysis markers

- Reduce candidate arrow/line thickness and opacity with a muted palette and much
  smaller arrowheads. Stroke widths stay thin as the board grows.
- Replace bright rank badges with small translucent circles and quiet numerals.
- Apply the same subtle arrow geometry to saved continuations. MultiPV destination
  clicks, rank priority, promotion choices and manual annotations retain their behavior.

## 0.5.4 — Ranked destination moves and Lichess opening explorer

- Draw each displayed MultiPV candidate as an arrow or Nibbler-style line. Choose
  the highest-ranked move on a shared destination; all lower ranks work by default.
- Clear old markers on MultiPV changes, preserve selected-piece priority, execute
  exact recommended promotions and retain manual promotion choices.
- Add an opt-in Masters / Lichess rated-player opening explorer beneath analysis,
  with speed/rating groups, game counts, White/draw/Black bars and supplied names.
- Hover database moves without navigating; click to add a legal variation while
  preserving prior lines. Standard-chess positions only; no game downloads yet.
- Add ChessDB cloud analysis as a third source, with service scores/notes, legal
  moves, explicit unknown states and learning disabled; no fabricated game counts.
- Support the current Lichess authentication requirement with masked, session-only
  token entry, official-host scoping and explicit 401 guidance. Tokens never save.
- Use cancellable Qt HTTPS, debouncing/pacing, bounded responses, a 256-position
  persistent cache, explicit offline/empty/error states and 429 cooldown.
- Add deterministic loopback HTTP tests and a separate optional live API check;
  no engine strength, speed or database-coverage claims.

## 0.5.3 — Spacious analysis and menu-based engine controls

- Threads, Hash, MultiPV, engine selection and continuous/bounded limits live in
  the top Engine menu; remove settings widgets from the analysis pane.
- MultiPV presets/custom values work in both continuous and bounded modes, honor
  advertised engine limits and clear a move focus when selecting a new count.
  Continuous searches ignore saved bounded node limits; halted analysis stays halted.
- Allocate more width/height to analysis, place the graph beneath the PV list and
  keep game moves below. Hide the tab bar while analyzing; retain PGN editing.
- Hide the Play instruction caption in Analysis and let it wrap in Play, avoiding
  an oversized board minimum width with native Windows font metrics.
- Flowing PV rows show complete wrapped move text without per-row button bars or
  inner scrolling; insert/pin/copy/focus remain available in a context menu.
- Preserve hover previews during unchanged-PV depth updates and prevent duplicate
  primary-line click handlers after search context changes.
- Migrate old settings using their effective PV count; resource presets no longer
  imply that they change MultiPV. No engine-strength or speed claim.

## 0.5.2 — Saved PGNs and resource refinements

- Write complete PGN copies automatically beside the SQLite library, with stable
  per-study filenames, atomic replacement and unchanged-file detection.
- Reopen previous studies through Saved PGNs / game library; open the archive
  folder directly from File or the library. Export older saved games in small
  background batches without changing the resume target or deleting corrupt data.
- Show Hash in GB from 1,024 MB across menus, quick controls and detailed stats;
  keep exact MB for engine commands/custom input. Add a 14-thread menu preset.
- Preserve the SQLite game and previous PGN if writing a new copy fails; repair
  invalid UTF-8 copies on the next save. Include event names in library entries.

## 0.5.1 — Accessible engine resources

- Direct Engine → Threads / Hash submenus and visible quick controls, with presets,
  custom integer values, engine-default choices and per-profile persistence.
- Engine-reported limits and conservative memory admission, crediting the running
  engine's acknowledged hash allocation when it is replaced.
- Distinguish saved settings from engine-acknowledged settings; changing resources
  preserves a stopped analysis state and clears stale candidate output.
- Fix a UCI ready-barrier race: a request replaced during option preparation must
  apply its latest options before the new position/search commands are sent.
- Freeze the originating profile/settings in saved analysis, including actual
  acknowledged UCI values; switching profiles cannot relabel the previous score.
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
