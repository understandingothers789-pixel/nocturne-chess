"""Persistent asynchronous UCI transport with stop barriers and bounded output."""

from collections import deque
from pathlib import Path
import os

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from ..engine.uci_types import parse_info, parse_option


class UciConnection(QObject):
    discovered = Signal(object)
    information = Signal(int, object)
    observation = Signal(int, object)
    completed = Signal(int, str)
    failed = Signal(str)
    status = Signal(str)
    configured = Signal()

    def __init__(self, parent=None, timeout_ms=5000):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.process.started.connect(self._started)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.readyReadStandardError.connect(self._stderr)
        self.process.errorOccurred.connect(self._process_error)
        self.process.finished.connect(self._finished)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)
        self.timeout_ms = timeout_ms
        self.phase = "closed"
        self.path = ""
        self.name = ""
        self.options = {}
        self.log = deque(maxlen=500)
        self.buffer = b""
        self.pending = None
        self.running = None
        self.applied = {}
        self.confirmed = {}
        self._prepared = None
        self._quitting = False
        self._last_info = {}
        self.observe_nodes = False
        self._last_exact_info = {}
        self._flush = QTimer(self)
        self._flush.setInterval(80)
        self._flush.timeout.connect(self._emit_info)
        self._flush.start()

    @property
    def alive(self):
        return self.process.state() != QProcess.ProcessState.NotRunning

    def launch(self, path, arguments=None):
        path = os.path.abspath(Path(path).expanduser())
        if not Path(path).is_file() or (os.name != "nt" and not os.access(path, os.X_OK)):
            raise ValueError("Choose an existing executable UCI engine file")
        self.close()
        self.path, self.name = path, Path(path).stem
        self.options, self.applied, self.buffer = {}, {}, b""
        self.confirmed, self._prepared = {}, None
        self._quitting = False
        self.phase = "launch"
        self.process.setProgram(path)
        self.process.setArguments(list(arguments or []))
        self.process.setWorkingDirectory(str(Path(path).parent))
        self.process.start()
        self.timer.start(self.timeout_ms)
        self.status.emit("Starting " + self.name)

    def send(self, text):
        if "\n" in text or "\r" in text or "\0" in text:
            raise ValueError("Invalid UCI command")
        self.log.append("> " + text)
        self.process.write((text + "\n").encode("utf-8"))

    def _started(self):
        self.phase = "uci"
        self.send("uci")

    def request(self, generation, position, go, options, study_id=""):
        self.pending = (generation, position, go, dict(options), study_id)
        self._last_info.clear()
        self._last_exact_info.clear()
        if self.phase == "search":
            self.running = None  # Old output becomes ineligible immediately.
            self.send("stop")
            self.phase = "stopping"
            self.timer.start(self.timeout_ms)
        elif self.phase == "idle":
            self._prepare()

    def stop(self):
        self.pending = None
        self.running = None
        self._last_info.clear()
        self._last_exact_info.clear()
        if self.phase == "search":
            self.send("stop")
            self.phase = "stopping"
            self.timer.start(self.timeout_ms)

    def _prepare(self):
        if self.pending is None:
            return
        desired = dict(self.pending[3])
        # Profiles are independent even when they share the same executable.
        for name, option in self.options.items():
            if option.kind != "button" and name not in desired:
                desired[name] = "" if option.default == "<empty>" else option.default
        if desired.get("UCI_Chess960") and "UCI_Chess960" not in self.options:
            raise ValueError("This engine does not advertise Chess960 support")
        for name, value in desired.items():
            option = self.options.get(name)
            if option is None:
                continue
            value = option.validate(value)
            if name == "Hash":
                from .hardware import hash_budget_mb

                budget = hash_budget_mb(int(self.confirmed.get("Hash", 0)))
                if budget is not None and int(value) > budget:
                    raise ValueError(
                        f"Hash exceeds the current memory budget ({budget} MB). Reduce it in Engine → Hash."
                    )
            if self.applied.get(name) != value:
                suffix = "" if option.kind == "button" else " value " + (value or "<empty>")
                self.send("setoption name " + name + suffix)
                self.applied[name] = value
        study = self.pending[4]
        if self.applied.get("__study") != study:
            self.send("ucinewgame")
            self.applied["__study"] = study
        self.phase = "ready"
        self._prepared = self.pending
        self.send("isready")
        self.timer.start(self.timeout_ms)

    def _read(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        if len(self.buffer) > 1_000_000:
            self._fail("Engine output exceeded the line buffer limit")
            return
        count = 0
        while b"\n" in self.buffer and count < 256:
            count += 1
            raw, self.buffer = self.buffer.split(b"\n", 1)
            self._line(raw.decode("utf-8", errors="replace").strip())
        if b"\n" in self.buffer:
            QTimer.singleShot(0, self._read)

    def _line(self, line):
        self.log.append("< " + line[:2048])
        if self.phase == "uci":
            if line.startswith("id name "):
                self.name = line[8:]
            elif option := parse_option(line):
                self.options[option.name] = option
            elif line == "uciok":
                self.timer.stop()
                self.phase = "initial-ready"
                self.send("isready")
                self.timer.start(self.timeout_ms)
        elif line == "readyok" and self.phase in ("initial-ready", "ready", "barrier"):
            self.timer.stop()
            initial = self.phase == "initial-ready"
            prepared = self.phase == "ready"
            prepared_request, self._prepared = self._prepared, None
            self.phase = "idle"
            if prepared:
                self.confirmed = self.applied.copy()
                self.configured.emit()
            if initial:
                self.discovered.emit({"path": self.path, "name": self.name, "options": self.options.copy()})
            if self.pending:
                if prepared and self.pending is prepared_request:
                    self.running, self.pending = self.pending, None
                    self.phase = "search"
                    self.send(self.running[1])
                    self.send(self.running[2])
                    tokens = self.running[2].split()
                    if "movetime" in tokens:
                        self.timer.start(int(tokens[tokens.index("movetime") + 1]) + self.timeout_ms)
                    self.status.emit(self.name + " · analyzing")
                else:
                    self._safe_prepare()
            elif initial:
                self.status.emit(self.name + " · ready")
        elif line.startswith("bestmove "):
            if self.phase == "stopping":
                self.phase = "barrier"
                self.send("isready")
                self.timer.start(self.timeout_ms)
            elif self.phase == "search" and self.running:
                self.timer.stop()
                self._emit_info()
                generation = self.running[0]
                self.running = None
                self.phase = "idle"
                self.completed.emit(generation, line.split()[1])
                if self.pending:
                    self._safe_prepare()
        elif self.phase == "search" and self.running:
            if info := parse_info(line):
                if self.observe_nodes:
                    self.observation.emit(self.running[0], info)
                self._last_info[info["multipv"]] = (self.running[0], info)
                if info.get("bound", "exact") == "exact":
                    self._last_exact_info[info["multipv"]] = (self.running[0], info)

    def _safe_prepare(self):
        try:
            self._prepare()
        except ValueError as exc:
            self._fail(str(exc))

    def _emit_info(self):
        pending, self._last_info = self._last_info, {}
        exact_pending, self._last_exact_info = self._last_exact_info, {}
        for rank in sorted(pending):
            generation, info = pending[rank]
            # Throttling must not discard an exact iteration when a later
            # bound for the same rank arrives before the next UI flush.
            exact = exact_pending.get(rank)
            if exact and info.get("bound", "exact") != "exact":
                if self.running and self.running[0] == exact[0]:
                    self.information.emit(*exact)
            if self.running and self.running[0] == generation:
                self.information.emit(generation, info)

    def _stderr(self):
        text = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        self.log.append("stderr: " + text[-4000:])

    def _process_error(self, error):
        if not self._quitting:
            self._fail("Engine process error: " + self.process.errorString())

    def _finished(self, code, status):
        if not self._quitting and self.phase != "failed":
            self._fail(f"Engine exited unexpectedly (code {code}). Open engine diagnostics for details.")

    def _timeout(self):
        self._fail(f"Engine did not respond during {self.phase}. Check the executable and engine options.")

    def _fail(self, message):
        self.phase = "failed"
        self.timer.stop()
        self.pending = self.running = None
        self._last_info.clear()
        self._last_exact_info.clear()
        self._quitting = True
        self.process.kill()
        self.confirmed.clear()
        self.configured.emit()
        self.failed.emit(message)
        self.status.emit(message)

    def close(self):
        self._quitting = True
        self.timer.stop()
        self.pending = self.running = None
        self._last_info.clear()
        self._last_exact_info.clear()
        if self.alive:
            self.send("quit")
            # Only close/replacement waits, bounded; ordinary navigation never waits.
            if not self.process.waitForFinished(150):
                self.process.kill()
                self.process.waitForFinished(150)
        self.phase = "closed"
        self.confirmed.clear()
        self.configured.emit()
