# Basic fixes and deferred redesign

Version 0.5.7.50 restores the interface from 0.5.7.47 and retains only the
engine reliability changes from the larger 0.5.7.48/49 release:

- Normal / F12 / F11 defaults: 1 billion / 200 million / 10 million nodes.
- Independent limit menus, persistence and a reset action in each menu.
- Live F12 output from the selected position through the remaining line.
- Pause/resume, deliberate navigation cancellation and stale-result guards.
- Self-play discovery and global telemetry fixes.

The original layout, candidate expansion controls and existing database
integration remain. The compact single-row candidates, side move tree, new
settings gear, animated evaluation bar and expanded player/database filters
are deferred. Their complete implementation is preserved on
`deferred/lichess-redesign-0.5.7.49`, based on
[`39a0fa2`](https://github.com/understandingothers789-pixel/nocturne-chess/commit/39a0fa2).
Published history is retained; no force push is needed to revisit that work.

The Windows workflow still produces an unsigned executable. The reported
“Windows protected your PC / unknown publisher” prompt is SmartScreen's
publisher/reputation warning. Splitting the features does not supply a trusted
publisher signature. The repository's signed-release packaging mode requires
a legitimate signing certificate; no certificate is included in the project.
