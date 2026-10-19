# Changelog

## 0.5.7.35 — Durable analysis and optional node snapshots

- Reopening a saved study restores its analysis paused, without automatically
  starting a new search and replacing the results. An interrupted F12 job saves
  its frozen line, unfinished position, engine profile/options and requested
  budget. Press F12 after reopening to resume without repeating completed positions;
  the unfinished position starts a fresh engine search at its original budget.
- Dev → Save analysis snapshots at node milestones is disabled by default.
  When enabled, normal analysis and F12 save 1M, 2M, 5M, 10M, 20M, 50M, 100M,
  200M, 500M, 1B, 2B, 5B, 10B, 20B, 50B, etc., following 1/2/5 indefinitely.
  Capture runs before display throttling. Snapshots retain each PV's reported
  depth/bound, actual nodes, engine options and timestamp. Targets use the first
  engine report reaching them; overshoot is shown, never disguised as exact work.
- Dev → Compare saved analysis snapshots… shows two selectable checkpoints
  side by side, with evaluation, depth, full PVs, observed nodes and a move/score
  comparison. Refresh adds checkpoints saved while the window is open.
- Checkpoints are separate SQLite library records, scoped to the PGN and move
  path (including repetition history). They survive close/reopen, navigation,
  variation node renumbering and disabling capture. A fresh Analyze clears the
  current position's saved results/checkpoints; starting a new F12 job clears its
  chosen line. Pausing/resuming F12 retains them. Selecting another PGN shows
  that study's own saved data. Deleting a library game deletes its checkpoints.

## 0.5.7.34 — Partial analysis, deeper review and position tools

- F12 retains the latest result for every PV, including unfinished iterations
  with different depths and bound scores. Each candidate keeps its own depth;
  inequalities remain labelled, and bounds are not exported as exact PGN evals.
  Stockfish's normal node overshoot is unchanged.
- Game review confirms suspected Mistakes and Blunders before assigning a
  final label. Both best and played moves are searched again using node-only
  limits: at least 10 million nodes, or four times the first pass's larger
  reported node count. Analysis → Confirm mistakes with deeper analysis toggles
  this default-on feature. The review detail retains the original evidence and
  shows the confirmation budget. F12's requested per-position budget is unchanged.
- Tree → Bookmark this position… (Ctrl+B) saves a name and note in the game
  library. Tree → Position bookmarks jumps to saved positions; Ctrl+B edits
  or deletes the current bookmark. Bookmarks follow node renumbering when a
  different variation is deleted. They are library data, separate from PGN comments.
- Database → Find where this line leaves the database scans the selected PGN
  line in order using the selected Masters/player filters and cached or live
  counts. The Game Moves header links to the first zero-game position and shows
  the preceding position's game count. Requests are paced and cancellable;
  access, connection and rate-limit failures show incomplete coverage, never
  a fabricated zero. ChessDB has no game counts and is excluded from this scan.

## 0.5.7.33 — Recent-change review and regression fixes

- Normal node presets now switch to a true node-only search. Unlimited really
  runs until halted; custom time/depth limits remain available separately.
- Saved MultiPV results from F12 and ordinary analysis appear when revisiting
  positions, without starting a new search. Unknown positions clear stale scores.
- Node-capped Stockfish searches may finish with a bound score. Auto-evaluation
  and review retain the last exact completed score and its actual depth instead
  of stalling; bound-only searches still pause for insufficient evidence.
- F11 pause/resume is independent of general game pause state. F11/F12 ignore
  held-key repeat, and self-play clears a previous targeted-move restriction.
- Left-arrow rewinds now resume the main line, matching wheel navigation.
- Graph zoom, panning, clicks and drawing use the same visible timeline. Future
  samples no longer flatten the current range or attract invisible clicks.
- Switching equal-length games resets the graph viewport. Corrupt preference
  migration metadata recovers without raising an exception.
- Windows artifact names follow the application version automatically. CI runs
  the full suite once, then packaging and smoke checks without repeating it.

## 0.5.7.32 — Toggle auto-evaluation and self-play

- F12 pauses and resumes an active auto-evaluation run, preserving its current
  position in the line.
- F11 pauses and resumes self-play from its current position.
- F11 and F12 are listed in the Engine menu beside the controls they operate.

## 0.5.7.31 — Synced graph and separate engine limits

- Evaluation graph follows the selected PGN position and grows its timeline as
  the user navigates the game.
- Engine menu exposes separate normal, auto-evaluation and self-play node caps.
- Normal analysis defaults to 1 billion nodes; auto-evaluation to 200 million;
  self-play to 10 million nodes per move.

## 0.5.7.30 — Recorded move destinations and full engine details

