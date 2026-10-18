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
  checks, multi-game parsing, comments/NAGs/evaluation and PGN clock annotation
  preservation. Imported clock tags are read-only position data, not active timers.
- `engine/uci_types.py`: typed advertised options, score/bound/WDL parsing and limits.
  It contains no search or position evaluation.
- `gui/uci_connection.py`: persistent QProcess, asynchronous lifecycle, stop/ready
  barriers, deadlines, 80 ms information batches, 1 MB line bound, 500-line log.
- `gui/engine.py`: generation IDs, position snapshots, legal PV/bestmove validation.
- `gui/engine_manager.py`: executable profiles, discovered option editors/presets.
- `gui/engine_resources.py`: menu-only QObject for advertised Threads/Hash choices;
  configuration in preferences is authoritative, with no hidden settings widgets.
  Window menus also manage MultiPV, active profile and bounded/continuous analysis.
- `gui/candidates.py`, `moves.py`, `board.py`, `widgets.py`: candidate interaction,
  reversible previews, destination execution, rendering and sampled graph.
- `gui/setup_position.py`: manual position editor with final library validation.
- `gui/window.py`: native menus, study tabs, analysis/review orchestration and saves.
  Studio appearance previews use a temporary visual configuration; only Save
  changes preferences. Board SVG renderers cache each available piece style.
  Game Moves renders numbered SAN/branches without metadata. An opt-in read-only
  raw PGN tab exposes full saved annotations, including clock and timestamp tags.
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
its snapshot. A second identity guard rejects results for a changed game/cursor/key/variation node.
Hover positions are separate boards and never become the analyzed position.
Smart Move requires a matching full FEN and rechecks live legal moves. An ordinary
selected piece takes priority; ambiguity and promotions require explicit choices.

The analysis pane contains status, actual PVs and a graph. Candidate move views
reserve a fixed three-line viewport per rank, including ranks awaiting output.
Font/DPI-aware measurement is cached; longer documents scroll within the slot.
Headers retain a fixed height. A hovered rank holds its displayed snapshot and
queues its newest update until hover ends. Only that rank can end its preview;
updates elsewhere cannot clear it. Clicks activate before the pending update can
replace their data. Position/context changes invalidate queued callbacks. Markers
and destination clicks follow displayed snapshots, including a queued flush.
These are the only runtime changes from the 0.5.7 baseline in patch 0.5.7.1.
Settings live in the Engine menu and line actions in context menus. The classic
split gives more width to analysis and keeps a compact move tree below.

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

## Opening explorer

explorer.py validates standard FEN queries and service statistics, recomputes SAN
and legal moves locally, and maintains a bounded, isolated SQLite cache.
gui/explorer_client.py owns QtNetwork transport: one active reply, cancellation
generations, 350 ms debounce, one-second minimum pacing, 10 s total timeout,
512 KiB payload limit and a global 429 cooldown without automatic retries.
The 24-hour cache is keyed by canonical position, source and effective filters;
stale cache can remain available with an explicit network error. No game library
records are modified by cache corruption.

gui/explorer_panel.py renders frequency-ordered database statistics beneath the
PV scroll area in a resizable splitter. Database menu commands own source/filters.
Queries run only while enabled in the active Analysis/Engine view. Hover/click
signals carry the study/node identity and pass the same legal rules boundary as
board moves. Board hover previews never trigger requests or navigate. Explorer
counts are not mixed with engine evaluation or MultiPV ranking.

Endpoints/filter groups were checked against the official Lichess API specs:
https://github.com/lichess-org/api/tree/master/doc/specs/tags/openingexplorer
The online integration does not copy or bundle the AGPL explorer server.

ChessDB is a separate queryall JSON adapter using learn=0 and showall=0. Its
service score/note rows contain no invented WDL/counts. Normal cp scores are
oriented to White; large mate/DTZ codes retain an explicit DB prefix. The cache
key retains the fifty-move clock for this source. Unknown/checkmate/stalemate
states and semantic rate limits are handled explicitly. Terminal responses are
checked against local rules. Source: https://chessdb.cn/cloudbookc_api_en.html

Lichess's current official host requires authentication. A masked Database-menu
dialog sets a session-only Bearer token; it is never persisted or included in
cache URLs/game records. Authorization is added only to HTTPS port 443 on
explorer.lichess.org and same-origin redirect policy applies. ChessDB and custom
test endpoints never receive it. HTTP 401/403 explains the native token menu.
The optional live check reports unauthenticated sources as protected, separately
from successful data queries; it never substitutes a fabricated response.


## Neutral appearance and clock presentation (0.5.7.3)

A shared theme.palette() supplies neutral dark/light colors to Qt stylesheets,
move HTML and custom-painted graphs/board frames. Classic/Grey board colors are
independent of interface light/dark mode. settings.normalize() records one
appearance_version migration: legacy Forest defaults become Classic, other
palettes remain unchanged, and later explicit choices round-trip normally.
The original icon is recolored and its multi-resolution ICO regenerated with Qt.

Display show_clocks is a validated persisted boolean. window._update_players()
reads the existing Game.clock_values() for both the analysis strip and Play
labels. Visibility never calls start_clock/pause_clock or changes game data.
Analysis retains its existing paused timing semantics and untimed games show
infinity. Player clocks keep a stable content margin when active styling changes.
Changing light/dark appearance recolors all candidate views, including pinned
rows, without changing their three-line measurement or move snapshots.
# PGN clock comments are parsed as read-only position data. The mainline or
# selected variation determines the last known clock for each color. The display
# does not turn imported annotations into an active timer or infer missing times.
