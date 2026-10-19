# Recent commit review — 0.5.7.33

Reviewed the ten commits ending at `1c4dd36`, plus the nearby implementation
commits from which the run modes and settings migrations originated. This is a
targeted regression review, not a guarantee that every possible bug is absent.

## Scope

| Commit | Change | Review coverage |
| --- | --- | --- |
| `1c4dd36` | F11/F12 toggles and Engine menu | Physical key events, pause/resume, mode switching, repeat suppression |
| `30f0930` | 0.5.7.31 download link | Artifact link retained |
| `67c9fb2` | Graph and three node-limit menus | Viewport, zoom, clicks, presets, Unlimited, settings persistence |
| `e37e579` | 0.5.7.30 build receipt | Historical link retained |
| `7ee61fd` | Recorded move outside MultiPV | Destination priority, engine fallback, promotion, stale-position protection |
| `02bd56a` | Engine names and run-limit versioning | Package/runtime/Windows version consistency and limits |
| `7b95a48` | Full UCI name | Actual advertised Stockfish name and profile-name fallback |
| `1ff35c2` | Variation navigation and run modes | Left/Right, wheel, halted navigation, review's frozen line |
| `294611c` | Download links | Historical links retained; new version linked after artifact upload |
| `b8148a5` | Auto-evaluation menu coverage | Preset selection and independence of the three limits |

## Confirmed issues fixed

1. A normal node preset could be ignored while Continuous mode was selected.
   Node presets now choose a node-only search; Unlimited selects `go infinite`.
   Explicit time/depth limits remain a separate mode. The old default also had
   a hidden ten-minute limit, which node-only searches now avoid.
2. F12 saved MultiPV results but revisiting a position cleared the candidate
   display. Saved lines now reload without running or rewriting a search.
   Ordinary analysis also retains its MultiPV lines. Unanalysed positions clear
   the previous position's score and telemetry.
3. Actual Stockfish 19 can end a node-capped search with a bound at an unfinished
   depth. The 80 ms output throttle could discard the preceding exact result,
   causing F12 to pause. The transport now preserves that exact result, and
   review/auto-evaluation use its genuine completed depth. A search with only
   bounds still pauses; bounds are never relabelled as exact scores. Ordinary
   analysis also keeps every exact candidate when a later primary bound arrives,
   rather than shrinking its saved cache to a single PV.
4. F11 used the global game-pause flag. Self-play now has its own pause state,
   clears a previous targeted-move restriction, and F11/F12 ignore held-key
   repeat. Both shortcuts remain visible in Engine.
5. The main-line rewind correction covered wheel navigation but missed the Left
   key. Left/Right navigation now resumes the main line at a shared position.
6. Graph drawing used the cursor range while zoom/pan used the whole game.
   These operations now share one viewport. Future samples do not determine the
   visible vertical scale or attract clicks outside the displayed range.
   Switching between equal-length games resets the old viewport.
7. A nonnumeric saved preference-version value could raise a TypeError during
   startup. The migration now tolerates malformed version metadata.
8. Windows packaging repeated the full suite after CI had already run it. The
   Windows workflow now runs the suite once, then builds and smoke-tests the
   package. Artifact names come from the application version.

## Validation

The pre-fix baseline passed 203 tests with 11 optional/environment skips.
New regression cases reproduced the gaps above despite that passing baseline.
After the fixes, the local suite passed **217 tests (206 passed, 11 skipped)**
in 263.1 seconds, and Ruff passed. A final live-cache follow-up reproduced one
additional edge case, then passed three focused checks after its correction.
Local skips cover opt-in deep perft (2),
loopback networking blocked by the execution sandbox (6), and unavailable real
Syzygy fixtures (3). The final Windows run passed **218 tests (213 passed,
5 optional skips)**, Ruff, packaging, executable smoke checks and live database
API checks. The [build receipt](BUILDING.md) links the downloadable artifact and
records its source commit and checksum.

The additional real-engine check uses the official Stockfish 19 Linux binary,
not the protocol simulator. A 100,000-node analysis returned 100,083 reported
nodes (ordinary engine overshoot) with five PVs and did not play a move. F12
then evaluated all 21 positions of a ten-move Ruy Lopez PGN; all five saved PVs
restored at every position with analysis halted. Self-play paused/resumed at
the same position, and Unlimited sent `go infinite`. Stockfish is used only for
development validation and is not bundled with Nocturne. Protocol simulator
tests separately cover deterministic stale output, bounds, rapid key toggles,
and recovery. Live API checks validate transport availability, not historical
database coverage for every position.

## Five ideas — not implemented

1. Save an overnight-analysis queue and its progress so F12 can resume after an
   application restart, optionally skipping positions already analysed to budget.
2. Compare two saved engine snapshots at different node budgets, showing which
   candidate moves and evaluations changed.
3. Add named position bookmarks with a short note and one-click navigation.
4. Mark the point where a game leaves the opening database, with sample counts
   so rare moves can be distinguished from moves with no recorded games.
5. Offer a second, deeper review pass only for suspected mistakes and blunders,
   making it easier to confirm classifications without rerunning the whole game.
