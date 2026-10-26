# Maia-3 in Nocturne

The Windows downloads include the official **Maia-3 79M** checkpoint and a CPU
inference worker. For CPU inference, no Python installation, Lichess token, hosted prediction API,
or extra model download is needed. Stockfish remains your separately selected
UCI engine. Maia predicts human move choices; Stockfish searches for strong moves.

## Analysis and ratings

Enable or disable Maia in **Engine → Maia-3 79M**, or use the checkbox above
analysis. The adjacent rating selector accepts 600–3000 in steps of 200 and uses
an equally rated opponent. Maia is used for standard chess; Chess960 keeps its
existing Stockfish analysis and does not receive unsupported Maia predictions.
These are Lichess blitz rating inputs, not guaranteed
accuracy at every rating; predictions at the extremes deserve caution.

Each Stockfish variation retains its evaluation and full PV. The probability in
the Maia column belongs to that row's **first legal UCI move**, including its
promotion suffix. Stockfish ordering never determines which probability is used.
Small probabilities retain their actual value; a dash means no result is ready.
**Inspect all Maia-ranked legal moves** opens the full policy inside the existing
analysis area, including moves outside MultiPV. The table columns are Move,
Stockfish eval (White’s perspective), and Maia probability. Missing engine
evaluations show a dash rather than an invented score. Hover the Move column
for a small-board Stockfish PV preview and scroll up/down to step backward/forward.
Changing rows resets the preview; moves without an engine PV show a brief message.
Scrolling the other columns scrolls the table normally. Clicking a move plays it.

The model uses the current PGN branch's actual history (up to eight positions),
with the official earliest-position padding when history is short. It stays
loaded in a separate process while Qt and Stockfish run independently. Requests
for positions you have left cannot replace the current results. Completed
policies for the last 128 positions, including their rating sweeps, are cached
locally and can be reused after reopening. History is part of the cache key.

Maia board arrows show every legal move with a probability strictly above 10%,
with no Top 1/3/5 cap. Their green/yellow/red colors use the Blunder Meter
classification; moves without an exact Stockfish comparison remain grey.
Colors update as Stockfish results arrive. Toggle them in **Engine → Maia-3 79M
→ Show Maia arrows (moves above 10%)**.

## Insights / Maia Tools

The right column has exactly three primary sections. **Display → Show Maia
insights** hides it while keeping the integrated probabilities available. Hidden
insights do not request new full rating sweeps; reopening them requests any
missing ratings for the current position. Maia overlays stay inside analysis
mode and cannot leak a previous position’s predictions into ordinary play. Use
**Display → Arrange panels** to resize, dock or detach it alongside existing
panels. Reset layout returns to the standard arrangement. The main board remains
square, with coordinates inside its edges and its evaluation bar on the right.

**Moves by Rating** plots the five likeliest moves at the selected rating across
600–3000. Each point is an actual inference at that rating, with an equally rated
opponent. Missing samples remain gaps. Click legend buttons to hide/show curves;
hover near a point for the exact percentage. The dashed marker is the selected
rating. Curves are model predictions, not measured database game frequencies.

**Move Map** is a scatter plot comparing human likelihood (vertical axis) with
Stockfish loss in pawns (horizontal axis). Best moves sit on the right; costly
choices sit on the left. Points share the meter's green/yellow/red categories.
Hover for the exact SAN move, likelihood and loss; click a point to select it in
the meter without playing it. Losses above three pawns sit at the `3+` edge;
tooltips retain the actual loss. Unsearched moves are omitted from the plot
rather than assigned an invented engine score. Promotions remain separate moves.

**Blunder Meter** groups Maia's predicted choices into **Best moves** (green),
**OK moves** (yellow) and **Blunders** (red). The stacked bar's widths sum the
actual Maia probabilities in each category. Each category lists its likeliest
moves. Select any legal Maia move below it to inspect its likelihood and loss.
The previous human/engine blend slider and composite score have been replaced.

