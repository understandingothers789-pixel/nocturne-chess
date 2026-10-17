# Analysis GUI acceptance checklist

The uploaded 2026-10-17 specification is the direction. No custom-engine work.

- [x] Research Nibbler implementation, issues and proposals; document stack decision.
- [x] Persistent external UCI processes, handshake/stop/ready deadlines, diagnostics.
- [x] Multiple engine profiles, advertised option editor and hardware presets.
- [x] Direct Threads/Hash menus, custom values, per-profile persistence and ready acknowledgement.
- [x] MultiPV with actual scores, bounds, WDL, legal interactive PVs.
- [x] Smart Move: destination click, ranking, selected-piece priority, stale guard.
- [x] python-chess rules, standard/Chess960, annotations and PGN round trips.
- [x] Full-game external analysis, pause/resume/cancel, reliable evaluation export.
- [x] Graph navigation and resizable classic/analysis-left workspaces.
- [x] Command palette, shortcuts, position setup and image export.
- [x] Windows build, simulated UCI tests, GUI and visual validation.
- [ ] Real Stockfish 19/development, manual Windows/DPI and large Syzygy verification.
- [x] Multiple game tabs and drag-and-drop PGN import.
- [ ] Named multi-study collections.
- [ ] Rich tree collapse/search/bookmarks/delete/restore controls.
- [ ] Cache/snapshots, split-board comparison, independent secondary engine.
- [x] Graph zoom/pan and inline hover information.
- [ ] WDL graph, calibrated review and adaptive budgets.
- [ ] Piece-set choices, fully editable panel layout, shortcut import/export.

Unchecked items are not release claims. Keep this synchronized with executed work.
