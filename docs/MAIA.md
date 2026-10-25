# Maia-3 in Nocturne

The Windows downloads include the official **Maia-3 79M** checkpoint and a CPU
inference worker. For CPU inference, no Python installation, Lichess token, hosted prediction API,
or extra model download is needed. Stockfish remains your separately selected
UCI engine. Maia predicts human move choices; Stockfish searches for strong moves.

## Analysis and ratings

Enable or disable Maia in **Engine → Maia-3 79M**, or use the checkbox above
analysis. The adjacent rating selector accepts 400–3000 in steps of 200 and uses
an equally rated opponent. Maia is used for standard chess; Chess960 keeps its
existing Stockfish analysis and does not receive unsupported Maia predictions.
These are Lichess blitz rating inputs, not guaranteed
accuracy at every rating; predictions at the extremes deserve caution.

Each Stockfish variation retains its evaluation and full PV. The probability in
the Maia column belongs to that row's **first legal UCI move**, including its
promotion suffix. Stockfish ordering never determines which probability is used.
Small probabilities retain their actual value; a dash means no result is ready.
**Inspect all Maia-ranked legal moves** opens the full policy inside the existing
analysis area, including moves outside MultiPV. Clicking a move plays it.

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
400–3000. Each point is an actual inference at that rating, with an equally rated
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

The existing Stockfish rods and numbered circles stay in place. Broad,
translucent violet Maia arrows are drawn on a separate layer beneath pieces.
Toggle them or choose the top 1, 3 or 5 in **Engine → Maia-3 79M**. The miniature
scatter map has no duplicated board controls. Main-board previews and existing
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

Choose **Set up optional GPU runtime…** to detect NVIDIA/AMD adapters and install
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
