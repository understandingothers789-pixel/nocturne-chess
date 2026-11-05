# Performance review for 0.5.7.139

Reviewed board rendering, menu events, candidate updates, notation rendering,
Maia charts and assessments, engine PV validation, game history, autosave and
PGN archiving, database requests, and Maia inference requests/cache persistence.

## Changes

- Cache rasterized chess pieces for the current piece set, physical size and
  screen scale. Resize and scale changes replace the cache; at most twelve
  piece images are retained for that size. The SVG assets remain authoritative.
- Skip evaluation graph history copies and repaints when samples, cursor,
  line length and game context are unchanged.
- Skip rebuilding Maia probability labels for identical policy/rating/theme inputs.
  Candidate-line updates still refresh labels when their root moves change.
- Skip rating chart updates when position, computed policies, selected rating and
  appearance are unchanged. Curve selection continues to repaint independently.
- Menu help uses a single one-shot timer per window. Menu ancestry checks run
  only for relevant events, rather than every mouse movement or paint event.

## Existing safeguards retained

- Engine PV validation caches legal continuations and SAN; previews retain their
  displayed snapshot while a user browses them.
- Notation updates reuse unchanged documents and replace only score/depth prefixes.
- Maia assessments retain depth/node information to resolve duplicate candidates.
- Database requests are asynchronous, debounced, paced and protected against stale
  replies. Rate limits and token boundaries remain enforced.
- Autosaves are deferred, preference writes avoid unchanged values, PGN backups
  avoid replacing identical text, and archive writes remain atomic.
- Maia inference deduplicates active/queued requests and keeps a bounded position
  cache. No model precision, engine search budget or prediction coverage changes.

## Measurement

A local offscreen Qt run measured 150 warm board repaints at 700 × 700:
SVG rendering averaged 4.95 ms per repaint; cached pieces averaged 1.14 ms.
This measures board painting on this machine, not engine search speed or total
application responsiveness. Resize and 2× scale rendering also completed.
