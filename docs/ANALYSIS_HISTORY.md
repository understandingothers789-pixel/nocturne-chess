# Analysis history and tactic hints

Enable **Analysis history** beside STOCKFISH (off by default). Checkpoints appear below it at 1M, 2M, 4M, 8M nodes and successive doublings. Skipped thresholds are omitted instead of being backfilled with identical data. Each captures the configured MultiPV lines from raw engine output once all requested ranks are available. Individual lines may have different depths; the tooltip reports the captured node count. No additional engine searches are launched for capture.

Select a checkpoint to inspect its lines with the usual board previews and move clicks. Live analysis continues without replacing the selected checkpoint. **Live** returns to current output.

- **Rank at that time** displays the captured ranking.
- **Keep moves in place** fixes rows to the latest ranking when you enter this mode. **Update move order** resets that order. Historical ranks appear beneath available lines; absent candidates say “Not in captured MultiPV.” No missing scores are inferred.

Checkpoints remain attached to their game position in memory (up to 128 positions). Starting a new search replaces that position’s checkpoints. They are not saved across application restarts. The separate developer snapshot archive remains available.

## Find tactics

Stop Stockfish and Leela first, then click **Find tactics**. The scan checks plies 4–12 by default of each line in the selected checkpoint, or current lines for Live. It runs in small cancellable steps. Changing checkpoint or position, or restarting analysis, cancels unfinished work. Click a result to preview the relevant position.

Results describe forks, newly created absolute pins, discovered attacks/checks, mate on the captured line, and possible sacrifices. Possible sacrifices require an offered piece to be captured on the next ply without equal immediate recovery; ordinary captures and exchanges are excluded. This intentionally conservative heuristic can miss sacrifices, including deeper compensation and declined offers.

These are pattern hints, not engine verification of a forced tactic or a sound sacrifice. A mate on one PV does not establish mate against every defense. No separate verification engine is launched in this version.

## More details

The text-only **Analysis history** button toggles capture. **More details** beside it provides:

- **Finer capture: use one engine thread**: slows the next search, allowing more time for early checkpoints. It does not insert artificial waits into the GUI, and cannot guarantee an engine emits data at every threshold. Normal thread settings return on the next search when this option is disabled.
- **First tactic ply / Last tactic ply**: set the scan range in half-moves, counting from the analyzed position. The default minimum is 4 and maximum is 12. Earlier moves are still replayed to establish the board, but their tactics are excluded from results.

Captured lines show compact depth labels, including their original greyed-out earlier candidates. Retained candidates fill the same spare rows up to five total as the live panel, keep their own capture-time depth and styling, and support hover previews and move clicks.
