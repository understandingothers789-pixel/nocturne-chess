"""Protocol test fixture, NOT a chess engine and never included in the app bundle."""

import sys
import threading
import time
import chess

mode = sys.argv[1] if len(sys.argv) > 1 else "normal"
lock = threading.Lock()
board = chess.Board()
stop = threading.Event()
thread = None
options = {}


def send(text):
    with lock:
        print(text, flush=True)


def finish():
    global thread
    stop.set()
    if thread:
        thread.join(timeout=0.5)
    thread = None


def search(position, command, event):
    if mode == "crash":
        sys.exit(2)  # main command path below handles real process crash
    moves = list(position.legal_moves)
    prefer = ["e2e4", "d2d4", "g1f3"]
    moves.sort(key=lambda m: prefer.index(m.uci()) if m.uci() in prefer else 100)
    if mode == "review-grades" and position.ply() == 2:
        moves.sort(key=lambda m: m.uci() != "g1f3")
    tokens = command.split()
    if "searchmoves" in tokens and mode != "ignore-searchmoves":
        allowed = tokens[tokens.index("searchmoves") + 1 :]
        moves = [m for m in moves if m.uci() in allowed]
    for depth in range(1, 5):
        if event.is_set():
            break
        for rank, move in enumerate(moves[: int(options.get("MultiPV", 1))], 1):
            child = position.copy()
            child.push(move)
            reply = next(iter(child.legal_moves), None)
            pv = move.uci() + (" " + reply.uci() if reply else "")
            score = "mate -3 upperbound" if mode == "bounds" else f"cp {35 - (rank - 1) * 20}"
            if mode == "bound-at-limit" and depth == 4 and rank == 1:
                score += " upperbound"
            if mode == "review-grades":
                value = [-600, 100, 150, 0, 140, 120][position.ply() % 6] if "searchmoves" in tokens else 150
                score = f"cp {value}"
            send(
                f"info depth {depth} seldepth {depth + 3} time {depth * 5} nodes {depth * 100} nps 20000 score {score} wdl 400 500 100 multipv {rank} pv {pv}"
            )
        time.sleep(0.015)
    if "infinite" in tokens or mode == "hold":
        event.wait(10)
    # Deliberately emit stale information after stop; transports must discard it.
    if event.is_set():
        send("info depth 99 score cp 999 pv a1a8")
    send("bestmove " + (moves[0].uci() if moves else "0000"))


for raw in sys.stdin:
    line = raw.strip()
    if line == "uci":
        if mode == "hang":
            continue
        send("id name Nocturne UCI transport simulator")
        for option in [
            "Threads type spin default 1 min 1 max 16",
            "Hash type spin default 16 min 1 max 8192",
            "MultiPV type spin default 1 min 1 max 8",
            "UCI_ShowWDL type check default false",
            "UCI_Chess960 type check default false",
            "SyzygyPath type string default <empty>",
            "Style type combo default Normal var Normal var Very Solid",
            "Clear Hash type button",
        ]:
            if mode == "single-pv" and option.startswith("MultiPV "):
                continue
            send("option name " + option)
        send("uciok")
    elif line == "isready":
        if mode != "no-ready":
            send("readyok")
    elif line.startswith("setoption name "):
        name, sep, value = line[15:].partition(" value ")
        options[name] = value
    elif line.startswith("position fen "):
        data = line[13:].split(" moves ")
        board = chess.Board(data[0], chess960=options.get("UCI_Chess960") == "true")
        if len(data) > 1:
            for text in data[1].split():
                board.push_uci(text)
    elif line.startswith("go "):
        finish()
        stop = threading.Event()
        if mode == "crash":
            raise SystemExit(2)
        thread = threading.Thread(target=search, args=(board.copy(), line, stop), daemon=True)
        thread.start()
    elif line == "stop":
        finish()
    elif line == "quit":
        finish()
        break
