"""Spawn-safe process entry points. This module deliberately never imports Qt."""

from __future__ import annotations

from multiprocessing.connection import Connection
from dataclasses import replace
import time
import traceback

from ..core.board import Board
from .benchmark import POSITIONS, metadata
from .external import run_external
from .search import SearchInfo, SearchLimits, Searcher
from .tablebase import probe, root_result


def info_payload(info: SearchInfo) -> dict:
    return {"depth": info.depth, "seldepth": info.seldepth, "score": info.score,
            "nodes": info.nodes, "seconds": info.seconds, "nps": info.nps,
            "pv": [m.uci() for m in info.pv], "hashfull": info.hashfull, "tbhits": info.tbhits}


def run_worker(request: dict, output: Connection, control: Connection):
    canceled = False

    def cancel():
        nonlocal canceled
        if not canceled and control.poll():
            try:
                control.recv()
            except EOFError:
                pass
            canceled = True
        return canceled

    def send(kind, payload):
        output.send((kind, payload))

    try:
        limits = SearchLimits(**request["limits"])
        if request.get("kind") == "benchmark":
            report = {"metadata": metadata(), "depth": limits.depth, "results": []}
            for name, fen in POSITIONS.items():
                if cancel():
                    break
                result = Searcher(limits, cancel).search(Board(fen))
                row = {"position": name, **info_payload(result.info),
                       "bestmove": result.best_move.uci() if result.best_move else None,
                       "stopped": result.stopped}
                report["results"].append(row)
                send("benchmark_progress", row)
            send("benchmark", report)
            return
        board = Board(request["initial_fen"])
        moves = request.get("moves", [])
        for text in moves:
            board.play_uci(text)
        started = time.perf_counter()
        path = request.get("tablebase_path", "")
        tb = probe(board, path, lambda: cancel() or time.perf_counter() - started >= limits.seconds)
        if path:
            send("tablebase", tb)
        def callback(info):
            send("info", info_payload(info))
        if executable := request.get("external"):
            result = run_external(executable, request["initial_fen"], moves, limits, cancel, callback,
                                  tablebase_path=path)
        else:
            result = root_result(board, tb, started)
            if result is None:
                remaining = max(.001, limits.seconds - (time.perf_counter() - started))
                result = Searcher(replace(limits, seconds=remaining), cancel).search(board, callback)
        send("result", {"move": result.best_move.uci() if result.best_move else None,
                        "info": info_payload(result.info), "stopped": result.stopped,
                        "claim_draw": result.claim_draw})
    except (BrokenPipeError, EOFError):
        pass
    except Exception as exc:
        try:
            send("error", {"message": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()})
        except (BrokenPipeError, EOFError):
            pass
    finally:
        output.close()
        control.close()
