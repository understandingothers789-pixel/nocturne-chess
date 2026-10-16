"""Qt process supervision with cancellation and stale-result protection."""

from __future__ import annotations

from dataclasses import asdict
import multiprocessing
import time

from PySide6.QtCore import QObject, QTimer, Signal

from ..core.game import Game
from ..engine.search import SearchLimits
from ..engine.worker import run_worker


class EngineController(QObject):
    message = Signal(int, str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.context = multiprocessing.get_context("spawn")
        self.generation = 0
        self.active = None
        self.retired = []
        self.timer = QTimer(self)
        self.timer.setInterval(25)
        self.timer.timeout.connect(self._poll)
        self.timer.start()

    @property
    def busy(self):
        return self.active is not None

    def start(self, game: Game, limits: SearchLimits, external="", kind="search") -> int:
        self.stop()
        output, child_output = self.context.Pipe(duplex=False)
        child_control, control = self.context.Pipe(duplex=False)
        request = {"kind": kind, "initial_fen": game.initial_fen,
                   "moves": [m.uci() for m in game.moves[:game.cursor]],
                   "limits": asdict(limits), "external": external}
        proc = self.context.Process(target=run_worker, args=(request, child_output, child_control), daemon=True)
        proc.start()
        child_output.close()
        child_control.close()
        self.active = (self.generation, proc, output, control)
        return self.generation

    def stop(self):
        self.generation += 1
        if self.active:
            generation, proc, output, control = self.active
            try:
                control.send("stop")
            except (BrokenPipeError, EOFError, OSError):
                pass
            self.retired.append((proc, output, control, time.monotonic() + .3))
            self.active = None

    def _poll(self):
        active = self.active
        if active:
            generation, proc, output, control = active
            try:
                for _ in range(40):
                    if not output.poll():
                        break
                    kind, payload = output.recv()
                    if generation != self.generation:
                        break
                    if kind in ("result", "error", "benchmark"):
                        self.active = None
                        self.retired.append((proc, output, control, time.monotonic() + .3))
                    self.message.emit(generation, kind, payload)
                    if self.active != active:
                        break
                if self.active == active and not proc.is_alive() and not output.poll():
                    self.active = None
                    self.retired.append((proc, output, control, time.monotonic()))
                    self.message.emit(generation, "error", {"message": f"Engine process exited ({proc.exitcode})"})
            except (EOFError, OSError):
                if self.active == active:
                    self.active = None
                    self.retired.append((proc, output, control, time.monotonic()))
                    self.message.emit(generation, "error", {"message": "Engine process disconnected"})
        remaining = []
        for proc, output, control, deadline in self.retired:
            if proc.is_alive() and time.monotonic() < deadline:
                remaining.append((proc, output, control, deadline))
            else:
                if proc.is_alive():
                    proc.terminate()
                proc.join(timeout=0)
                if proc.is_alive():
                    remaining.append((proc, output, control, time.monotonic()))
                    continue
                output.close()
                control.close()
                proc.close()
        self.retired = remaining

    def close(self):
        self.stop()
        self.timer.stop()
        for proc, output, control, _ in self.retired:
            if proc.is_alive():
                proc.terminate()
            proc.join(timeout=.4)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=.2)
            output.close()
            control.close()
            if not proc.is_alive():
                proc.close()
        self.retired.clear()
