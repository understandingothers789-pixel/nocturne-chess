"""Optional, explicitly selected local UCI engine. Never used by custom search."""

from __future__ import annotations

import queue
import subprocess
import threading
import time
from typing import Callable

from ..core.board import Board
from .search import MATE, SearchInfo, SearchLimits, SearchResult


class ExternalEngineError(RuntimeError):
    pass


def run_external(command: str | list[str], initial_fen: str, moves: list[str], limits: SearchLimits,
                 cancel: Callable[[], bool], on_info: Callable[[SearchInfo], None], tablebase_path="") -> SearchResult:
    board = Board(initial_fen)
    for move in moves:
        board.play_uci(move)
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    try:
        proc = subprocess.Popen([command] if isinstance(command, str) else command,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=flags)
    except OSError as exc:
        raise ExternalEngineError(f"Cannot start the selected executable: {exc}") from exc
    lines: queue.Queue[str | None] = queue.Queue(maxsize=2048)

    def reader():
        try:
            for line in proc.stdout:
                # Bound protocol-line size and queued output from noisy engines.
                if len(line) <= 65536:
                    try:
                        lines.put_nowait(line.strip())
                    except queue.Full:
                        pass
        finally:
            try:
                lines.put_nowait(None)
            except queue.Full:
                pass

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    def send(text):
        try:
            proc.stdin.write(text + "\n")
            proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise ExternalEngineError("The selected engine closed its input") from exc

    def next_line(deadline):
        while time.perf_counter() < deadline:
            if cancel():
                raise ExternalEngineError("External search canceled")
            try:
                line = lines.get(timeout=.025)
            except queue.Empty:
                if proc.poll() is not None:
                    raise ExternalEngineError("The selected engine exited unexpectedly")
                continue
            if line is None:
                raise ExternalEngineError("The selected engine closed its output")
            return line
        raise ExternalEngineError("UCI engine did not respond before its deadline")

    started = time.perf_counter()
    info = SearchInfo(0, 0, 0, 0, 0, ())
    try:
        send("uci")
        handshake_deadline = time.perf_counter() + 5
        options = set()
        while True:
            line = next_line(handshake_deadline)
            if line.startswith("option name "):
                options.add(line[12:].split(" type ", 1)[0].lower())
            if line == "uciok":
                break
        if "hash" in options:
            send(f"setoption name Hash value {limits.hash_mb}")
        if "threads" in options:
            send("setoption name Threads value 1")
        if "syzygypath" in options and tablebase_path:
            if "\n" in tablebase_path or "\r" in tablebase_path:
                raise ExternalEngineError("Invalid Syzygy path")
            send("setoption name SyzygyPath value " + tablebase_path)
        send("ucinewgame")
        send("isready")
        ready_deadline = time.perf_counter() + 5
        while next_line(ready_deadline) != "readyok":
            pass
        send("position fen " + initial_fen + (" moves " + " ".join(moves) if moves else ""))
        started = time.perf_counter()
        send(f"go movetime {max(1, int(limits.seconds * 1000))} depth {limits.depth}")
        deadline = started + limits.seconds + .4
        while True:
            line = next_line(deadline)
            if line.startswith("bestmove "):
                token = line.split()[1]
                if token in ("0000", "(none)"):
                    if any(board.legal_moves()):
                        raise ExternalEngineError("External engine returned no move in a playable position")
                    move = None
                else:
                    try:
                        move = board.parse_uci(token)
                    except ValueError as exc:
                        raise ExternalEngineError("External engine returned an illegal move") from exc
                return SearchResult(move, info)
            if line.startswith("info "):
                parsed = parse_info(line, board, time.perf_counter() - started, info)
                if parsed is not None:
                    info = parsed
                    on_info(info)
    finally:
        if proc.poll() is None:
            try:
                send("stop")
                send("quit")
                proc.wait(timeout=.15)
            except (ExternalEngineError, subprocess.TimeoutExpired):
                proc.kill()
                proc.wait(timeout=1)
        for stream in (proc.stdin, proc.stdout):
            if stream:
                stream.close()
        thread.join(timeout=.1)


def parse_info(line: str, board: Board, elapsed: float, previous: SearchInfo) -> SearchInfo | None:
    tokens = line.split()
    if "string" in tokens:
        return None
    try:
        def number(name, default):
            return int(tokens[tokens.index(name) + 1]) if name in tokens else default
        if number("multipv", 1) != 1:
            return None
        score = previous.score
        if "score" in tokens:
            index = tokens.index("score")
            kind, value = tokens[index + 1], int(tokens[index + 2])
            if kind == "cp":
                score = max(-28999, min(28999, value))
            elif kind == "mate":
                score = (MATE - min(999, abs(value) * 2 - 1)) * (1 if value > 0 else -1) if value else -MATE
        pv = []
        if "pv" in tokens:
            copy = board.copy(history=False)
            for text in tokens[tokens.index("pv") + 1:]:
                try:
                    move = copy.parse_uci(text)
                except ValueError:
                    break
                pv.append(move)
                copy.push(move)
        return SearchInfo(number("depth", previous.depth), number("seldepth", previous.seldepth), score,
                          max(0, number("nodes", previous.nodes)), elapsed, tuple(pv),
                          min(1000, max(0, number("hashfull", previous.hashfull))),
                          max(0, number("tbhits", previous.tbhits)))
    except (ValueError, IndexError):
        return None
