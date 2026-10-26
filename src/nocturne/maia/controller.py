"""Asynchronous local policy requests with stale-position rejection and cache."""

from collections import OrderedDict
import hashlib
import json
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from . import RATINGS, MODEL_REVISION


class MaiaController(QObject):
    changed = Signal(dict)
    status = Signal(str)

    def __init__(self, directory, parent=None):
        super().__init__(parent)
        self.device_mode = "auto"
        self.device_label = "not loaded"
        self._external = False
        self._cpu_retry = False
        self.directory = Path(directory)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.readyReadStandardError.connect(lambda: self.process.readAllStandardError())
        self.process.errorOccurred.connect(self._error)
        self.process.finished.connect(self._finished)
        self._buffer = b""
        self._serial = 0
        self._active = None
        self._queued = None
        self._ready = False
        self._busy = False
        self._failed = False
        self._closing = False
        self.outcomes = {}
        self.policies = {}
        self.cache = OrderedDict()
        self.value_cache = {}
        self.cache_path = self.directory / "maia-policy-cache.json"
        try:
            data = json.loads(self.cache_path.read_text())
            if data.get("model") == MODEL_REVISION:
                self.value_cache = data.get("outcomes", {})
                self.cache.update(list(data.get("positions", {}).items())[-128:])
        except (OSError, ValueError, AttributeError):
            pass
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(100)
        self.debounce.timeout.connect(self._dispatch)

    def request(self, root, moves, rating=1800, sweep=False):
        ratings = [rating] + ([r for r in RATINGS if r != rating] if sweep else [])
        key = hashlib.sha256(json.dumps([MODEL_REVISION, "white-wdl-v1", root, moves], separators=(",", ":")).encode()).hexdigest()
        signature = (key, tuple(ratings))
        if self._queued and self._queued[0] == signature:
            return
        if self._active and self._active[0] == signature:
            return
        self._serial += 1
        self.outcomes = dict(self.value_cache.get(key, {}))
        self.policies = dict(self.cache.get(key, {}))
        self.changed.emit(self.policies)
        request = {"id": self._serial, "root": root, "moves": moves, "ratings": ratings}
        self._queued = (signature, request)
        if all(str(r) in self.policies and str(r) in self.outcomes for r in ratings):
            self._active, self._queued = self._queued, None
            self.status.emit("Maia-3 79M · cached")
            return
        self.debounce.start()

    def _dispatch(self):
        if self._closing or not self._queued or self._failed:
            return
        if self.process.state() == QProcess.ProcessState.NotRunning:
            if getattr(sys, "frozen", False):
                folder = Path(sys.executable).parent / "Maia"
                command = [str(folder / "NocturneMaia.exe"), str(folder / "maia3-79m.pt")]
            else:
                checkpoint = Path(__file__).resolve().parents[3] / "models" / "maia3-79m.pt"
                if not checkpoint.is_file():
                    self.status.emit("Maia-3 79M · model included in Windows download")
                    return
                command = [sys.executable, "-m", "nocturne.maia.worker", str(checkpoint)]
            runtime = self.directory / "maia-gpu"
            python = runtime / "Scripts/python.exe"
            self._external = (self.device_mode == "auto" and not self._cpu_retry
                              and (runtime / "ready.json").is_file() and python.is_file())
            env = QProcessEnvironment.systemEnvironment()
            env.insert("NOCTURNE_MAIA_DEVICE", "cpu" if self._cpu_retry else self.device_mode)
            if self._external:
                source = (Path(sys.executable).parent / "Maia" / "gpu-source" if getattr(sys, "frozen", False)
                          else Path(__file__).resolve().parents[2])
                env.insert("PYTHONPATH", str(source))
                checkpoint = (Path(sys.executable).parent / "Maia" / "maia3-79m.pt" if getattr(sys, "frozen", False)
                              else Path(__file__).resolve().parents[3] / "models/maia3-79m.pt")
                command = [str(python), "-m", "nocturne.maia.worker", str(checkpoint)]
            self.process.setProcessEnvironment(env)
            self.status.emit("Loading Maia-3 79M…")
            self.process.start(command[0], command[1:])
            return
        if not self._ready or self._busy:
            return
        self._active, self._queued = self._queued, None
        self._busy = True
        self.process.write((json.dumps(self._active[1]) + "\n").encode())
        self.status.emit(f"Maia-3 79M · {self.device_label} · predicting…")

    def _read(self):
        self._buffer += bytes(self.process.readAllStandardOutput())
        while b"\n" in self._buffer:
            raw, self._buffer = self._buffer.split(b"\n", 1)
            try:
                message = json.loads(raw)
            except (ValueError, UnicodeError):
                continue
            if message.get("device"):
                self.device_label = message["device"]
            if message.get("ready"):
                self._ready = True
                self._dispatch()
            elif message.get("error"):
                if message.get("id") is None or message.get("id") == self._serial:
                    self.status.emit(message["error"])
                if message.get("id") is None:
                    self._failed = True
                else:
                    self._busy = False
                    if self._queued:
                        self._dispatch()
            elif self._active and message.get("id") == self._serial == self._active[1]["id"]:
                self.outcomes.update(message.get("outcomes", {}))
                self.value_cache[self._active[0][0]] = self.outcomes.copy()
                self.policies.update(message.get("policies", {}))
                self.cache[self._active[0][0]] = self.policies.copy()
                self.changed.emit(self.policies)
                if message.get("complete"):
                    self.status.emit(f"Maia-3 79M · {self.device_label}")
                    self._save_cache()
            if message.get("complete"):
                self._busy = False
                if self._queued:
                    self._dispatch()

    def _save_cache(self):
        while len(self.cache) > 128:
            key, _ = self.cache.popitem(last=False)
            self.value_cache.pop(key, None)
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = self.cache_path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"model": MODEL_REVISION, "positions": self.cache, "outcomes": self.value_cache}), encoding="utf-8")
            temporary.replace(self.cache_path)
        except OSError:
            pass

    def _retry_cpu(self):
        if not self._external or self._cpu_retry:
            return False
        self._cpu_retry = True
        if self._active and not self._queued:
            self._queued = self._active
        self._active = None
        self._ready = self._busy = self._failed = False
        self.status.emit("GPU worker unavailable · retrying bundled CPU")
        QTimer.singleShot(0, self._dispatch)
        return True

    def _error(self, error):
        if error != QProcess.ProcessError.FailedToStart:
            return
        if not self._closing:
            if self._retry_cpu():
                return
            self._failed = True
            self.status.emit("Maia could not start. The Stockfish analysis remains available.")

    def _finished(self, *args):
        self._ready = False
        if not self._closing:
            if self._retry_cpu():
                return
            self._failed = True
            self.status.emit("Maia worker stopped. Disable and enable Maia to retry.")

    def stop(self):
        self.debounce.stop()
        self._serial += 1
        self._active = self._queued = None
        self._closing = True
        self.process.kill()
        self.process.waitForFinished(1000)
        self._closing = False
        self._failed = False
        self._cpu_retry = False
        self._ready = False
        self._busy = False
        self.outcomes = {}
        self.policies = {}
        self.changed.emit({})
