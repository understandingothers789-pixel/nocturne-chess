"""One compact entry point for persisted search modes and advertised resources."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
    QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QSpinBox, QVBoxLayout,
)

from ..settings import DEFAULTS
from .engine_resources import resource_option, resource_limits


class EngineSettings(QDialog):
    manage_requested = Signal()

    def __init__(self, config, profiles, parent=None, allocated_hash=0):
        super().__init__(parent)
        self.setWindowTitle("Engine settings")
        self.setMinimumWidth(430)
        self.profiles = profiles
        self.allocated_hash = allocated_hash
        self._config = dict(config)
        self._resources = {}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self.engine = QComboBox()
        for profile in profiles:
            self.engine.addItem(profile.get("label") or profile.get("name") or profile["path"], profile["id"])
        self.engine.setCurrentIndex(max(0, self.engine.findData(config.get("engine_id"))))
        form.addRow("Engine", self.engine)
        self.mode = QComboBox()
        for title, key in (("Node limit", "nodes"), ("Unlimited", "infinite"),
                           ("Time limit", "time"), ("Depth limit", "depth"),
                           ("Combined limits · first reached", "bounded")):
            self.mode.addItem(title, key)
        form.addRow("Normal analysis stops at", self.mode)
        self.normal_nodes = self._nodes(0)
        self.eval_nodes = self._nodes(0)
        self.play_nodes = self._nodes(1)
        form.addRow("Normal nodes per position", self.normal_nodes)
        form.addRow("Auto-evaluation nodes · F12", self.eval_nodes)
        form.addRow("Auto-play nodes per move · F11", self.play_nodes)
        self.seconds = QDoubleSpinBox()
        self.seconds.setRange(0.05, 600)
        self.seconds.setDecimals(2)
        self.seconds.setSuffix(" seconds")
        form.addRow("Search time", self.seconds)
        self.depth = QSpinBox()
        self.depth.setRange(1, 128)
        form.addRow("Search depth", self.depth)
        self.multipv = QSpinBox()
        self.multipv.setRange(1, 5)
        self.multipv.setSuffix(" / 5")
        form.addRow("MultiPV", self.multipv)
        self.threads, self.hash = QSpinBox(), QSpinBox()
        self.hash.setGroupSeparatorShown(True)
        self.hash.setSuffix(" MB")
        form.addRow("Threads", self.threads)
        form.addRow("Hash memory", self.hash)
        self.delay = QSpinBox()
        self.delay.setRange(0, 3000)
        self.delay.setSuffix(" ms")
        form.addRow("Self-play move delay", self.delay)
        self.syzygy = QLineEdit()
        self.syzygy.setPlaceholderText("Optional tablebase folder")
        tablebases = QHBoxLayout()
        tablebases.addWidget(self.syzygy, 1)
        self.browse_tablebases = QPushButton("Browse…")
        self.browse_tablebases.clicked.connect(self._browse_tablebases)
        tablebases.addWidget(self.browse_tablebases)
        form.addRow("Syzygy tablebases", tablebases)
        self.support = QLabel()
        self.support.setWordWrap(True)
        layout.addWidget(self.support)
        more = QPushButton("Choose engines / additional UCI options…")
        more.clicked.connect(self._manage)
        layout.addWidget(more)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                       QDialogButtonBox.StandardButton.Cancel |
                                       QDialogButtonBox.StandardButton.RestoreDefaults)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self.reset_defaults)
        layout.addWidget(self.buttons)
        self.engine.currentIndexChanged.connect(self._profile_changed)
        self.mode.currentIndexChanged.connect(self._sync_mode)
        self._fill(config)
        self._profile_changed()

    @staticmethod
    def _nodes(minimum):
        widget = QSpinBox()
        widget.setRange(minimum, 2_000_000_000)
        widget.setSingleStep(100_000_000)
        widget.setGroupSeparatorShown(True)
        if not minimum:
            widget.setSpecialValueText("Unlimited")
        return widget

    def _fill(self, config):
        self.mode.setCurrentIndex(max(0, self.mode.findData(config.get("analysis_kind"))))
        self.normal_nodes.setValue(config["analysis_nodes"])
        self.eval_nodes.setValue(config["auto_eval_nodes"])
        self.play_nodes.setValue(config["auto_play_nodes"])
        self.seconds.setValue(config["analysis_seconds"])
        self.depth.setValue(config["analysis_depth"])
        self.multipv.setValue(min(5, config["multipv"]))
        self.delay.setValue(config.get("watch_delay_ms", 500))
        self.syzygy.setText(config.get("syzygy_path", ""))
        self._sync_mode()

    def _sync_mode(self):
        mode = self.mode.currentData()
        self.normal_nodes.setEnabled(mode in ("nodes", "bounded"))
        self.seconds.setEnabled(mode in ("time", "bounded"))
        self.depth.setEnabled(mode in ("depth", "bounded"))

    def _profile_changed(self):
        profile = next((p for p in self.profiles if p["id"] == self.engine.currentData()), None)
        self._resources = {}
        for name, widget in (("Threads", self.threads), ("Hash", self.hash)):
            option = resource_option(profile, name)
            widget.setEnabled(bool(option))
            if option:
                minimum, maximum = resource_limits(option, self.allocated_hash)
                widget.setEnabled(maximum >= minimum)
                widget.setRange(minimum, max(minimum, maximum))
                value = int(profile.get("values", {}).get(name, option.default))
                widget.setValue(value)
                widget.setToolTip(f"Engine range: {option.minimum:,}–{option.maximum:,}")
                self._resources[name] = widget
                if name == "Threads":
                    widget.setSuffix(f" / {maximum}")
        option = profile.get("options", {}).get("MultiPV") if profile else None
        maximum = max(1, min(5, int(option.get("maximum", 1)))) if option else 1
        self.multipv.setRange(1, maximum)
        self.multipv.setEnabled(bool(option))
        self.multipv.setSuffix(f" / {maximum}")
        supports_tb = bool(profile and "SyzygyPath" in profile.get("options", {}))
        self.syzygy.setEnabled(supports_tb)
        self.browse_tablebases.setEnabled(supports_tb)
        self.support.setText("Only settings advertised by this engine are enabled. Node limits are independent. "
                             "Disabled time/depth fields do not constrain node-only or unlimited searches.")

    def reset_defaults(self):
        self._fill(DEFAULTS)
        profile = next((p for p in self.profiles if p["id"] == self.engine.currentData()), None)
        for name, widget in self._resources.items():
            option = resource_option(profile, name)
            widget.setValue(int(option.default))

    def values(self):
        mode = self.mode.currentData()
        nodes = self.normal_nodes.value()
        if mode == "nodes" and nodes == 0:
            mode = "infinite"
        return dict(engine_id=self.engine.currentData() or "", analysis_kind=mode,
                    analysis_nodes=nodes, auto_eval_nodes=self.eval_nodes.value(),
                    auto_play_nodes=self.play_nodes.value(), analysis_seconds=self.seconds.value(),
                    analysis_depth=self.depth.value(), multipv=self.multipv.value(),
                    watch_delay_ms=self.delay.value(), syzygy_path=self.syzygy.text().strip())

    def resource_values(self):
        return {name: widget.value() for name, widget in self._resources.items() if widget.isEnabled()}

    def _manage(self):
        self.reject()
        self.manage_requested.emit()

    def _browse_tablebases(self):
        path = QFileDialog.getExistingDirectory(self, "Choose Syzygy tablebase folder", self.syzygy.text())
        if path:
            self.syzygy.setText(path)
