"""Engine-advertised option editor and persistent executable profiles."""

from dataclasses import asdict
from pathlib import Path
import os
import platform
from zipfile import BadZipFile
from uuid import uuid4

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..engine.stockfish_dev import install_development
from .uci_connection import UciConnection
from .engine_resources import format_hash_mb


class StockfishDownload(QThread):
    status = Signal(str)

    def __init__(self, root, architecture, parent):
        super().__init__(parent)
        self.root = root
        self.architecture = architecture
        self.result = None
        self.error = ""

    def run(self):
        try:
            self.result = install_development(self.root, self.architecture, self.status.emit)
        except (OSError, ValueError, KeyError, TypeError, BadZipFile) as exc:
            self.error = str(exc)


class EngineManager(QDialog):
    def __init__(self, profiles, selected="", parent=None, allocated_hash=0, *, download_directory=None):
        super().__init__(parent)
        self.setWindowTitle("UCI engine profiles")
        self.resize(720, 650)
        self.profiles = [{**p, "values": dict(p.get("values", {}))} for p in profiles]
        self.selected = selected
        self.download_directory = download_directory
        self.download = None
        self.allocated_hash = allocated_hash
        self.connection = UciConnection(self)
        self.connection.discovered.connect(self._discovered)
        self.connection.failed.connect(self._failed)
        self.widgets = {}
        self._detect_id = None
        self._detect_timer = QTimer(self)
        self._detect_timer.setSingleShot(True)
        self._detect_timer.timeout.connect(self._detect)
        layout = QVBoxLayout(self)
        self.selector = QComboBox()
        for p in self.profiles:
            self.selector.addItem(p.get("label") or p.get("name", Path(p["path"]).stem), p["id"])
        layout.addWidget(self.selector)
        row = QHBoxLayout()
        for text, slot in [
            ("Add executable…", self._add),
            ("Detect options / restart", self._detect),
            ("Remove profile", self._remove),
        ]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        layout.addLayout(row)
        if os.name == "nt" and download_directory is not None:
            button = QPushButton("Download latest Stockfish development build")
            button.setToolTip("Get the latest development release from the official Stockfish GitHub repository and add it as an engine profile.")
            button.clicked.connect(self._download_stockfish)
            layout.addWidget(button)
        self.label = QLineEdit()
        self.path = QLineEdit()
        self.path.setReadOnly(True)
        form = QFormLayout()
        form.addRow("Profile name", self.label)
        form.addRow("Executable", self.path)
        layout.addLayout(form)
        self.status = QLabel("Select an installed executable or download Stockfish.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        presets = QHBoxLayout()
        for name, threads, hash_mb in [
            ("Casual", 2, 256),
            ("Balanced", 6, 1024),
            ("8 threads / 4 GB", 8, 4096),
        ]:
            b = QPushButton(name)
            b.clicked.connect(lambda checked=False, t=threads, h=hash_mb: self._preset(t, h))
            presets.addWidget(b)
        layout.addLayout(presets)
        note = QLabel(
            "CPU presets for Ryzen 9800X3D / 32 GB are starting points, not measured optima.\nStockfish CPU analysis does not use your Radeon GPU. Hash accepts a custom MB value."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll, 1)
        self.options_widget = QWidget()
        self.form = QFormLayout(self.options_widget)
        self.scroll.setWidget(self.options_widget)
        self.diagnostics = QPlainTextEdit()
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setMaximumHeight(115)
        layout.addWidget(self.diagnostics)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.selector.currentIndexChanged.connect(self._select)
        self.selector.setCurrentIndex(max(0, self.selector.findData(selected)))
        self._select()

    def _profile(self):
        key = self.selector.currentData()
        return next((p for p in self.profiles if p["id"] == key), None)

    def _remember(self):
        p = next((p for p in self.profiles if p["id"] == self.selected), None)
        if p:
            p["label"] = self.label.text().strip() or p.get("name", "Engine")
            for name, w in self.widgets.items():
                if isinstance(w, QCheckBox):
                    value = w.isChecked()
                elif isinstance(w, QSpinBox):
                    value = w.value()
                elif isinstance(w, QComboBox):
                    value = w.currentText()
                else:
                    value = w.text()
                p["values"][name] = value

    @staticmethod
    def _signature(path):
        try:
            stat = Path(path).stat()
            return f'{stat.st_size}:{stat.st_mtime_ns}'
        except OSError:
            return ''

    def _select(self):
        self._detect_timer.stop()
        self._detect_id = None
        self.connection.close()
        self._remember()
        p = self._profile()
        self.selected = p["id"] if p else ""
        self.label.setText(p.get("label", p.get("name", "")) if p else "")
        self.path.setText(p["path"] if p else "")
        self._render(p.get("options", {}) if p else {})
        self.diagnostics.clear()
        if not p:
            self.status.setText('Add an executable to discover its supported UCI options.')
        elif (not p.get('options_detected') or not p.get('options_signature')
              or p['options_signature'] != self._signature(p['path'])):
            self.status.setText('Detecting supported options for this executable…')
            self._detect_timer.start(0)
        else:
            self._ready_status(p)

    def _ready_status(self, p):
        count = len(p.get('options', {}))
        self.status.setText(f"{p.get('name', 'Engine')} · {count} advertised options"
                            + (' · This engine advertises no configurable options.' if not count else ''))

    def _render(self, options):
        while self.form.rowCount():
            self.form.removeRow(0)
        self.widgets = {}
        p = self._profile()
        for name, o in options.items():
            kind = o["kind"]
            value = p["values"].get(name, o.get("default", ""))
            if kind == "button":
                w = QPushButton(name)
                w.clicked.connect(lambda checked=False, n=name: self._button(n))
                self.form.addRow("", w)
                continue
            if kind == "check":
                w = QCheckBox()
                w.setChecked(value is True or str(value).lower() == "true")
            elif kind == "spin":
                w = QSpinBox()
                w.setRange(max(-2147483647, o["minimum"]), min(2147483647, o["maximum"]))
                if name == "Hash":
                    from .hardware import hash_budget_mb

                    budget = hash_budget_mb(self.allocated_hash)
                    if budget is not None:
                        w.setMaximum(max(w.minimum(), min(w.maximum(), budget)))
                w.setValue(int(value))
            elif kind == "combo":
                w = QComboBox()
                w.addItems(o["choices"])
                w.setCurrentText(str(value))
            else:
                w = QLineEdit("" if value == "<empty>" else str(value))
            self.widgets[name] = w
            if name in ("MultiPV", "UCI_Chess960", "UCI_AnalyseMode"):
                w.setEnabled(False)
                name_label = name + " (controlled by analysis mode / board)"
            else:
                name_label = name
            self.form.addRow(name_label, w)
            if name == "Hash" and isinstance(w, QSpinBox):
                w.setSuffix(" MB")
                readable = QLabel(format_hash_mb(w.value()))
                w.valueChanged.connect(lambda value, display=readable: display.setText(format_hash_mb(value)))
                self.form.addRow("Hash size", readable)

    def _add(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose your UCI engine", "", "Executables (*.exe);;All files (*)"
        )
        if path:
            self._add_profile(path, Path(path).stem)

    def _add_profile(self, path, label):
        self._remember()
        p = {
            "id": str(uuid4()),
            "path": path,
            "name": Path(path).stem,
            "label": label,
            "values": {},
            "options": {},
        }
        self.profiles.append(p)
        self.selector.addItem(p["label"], p["id"])
        self.selector.setCurrentIndex(self.selector.count() - 1)
        self._detect()

    def _download_stockfish(self):
        machine = os.environ.get("PROCESSOR_ARCHITEW6432", platform.machine()).lower()
        architecture = {"amd64": "x86-64", "x86_64": "x86-64",
                        "arm64": "arm64", "aarch64": "arm64"}.get(machine)
        if architecture is None:
            self.status.setText("No official Windows development download for this CPU architecture.")
            return
        self._detect_timer.stop()
        self.connection.close()
        self.download = StockfishDownload(self.download_directory, architecture, self)
        self.download.status.connect(self.status.setText)
        self.download.finished.connect(self._download_finished)
        self.setEnabled(False)
        self.download.start()

    def _download_finished(self):
        worker = self.download
        self.download = None
        self.setEnabled(True)
        worker.deleteLater()
        if worker.result is None:
            self.status.setText(f"Stockfish download failed. {worker.error}")
            return
        tag, path = worker.result
        existing = next((profile for profile in self.profiles if Path(profile["path"]) == path), None)
        if existing:
            self.selector.setCurrentIndex(self.selector.findData(existing["id"]))
            self._detect()
        else:
            self._add_profile(str(path), tag)

    def _remove(self):
        p = self._profile()
        if p:
            self.profiles.remove(p)
            self.selector.removeItem(self.selector.currentIndex())

    def _detect(self):
        self._detect_timer.stop()
        p = self._profile()
        if p:
            self._remember()
            self._detect_id = p["id"]
            self.status.setText("Waiting for uci / readyok…")
            try:
                self.connection.launch(p["path"])
            except ValueError as exc:
                self._failed(str(exc))

    def _discovered(self, data):
        p = self._profile()
        if (not p or self._detect_id != p["id"]
                or Path(p["path"]).resolve() != Path(data["path"]).resolve()):
            return
        self._remember()
        p["name"] = data["name"]
        p["options"] = {n: asdict(o) for n, o in data["options"].items()}
        p["options_detected"] = True
        p['options_signature'] = self._signature(p['path'])
        self._ready_status(p)
        self._render(p["options"])
        self.diagnostics.setPlainText("\n".join(self.connection.log))

    def _failed(self, text):
        self.status.setText(text)
        self.diagnostics.setPlainText("\n".join(self.connection.log))

    def _preset(self, threads, hash_mb):
        for name, value in [("Threads", threads), ("Hash", hash_mb)]:
            w = self.widgets.get(name)
            if isinstance(w, QSpinBox):
                w.setValue(min(w.maximum(), max(w.minimum(), value)))

    def _button(self, name):
        if self.connection.phase == "idle":
            self.connection.send("setoption name " + name)
        else:
            self.status.setText("Detect/connect this engine before sending its button option.")

    def _accept(self):
        self._remember()
        if self._profile() and not Path(self._profile()["path"]).is_file():
            QMessageBox.warning(self, "Missing engine", "Choose an existing engine executable.")
            return
        self.accept()

    def done(self, result):
        if self.download is not None:
            return
        self._detect_timer.stop()
        self.connection.close()
        super().done(result)