Allow Smart Move destination clicks to play the game's recorded next move even
when that move is outside MultiPV. Show the complete engine name reported by
UCI. Add F11 self-play from the current position, defaulting to 10 million
nodes per move; set F12 line evaluation to 200 million nodes per position and
normal analysis to a 1 billion node limit. When ordinary navigation backs out
of a variation onto the main line, continue forward along the main line while
preserving the selected variation during game review.

## 0.5.7.28 — Default analysis lines to compact and move controls to Engine

Turn off the global expand-all option for the default and migrate older saved
preferences to that default once. Move both global expansion and cursor-preview
controls from Dev to Engine. The expansion option remains available when
intentionally needed; per-candidate arrows continue to expand one line.

## 0.5.7.27 — Enforce compact MultiPV row limits

Remove the persisted global “Expand all analysis lines” override, which could
set all candidate rows to unlimited height and bypass MultiPV row limits. Up to
four candidates now remain in three-row slots and five or more remain in
two-row slots. Per-candidate arrows still expand one variation on demand.

## 0.5.7.26 — Evaluation-first telemetry and stable compact PV rows

Show the current evaluation to the left of depth in the top engine telemetry,
matching the evaluation-then-depth order used by each MultiPV candidate. Keep
compact candidate slots at a fixed three move rows for one to four MultiPV
lines while longer engine variations update; use each candidate's arrow to
view the remaining moves.

## 0.5.7.25 — Cleaner depth labels and clearer engine telemetry

Hide selective depth by default in candidate headers and top telemetry, with an
optional Display setting to show it in both places. Emphasize depth, node count
and nodes per second in the top telemetry with slightly larger, blue-accented
values.

## 0.5.7.24 — Preserve wheel preview during pointer jitter

Candidate wheel browsing now remains on its selected ply when tiny mouse
movement stays over the same move. Moving onto a different move resumes normal
hover preview behavior.

## 0.5.7.23 — MultiPV-aware candidate row height

Candidate lines now reserve three move rows when one to four MultiPV lines are
selected, and two rows when five or more are selected. Per-line arrows still
expand a candidate to its full engine variation.

## 0.5.7.22 — Stable MultiPV wheel previews during engine updates

Wheel-browsing a candidate now keeps its current move and displayed PV snapshot
while Stockfish reports updates for that same root move. New continuations wait
until the preview ends, so the selected ply does not jump back to the start. If
the candidate's root move changes at its MultiPV rank, the preview resets and
shows the new line.

## 0.5.7.21 — Two-row MultiPV with per-line expansion

Candidate lines now reserve two move rows by default. A small arrow at the end
of each candidate's second row expands only that line to show its full current
engine PV; the arrow collapses it back to two rows. Other candidates stay
compact, and expansion resets when that row's suggested first move changes.
The existing developer option can still expand every candidate at once.

Lichess Masters and player database status now distinguishes a query that is
still loading, a completed position with no matching game sample, and a real
service or connection error. Empty results say “No games found.”

## 0.5.7.20 — Clearer MultiPV evaluation and depth hierarchy

MultiPV rows now lead with a prominent evaluation and its search depth placed
closely beside it. The three reserved move lines stay in a fixed middle section;
W/D/L, API win rate, frequency and database details move to a consistent footer.
This makes the score and depth easier to scan without shifting candidate lines
as analysis updates.

## 0.5.7.19 — High-resolution Cburnett and registered SVG piece sets

- Draw Cburnett directly from its licensed SVG artwork at device resolution, using its own viewBox spacing without an extra inset.
- Keep one registry for filename conventions and asset locations; every registered SVG style shares the same antialiased Qt vector renderer.
- Verify all 36 pieces across Nibbler, Cburnett and Original at 1×, 2× and 3× device pixel ratios.

## 0.5.7.18 — Crisp Nibbler-style vector rendering

- Render the matching shaded Merida SVGs at native device resolution, retaining the Nibbler look and default preference.
- Use vectors consistently for board, dragging, animation, settings, promotion and cursor previews.
- Preserve all original PNG bytes as licensed archival references; update artwork notices.
- Cover transparent rendering and antialiased edges at 1×, 2× and 3× device pixel ratios.
- Cumulative native Windows validation passed twice: 179 passed/5 optional skips, Ruff twice, PyInstaller and both frozen launch checks.

## 0.5.7.17 — Experimental cursor hover board

- Add an opt-in, remembered Dev setting to preview on a small mouse-transparent board near the pointer.
- Keep the main board fixed and copy its appearance/orientation for history, PV and database previews.
- Clamp placement to the window/screen; dismiss on leave, navigation, deactivation, hide, close or toggle.
- Preserve candidate snapshot freezing, queued updates, click activation and wheel previews.

