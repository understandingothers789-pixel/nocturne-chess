"""Exact move-generation validation, independent of GUI and search."""

import argparse
import time

from nocturne.core.board import Board, START_FEN, divide, perft


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fen", default=START_FEN)
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--divide", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.depth <= 8:
        parser.error("Depth must be between zero and eight")
    board = Board(args.fen)
    started = time.perf_counter()
    if args.divide and args.depth:
        counts = divide(board, args.depth)
        for move, count in sorted(counts.items()):
            print(f"{move}: {count:,}")
        total = sum(counts.values())
    else:
        total = perft(board, args.depth)
    elapsed = time.perf_counter() - started
    print(f"depth {args.depth} · {total:,} nodes · {elapsed:.3f}s · {int(total / max(.001, elapsed)):,} nodes/sec")


if __name__ == "__main__":
    main()
