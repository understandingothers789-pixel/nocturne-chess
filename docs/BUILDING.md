# Windows 11 desktop builds · 0.5.7.36

## [0.5.7.36 — Download Windows ZIP](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39296780043/artifacts/12209442411)

Extract All, then open **Nocturne/Nocturne.exe**. The executable is unsigned.

Source commit [`5ea7d0f`](https://github.com/understandingothers789-pixel/nocturne-chess/commit/5ea7d0f)
includes automatic Masters coverage with authenticated statistics enabled, a gold
and underlined out-of-book PGN move, and a hover tooltip. The highlight remains
visible on the selected move. Disabling statistics or clearing the session token
removes it; changing lines resets coverage. Errors never stand in for zero games.
Entering a token restarts coverage if it previously stopped before authentication.

Windows run [39296780043](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39296780043)
passed lint, the full test suite, packaging, packaged smoke checks and the live
database check. Locally, four focused coverage/GUI checks passed, as did the
version-resource consistency check after synchronizing the Windows metadata.

Artifact **12209442411**, `Nocturne-0.5.7.36-Windows-x64-unsigned`,
57,963,210 bytes, expires 2026-11-18. GitHub artifact SHA-256:
`6152674761c8c051e3a437493cc9fd3f315bd02d7dfec6395adcea4bbc713130`.

## [0.5.7.35 — Download Windows ZIP](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39211281773/artifacts/12168345473)

Extract All, then open **Nocturne/Nocturne.exe**. The executable is unsigned.

Source commit [`0c2c481`](https://github.com/understandingothers789-pixel/nocturne-chess/commit/0c2c481e80c9525af9c6ec01b9e45e225708f09e)
adds paused analysis restoration, durable F12 progress, optional 1/2/5 node
checkpoints and a side-by-side comparison window. Snapshot capture is off by
default in **Dev → Save analysis snapshots at node milestones**; view them using
**Dev → Compare saved analysis snapshots…**. Checkpoints live in the local SQLite
library, separately from the game payload. Their keys include the PGN and full
move history, so variation renumbering and unrelated positions do not mix records.
See the [changelog](../CHANGELOG.md) for retention and resume behavior.

Windows run [39211281773](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39211281773)
passed Ruff, **229 tests (224 passed / 5 optional skips)** in 234.436 seconds,
PyInstaller packaging, packaged GUI/UCI smoke checks and the live Masters,
Lichess players and ChessDB API checks. CI ran the full suite once; packaging
did not repeat it. The optional skips are deep perft (2) and unavailable real
Syzygy fixtures (3).

Five focused local tests cover immutable scoped snapshots, 1/2/5 milestones
through 50 billion nodes, comparison controls, closed/reopened analysis staying
paused, fresh Analyze clearing only the current position, and F12 resuming its
unfinished position without rewriting completed positions. Three existing
engine/cache/toggle regressions also passed. A separate real Stockfish 19 check
captured all five PVs at the 1M, 2M and 5M targets, actually reported at
1,053,646, 2,803,866 and 5,000,559 nodes. The comparison showed each PV's actual
depth and bounds; the results restored paused after reopening. This check did
not bundle Stockfish with the app or claim exact node counts at each target.

Artifact **12168345473**, `Nocturne-0.5.7.35-Windows-x64-unsigned`,
57,961,836 bytes, expires 2026-11-18. GitHub artifact SHA-256:
`b02984bb408732326d45b734e1feeca61d5e9ac1ebbd470becc5a233b166a7f9`.

# Windows 11 desktop builds · 0.5.7.34

## [0.5.7.34 — Download Windows ZIP](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39209125609/artifacts/12166893141)

Extract All, then open **Nocturne/Nocturne.exe**. The executable is unsigned.

Source commit [`22336bb`](https://github.com/understandingothers789-pixel/nocturne-chess/commit/22336bbb229fc49e5e848159a773cc38297903cd)
adds partial MultiPV persistence, deeper confirmation of suspected mistakes and
blunders, named position bookmarks with notes, and a cancellable opening-database
coverage scan. The [changelog](../CHANGELOG.md) lists the menu locations and
budgets. Ideas 1 and 2 remain proposals; ideas 3, 4 and 5 are implemented.

Windows run [39209125609](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39209125609)
passed Ruff, **224 tests (219 passed / 5 optional skips)** in 276.850 seconds,
PyInstaller packaging, packaged GUI/UCI smoke checks and the live Masters,
Lichess players and ChessDB API checks. The full suite ran once in CI and was
not repeated by the packaging script. The optional skips are deep perft (2)
and unavailable real Syzygy fixtures (3).

Focused local checks covered mixed-depth and bound-result persistence, bookmark
storage/navigation after variation deletion, deeper review changing a provisional
Blunder to Excellent, and database zero-count/error distinctions. An additional
check with official Stockfish 19 saved and restored all five PVs at three
positions. Its root depths were **11, 11, 10, 10, 10**; subsequent positions
included saved bounds. The 100,000-node normal search reported **100,083 nodes**,
unchanged normal overshoot. F11 pause/resume and Unlimited also passed. Stockfish
is a development check only and is not bundled with the application.

Artifact **12166893141**, `Nocturne-0.5.7.34-Windows-x64-unsigned`,
57,940,392 bytes, expires 2026-11-18. GitHub artifact SHA-256:
`5489fdf301466b4e5ae7d7c5c4a9ab1aa6540b642db398ed2e1913b7b69798ce`.

# Windows 11 desktop builds · 0.5.7.33

## [0.5.7.33 — Download Windows ZIP](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39207032446/artifacts/12165844502)

Extract All, then open **Nocturne/Nocturne.exe**. The executable is unsigned.

Source commit [`dc64bd3`](https://github.com/understandingothers789-pixel/nocturne-chess/commit/dc64bd392f978ec07c09271e0d66db5a51f7b630)
includes the recent-change review fixes and the F11/F12 toggles introduced in
0.5.7.32. The [review report](RECENT_COMMIT_REVIEW.md) describes the confirmed
bugs, regression coverage and five improvement ideas.

Windows run [39207032446](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39207032446)
passed Ruff, **218 tests (213 passed / 5 optional skips)** in 311.1 seconds,
PyInstaller packaging, packaged GUI/UCI smoke checks and the live Masters,
Lichess players and ChessDB API checks. The skips are opt-in deep perft (2)
and unavailable real Syzygy fixtures (3). CI runs the suite once, then packages
and smoke-tests the app without repeating the suite.

Local validation passed 217 tests (206 passed / 11 skips), followed by three
focused checks for the final live-cache fix. A separate check using official
Stockfish 19 evaluated 21 positions with five PVs each and verified cached
restoration, node-only analysis, Unlimited and self-play pause/resume.

Artifact **12165844502**, `Nocturne-0.5.7.33-Windows-x64-unsigned`,
57,926,081 bytes, expires 2026-11-18. GitHub artifact SHA-256:
`112664790035e55521045e2a76baf30abd5c9f0789581d581f74bbd172f73e98`.

# Windows 11 desktop builds · 0.5.7.30

## [Download Windows 0.5.7.30](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39196589327/artifacts/12161284918)

[Download the Windows ZIP](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39196589327/artifacts/12161284918).
Extract All, then open **Nocturne/Nocturne.exe**. The executable is unsigned.

This release can play the recorded game move by destination even when it falls
outside the selected MultiPV. It also shows the full engine name reported by
UCI and includes F11 self-play, F12 line evaluation and the updated node limits.
Ordinary navigation back to a shared main-line position resumes the main line;
game review continues to preserve its selected variation.

Windows run [39196589327](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39196589327)
passed lint, all 200 tests, packaged build and smoke checks, and the live
database API check. Artifact **12161284918**, `Nocturne-0.5.7.30-Windows-x64-unsigned`,
57,911,876 bytes, expires 2026-11-18. SHA-256:
`1fcf142c0174ac4e950832da5aae67c3f9fbfcdff72c12e78a68b74f93125316`.

# Windows 11 desktop builds · 0.5.7.28

## [Download Windows 0.5.7.28](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39191809527/artifacts/12159804179)

[Download the Windows ZIP](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39191809527/artifacts/12159804179).
Extract All, then open **Nocturne/Nocturne.exe**. The executable is unsigned.

The global expand-all option defaults off and resets older saved values once.
Both expand-all and cursor-preview controls are in the Engine menu.

Windows run [39191809527](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39191809527)
passed lint, the full test suite, packaged build and smoke checks, and the live
database API check. Artifact **12159804179**, `Nocturne-0.5.7.28-Windows-x64-unsigned`,
57,908,768 bytes, expires 2026-11-18. SHA-256:
`37ddca0a0a0a6ee65621f596e1655fd67c77a181e8914a3df4ee3c67f41e120f`.

# Windows 11 desktop builds · 0.5.7.27

## Download Windows 0.5.7.27

Build pending.

The persisted global expand-all override is removed. Compact MultiPV rows now
stay at three move rows for up to four candidates and two rows for five or more;
per-candidate arrows still expand one selected variation.

# Windows 11 desktop builds · 0.5.7.26

## Download Windows 0.5.7.26

[Download the Windows ZIP](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39188713970/artifacts/12158309732).
Extract All, then open **Nocturne/Nocturne.exe**. The executable is unsigned.

Evaluation now appears before depth in top engine telemetry, and compact
MultiPV candidates keep their three-row slots stable for up to four lines.
Feature commit [`6de684f`](https://github.com/understandingothers789-pixel/nocturne-chess/commit/6de684f59e5316fc5d3d67180294d91582e66602).
Windows run [39188713970](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39188713970)
passed **192 tests (187 passed / 5 optional skips)**, Ruff, PyInstaller,
packaged launch checks and the live database API check. Local validation passed
**181 tests with 11 skips** and Ruff.

Artifact **12158309732**, `Nocturne-0.5.7.26-Windows-x64-unsigned`,
57,902,068 bytes, expires 2026-11-18. SHA-256:
`94cfa100a1f806f4781716aa95d5efe28529ec2ad424680e110445f77c35cc90`.

# Windows 11 desktop builds · 0.5.7.25

## Download Windows 0.5.7.25

[Download the Windows ZIP](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39186772633/artifacts/12158418237).
Extract All, then open **Nocturne/Nocturne.exe**. The executable is unsigned.

Feature commit `eeaa0a62f1bbc1ec763aa87c7a8f9dcc385f67dd` hides selective depth
by default and adds the **Display → Show selective depth (seldepth)** setting
for candidate headers and top telemetry. Depth, node count, and nodes per second
are slightly larger with a restrained blue accent. Windows run
[39186772633](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39186772633)
passed **191 tests (186 passed / 5 optional skips)** in 202.159 seconds, Ruff,
PyInstaller and packaged launch checks.

Artifact **12158418237**, `Nocturne-0.5.7.25-Windows-x64-unsigned`,
57,898,979 bytes, expires 2026-11-18. SHA-256:
`57aa87ec59554d28d5d89144c491adce7ee81751e844e3478d02a346497dfd01`.

# Windows 11 desktop builds · 0.5.7.24

## Download Windows 0.5.7.24

[Download the Windows ZIP](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39185429686/artifacts/12157744055).
Extract All, then open **Nocturne/Nocturne.exe**. The executable is unsigned.

Feature commit `3464e0f73cf808ee626b8b01bdf6d2543eb81e01` keeps candidate wheel
previews on their selected ply during pointer motion within the same move.
Moving to a different move resumes hover preview. Windows run
[39185429686](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39185429686)
passed **189 tests (184 passed / 5 optional skips)** in 193.775 seconds, Ruff,
PyInstaller and packaged launch checks.

Artifact **12157744055**, `Nocturne-0.5.7.24-Windows-x64-unsigned`,
57,898,467 bytes, expires 2026-11-18. SHA-256:
`e8fcf3f0e591e4cc8f8d0cfddc6788ab2dd99d0ec9b48f98a310107e6b35dd77`.

# Windows 11 desktop builds · 0.5.7.23

## Download Windows 0.5.7.23

[Download the Windows ZIP](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39184268239/artifacts/12157563087).
Extract All, then open **Nocturne/Nocturne.exe**. The executable is unsigned.

Feature commit `49662cc173a44db64841491c3ba5c854c4dedd0a` selects three compact
move rows for one to four MultiPV candidates, and two rows for five or more.
Each candidate's arrow still expands only that line to the complete engine PV.
Windows run [39184268239](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39184268239)
passed **188 tests (183 passed / 5 optional skips)** in 215.955 seconds, Ruff,
PyInstaller and packaged launch checks. The optional API check confirmed
ChessDB returned 29 legal moves; authenticated Lichess data requires a user
access token.

Artifact **12157563087**, `Nocturne-0.5.7.23-Windows-x64-unsigned`,
57,897,215 bytes, expires 2026-11-18. SHA-256:
`0dc3dc3b4bae7b402b8cae4d7c49a56f35b74bf1c36961e97f70541777804745`.

# Windows 11 desktop builds · 0.5.7.22

## Download Windows 0.5.7.22

[Download the Windows ZIP](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39182767872/artifacts/12157436125).
Extract All, then open **Nocturne/Nocturne.exe**. The executable is unsigned.

Feature commit `750d647d4e4d0c677927a7b64292dd4f67dced73` keeps the selected
wheel-preview ply stable during updates to the same candidate root move and
resets the preview when that rank gets a different root move. Windows run
[39182767872](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39182767872)
passed **187 tests (182 passed / 5 optional skips)** in 206.268 seconds, Ruff,
PyInstaller and both packaged launch checks. The optional live database check
completed; ChessDB returned 29 legal moves.

Artifact **12157436125**, `Nocturne-0.5.7.22-Windows-x64-unsigned`,
57,897,291 bytes, expires 2026-11-17. SHA-256:
`6e74edc20d2fbaac06be9f6ae7c50ec82741ef29004214af0804934d02a44bf1`.

## Download Windows 0.5.7.21

[Download the Windows ZIP](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39165248055/artifacts/12150402048).
Extract All, then open **Nocturne/Nocturne.exe**. The executable is unsigned.

Feature commit `fbdccac4817f61fc1ba694c93d667d4cb08ab08d` adds two-row MultiPV
with independent per-candidate expansion. Follow-up commit
`d1c1b019ec931a0559a10b1e6016d6b246d146c7` passes database loading, empty-result
and service-error status to the candidate footer. Windows run
[39165248055](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39165248055)
passed **186 tests (181 passed / 5 optional skips)** in 205.575 seconds, Ruff,
PyInstaller and packaged launch checks. The optional live database check also
completed; ChessDB returned 29 legal moves.

Artifact **12150402048**, `Nocturne-0.5.7.21-Windows-x64-unsigned`,
57,894,483 bytes, expires 2026-11-17. SHA-256:
`87f3dae9f32423bda6c92aeb89fd436e9f46c732316f272517c580c99ea79212`.

# Download Windows 0.5.7.20

[Download the Windows ZIP](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39161047849/artifacts/12149276470).
Extract All, then open **Nocturne/Nocturne.exe**. The executable is unsigned.

Feature commit `4e4b04456ca108547e774b1e0c3c0127370bb854`, run
**39161047849**, job **117774243507**, succeeded. The native suite passed with
**184 tests (179 passed / 5 optional skips)**; Ruff, PyInstaller and packaged
launch checks passed. The source ZIP is included in the artifact.

Artifact **12149276470**, `Nocturne-0.5.7.20-Windows-x64-unsigned`,
57,888,497 bytes, expires 2026-11-17. SHA-256:
`91a6a0683a862a652a647668b3b435813c3baf6e1eeb685c4340f165613d9cc1`.
The optional live API check reported that authenticated Lichess Masters and
Players results require a user access token; ChessDB returned 29 legal moves.

Tested source `6339a03daf29939c69628164449bc26616ea6489`, run **39110217241**,
job **117624541482** succeeded. Both native suites: **184 tests, 179 passed /
5 optional skips**, in 142.631s and 148.320s. Ruff passed twice; PyInstaller and
both frozen launch gates passed. Hidden lookup/navigation, API headers, cursor
snapshot/wheel/click, high-DPI vector rendering and real HTTP pacing regressions
passed twice. The packaged executable verifies collected SVGs and cursor boards
as well as offline data and external-UCI/Game Review completion.

Artifact **12130256462**: 57,794,796 bytes, expires 2026-11-17. SHA-256:
`c4473d4d59285be889e6cdf7d2707ba37e5ed6b9c0d268f0dfc279123b57abeb`.
Lichess live checks reported the expected access-token requirement; ChessDB
returned 29 validated legal moves. Fixture statistics remain labelled test data.
Only documentation changed after the tested source commit. No new launcher or
security-policy change was introduced. The artifact remains an unsigned build.

Feature commits are labelled 0.5.7.16 (database), 0.5.7.17 (cursor preview),
0.5.7.18 (Nibbler SVG pieces) and 0.5.7.19 (Cburnett/vector registry). The
newest cumulative build validates the full application.

## Previous verified download · 0.5.7.15

[Download Windows 0.5.7.15](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39107769865/artifacts/12129033459). Extract All and open **Nocturne/Nocturne.exe**.
Includes exact Nibbler PNGs, blue evaluation/API metrics, 10% palette-relative
last-move shading, dotted ±1-pawn compressed graph and compact move spacing.
Production Game Review has no total 10/20-second cap.

Source `4ff370ea4b2d0961e8ee4b6f4903faaeb165331d`, run 39107769865/job
117617227322 succeeded. Both native suites: **178 tests, 173 passed / 5 optional
skips**, in 159.879s and 157.084s. Ruff passed twice. PyInstaller, offline frozen
launch and external-UCI/Game Review frozen checks passed. The real HTTP pacing,
early-callback, native-DPI spacing and review completion regressions passed twice.
Artifact 12129033459: 57,235,802 bytes, retained until 2026-11-17. SHA-256:
`57079d9db689df64a1313734d25fe6fd8a556a954e7532285dfce940351eb05a`.
Only documentation changed after the tested application commit. Earlier failed
builds were not uploaded.

0.5.7.14 introduced compact move spacing,
dotted ±1-pawn graph guides, exact Nibbler pieces, blue metrics and 10% shading.
Graph and spacing have separate version-labelled commits.

0.5.7.12 introduced the exact Nibbler PNG set
as default, blue metrics and 10% square shading. The spec recursively includes
all artwork and licenses; package data also covers PNGs and editable SVG sources.

0.5.7.11 introduced blue analysis/API metrics, neutral depth and 10% move shading.
Its native run passed twice (167 passed/5 optional skips per run). Later cumulative
versions contain those changes; see the newest download above.

[Download Windows 0.5.7.10](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39101008893/artifacts/12126636588). Extract All and open **Nocturne/Nocturne.exe**.
Softer distinct move colors, quieter palette-relative board highlights, and
independent game/PV wheel options. Source `2f68a331f6f213ac03b5e9cdf33b11929518aa26`
passed run 39101008893/job 117597097215: both full native runs **169 tests,
164 passed / 5 optional skips**, in 131.223s and 128.822s. Ruff passed twice;
PyInstaller and both gated packaged launch checks passed. Artifact 12126636588:
55,885,463 bytes, expires 2026-11-17. SHA-256:
`552dd4f800ff646ee850a4597666b6d2bdebd4b2396c6a86bcebf504493a75c7`.
Only documentation changed after this verified application build.

The prior verified downloads remain below.

[Download Windows 0.5.7.9](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39100427444/artifacts/12126700388). Extract All and open **Nocturne/Nocturne.exe**.
This build adds equal-width padded SAN targets and Dev → Expand analysis beyond
three rows. Source `439b2dc0ccf6a1c97f7e1dbbb32fa2d5b351859d` passed run
39100427444/job 117595398583: both native suites ran 165 tests, **160 passed /
5 optional skips**, in 74.675s and 82.054s. Ruff passed twice, PyInstaller and
both frozen launch checks passed. Artifact 12126700388: 55,631,228 bytes,
retained until 2026-11-17. SHA-256:
`5d5ed7b16311c46faae08e2e92afe923a29e481a780c51bd356c38e9fed1c3d0`.
Only documentation changed after this tested application commit.

[Previous Windows 0.5.7.8 download](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39099441736/artifacts/12124934909).
This version removes analysis-panel badges/rank colors and softens White/Black
text tints, preserving the approved board renderer exactly. Source commit
6e12832ff813f74c4946d0cb018e04e6c698fbf8 passed Windows run 39099441736/job
117592505281: 163 tests twice, 158 passed/5 optional skips each, in 134.600s and
137.800s. Ruff passed twice; packaging and both frozen launch checks passed.
Artifact 12124934909 is 55,392,327 bytes, retained until 2026-11-17. SHA-256:
`0ca9a00c0e5470b6f068bfcefb9ce3a7114352d3e7df523a935e9b7bd0501ba7`.

## Earlier fallback builds

Three cumulative feature commits have separate Windows artifacts:

1. [0.5.7.5: live Studio previews](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39097285528/artifacts/12125655113).
2. [0.5.7.6: previews and MultiPV circles/colors](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39097588959/artifacts/12125422408).
3. [0.5.7.7: all above plus clean Game Moves/raw PGN](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39098023371/artifacts/12125303892).

Select the matching versioned artifact after the workflow succeeds. The 0.5.7.5
run passed both 160-test Windows runs (155 passed/5 skipped each), and 0.5.7.6
passed both 162-test runs (157 passed/5 skipped each). Both passed packaged launch
checks. The last run passed 163 tests twice (158 passed/5 optional skips each),
Ruff and both frozen launch checks for source 9236c785e9cded1ea7b39e3f2693ac9077ce6db4.
Final run 39098023371/job 117588388622 took 113.465s / 128.494s for the suites.
Artifact 12125303892 is 55,156,789 bytes; SHA-256:
`221126c71b044e1b8f5f946af5e1aaf41bf902127db7e83c2d25e58b64644ba0`.
The existing unsigned packaging/build tools are retained for all three downloads;
Windows Smart App Control acceptance cannot be established by CI.

## Previously verified baseline

[Download the tested, unsigned **Nocturne-0.5.7.4 Windows ZIP**](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39096484337/artifacts/12125455189).
Sign into GitHub, download, Extract All, then open **Nocturne/Nocturne.exe**.
Keep the full folder. No Python, compiler or batch launcher is needed to play/analyze.
You select your own Stockfish executable from the Engine menu.

The previous 0.5.7.4 Windows run 39096484337 succeeded for source commit
d020afff00f871f23ccea7c390f27865bf85b964. Both native runs passed 154 tests with
5 optional skips (83.309s / 92.496s). Ruff passed twice. PyInstaller and both
packaged smoke checks passed, including external-UCI review. The artifact is
54,697,193 bytes, retained until 2026-11-17. SHA-256:
`8d4a33a54066c972c0f1dc71b1ac83e55ad74781b27771d5d4c7a7d57de4ca66`.

Live authenticated Lichess data requires a user session token. Separate live
connectivity checks distinguish protected responses from actual returned data;
a green workflow alone is not evidence of successful API data retrieval.
The current build also queried live ChessDB successfully (29 legal moves);
Lichess reported its authentication requirement. No desktop application code
changed after the passing build.

## Appearance, clocks and Windows trust status

0.5.7.3 adds neutral charcoal/light styling, Classic brown/cream and Grey boards,
a one-time legacy-default migration, and saved Display → Clocks visibility.
The working Cburnett pieces, three-line PV slots, UCI/rules/game model, build
script/specification and dependencies are retained. Timed Play clocks continue
when hidden; Analysis pauses them and untimed games show infinity. Configure a
time control in File → New game in a playing mode. 0.5.7.4 reads standard PGN
`[%clk]` annotations and shows the last recorded time for each side at the selected
mainline or variation position. Missing values use an em dash; annotations remain
read-only and do not create a running clock. See the workflow result for current
native Windows validation evidence.

[Working Windows 0.5.7.3 download](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/39095336406/artifacts/12124810527) remains available as a fallback.
These are unsigned test builds. The user confirms 0.5.7.2 runs on their computer;
acceptance of the new executable on that setup is unverified here. No signing,
certificate, launcher or security-policy change is included. Manual Windows DPI
and narrow Play-sidebar layout checks remain open; see TODO/PROGRESS.

## Reproducible Windows build

Install Python 3.12 x64 with its Python launcher. In a source checkout:

```text
py -3.12 scripts/build_windows.py --build-only
```

The Python build creates `.venv-build`, installs pinned runtime/build/validation
dependencies, installs the project, runs Ruff and full unittest discovery,
renders the icon, runs PyInstaller and launches the packaged app for smoke checks.
A second smoke connects the packaged GUI, completes a two-move Game Review and
checks full accuracy coverage using the development-only protocol fixture
using the build environment's Python. Neither that interpreter nor the fixture
is a bundled chess engine. A failing check stops the build. The source ZIP includes
the installed python-chess Python source and notices.

Outputs:

- `dist/Nocturne/Nocturne.exe`: windowed native GUI plus `_internal` shared libraries.
- `dist/Nocturne-0.5.7.15-source.zip`: source, tests, documentation, rules-library source.

No C compiler is required for the new external-only GUI. The prior custom UCI
executable/native table reader are not part of this distribution. Source installation
also supports `python -m nocturne` after installing runtime requirements.

Build dependencies need network access once unless a matching wheelhouse is prepared.
The application uses local data and local UCI processes during normal operation.
No Stockfish executable or table file is downloaded by the application/build.

## CI and release status

The checked-in Windows workflow performs validation, builds the actual Windows
executable, runs the packaged smoke checks and uploads the portable directory plus
source archive for 30 days. Creating a workflow file is not evidence it ran: actual
run IDs/results are recorded in PROGRESS.md and the README download link.
Unsigned test builds are explicitly authorized for this project; they may trigger
Windows publisher/reputation prompts. No bypass or Windows policy change is supplied.

For a separately signed release, sign the native files using your legitimate
certificate, then run the Python builder's `--package-signed --signtool PATH` mode.
It verifies signatures with the Windows SDK before making a signed-release ZIP.
Signing credentials/certificates are not bundled. Never copy the EXE alone.

## Linux development checks

```sh
QT_QPA_PLATFORM=offscreen python -m pytest -q
python -m ruff check src tests scripts
QT_QPA_PLATFORM=offscreen python scripts/capture_preview.py --simulate
```

`--simulate` explicitly labels screenshots as UCI transport test data, not measured
Stockfish analysis. `--engine /path/to/engine` uses a supplied actual engine instead.
The Linux environment cannot produce a Windows executable; native Windows CI does.

### Standalone database connectivity check

Run `python scripts/check_explorer_api.py` from a source install, or use the
manual **Live database connectivity** workflow. It queries one fixed opening
position, reports Lichess authentication requirements without a user token, and
checks ChessDB independently. It never accepts or logs tokens.

Connectivity-only run 39065979799/job 117493627053 passed on Windows for
3a53f9c601a1aec57f754ffcc45007c1882c31de. Masters/player endpoints returned
authentication-required responses; no authenticated data claim is made. ChessDB
returned valid JSON containing 29 locally validated legal moves for 1.e4 e5.
The UTF-8 diagnostic completed without callback errors.