## 0.5.7.16 — Keep database statistics when hiding the explorer

- Separate explorer visibility from database lookup opt-in; preserve API win, frequency and source metadata while hidden.
- Source selection enables statistics without opening the lower table.
- Retain explicit lookup disable, offline default, cache reuse and stale-result guards.

## 0.5.7.15 — Enforce database pacing and allow cold CI startup

- Use a precise Qt timer and recheck debounce/interval/backoff monotonic deadlines
  before sending database requests; early callbacks rearm without dispatch.
- Add an offline regression for early callbacks and backoff, retaining real HTTP pacing checks.
- Allow the six-move review fixture 20 seconds for permitted cold handshakes,
  searches and UI/disk work, with full grading/restore assertions and diagnostics.
- Real reviews remain per-position and continue to the end without a total time cap.

## 0.5.7.14 — Compact game history and comfortable analysis spacing

- Reduce SAN slot width and inter-move gaps to fit more analysis columns while respecting native font/DPI metrics.
- Retain text sizes, padded click areas and three reserved PV rows with tighter leading.
- Make game history the densest section; reduce its panel padding and navigation height.
- Preserve hover snapshots, queued candidate clicks, colors and wheel behavior.

## 0.5.7.13 — Dotted evaluation guides and compressed graph scale

- Add labelled dotted ±1.00-pawn guides and a subtle equality baseline.
- Preserve detail near zero with a linear segment and logarithmic compression
  beyond one pawn; smoothly fit the range with 12% transformed-scale headroom.
- Keep mate sentinels at the edges, independent of centipawn range fitting.
- Clip zoomed plotting to its bounds and retain accurate click/zoom/pan mapping.

## 0.5.7.12 — Exact Nibbler pieces by default

- Bundle all twelve unmodified Nibbler PNGs with verified upstream blob hashes,
  artist/license notices and upstream editable Merida SVGs.
- Use smoothly scaled original images in board, drag/animation, settings preview
  and promotion icons. Retain optional Cburnett and Original SVG styles.
- Select Nibbler once on upgrade, then respect later saved piece choices.
- Retain blue analysis/database headers, neutral depth, 10% square shading and wheel navigation.

## 0.5.7.11 — Blue analysis metrics and clearer move shading

- Color evaluation, API win and frequency blue in suggested-line headers; keep
  depth, W/D/L, samples and database provenance neutral. Use the available width.
- Join validated explorer counts by position and candidate UCI move; distinguish
  live/cache data, missing samples and ChessDB scores without invented statistics.
- Keep metadata heights uniform across candidates and stable during API updates.
- Increase palette-relative last-move brightness adjustment from 5% to 10%.

## 0.5.7.10 — Restrained colors, quieter hints and wheel navigation

- Lower UI text brightness; distinguish White/Black PV moves with ivory/warm
  tints and game history with soft blue in both appearances.
- Thin candidate rods and shrink numbered circles. Replace fixed yellow last-
  move overlays with a hue-preserving five-point HSV brightness adjustment.
- Add persistent Display toggles for wheel game navigation and reversible PV
  previews. Preserve branches, hover snapshots and three-row slots.
- Accumulate partial wheel/trackpad gestures; Shift keeps ordinary scrolling.

## 0.5.7.9 — Padded move slots and expandable analysis

- Give analysis SAN moves equal-width, nonbreaking padded hit areas and more vertical room.
- Keep three reserved rows by default; Dev → Expand analysis beyond three rows
  fits each full PV without an inner scrollbar, including newly created rows.
- Remember the display preference without restarting engine analysis.

## 0.5.7.8 — Quieter MultiPV analysis panel

- Remove analysis-row rank badges and teal/green rank coloring.
- Use neutral headings and barely different White/Black move-text tints in both
  appearances. Keep the board's existing candidate colors, circles and lines.
- Preserve fixed three-line PV slots, hover snapshots and destination clicks.

## 0.5.7.7 — Download 3: clean Game Moves and optional raw PGN

- Show only move numbers/SAN and branch parentheses in the bottom Game Moves
  component, preserving selection, hover previews and navigation.
- Keep clocks/timestamps/comments/NAGs/review annotations in saves and PGN export.
- Add Dev → Show raw PGN data, off by default, with a separate read-only tab and
  copy control. Protect text-view keyboard focus from board shortcuts.

## 0.5.7.6 — Download 2: teal/green MultiPV circles and lines

- Use teal for rank one and green for alternatives, with numbered destination
  circles, thin connecting lines, matching row badges and colored move text.
- Keep three reserved move-text lines, hover snapshots, pins, legal destination
  execution and highest-ranked shared-destination selection.
- Apply reference lines once on upgrade; retain later explicit arrow selections.

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
