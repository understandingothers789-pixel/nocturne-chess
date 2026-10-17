# Native analysis architecture · 0.5

The desktop product is an external-UCI GUI. Retaining Python/PySide6 preserves
working native board rendering, local libraries and a tested Windows distribution;
Qt QProcess supplies asynchronous, safe child-process transport. See the
[Nibbler research](NIBBLER_RESEARCH.md) for the technology decision and evidence.

## Boundaries

- `core/rules.py`: python-chess adapter, legal moves, FEN/Chess960, draw rules;
  converts 64-square library positions to the board widget's 0x88 coordinates.
- `core/game.py`, `variation.py`: authoritative study/clock state, ordered branches,
  node annotations/evaluations, validated schema-2 saves with schema-1 migration.
- `core/notation.py`: SAN and python-chess PGN import/export, strict structure
  checks, multi-game parsing, comments/NAGs/evaluation annotation preservation.
- `engine/uci_types.py`: typed advertised options, score/bound/WDL parsing and limits.
  It contains no search or position evaluation.
- `gui/uci_connection.py`: persistent QProcess, asynchronous lifecycle, stop/ready
  barriers, deadlines, 80 ms information batches, 1 MB line bound, 500-line log.
- `gui/engine.py`: generation IDs, position snapshots, legal PV/bestmove validation.
- `gui/engine_manager.py`: executable profiles, discovered option editors/presets.
- `gui/candidates.py`, `moves.py`, `board.py`, `widgets.py`: candidate interaction,
  reversible previews, destination execution, rendering and sampled graph.
- `gui/setup_position.py`: manual position editor with final library validation.
- `gui/window.py`: native menus, study tabs, analysis/review orchestration and saves.
- `storage.py`: transactional SQLite records/preferences, no Qt dependency.

Historical custom rules/search/UCI/Fathom modules remain as 0.4-era source. The
new GUI does not invoke them. PyInstaller excludes the custom search/evaluation,
worker/UCI entry point and native table reader. SyzygyPath goes to the supplied engine.

## Engine state contract

`launch → uci → initial-ready → idle → ready → search`.
On replacement/navigation: immediately invalidate the generation, send `stop`,
discard old info, await `bestmove`, then an `isready` barrier. Keep only the newest
pending position. Unknown options are not sent. Invalid supported values or
unsupported Chess960 requests produce an explicit error. Finite searches have
an additional response deadline; stop/ready/handshake phases have deadlines.
Failed processes can be explicitly restarted. Executable/arguments are separate;
there is no shell or web content. UTF-8 is used with replacement for diagnostics.

Only the GUI thread mutates a study. PV prefixes and bestmove are checked against
its snapshot. A second identity guard rejects results for a changed game/cursor/key.
Hover positions are separate boards and never become the analyzed position.
Smart Move requires a matching full FEN and rechecks live legal moves. An ordinary
selected piece takes priority; ambiguity and promotions require explicit choices.

## Data and scoring

Raw UCI scores retain cp/mate, value and exact/lower/upper bound. Plot coordinates
are separate from mate values; UI WDL is reversed for Black to move and only shown
when reported. No conversion is presented as an engine win probability.

Analysis is stored by node, including engine name, options, timestamp, raw score,
depths and PV. Full-line review freezes node IDs and uses position snapshots,
not a full-tree clone per position. A separate targeted root search supplies the
played-move comparison. Completed exact scores and review evidence survive
cancellation/autosave and PGN export. Achieved depths remain available because
time-equal comparisons can still differ in depth. Live and review results are
separate from temporary board previews. One external process analyzes the selected
tab; other tabs retain positions and saved samples.

## Distribution and limits

PyInstaller produces one native windowed Nocturne application. No engine binary,
network service or Windows script launcher is bundled. Source installation uses
Python 3.12+, PySide6 and chess 1.11.2. python-chess changes combined distribution
terms to GPL-3.0-or-later; original code/assets remain MIT-licensed. Source archives
include the runtime rules library's Python source and all notices.

Imports are bounded to 4 MB, 20,000 nodes and 1,000 PGN games. Very large-tree UI
latency and cold external-engine initialization still require profiling. Manual
Windows/DPI testing and actual Stockfish builds are pending. Advanced comparison,
cache/snapshots, rich tree editing and flexible dock layouts are explicit roadmap
items, not hidden/nonfunctional controls.
