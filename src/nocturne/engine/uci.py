"""Standard UCI entry point. No Qt import and no external engine dependency."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import replace

from .. import __version__
from ..core.board import Board
from .search import MATE, MATE_THRESHOLD, SearchInfo, SearchLimits, Searcher
from .tablebase import probe, root_result


def uci_info(info: SearchInfo) -> str:
    score = f"cp {info.score}"
    if abs(info.score) > MATE_THRESHOLD:
        distance = (MATE - abs(info.score) + 1) // 2
        score = f"mate {distance if info.score > 0 else -distance}"
    pv = " ".join(m.uci() for m in info.pv)
    return (f"info depth {info.depth} seldepth {info.seldepth} score {score} nodes {info.nodes} "
            f"nps {info.nps} time {int(info.seconds * 1000)} hashfull {info.hashfull} tbhits {info.tbhits} pv {pv}")


class UciSession:
    def __init__(self, output=None):
        self.board = Board()
        self.hash_mb = 32
        self.syzygy_path = ""
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._write_lock = threading.Lock()
        self.output = output or sys.stdout

    def send(self, line):
        with self._write_lock:
            self.output.write(line + "\n")
            self.output.flush()

    def stop(self):
        self._cancel.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def position(self, args: list[str]):
        self.stop()
        if not args:
            raise ValueError("position needs startpos or fen")
        if args[0] == "startpos":
            board, offset = Board(), 1
        elif args[0] == "fen" and len(args) >= 7:
            board, offset = Board(" ".join(args[1:7])), 7
        else:
            raise ValueError("Invalid position command")
        if len(args) > offset:
            if args[offset] != "moves":
                raise ValueError("Expected moves")
            for move in args[offset + 1:]:
                board.play_uci(move)
        self.board = board

    def go(self, args: list[str]):
        self.stop()
        values = {}
        i = 0
        while i < len(args):
            name = args[i]
            if name in ("depth", "movetime", "wtime", "btime", "winc", "binc", "movestogo", "nodes"):
                if i + 1 == len(args):
                    raise ValueError(f"Missing {name} value")
                values[name] = max(0, int(args[i + 1]))
                i += 2
            elif name == "infinite":
                values[name] = True
                i += 1
            else:
                raise ValueError(f"Unsupported go parameter: {name}")
        depth = min(64, max(1, values.get("depth", 64)))
        if "movetime" in values:
            seconds = max(.001, values["movetime"] / 1000)
        elif "infinite" in values or ("depth" in values and not any(k in values for k in ("wtime", "btime"))):
            seconds = 86400.0
        elif "wtime" in values or "btime" in values:
            prefix = "w" if self.board.turn == 1 else "b"
            available = values.get(prefix + "time", 1000) / 1000
            increment = values.get(prefix + "inc", 0) / 1000
            allocation = available / max(1, values.get("movestogo", 30)) + increment * .7
            seconds = max(.001, min(allocation, available - .05))
        else:
            seconds = 1.0
        limits = SearchLimits(depth=depth, seconds=seconds, nodes=values.get("nodes") or None, hash_mb=self.hash_mb)
        board = self.board.copy()
        self._cancel = threading.Event()
        cancel = self._cancel
        path = self.syzygy_path

        def run():
            try:
                started = time.perf_counter()
                tb = probe(board, path, cancel.is_set)
                if path:
                    self.send("info string " + tb["message"])
                result = root_result(board, tb, started)
                if result is None:
                    remaining = max(.001, limits.seconds - (time.perf_counter() - started))
                    result = Searcher(replace(limits, seconds=remaining), cancel.is_set).search(
                        board, lambda info: self.send(uci_info(info)))
                elif result.info.tbhits:
                    self.send(uci_info(result.info))
                move = result.best_move
                if result.claim_draw:
                    self.send("info string draw claim available; UCI transport returns a legal move")
                    move = next(board.legal_moves(), None)
                self.send("bestmove " + (move.uci() if move else "0000"))
            except Exception as exc:
                self.send(f"info string search error: {type(exc).__name__}: {exc}")
                fallback = next(board.legal_moves(), None)
                self.send("bestmove " + (fallback.uci() if fallback else "0000"))

        self._thread = threading.Thread(target=run, name="nocturne-uci-search", daemon=True)
        self._thread.start()

    def command(self, line: str) -> bool:
        parts = line.strip().split()
        if not parts:
            return True
        command, args = parts[0], parts[1:]
        try:
            if command == "uci":
                for line in (f"id name Nocturne {__version__}", "id author Nocturne Chess contributors",
                             "option name Hash type spin default 32 min 1 max 256",
                             "option name Threads type spin default 1 min 1 max 1",
                             "option name SyzygyPath type string default <empty>", "uciok"):
                    self.send(line)
            elif command == "isready":
                self.send("readyok")
            elif command == "ucinewgame":
                self.stop()
                self.board = Board()
            elif command == "setoption":
                if "name" not in args:
                    raise ValueError("setoption needs a name")
                value_index = args.index("value") if "value" in args else len(args)
                name = " ".join(args[args.index("name") + 1:value_index]).lower()
                value = " ".join(args[value_index + 1:])
                if name == "hash":
                    self.hash_mb = min(256, max(1, int(value)))
                elif name == "syzygypath":
                    self.stop()
                    self.syzygy_path = "" if value == "<empty>" else value
                elif name == "threads" and value != "1":
                    self.send("info string Nocturne supports one search thread")
            elif command == "position":
                self.position(args)
            elif command == "go":
                self.go(args)
            elif command == "stop":
                self.stop()
            elif command == "quit":
                self.stop()
                return False
            elif command == "d":
                self.send("info string " + self.board.fen())
        except ValueError as exc:
            self.send(f"info string invalid command: {exc}")
        return True


def main():
    session = UciSession()
    try:
        for line in sys.stdin:
            if not session.command(line):
                break
    finally:
        session.stop()


if __name__ == "__main__":
    main()
