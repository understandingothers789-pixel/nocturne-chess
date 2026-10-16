# Engine measurements — 0.3.0 preview

Actual measurements from this workspace. These are performance experiments, not a strength rating.

Command:

```sh
python -m nocturne.engine.benchmark --depth 3 --repeat 3 --variants default no-tt no-ordering no-killers pvs --output benchmarks/baseline-0.3.0.json
```

Environment: Python 3.12.14; INTEL(R) XEON(R) PLATINUM 8573C; Linux-6.18.44-x86_64-with-glibc2.41.

| Position | Default median | PVS median | Default nodes | Score (side to move) |
| --- | ---: | ---: | ---: | ---: |
| start | 0.126 s | 0.130 s | 664 | +68 cp |
| kiwipete | 6.787 s | 5.954 s | 27,421 | +58 cp |
| rook_endgame | 0.060 s | 0.065 s | 433 | +125 cp |
| promotion_tactics | 0.559 s | 0.878 s | 2,521 | +583 cp |
| middlegame | 2.523 s | 3.086 s | 8,918 | +68 cp |

All default/PVS rows reached depth 3. Scores agreed. PVS was faster in one
position and slower in others; aggregate medians did not improve. It remains
**off by default**. The table uses fresh tables per run and includes iterative
deepening and quiescence. NPS is not perft speed and depends on evaluation cost.

The raw record also contains disabled-TT, disabled-ordering and disabled-killer
experiments. Some disabled-ordering/killer searches hit the 10 s cap. Their
elapsed times and scores must not be treated as equal-depth comparisons.

## Self-play smoke experiment

```sh
python -m nocturne.engine.benchmark --match --seconds .025 --games 2 --plies 80 --variants default pvs --output benchmarks/selfplay-smoke-0.3.0.json
```

One default win by mate at ply 37; one unfinished game at ply 80. Colors were
alternated. This checks that legal games can unfold through the engine/model
stack. Two games with tiny budgets do not establish a strength difference.
Time-limited runs need not reproduce identical moves under different CPU load.
No Elo has been estimated.

## Regression policy

Compare fixed-depth runs at the same completed depth on the same machine.
Use repeated measurements, inspect score/PV changes, and run paired games with
colors reversed and a diverse opening set before drawing strength conclusions.
Keep incomplete games unadjudicated and distinguish timeout from completed depth.

Native C++/Rust, null-move pruning, LMR, SEE, aspiration windows and incremental
evaluation are future measured experiments. No speedup from them is claimed.
