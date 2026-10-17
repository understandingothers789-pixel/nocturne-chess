# Nocturne Analysis · 0.5.0

A native, offline Windows chess analysis GUI inspired by Nibbler. You supply
Stockfish or another UCI executable. **The desktop app has no built-in engine.**

The 0.5 direction replaces the earlier custom-engine product. Historical engine
source/tests remain for reproducibility; they are excluded from the desktop bundle.

![Real Qt application, using explicitly labelled simulated UCI test data](docs/preview.png)

*This screenshot uses the protocol test simulator, not Stockfish or measured chess
analysis. The simulator is not bundled in the application.*

## Windows: download and open

[Windows builds](https://github.com/understandingothers789-pixel/nocturne-chess/actions/workflows/windows.yml).
Choose the latest successful 0.5.0 run and download
**Nocturne-0.5.0-Windows-x64-unsigned** under Artifacts (GitHub sign-in required).
Extract the entire ZIP, open **Nocturne**, and double-click **Nocturne.exe**.
Keep its `_internal` folder beside the executable. Python is not required.
These are unsigned test builds; no batch/PowerShell launcher or security-policy
change is provided. The ZIP also includes the corresponding source archive.

## Connect your Stockfish

1. **Engine → Choose engine… → Add executable…**. Select your existing engine.
2. Wait for the reported engine name/options, choose a profile name, then **OK**.
3. Use **Live · maximum strength** for continuous MultiPV 1, **Explore alternatives**
   for multiple candidates, or **Bounded analysis** for time/depth/node limits.
4. **Analysis → Go/Halt** starts/stops analysis. Moving or navigating restarts the
   search on the new position while retaining the engine process/hash allocation.

Stockfish versions are not hardcoded. Options are discovered via `uci`, including
Threads, Hash, MultiPV, SyzygyPath, UCI_Chess960 and UCI_ShowWDL when advertised.
Other spin/check/string/combo/button options have a generic editor. Values respect
reported bounds; Hash also respects a conservative current memory budget. Custom
MB values are supported. Hardware presets for a Ryzen 9800X3D/32 GB are starting
points: 2 threads/256 MB, 6/1024, or 8/4096 with MultiPV 1. They are not benchmarks
or verified optima. Conventional Stockfish CPU analysis does not use the Radeon GPU.

No engine or table files are downloaded or bundled. **Choose Syzygy folder…** sends
its path to compatible engines; separate folders can be entered using `;` on Windows
in Settings or the engine's own SyzygyPath option. The external engine performs the
probes, and reported TB hits are displayed. Unsupported options are not fabricated.

## Explore quickly

- **Smart Move** is enabled by default. Click the numbered destination of the top
  recommendation without first selecting its piece. Enable **Display → Smart Move
  · allow all displayed candidates** to execute alternatives too.
- A selected piece takes priority. Shared destinations open a ranked move chooser;
  promotions offer a piece chooser. Every execution checks the live position and
  legal moves. Alt+1/2/3 follow the same Smart Move policy.
- Candidate rows show actual cp/mate/bound scores, depths, nodes and engine WDL
  where supplied. Scores and WDL are oriented to White. No cp-to-probability or
  Leela policy/visit statistics are invented. The evaluation bar uses a display
  scaling curve, not a claimed win probability.
- Hover a PV/history move to preview its position. Leaving restores the live board
  without moving the analyzed position. Click a PV move to insert its prefix;
  **Insert** adds the full line as branches. **Pin** freezes a row for the current
  position; **SAN/UCI** copy it; **Focus** uses `searchmoves` for that candidate.
  **Analysis → Analyze all legal moves again** clears the focus.
- Changing a position invalidates every recommendation/preview. Engine stop waits
  for `bestmove` and an `isready` barrier before the next search. Diagnostics are
  available in the Engine menu; logs and output queues are bounded.

The default workspace is board left, analysis right, moves and graph below.
Splitters resize the panels; **Display → Analysis on the left** preserves the
previous layout. Light/dark palettes, coordinates, animations, overlay visibility,
branch arrows and compact/detailed statistics are configurable. Manual annotations
use right-click squares and right-drag arrows. Board images can be exported as PNG.

## Studies, PGN and Chess960

Paste PGN or FEN directly, edit PGN in the side tab, open files, or drop PGNs onto
the window. Multiple games open in separate study tabs and are saved to the library.
Ctrl+T opens a new tab. Rename studies from File; opening another study preserves
existing work. Up to 20 study IDs reopen; older games remain in the library.

Alternate moves preserve the original continuation. Nested branches, comments,
starting comments, NAGs, tags and standard `[%eval]` annotations round-trip.
**Tree → Edit comment / annotations…** edits the current node. Promote a line or
switch siblings using Tree. Comments containing literal `}` follow the PGN format's
restriction; do not expect a literal closing brace inside a brace comment to survive.
Single-import limits are 4 MB/20,000 nodes and 1,000 games.

**File → Set up position…** provides piece placement, erase, clear/reset, side to
move, castling and EP fields. Positions are validated before use. **New Chess960
position…** accepts a Scharnagl index 0–959. Chess960 uses rook-square UCI castling
and Shredder FEN rights; an engine must advertise UCI_Chess960 for analysis.
Rules and PGN handling use python-chess, with a small adapter for vector drawing.

Autosaves and settings use local SQLite in Qt's application data directory,
typically `%LOCALAPPDATA%/Nocturne/Nocturne Chess`. Corrupt records are reported,
not silently deleted. Back up the database while the app is closed.

## Analyze a complete line

**Analysis → Analyze entire line… (F12)** uses a chosen per-position time budget
and the bounded depth/node settings. It evaluates each position and performs a
separate root `searchmoves` search for a played alternative. It does not move the
visible board. Pause/resume/cancel preserve completed results. Evaluations and
review evidence are saved with their nodes and exported as PGN annotations.

For exact centipawn scores, estimated losses of 50/100/200 cp mark inaccuracy,
mistake/blunder. Best means the engine's reported first move. Different achieved
depths are retained, so these equal-limit comparisons are estimates, not objective
proof of move quality. Mate scores are shown for inspection rather than mixed
arithmetically with centipawns. Bound scores do not become exact review labels.
The graph uses White's perspective: click a sample to navigate, hover for its value,
wheel to zoom, middle-drag to pan, and double-click to reset the view.

**Ctrl+K** opens searchable commands. **Display → Keyboard shortcuts…** remaps
commands with duplicate-key conflict checking and JSON import/export.

## Build and validation

Python 3.12+, native PySide6; no browser or compiler is needed for source installation:

```sh
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.venv\Scripts\python.exe -m nocturne
```

Use the virtual environment's Python for these commands. [Windows build instructions](docs/BUILDING.md)
produce the windowed executable with PyInstaller. Runtime works offline after installation.

Executed validation is recorded in [PROGRESS.md](PROGRESS.md). The external protocol
simulator tests startup, advertised options, MultiPV, bounds, process reuse, stale
output, crash/timeout recovery, Smart Move, review and PGN export. It is not a
playing engine. Real Stockfish 19/development builds were not installed here, so
that real-engine verification remains outstanding; no strength or speed claim is made.

## Remaining work and comparison

[Nibbler research and comparison](docs/NIBBLER_RESEARCH.md) ·
[Acceptance checklist](docs/ANALYSIS_ROADMAP.md) · [Architecture](docs/ARCHITECTURE.md).

This is a usable analysis release, not a claim of full Nibbler parity. Remaining:
independent second-engine/split-board comparison; persistent cross-study analysis
cache/snapshots; rich tree collapse/search/bookmarks/delete/restore; study collections;
figurines and additional piece sets; WDL graph/scaling controls; arbitrary saved panel
layouts; calibrated/adaptive game review. Review pause state survives in-session;
completed evidence survives restart, but an active queue is not resumed automatically.
Each tab retains its study; only the selected tab is actively analyzed. Play/self-play
currently use the selected single engine profile. Full manual Windows interaction,
DPI/suspend behavior and actual Stockfish/large Syzygy collections remain unverified.

## Licenses

The combined analysis application is **GPL-3.0-or-later** because it uses
python-chess. See [COPYING](COPYING). Original Nocturne code/assets retain their
MIT grant in [LICENSE](LICENSE). No Nibbler code/assets or Stockfish binary is
included. The source ZIP includes Nocturne source and the installed python-chess
Python source. Qt/Python and dependency details are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
