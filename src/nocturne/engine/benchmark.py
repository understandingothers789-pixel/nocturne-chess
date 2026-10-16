"""Reproducible fixed-position speed checks and limited self-play experiments."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import statistics
import sys

from .. import __version__
from ..core.board import Board, START_FEN
from ..core.game import Game
from .search import SearchLimits, Searcher

POSITIONS = {
    "start": START_FEN,
    "kiwipete": "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "rook_endgame": "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "promotion_tactics": "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
    "middlegame": "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10",
}
VARIANTS = {
    "default": {}, "no-tt": {"use_tt": False},
    "no-ordering": {"use_ordering": False, "use_killers": False},
    "no-killers": {"use_killers": False}, "pvs": {"use_pvs": True},
}


def metadata():
    cpu = platform.processor() or platform.machine()
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {"engine": f"Nocturne {__version__}", "utc": datetime.now(timezone.utc).isoformat(),
            "python": sys.version.split()[0], "platform": platform.platform(), "cpu": cpu,
            "note": "Single process/thread. Wall-clock speed is environment-specific; no Elo inference."}


def benchmark(depth=3, seconds=10.0, repeat=3, variants=("default",)) -> dict:
    report = {"metadata": metadata(), "depth": depth, "time_cap_seconds": seconds,
              "repeats": repeat, "positions": POSITIONS, "results": []}
    for name, fen in POSITIONS.items():
        for variant in variants:
            runs = []
            for _ in range(repeat):
                result = Searcher(SearchLimits(depth=depth, seconds=seconds, **VARIANTS[variant])).search(Board(fen))
                info = result.info
                runs.append({"depth": info.depth, "nodes": info.nodes, "seconds": info.seconds,
                             "nps": info.nps, "score_cp": info.score,
                             "bestmove": result.best_move.uci() if result.best_move else None,
                             "pv": [m.uci() for m in info.pv], "hashfull": info.hashfull,
                             "stopped": result.stopped})
            report["results"].append({"position": name, "variant": variant, "runs": runs,
                                      "median_seconds": statistics.median(r["seconds"] for r in runs),
                                      "median_nps": statistics.median(r["nps"] for r in runs)})
    return report


def match(games=2, seconds=.05, max_plies=100, variant_a="default", variant_b="pvs") -> dict:
    """Alternate colors; retain unfinished games instead of invented adjudication."""
    report = {"metadata": metadata(), "variants": [variant_a, variant_b], "seconds_per_move": seconds,
              "max_plies": max_plies, "games": [], "a_wins": 0, "b_wins": 0, "draws": 0, "unfinished": 0}
    for index in range(games):
        game = Game()
        colors = {1: variant_a, -1: variant_b} if index % 2 == 0 else {1: variant_b, -1: variant_a}
        game.headers.update({"White": colors[1], "Black": colors[-1], "Event": "Nocturne reproducible experiment"})
        for _ in range(max_plies):
            if game.outcome:
                break
            variant = colors[game.board.turn]
            result = Searcher(SearchLimits(depth=8, seconds=seconds, **VARIANTS[variant])).search(game.board)
            if result.claim_draw:
                game.claim_draw()
                break
            if result.best_move is None:
                break
            game.play(result.best_move)
        outcome = game.outcome
        if not outcome:
            report["unfinished"] += 1
        elif outcome.winner is None:
            report["draws"] += 1
        elif colors[outcome.winner] == variant_a:
            report["a_wins"] += 1
        else:
            report["b_wins"] += 1
        report["games"].append({"result": outcome.result if outcome else "*",
                                 "reason": outcome.reason if outcome else "Ply cap; unadjudicated",
                                 "plies": game.cursor, "pgn": game.pgn()})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=["default"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--match", action="store_true")
    parser.add_argument("--games", type=int, default=2)
    parser.add_argument("--plies", type=int, default=100)
    args = parser.parse_args(argv)
    if not 1 <= args.repeat <= 100 or not 1 <= args.games <= 1000 or not 1 <= args.plies <= 2000:
        parser.error("Repeat, game or ply count out of range")
    report = match(args.games, args.seconds, args.plies, args.variants[0], args.variants[-1]) if args.match else benchmark(
        args.depth, args.seconds, args.repeat, args.variants)
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"Recorded {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
