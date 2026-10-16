"""Offline Syzygy root probes. Tables are supplied by the user, never downloaded."""

from pathlib import Path
import os
import time

from ..core.board import SQUARES
from .search import SearchInfo, SearchResult

FAILED = 0xFFFFFFFF
MAGIC = {".rtbw": bytes.fromhex("71e8235d"), ".rtbz": bytes.fromhex("d7660ca5")}
WDL_NAMES = {-2: "Loss", -1: "Blessed loss (50-move draw)", 0: "Draw",
             1: "Cursed win (50-move draw)", 2: "Win"}


def probe(board, path, cancel=lambda: False):
    """Return diagnostic or exact root result, always from the side-to-move POV."""
    if not path:
        return {"status": "disabled", "message": "Syzygy: not configured"}
    count = sum(bool(board.cells[s]) for s in SQUARES)
    if count > 7:
        return {"status": "outside", "message": f"Syzygy: position has {count} pieces (maximum 7)"}
    if board.castling:
        return {"status": "unsupported", "message": "Syzygy: castling rights must be absent"}
    if board.outcome():
        return {"status": "terminal", "message": "Syzygy: position already has a rules result"}
    try:
        directories = [Path(p).expanduser() for p in path.split(os.pathsep) if p.strip()]
        if not directories or any(not p.is_dir() for p in directories):
            raise ValueError("Select a folder containing .rtbw / .rtbz files")
        files = []
        for directory in directories:
            for file in directory.iterdir():
                if cancel():
                    return {"status": "canceled", "message": "Syzygy: canceled"}
                if file.suffix.lower() not in MAGIC:
                    continue
                with file.open("rb") as stream:
                    magic = stream.read(4)
                if file.stat().st_size % 64 != 16 or magic != MAGIC[file.suffix.lower()]:
                    raise ValueError(f"Incomplete or invalid table: {file.name}")
                files.append(file)
        if not any(p.suffix.lower() == ".rtbw" for p in files):
            raise ValueError("No .rtbw WDL tables found in the selected folder")
        from . import _syzygy
        bitboards = [0] * 8
        # Native API order: white, black, kings, queens, rooks, bishops, knights, pawns.
        slots = {6: 2, 5: 3, 4: 4, 3: 5, 2: 6, 1: 7}
        for square in SQUARES:
            piece = board.cells[square]
            if piece:
                bit = 1 << ((square >> 4) * 8 + (square & 7))
                bitboards[0 if piece > 0 else 1] |= bit
                bitboards[slots[abs(piece)]] |= bit
        ep = ((board.ep >> 4) * 8 + (board.ep & 7)) if board.ep is not None else 0
        largest, wdl, result = _syzygy.probe(os.pathsep.join(map(str, directories)), *bitboards,
                                             board.halfmove, ep, board.turn == 1)
        if wdl == FAILED:
            return {"status": "missing", "message": f"Syzygy: tables not available for this position (loaded up to {largest} pieces)"}
        category = wdl - 2
        data = {"status": "wdl", "wdl": category, "largest": largest,
                "message": f"Syzygy WDL: {WDL_NAMES[category]} · side to move; DTZ unavailable"}
        if result != FAILED:
            start, end, promotion = (result >> 10) & 63, (result >> 4) & 63, (result >> 16) & 7
            def coordinate(s):
                return chr(97 + s % 8) + str(s // 8 + 1)
            text = coordinate(start) + coordinate(end) + {0: "", 1: "q", 2: "r", 3: "b", 4: "n"}[promotion]
            move = board.parse_uci(text)  # Our generator remains the legality authority.
            dtz = (result >> 20) & 4095
            dtz = -dtz if category < 0 else dtz
            data.update(status="hit", dtz=dtz, move=move.uci(),
                        message=f"Syzygy: {WDL_NAMES[category]} · DTZ {dtz} ply · side to move")
        elif board.halfmove:
            data["message"] += "; raw WDL does not account for the current halfmove clock"
        return data
    except ImportError:
        return {"status": "error", "message": "Syzygy reader not built; normal search remains available"}
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        return {"status": "error", "message": f"Syzygy unavailable: {exc}"}


def root_result(board, data, started=None):
    """Use DTZ only at the root; repetition/claim-sensitive cases stay in search."""
    if (data.get("status") != "hit" or board.outcome() or board.claimable_draws()
            or len(set(board.key_history)) != len(board.key_history)):
        return None
    move = board.parse_uci(data["move"])
    score = 20000 if data["wdl"] == 2 else -20000 if data["wdl"] == -2 else 0
    elapsed = time.perf_counter() - started if started is not None else 0
    return SearchResult(move, SearchInfo(0, 0, score, 0, elapsed, (move,), tbhits=1))
