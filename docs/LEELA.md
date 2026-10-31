# Leela WDL analysis

0.5.7.127 remains the last build before this optional integration.

Enable **Leela WDL** beside Maia to automatically download the latest stable
Lc0 Windows ONNX DirectML release, Microsoft's DirectML 1.15.4 runtime (the
version recommended by the current Lc0 package), and BT4-it332 network.
Downloaded engine/runtime licenses remain in the local leela setup folder.
The setup uses about 400 MB of downloads and requires an Internet connection.
DirectML supports AMD GPUs including the Radeon RX 9070 XT; actual performance
and driver compatibility must be checked on the user's computer.

Maia and Leela are mutually exclusive; both can be disabled. Stockfish remains
independent. Leela uses a separate process with a ten-second search budget by
default. Its results are debounced and cached for 128 position/matchup combinations.
Board navigation cancels obsolete work. The first network load may take time.

Black is the default fixed perspective at 2700 versus 2450 (250 Elo advantage).
These initial settings follow the Lc0 documentation's suggested example.
Details lets you switch to White, edit both ratings or the rating advantage,
and change the search time and GPU index. Changing perspective keeps the same
selected-side rating and gap, so the higher-rated color changes.
W/D/L is always for that selected color, even when the other side is to move.
These are model estimates, not measured human winning probabilities. Lc0 still
searches at full strength; rating calibration does not weaken its tactical search.

The implementation requests WDLCalibrationElo, Contempt, ContemptMode,
WDLEvalObjectivity=0 and WDLContemptAttenuation=1. The BT4 draw-rate reference
is 0.62. Numbered rods rank Leela candidates, not move-play probabilities;
all searched Leela candidates can have rods. They do not use Maia's 10% cutoff.
The upper W/D/L badges appear only for Stockfish moves that Lc0 has also searched.

GPU errors appear in the Leela panel. Use Retry setup for interrupted downloads;
use the GPU index control if DirectML picks another adapter. No silent CPU
fallback is used. The AMD hardware has not been available on the build runner.

Sources:
- https://github.com/LeelaChessZero/lc0/releases/latest
- https://lczero.org/play/networks/bestnets/
- https://lczero.org/play/configuration/flags/
- https://lczero.org/blog/2024/03/gm-matthew-sadler-on-wdl-contempt/
