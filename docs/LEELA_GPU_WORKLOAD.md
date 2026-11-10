# Leela GPU workload controls

## Findings

The existing nodes-per-second setting is sent as Lc0's `NodesPerSecondLimit`. In Lc0 0.32.1, the classic search computes its rate and sleeps after completing an inference batch. It does not cap instantaneous GPU power. Lc0's own option description notes that smaller minibatches improve limiter accuracy. Normal Nocturne operation previously paired this setting with batch size 16 and two search threads.

Reference: https://github.com/LeelaChessZero/lc0/blob/v0.32.1/src/search/classic/search.cc (the loop following “waste time to limit nps”), and `src/search/classic/params.cc` (`NodesPerSecondLimit`).

## Controls in Leela Advanced

| GPU workload | Effective batch size | Search threads | Effective NPS ceiling |
|---|---:|---:|---:|
| Normal | User setting | 2 | User setting; zero means unlimited |
| Low | At most 4 | 1 | At most 500 |
| Minimal | 1 | 1 | At most 100 |

Lower custom NPS limits are respected in Low and Minimal. The displayed effective settings explain the active limits; saved normal batch/speed choices are preserved when switching modes. These controls do not set a hardware wattage or GPU utilization percentage. GPU/model initialization can still spike, and coil whine may persist.

**Analyze only when I click Analyze again** prevents new searches during navigation. Completed cached results remain available. **Stop Leela** cancels a pending or active search and prevents automatic restart until Analyze again is clicked. A manually requested initial search resumes after setup finishes unless stopped in the meantime.

Engine option verification requires the batch/thread/speed controls when limiting workload. Unsupported engines are stopped rather than silently claiming a limit is applied. Late messages from a previous search are ignored. Pending launch timers are cancelled before switching positions or returning cached results.

## Tradeoffs and scope

Lower workload means fewer examined positions within a fixed time. Searches with a node target can take much longer. Short results should be treated as preliminary. The neural-network model, board position, and WDL matchup settings are not replaced by a weaker model. Maia and other GPU applications have their own workloads.

Software checks cover effective option forwarding, saved settings, on-demand scheduling, stop/resume behavior and stale-message rejection. Physical GPU wattage and sound levels cannot be measured in the current environment; there is no claim of a guaranteed hardware power reduction.
