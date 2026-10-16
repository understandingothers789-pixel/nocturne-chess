# Nocturne Chess · 0.3.1

A native, offline chess studio with an independent Python chess engine, a
PySide6 desktop interface, and reproducible rules/search tests. Designed for
Windows 11; developed and exercised in this Linux environment.

![Actual Qt window with real engine analysis](docs/preview.png)

This release implements the first three development milestones and selected
UCI/analysis tools. The longer roadmap remains explicit in [TODO.md](TODO.md).
It does not claim a verified Elo or complete advanced analysis suite.

## Play

[Download the Windows test ZIP (0.3.1)](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/38960506947/artifacts/12073040643) (GitHub sign-in required).

Future Windows test builds are available from the latest successful run on the
[Actions page](https://github.com/understandingothers789-pixel/nocturne-chess/actions).
While signed into GitHub, open the run and download the artifact named
**Nocturne-0.3.1-Windows-x64-unsigned**. Extract the entire ZIP, open the
`Nocturne` folder, and double-click `Nocturne.exe`. Keep `_internal` beside it.
Python is not required. These test builds are unsigned and Windows may show a
SmartScreen warning. They expire after 30 days. No batch or PowerShell launcher
files are included. The executable built locally in this Linux workspace is
still Linux-only; use the Windows artifact from GitHub.

For developers with the source on Windows, the [developer-only Python
builder](scripts/build_windows.py) validates a local build. It does not create a
signed release or make SmartScreen warnings impossible.

To run the source on a development machine with Python 3.12 or newer:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pip install --no-deps --no-build-isolation -e .
.venv\Scripts\python -m nocturne
```

On Linux/macOS use `python3 -m venv .venv` and `.venv/bin/python`. A Linux
desktop needs the usual Qt/X11/Wayland system libraries. For headless tests set
`QT_QPA_PLATFORM=offscreen`. Dependencies are fetched during installation only.

## What works

* **Custom rules:** legal moves, checks and endings, castling, pinned en passant,
  all promotions, FEN, SAN/UCI notation, main-line PGN, repetition, draw claims
  including intended moves, and automatic fivefold/75-move endings.
* **Independent AI:** tapered evaluation, iterative negamax alpha-beta,
  quiescence with check evasions, ordered moves, killer/history heuristics,
  Zobrist transposition table, mate distance, PV and time/node limits.
* **Native board:** vector pieces, click/drag input, promotion selection,
  legal/capture/last-move/check highlights, right-button annotations, flip,
  coordinates, animation, four board palettes, dark/light appearance.
* **Game modes:** Human vs AI with side choice and six search profiles, two
  local players, automatic AI vs AI with optional local UCI engines, and an
  analysis workspace with independent saved copies and history branching.
* **Local games:** increment clocks, optional takebacks, pause/resign/draw,
  SAN history, autosave, paused resume, library, PGN export and FEN clipboard.
* **Analysis/development:** evaluation bar, suggested-move arrow, single PV,
  sampled evaluation graph, adjustable analysis limits, depth/seldepth/nodes/
  NPS/hash/time telemetry, benchmark export and saved engine-game statistics.
* **Interoperability:** console UCI engine and explicit selection of an installed
  external UCI executable. Stockfish is never downloaded, bundled, or used to
  power the custom engine.

Search runs in separate processes. The GUI checks job generation and position
identity before accepting a result. Editing, undoing, importing or starting a
new game cancels the previous job. Engine results still cross the legal-move
boundary before they can change the game.

## Using the studio

The top menus follow Nibbler's File, Tree, Analysis, Display, Engine and Play
organization for supported features. Hover tooltips are removed. In the **PGN**
tab, paste a full PGN game or plain SAN moves (for example `1. e4 e5 2. Nf3 Nc6 *`)
and click **Apply PGN**. Invalid text preserves the current game and your draft.
**Load current** resets the editor to the game on the board. Normal
Ctrl+C/Ctrl+V work inside the editor. PGN import keeps only the main line. [See the PGN editor](docs/preview-pgn.png).

**File → Load FEN / PGN from clipboard** (Ctrl+Shift+V) imports clipboard text
directly. **File → Write PGN to clipboard** (Ctrl+Shift+P) copies the current
game. File-based Open PGN and Save this game as PGN remain available.

**New game** selects mode, side, difficulty, clock and player/engine choices.
Beginner/Casual select among searched moves within a bounded score margin;
stronger profiles increase depth/time. The profiles are not Elo ratings.

Click a piece then its destination, or drag it. Promotion always offers a
choice. Right-click marks a square; right-drag draws an arrow. Escape clears
annotations. The last move and a checked king have distinct highlights.

**Analysis** saves and forks the current game before exploration, preserving
the played game in the library. History navigation pauses clocks. A new move
from an earlier position replaces the continuation in that analysis copy;
full variation trees are a later milestone. **Import** accepts a legal FEN or
one PGN game. A FEN contains no prior repetition history; importing a PGN
replays and preserves that history.

The Engine tab shows actual search samples, from White's perspective.
**Analyze position** starts one bounded search; **Stop analysis** cancels it.
Subsequent analysis moves/navigation trigger a new search. Settings can hide
the evaluation bar and arrows while playing. A sampled graph is not a
complete automated game review, and no move-quality labels are invented.

**Draw** claims a currently available draw, or offers an intended-move claim
and a draw offer. An intended-move claim accepts SAN or UCI without committing
the declared move. UCI has no draw-offer protocol, so external-engine games
support valid claims but cannot negotiate offers through UCI.

**Settings → External engine** selects a trusted local executable. Select the
external source in New Game or the analysis source selector. Invalid engine
moves are rejected; process/protocol failures pause play with an error message.

**Engine lab** pauses the game and runs five known FENs with fresh hash tables,
recording completed depth, score, PV, nodes and duration. Time-capped rows are
marked. Use JSON exports for comparisons. See [measured results](docs/BENCHMARKS.md).

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| Ctrl+N / Ctrl+S | New game / save |
| Ctrl+O / Ctrl+E | Open / save PGN file |
| Ctrl+Shift+C | Copy FEN |
| Ctrl+I | Open PGN editor |
| Ctrl+Shift+V / Ctrl+Shift+P | Load clipboard / copy PGN |
| F / Escape | Flip / clear annotations |
| Left / Right | Takeback / next history position |
| Home / End | First / latest history position |
| Space | Pause / continue play |

## Validate and benchmark

The core suite can run without Qt or external chess packages; those tests are
explicitly skipped if their dependencies are missing. The pinned development
environment runs native Qt and independent-oracle tests too.

```sh
python -m unittest discover -s tests -v
python -m pytest -q
ruff check src tests scripts
python scripts/perft.py --depth 4 --divide
python -m nocturne --uci
python -m nocturne.engine.benchmark --depth 3 --repeat 3 --output benchmarks/new.json
python -m nocturne.engine.benchmark --match --seconds .1 --games 10 --variants default pvs --output benchmarks/match.json
```

Opt into deeper perft with `NOCTURNE_DEEP_TESTS=1` (PowerShell:
`$env:NOCTURNE_DEEP_TESTS='1'`). Executed results, failures/fixes and milestone
status are recorded in [PROGRESS.md](PROGRESS.md). Start depth 5 matched
4,865,609 nodes; Kiwipete depth 4 matched 4,085,603.

## Limits and future milestones

General dead-position proof for arbitrary blocked positions is not implemented.
Material draws are recognized conservatively: bare kings, one minor vs king,
and bishop-only positions with every bishop on the same color. No known legal
move edge case is intentionally omitted.

PGN interchange keeps the main line and tags; comments, NAGs and variations are
accepted/skipped on import and are not preserved. Multi-PV, full variation
trees, automated move classification/blunder review, an opening database,
sound and alternate piece sets are pending. PVS remains an opt-in benchmark
experiment; null-move pruning, LMR, SEE, NNUE and native engine acceleration are
not implemented. The custom engine supports one search thread. Hash size is an
approximate Python object-memory budget. Search budgets cover calculation;
process startup also consumes real game-clock time.

Saved data uses versioned SQLite in Qt's local application-data directory
(typically `%LOCALAPPDATA%/Nocturne/Nocturne Chess` on Windows). Close the app
before backing up the database. Invalid records are reported and retained;
invalid preferences fall back to bounded defaults. The app never deletes a
corrupt library to conceal an error.

## Project and licenses

[Architecture](docs/ARCHITECTURE.md) · [Progress](PROGRESS.md) ·
[Roadmap](TODO.md) · [Changelog](CHANGELOG.md) · [Windows build](docs/BUILDING.md)

Project code and original SVG assets: [MIT](LICENSE). Qt/PySide and build-tool
notices are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). python-chess is a
development-only oracle, explicitly excluded from the application bundles.