Nocturne uses the centipawn fallback boundaries documented in
[Maia Platform's classification implementation](https://github.com/CSSLab/maia-platform-frontend/blob/a6e52f5c811ee18863cb2f0e81f2433a5b9905de/src/hooks/useAnalysisController/utils.ts):
loss up to **50 cp** is green; over 50 through **150 cp** is yellow; over 150 cp
is red. Loss is relative to the best available exact searched Stockfish move,
using raw UCI side-to-move scores for both White and Black. These are comparison
categories, not claims about the game's final outcome or an official Maia-3
blunder prediction model. Maia Platform can also use winrate-based thresholds;
Nocturne's meter explicitly uses the centipawn method.

**Not evaluated** probability stays grey. Moves outside MultiPV and bound-only
scores do not become blunders by default. Exact mate lines leave centipawn
comparisons unknown. Partial analysis retains its actual policy coverage instead
of being rescaled to 100%; increase MultiPV to classify more human choices.
No additional Stockfish searches are started merely by opening these insights.

## Board indicators

Stockfish uses slim rods and numbered circles. Maia uses wider, outlined arrows
with stronger opacity. Short arrows render above pieces so their tips remain visible. Maia colors follow the Blunder
Meter categories; unsearched moves remain grey. Every move above 10% is shown.
Toggle Maia arrows in **Engine → Maia-3 79M**. The scatter map has no duplicated
board controls. Main-board previews and existing
candidate hover/wheel behavior remain available.

## Reproducibility

Upstream code: [CSSLab/maia3](https://github.com/CSSLab/maia3), revision
`1e13597c42d4858b7cfd7cfdae01e297263364b2`. The model is
[UofTCSSLab/Maia3-79M](https://huggingface.co/UofTCSSLab/Maia3-79M), revision
`a107d6ceb7b298cb04ae1da4edffe2939858b894`. The build verifies the official
checkpoint's LFS SHA-256 and loads tensor state dictionaries with
`weights_only=True`; it never enables arbitrary checkpoint pickle loading.

Maia components and weights are AGPL-3.0. Upstream attribution, license text,
worker source, and the exact architecture settings accompany the source ZIP.
PyTorch and NumPy runtime license metadata accompany the worker. Build checks
exercise real White/Black move probabilities, promotion identity, rating
conditioning, legal-mask normalization, and the packaged worker protocol.

## Optional GPU acceleration (0.5.7.67)

Use **Engine → Maia-3 79M → Inference device**. **Auto** uses a verified optional
GPU runtime when installed; **CPU only** forces CPU. The ordinary Windows ZIP
continues to include a working CPU worker.

In the Windows app, **Auto** reuses a ready GPU environment across launches and
updates. If it is missing, Auto starts setup automatically, without a separate
setup click or confirmation. A failed automatic attempt is remembered to avoid
repeated downloads; deliberately select Auto again to retry after fixing the
reported problem. **CPU only** never starts GPU setup.

**Set up optional GPU runtime…** also lets you manually reinstall: it detects NVIDIA/AMD adapters and installs
an isolated runtime under Nocturne’s local data folder (`maia-gpu`). This setup
requires Python 3.12 x64 (python.org launcher) and an internet connection, and can
download several GB. It uses NVIDIA PyTorch CUDA 12.8 or AMD ROCm 7.2.1 / PyTorch 2.9.1;
actual model inference must succeed on the GPU before setup is marked ready.
GPU/driver compatibility varies. Setup does not install drivers or change global
Python packages. If unsupported operations, insufficient memory or a worker
failure prevent GPU use, inference falls back to CPU. The status line reports
the actual device, or that the result came from cache. Existing policy caches
remain reusable; a cached position does not run the GPU again.

Native ROCm uses PyTorch’s `torch.cuda` interface, distinguished by `torch.version.hip`.
Windows AMD setup follows AMD’s official ROCm 7.2.1 package list and requires
AMD graphics driver 26.2.2. The supported matrix includes RX 9070 XT; support
is not assumed for every AMD GPU. See [AMD installation instructions](https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/install/installrad/windows/install-pytorch.html)
and [Windows hardware matrix](https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/compatibility/compatibilityrad/windows/windows_compatibility.html).
DirectML is a different Microsoft backend; it is not installed by this setup.
NVIDIA/AMD hardware has not been available in the development environment;
Windows CI checks the bundled CPU model, not physical GPU performance.

## Board overlay components (0.5.7.69)

Stockfish candidates use slim rods and numbered endpoint circles, without
arrowheads. Maia moves above 10% retain their broad translucent arrows. A move
shared by both therefore has one Maia arrow, one Stockfish rod and one numbered
circle. A Stockfish-only candidate has a rod and circle; a Maia-only move has an
arrow. Existing profiles using the old Stockfish arrow style receive the same
new rendering. Manual arrows and variation previews retain their own behavior.
The obsolete candidate-arrow style menu has been removed.

## Direct chart labels (0.5.7.70)

Moves by Rating labels each visible curve directly at its right endpoint using
the same SAN name and color as its legend button. A reserved label lane and
connector lines keep low-probability labels from overlapping without moving
the plotted values. Labels follow the last available sample when sweeps are
incomplete. The buttons below remain available to hide/show curves.

## Edge arrowheads and instant placement (0.5.7.71)

Maia arrow tips stop 5% inside the destination square along the approach ray,
instead of meeting Stockfish’s numbered circle in the center. Short arrowheads
scale to fit the shortened shaft and render above pieces for visibility.
Stockfish rods and circles remain on top. Manual arrows are unchanged.

Move animations are off by default, including a one-time reset of old saved
profiles. Moves therefore appear immediately after a click or drag; the Display
menu can still enable animations later if explicitly desired. Moves by Rating
labels have their own tooltip hit areas, referencing the actual last sample
rather than a nearby curve when collision spacing displaces the label.

The insight cards are ordered **01 Moves by Rating**, **02 Blunder Meter**, then
**03 Move Map**. Practical traps remain a design proposal; no additional engine
searches are started for them in this version.

## Stable navigation spacing (0.5.7.72)

Maia tips now stop 25% inside the destination square, halfway between its
approach edge and center. Stockfish keeps its center circles. Empty positions
reserve the selected MultiPV row count, including positions with fewer legal
moves. Clearing analysis removes its content while preserving compact row
heights, keeping the game line under the cursor. Telemetry retains its measured
height when cleared and adapts again when the panel width changes.

## Structured Game Line (0.5.7.72)

The Game Line under engine candidates uses paired White/Black rows, indented
variation rows and saved White-perspective evaluations beside each move. Missing
evaluations stay blank; displaying the tree starts no new searches. The current
move is highlighted. It occupies the available space and scrolls vertically;
its wheel no longer navigates the game. Board and bottom Game Moves scrolling
retain navigation, and the bottom PGN retains parentheses. Clicking a Game Line
move still navigates directly. Score updates preserve the reader's scroll position;
explicit move selection reveals the selected row.

## Connected variation guides (0.5.7.73)

Game Line groups variations with continuous guide rails and short branch ticks.
Nested alternatives share their parent rail and receive their own indentation.
Move numbers stay in a separate gutter; saved evaluations remain beside moves.
The guides follow the text layout when scrolling or resizing. Bottom PGN notation
and board navigation remain unchanged.

## Maia outcome rail (0.5.7.76)

The rail to the left of the insight cards shows the current position at the selected
equal-player rating. White, grey and dark sections mean White win, draw and Black win.
The number is White win probability; hover for all outcomes and expected score
(White win plus half the draw probability). Missing results remain unavailable.

This uses the bundled model value head in the same forward pass as its move policy.
The official Maia implementation documents labels as side-to-move loss/draw/win:
https://github.com/CSSLab/maia3/blob/1e13597c42d4858b7cfd7cfdae01e297263364b2/maia3/uci.py#L196
Nocturne reverses loss/win only when White is to move, yielding White win/draw/Black win
for both turns. Position/history/rating caches retain outcomes alongside policies;
old policy-only entries are refreshed. This is a human outcome prediction, not centipawns.

Game Line notation uses the bundled Cburnett SVG piece shapes rendered at high
resolution for clear small icons. Stored and copied PGN remains standard SAN.
