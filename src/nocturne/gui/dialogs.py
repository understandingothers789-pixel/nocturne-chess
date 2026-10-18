"""Compact native dialogs; each exposed setting has a real consumer."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .board import BoardWidget
from .theme import BOARD_THEMES, stylesheet


class NewGameDialog(QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("A new game")
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        title = QLabel("Make time for a game.")
        title.setObjectName("title")
        layout.addWidget(title)
        subtitle = QLabel("Your board. Your pace.")
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)
        layout.addSpacing(18)
        form = QFormLayout()
        form.setSpacing(15)
        self.mode = QComboBox()
        for label, value in (
            ("Play selected UCI engine", "human_ai"),
            ("Two players · local", "human"),
            ("Watch engines", "ai_ai"),
            ("Analysis board", "analysis"),
        ):
            self.mode.addItem(label, value)
        self.mode.setCurrentIndex(max(0, self.mode.findData(config.get("mode", "human_ai"))))
        self.side = QComboBox()
        for label, value in (("White", 1), ("Black", -1), ("Random", 0)):
            self.side.addItem(label, value)
        self.side.setCurrentIndex(max(0, self.side.findData(config.get("human_color", 1))))
        self.difficulty = QComboBox()
        self.difficulty.addItems(["Beginner", "Casual", "Intermediate", "Advanced", "Expert", "Maximum"])
        self.difficulty.setCurrentText(config.get("difficulty", "Intermediate"))
        self.minutes = QComboBox()
        for label, seconds in (
            ("No clock", 0),
            ("1 minute", 60),
            ("3 minutes", 180),
            ("5 minutes", 300),
            ("10 minutes", 600),
            ("15 minutes", 900),
            ("30 minutes", 1800),
        ):
            self.minutes.addItem(label, seconds)
        self.minutes.setCurrentIndex(max(0, self.minutes.findData(config.get("seconds", 0))))
        self.increment = QSpinBox()
        self.increment.setRange(0, 60)
        self.increment.setSuffix(" sec / move")
        self.increment.setValue(config.get("increment", 0))
        self.takebacks = QCheckBox("Allow takebacks")
        self.takebacks.setChecked(config.get("takebacks", True))
        self.white = QLineEdit(config.get("white_name", "White"))
        self.black = QLineEdit(config.get("black_name", "Black"))
        self.white_engine = QComboBox()
        self.black_engine = QComboBox()
        for combo in (self.white_engine, self.black_engine):
            combo.addItem("Selected external UCI profile", "external")
        self.white_engine.setCurrentIndex(
            max(0, self.white_engine.findData(config.get("white_engine", "custom")))
        )
        self.black_engine.setCurrentIndex(
            max(0, self.black_engine.findData(config.get("black_engine", "custom")))
        )
        form.addRow("Mode", self.mode)
        form.addRow("Your pieces", self.side)
        form.addRow("Clock", self.minutes)
        form.addRow("Increment", self.increment)
        form.addRow("White player", self.white)
        form.addRow("Black player", self.black)
        form.addRow("White engine", self.white_engine)
        form.addRow("Black / opponent engine", self.black_engine)
        form.addRow("", self.takebacks)
        layout.addLayout(form)
        note = QLabel(
            "Uses your selected UCI engine profile and bounded search settings.\nNo engine is downloaded or bundled."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Start game")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.mode.currentIndexChanged.connect(self._enabled)
        self._enabled()

    def _enabled(self):
        mode = self.mode.currentData()
        self.side.setEnabled(mode == "human_ai")
        self.difficulty.setEnabled(mode in ("human_ai", "ai_ai"))
        self.white_engine.setEnabled(mode == "ai_ai")
        self.black_engine.setEnabled(mode in ("human_ai", "ai_ai"))
        for widget in (self.minutes, self.increment):
            widget.setEnabled(mode != "analysis")

    def config(self) -> dict:
        return {
            "mode": self.mode.currentData(),
            "human_color": self.side.currentData(),
            "difficulty": self.difficulty.currentText(),
            "seconds": self.minutes.currentData(),
            "increment": self.increment.value(),
            "takebacks": self.takebacks.isChecked(),
            "white_name": self.white.text().strip() or "White",
            "black_name": self.black.text().strip() or "Black",
            "white_engine": self.white_engine.currentData(),
            "black_engine": self.black_engine.currentData(),
        }


class SettingsDialog(QDialog):
    appearance_changed = Signal(dict)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Studio settings")
        self.setMinimumWidth(780)
        self.resize(860, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        title = QLabel("Make yourself at home.")
        title.setObjectName("title")
        layout.addWidget(title)
        content = QHBoxLayout()
        preview_column = QVBoxLayout()
        self.preview = BoardWidget()
        self.preview.setAccessibleName("Appearance preview chessboard")
        self.preview.setMinimumSize(260, 260)
        self.preview.setMaximumWidth(330)
        self.preview.interactive = False
        if parent is not None and hasattr(parent, "game"):
            self.preview.set_position(parent.game.board, parent.board_view.last_move)
            self.preview.set_recommendations(parent.board_view.recommendations)
            self.preview.candidate_style = parent.board_view.candidate_style
        preview_column.addWidget(self.preview, 1)
        caption = QLabel("Live preview · Save to keep your choices.\nCancel restores your previous appearance.")
        caption.setWordWrap(True)
        caption.setObjectName("muted")
        preview_column.addWidget(caption)
        content.addLayout(preview_column)
        controls = QWidget()
        form = QFormLayout(controls)
        form.setSpacing(14)
        self.theme = QComboBox()
        self.theme.addItems(BOARD_THEMES)
        self.theme.setCurrentText(config.get("theme", "Classic"))
        form.addRow("Board palette", self.theme)
        self.pieces = QComboBox()
        self.pieces.addItems(["Nibbler", "Cburnett", "Original"])
        self.pieces.setCurrentText(config.get("piece_set", "Nibbler"))
        form.addRow("Piece style", self.pieces)
        self.checks = {}
        for key, label, default in (
            ("light", "Light appearance", False),
            ("coordinates", "Show coordinates", True),
            ("animations", "Animate moves", True),
            ("overlays", "Show analysis arrows and evaluation", True),
        ):
            check = QCheckBox(label)
            check.setChecked(config.get(key, default))
            self.checks[key] = check
            form.addRow("", check)
        self.hash = QSpinBox()
        self.hash.setRange(1, 65536)
        self.hash.setValue(config.get("hash_mb", 32))
        self.hash.setSuffix(" MB · budget")
        self.depth = QSpinBox()
        self.depth.setRange(1, 128)
        self.depth.setValue(config.get("analysis_depth", 8))
        form.addRow("Analysis depth limit", self.depth)
        self.seconds = QDoubleSpinBox()
        self.seconds.setRange(0.05, 600)
        self.seconds.setSingleStep(0.5)
        self.seconds.setValue(config.get("analysis_seconds", 3.0))
        self.seconds.setSuffix(" sec")
        form.addRow("Bounded analysis time", self.seconds)
        self.nodes = QSpinBox()
        self.nodes.setRange(0, 2_000_000_000)
        self.nodes.setSpecialValueText("No node cap")
        self.nodes.setValue(config.get("analysis_nodes", 0))
        form.addRow("Analysis nodes", self.nodes)
        self.delay = QSpinBox()
        self.delay.setRange(0, 3000)
        self.delay.setSingleStep(100)
        self.delay.setValue(config.get("watch_delay_ms", 500))
        self.delay.setSuffix(" ms")
        form.addRow("Watch-mode move delay", self.delay)
        engine_row = QHBoxLayout()
        self.external = QLineEdit(config.get("external_path", ""))
        self.external.setPlaceholderText("Optional installed UCI executable")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        engine_row.addWidget(self.external)
        engine_row.addWidget(browse)
        tb_row = QHBoxLayout()
        self.syzygy = QLineEdit(config.get("syzygy_path", ""))
        self.syzygy.setPlaceholderText("Folder with .rtbw and .rtbz files")
        tb_browse = QPushButton("Browse…")
        tb_browse.clicked.connect(self._browse_syzygy)
        tb_row.addWidget(self.syzygy)
        tb_row.addWidget(tb_browse)
        form.addRow("Syzygy tablebases", tb_row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(controls)
        content.addWidget(scroll, 1)
        layout.addLayout(content, 1)
        note = QLabel(
            "Threads, Hash and other engine options are in Engine profiles.\nTime/depth/node limits apply to bounded analysis and game review."
        )
        note.setObjectName("muted")
        layout.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.theme.currentTextChanged.connect(self._preview_appearance)
        self.pieces.currentTextChanged.connect(self._preview_appearance)
        for check in self.checks.values():
            check.toggled.connect(self._preview_appearance)
        self._preview_appearance()

    def appearance(self):
        return {"theme": self.theme.currentText(), "piece_set": self.pieces.currentText(),
                **{k: c.isChecked() for k, c in self.checks.items()}}

    def _preview_appearance(self, *_):
        appearance = self.appearance()
        self.setStyleSheet(stylesheet(appearance["light"]))
        self.preview.theme = appearance["theme"]
        self.preview.set_piece_set(appearance["piece_set"])
        for key in ("light", "coordinates", "animations", "overlays"):
            setattr(self.preview, key, appearance[key])
        self.preview.update()
        self.appearance_changed.emit(appearance)

    def _browse(self):
        file, _ = QFileDialog.getOpenFileName(
            self, "Select a trusted UCI engine executable", "", "Executables (*.exe);;All files (*)"
        )
        if file:
            self.external.setText(file)

    def _browse_syzygy(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Choose Syzygy tablebase folder", self.syzygy.text()
        )
        if directory:
            self.syzygy.setText(directory)

    def config(self):
        return {
            **self.appearance(),
            "analysis_nodes": self.nodes.value(),
            "analysis_depth": self.depth.value(),
            "analysis_seconds": self.seconds.value(),
            "external_path": self.external.text().strip(),
            "watch_delay_ms": self.delay.value(),
            "syzygy_path": self.syzygy.text().strip(),
        }


class TextDialog(QDialog):
    def __init__(self, title: str, caption: str, text="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(620, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        label = QLabel(caption)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.editor = QPlainTextEdit(text)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.editor)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
