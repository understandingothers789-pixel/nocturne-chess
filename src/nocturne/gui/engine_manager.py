"""Engine-advertised option editor and persistent executable profiles."""

from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

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

from .uci_connection import UciConnection


class EngineManager(QDialog):
    def __init__(self, profiles, selected="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("UCI engine profiles")
        self.resize(720, 650)
        self.profiles = [{**p, "values": dict(p.get("values", {}))} for p in profiles]
        self.selected = selected
        self.connection = UciConnection(self)
        self.connection.discovered.connect(self._discovered)
        self.connection.failed.connect(self._failed)
        self.widgets = {}
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
        self.label = QLineEdit()
        self.path = QLineEdit()
        self.path.setReadOnly(True)
        form = QFormLayout()
        form.addRow("Profile name", self.label)
        form.addRow("Executable", self.path)
        layout.addLayout(form)
        self.status = QLabel("Select an installed executable. No engine is downloaded.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        presets = QHBoxLayout()
        for name, threads, hash_mb in [
            ("Casual", 2, 256),
            ("Balanced", 6, 1024),
            ("Maximum / PV 1", 8, 4096),
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

    def _select(self):
        self._remember()
        p = self._profile()
        self.selected = p["id"] if p else ""
        self.label.setText(p.get("label", p.get("name", "")) if p else "")
        self.path.setText(p["path"] if p else "")
        self._render(p.get("options", {}) if p else {})

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

                    budget = hash_budget_mb()
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

    def _add(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose your UCI engine", "", "Executables (*.exe);;All files (*)"
        )
        if not path:
            return
        self._remember()
        p = {
            "id": str(uuid4()),
            "path": path,
            "name": Path(path).stem,
            "label": Path(path).stem,
            "values": {},
            "options": {},
        }
        self.profiles.append(p)
        self.selector.addItem(p["label"], p["id"])
        self.selector.setCurrentIndex(self.selector.count() - 1)
        self._detect()

    def _remove(self):
        p = self._profile()
        if p:
            self.profiles.remove(p)
            self.selector.removeItem(self.selector.currentIndex())

    def _detect(self):
        p = self._profile()
        if p:
            self._remember()
            self.status.setText("Waiting for uci / readyok…")
            try:
                self.connection.launch(p["path"])
            except ValueError as exc:
                self._failed(str(exc))

    def _discovered(self, data):
        p = self._profile()
        if not p or p["path"] != data["path"]:
            return
        p["name"] = data["name"]
        p["options"] = {n: asdict(o) for n, o in data["options"].items()}
        self.status.setText(data["name"] + " · ready · " + str(len(data["options"])) + " advertised options")
        self._render(p["options"])
        self.diagnostics.setPlainText("\n".join(self.connection.log))

    def _failed(self, text):
        self.status.setText(text)
        self.diagnostics.setPlainText("\n".join(self.connection.log))

    def _preset(self, threads, hash_mb):
        for name, value in [("Threads", threads), ("Hash", hash_mb), ("MultiPV", 1)]:
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
        self.connection.close()
        super().done(result)
