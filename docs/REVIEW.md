# Game Review · Nocturne accuracy v1

Game Review is optional, local and powered by the user's external UCI engine.
Open Analysis → Game Review, or the Game Review button above PVs. Start reviews
the selected line through its saved continuation. Navigating within the review
does not alter that line. Normal board moves can create alternative branches.

## Evidence and limits

For each played move, an unrestricted search finds the engine's best move from
the position **before** that move. If the played move differs, another search
from that same position uses `searchmoves` to evaluate the played alternative.
Both use the same configured depth/time/node limits, profile and options. Time is
per search, so a non-best move can require two searches. A final-position search
also saves an evaluation for the graph. Review uses MultiPV 1 independently of
the normal analysis MultiPV setting. Threads/Hash come from the Engine menu.

Scores are from the mover's perspective in both searches; Black scores are not
mistakenly subtracted in White's perspective. The evidence retains score type,
bound, PV, achieved depth, engine name, applied UCI options, requested limits and
root FEN. Root FEN and played UCI move bind every saved grade to its position.
Missing scores, bound scores, mate-zero scores or ignored `searchmoves` pause
review instead of receiving a label. Cancel retains completed grades; pause/resume
continues in-session. Restarting a review clears old grades on that selected line
before calculating new ones. Other variations retain their results.

## Numerical method

For centipawn score `cp`, convert to an outcome proxy on a 0–100 scale:

```text
P(cp) = 50 + 50 × tanh(0.00184104 × cp)
```

This is a display/review model, not an observed or calibrated probability that
the user will win. Extreme cp values saturate numerically. Positive mate maps to
100, negative mate to 0; mate distance is deliberately not graded. Mate zero is
unscored because it cannot describe a legal nonterminal root in this comparison.

Let `L = max(0, P(best) − P(played))`, in percentage points. The engine's reported
first move receives Best and 100. Other moves use the unrounded loss bands:

| Label | Outcome-proxy loss |
|---|---|
| Excellent | Less than 1 point |
| Good | At least 1, less than 3 |
| Inaccuracy | At least 3, less than 8 |
| Mistake | At least 8, less than 20 |
| Blunder | At least 20 |

Per-move estimated accuracy is:

```text
A(L) = clamp(103.1668100711649 × exp(−0.04354415386753951 × L)
             − 3.166924740191411 + 1, 0, 100)
```

White and Black estimates are the arithmetic mean of each side's graded moves.
Overall is the move-weighted arithmetic mean across both sides. An unreviewed
move is excluded, never assigned 100. No graded moves displays a dash. Incomplete
coverage displays partial/provisional status and exact reviewed/total counts.
All six quality counts describe graded moves only.

The numerical transforms refer to the published Lichess curves inspected on
2026-10-17, independently implemented here:

- [scalachess score-to-percentage model](https://github.com/lichess-org/scalachess/blob/master/core/src/main/scala/eval.scala)
- [lila per-move accuracy curve](https://github.com/lichess-org/lila/blob/master/modules/analyse/src/main/AccuracyPercent.scala)

Nocturne's arithmetic mean, selected-line comparisons and label bands differ
from Lichess's full game aggregation. **This is not a Chess.com or Lichess game
accuracy score, a percent of objectively correct moves, or an Elo estimate.**
No upstream Scala code/assets, engine executable or remote review service is
bundled. Analysis works offline after selecting a local engine.

## Interpreting results

Shallow searches can misjudge moves. Equal time budgets can reach different
depths, and targeted searches can score higher than the unrestricted search;
negative estimated loss is clamped to zero. Engines have different centipawn
scales, so compare reviews with the same engine/options and adequate limits.
The detail view shows the best/played scores and achieved depths so the user can
inspect questionable grades. Winning-mate and already-lost-mate positions have
special limitations: the proxy grades retained outcomes, not faster mates or
longer resistance. Brilliant, book, sacrifice and opening-theory labels are not
inferred. Automated UCI-fixture grades verify behavior, not playing strength.

Results and full evidence are saved in the local game library. PGN exports
labels, accuracy estimates, criteria and existing evaluation annotations as
comments. Reimported PGN cannot reconstruct full search evidence and must be
reviewed again to produce a new summary. Legacy cp-only review records are not
silently converted into percentage grades. Malformed legacy records are skipped
for summaries and do not break PGN export.

At compact window heights the review panel scrolls vertically so all controls
and evidence remain reachable. The normal analysis pane retains its existing
layout and is restored with Back to analysis. Selecting a result shows that move;
Show position before selected move returns to its parent without restarting
halted analysis. Continuous analysis resumes only when the user chooses Go.

Manual Windows/DPI and real Stockfish review remain release checks; synthetic
screenshots explicitly say UCI simulator test scores and are not engine results.
