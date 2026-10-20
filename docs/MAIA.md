# Maia-3 in Nocturne

The Windows downloads include the official **Maia-3 79M** checkpoint and a CPU
inference worker. No Python installation, Lichess token, hosted prediction API,
or extra model download is needed. Stockfish remains your separately selected
UCI engine. Maia predicts human move choices; Stockfish searches for strong moves.

## Analysis and ratings

Enable or disable Maia in **Engine → Maia-3 79M**, or use the checkbox above
analysis. The adjacent rating selector accepts 400–3000 in steps of 200 and uses
an equally rated opponent. These are Lichess blitz rating inputs, not guaranteed
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

## Insights / Maia Tools

The right column has exactly three primary sections. **Display → Show Maia
insights** hides it while keeping the integrated probabilities available. Use
**Display → Arrange panels** to resize, dock or detach it alongside existing
panels. Reset layout returns to the standard arrangement. The main board remains
square, with coordinates inside its edges and its evaluation bar on the right.

**Moves by Rating** plots the five likeliest moves at the selected rating across
400–3000. Each point is an actual inference at that rating, with an equally rated
opponent. Missing samples remain gaps. Click legend buttons to hide/show curves;
hover near a point for the exact percentage. The dashed marker is the selected
rating. Curves are model predictions, not measured database game frequencies.

**Move Map** sums predicted probabilities by destination square. Brighter squares
are more likely destinations, and arrows show the three most likely moves.
Hover a square to distinguish individual moves, including underpromotions.
It follows the main board's position, orientation, appearance and selected rating.

**Blender Meter** compares a selected move without playing it. It shows Maia's
probability and a Nocturne relative-quality measure from the available Stockfish
MultiPV search. If exact centipawn scores establish a loss `L` from the best
searched move, the quality is `Q = exp(-L / 100)`. Thus 0 cp loss means 100%
relative quality and 100 cp loss means about 36.8%. This is a comparison scale,
not a win probability or an official Maia statistic. A bound score, mate score,
or unsearched move leaves the quality and blend unknown.

For slider weight `w` (Human = 0, Engine = 1), the displayed Nocturne blend is
`100 × ((1-w) × MaiaProbability + w × Q)`. Both inputs remain visible. No extra
Stockfish search is started merely by using the meter.

## Board indicators

The existing Stockfish rods and numbered circles stay in place. Broad,
translucent violet Maia arrows are drawn on a separate layer beneath pieces.
Toggle them or choose the top 1, 3 or 5 in **Engine → Maia-3 79M**. The miniature
move map has no duplicated board controls. Main-board previews and existing
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
