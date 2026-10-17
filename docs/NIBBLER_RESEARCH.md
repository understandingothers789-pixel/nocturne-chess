# Nibbler research and Nocturne analysis direction

Inspected 2026-10-17, Nibbler master tree
`6eb0f066402c0cf53d08d682dbc394acd9cb5fb9` (GPL-3.0). This is an original
implementation: no Nibbler code or assets are copied.

## Verified behavior, beyond the README

- [90_engine.js](https://github.com/rooklift/nibbler/blob/master/files/src/renderer/90_engine.js)
  maintains desired/current search states, validates searchmoves and waits for
  UCI/ready handshakes. Preserve persistent processes and orderly stop barriers.
- [80_info.js](https://github.com/rooklift/nibbler/blob/master/files/src/renderer/80_info.js)
  parses cp/mate/MultiPV/depth/nodes and separates engine search cycles. Stockfish
  PVs can be incomplete while updating; validate each prefix before displaying.
- [81_arrows.js](https://github.com/rooklift/nibbler/blob/master/files/src/renderer/81_arrows.js)
  builds one-click destination mappings, resolves shared destinations by display
  ordering and adjusts ordinary castling arrowheads. Preserve direct destination
  execution, but explicitly prioritize selected pieces and expose ambiguity.
- [95_hub.js](https://github.com/rooklift/nibbler/blob/master/files/src/renderer/95_hub.js)
  previews PVs without moving the analyzed node; includes navigation, annotation,
  engine play and automatic evaluation coordination.
- [55_winrate_graph.js](https://github.com/rooklift/nibbler/blob/master/files/src/renderer/55_winrate_graph.js)
  maps graph clicks to nodes. main.js supplies native menus and shortcuts;
  43_chess960.js and PGN modules provide variant/tree handling.
- README documents full-game analysis, targeted searchmoves and a Stockfish
  maximum-strength configuration with MultiPV 1. Leela policy/visit statistics
  are engine-specific, not substitutes for Stockfish candidate scores.

## Reported problems and requests (not independently reproduced)

- [#273](https://github.com/rooklift/nibbler/issues/273): show all saved PGN
  continuations as arrows, rather than only one branch.
- [#274](https://github.com/rooklift/nibbler/issues/274): Stockfish automatic
  evaluation export omitted some moves. Attach completed scores to immutable
  position/node identities and export each completed value explicitly.
- [#289](https://github.com/rooklift/nibbler/issues/289): manual hash sizes.
  Adopt engine-advertised limits; the report's hardware measurements are not
  treated as independently verified performance advice.
- [#284](https://github.com/rooklift/nibbler/issues/284): annotations;
  [#279](https://github.com/rooklift/nibbler/issues/279): font customization;
  [#285](https://github.com/rooklift/nibbler/issues/285): keyboard tree navigation.
- [#294](https://github.com/rooklift/nibbler/issues/294): reported drag cursor
  problems with older Electron. Retaining native Qt avoids that Chromium path.
- [PR #302](https://github.com/rooklift/nibbler/pull/302) proposes restoring
  standard [%eval] data; [PR #300](https://github.com/rooklift/nibbler/pull/300)
  discusses clipboard merge and preservation of comments/NAGs; [PR #296](https://github.com/rooklift/nibbler/pull/296)
  discusses multiple Syzygy paths. A proposal is not evidence of released behavior.

## Design recommendations and architecture decision

Keep Qt/PySide6 rather than rebuild in Electron/React. The existing native
board, autosaves, move tree and tested Windows distribution already work.
Qt's asynchronous QProcess provides safe argument arrays, signals, lifecycle
supervision and UI-thread independence without a browser/IPC security surface.
This is a migration of the working app, not an additional competing prototype.

Stop custom-engine development. The desktop app must require an explicitly
selected external executable for analysis/play. Legacy engine source remains
for historical reproducibility, isolated from the new GUI analysis path.
Use python-chess for GUI rules/Chess960/PGN, with a small coordinate adapter
retaining the existing vector board. Its GPL-3.0-or-later terms apply to the
combined distributed application; retain license/source notices. No engine
binary, Nibbler assets or network service is bundled.

Priority: persistent UCI lifecycle and advertised options; Stockfish MultiPV,
actual WDL/bounds/mate scores; Smart Move with position identity and legal
validation; reversible PV hover/click/insert; annotated PGN round trips;
full-game review with position-associated results; workspace/command controls.
Do not display Leela-only statistics, invented WDL, confidence, Elo or speed
claims. Ryzen 9800X3D presets are conservative starting points, not benchmark
results: 2 threads/256 MB casual, 6/1024 balanced, 8/4096 maximum/MultiPV 1.
No Radeon GPU acceleration is claimed for conventional Stockfish.

Advanced comparison/snapshots, cache, shortcut editing, multiple tabs and rich
study organization are tracked separately. Controls are exposed only when wired.

## Implemented comparison at 0.5.0

| Workflow | Nocturne 0.5 | Qualification |
|---|---|---|
| One-click engine destinations | Smart Move, ranked chooser, selected-piece priority | Root/FEN and legal checks |
| Candidate PVs | Actual MultiPV cp/mate/bounds/WDL; hover, insert, pin, copy, focus | Single active external session |
| Continuous analysis | Persistent QProcess and newest-request queue | Requires supplied executable |
| Graph and full-line evaluation | Click/hover/zoom/pan; targeted played-move searches; PGN eval export | Estimated cp-loss thresholds, achieved depths retained |
| PGN studies | Tabs, nested variations, comments/NAGs, local autosaves | Rich collapse/search/delete/restore pending |
| Engine configuration | Reported options, named profiles, custom hash, CPU presets | Presets are not measured optima |
| Chess960 | Library rules, Shredder FEN and UCI option enforcement | Real-engine Chess960 verification pending |
| Usability additions | Manual setup, command palette, shortcut editor, board PNG export | Full arbitrary docking/piece choices pending |
| Engine-specific statistics | Reported Stockfish/UCI fields only | No invented Leela statistics |
| Comparison/cache/snapshots | Deferred | No nonfunctional controls exposed |

No claim is made that all Nibbler features are present or that this GUI increases
Stockfish's chess strength. Screenshots with the simulator are labelled test data.

0.5.3 keeps resource presets independent of MultiPV. Select PV 1 explicitly in
the Engine menu when evaluating that configuration; no preset claims an optimum.
