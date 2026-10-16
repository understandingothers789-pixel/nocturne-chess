"""The desktop shell. The game model remains the sole rules authority."""

from __future__ import annotations

from pathlib import Path
import json
import random

from PySide6.QtCore import QEvent, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QDialog, QDialogButtonBox, QFileDialog,
    QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QMenu, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from .. import __version__
from ..core.board import Board, Move, SQUARES
from ..core.game import Game, TimeControl
from ..core.notation import parse_san, san
from ..engine.evaluate import evaluate
from ..engine.search import SearchLimits, difficulty_limits, score_text
from ..settings import normalize
from ..storage import Store, StorageError
from .board import BoardWidget
from .dialogs import NewGameDialog, SettingsDialog, TextDialog
from .engine import EngineController
from .theme import ASSETS, stylesheet
from .widgets import EvaluationBar, EvaluationGraph


def label(text: str, style: str = "", wrap=False) -> QLabel:
    widget = QLabel(text)
    if style:
        widget.setObjectName(style)
    widget.setWordWrap(wrap)
    return widget


def button(text, callback, style=""):
    widget = QPushButton(text)
    if style:
        widget.setObjectName(style)
    widget.clicked.connect(callback)
    return widget


class MainWindow(QMainWindow):
    def __init__(self, data_dir: Path | None = None):
        super().__init__()
        self._closing = False
        self.setWindowTitle(f"Nocturne Chess · {__version__}")
        self.setWindowIcon(QIcon(str(ASSETS / "icon.svg")))
        self.resize(1340, 920)
        self.setMinimumSize(1024, 660)
        location = data_dir or Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
        self.store: Store | None = None
        self._storage_message = ""
        try:
            self.store = Store(location / "nocturne.db")
        except (StorageError, OSError) as exc:
            self._storage_message = str(exc)
        self.config = normalize(self.store.get("settings", {}) if self.store else {})
        self.config.setdefault("mode", "human_ai")
        self.config.setdefault("human_color", 1)
        self.game = Game()
        self.game.metadata = self.config.copy()
        self.paused = False
        if self.store:
            try:
                resumed = self.store.resume()
                if resumed:
                    self.game = resumed
                    self._load_game_config()
                    self.paused = True
            except StorageError as exc:
                self._storage_message = str(exc)
        self.analysis_mode = self.config.get("mode") == "analysis"
        if self.analysis_mode:
            self.paused = False
        self._analysis_enabled = self.analysis_mode
        self._job = None
        self._lab = None
        self._benchmark_report = None
        self._last_info = None
        self._history_signature = None
        self._build()
        self.engine = EngineController(self)
        self.engine.message.connect(self._engine_message)
        self._shortcuts()
        self._apply_settings()
        self.pause_button.setText("Continue" if self.paused else "Pause")
        self._refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(100)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self._save)
        self.autosave_timer.start(15000)
        if self._storage_message:
            QTimer.singleShot(0, lambda: self._error("Library unavailable", self._storage_message))
        QTimer.singleShot(100, self._schedule_engine)

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(164)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(15, 25, 15, 20)
        nav.setSpacing(8)
        logo = QLabel()
        logo.setPixmap(QIcon(str(ASSETS / "icon.svg")).pixmap(45, 45))
        nav.addWidget(logo)
        brand = label("NOCTURNE")
        brand.setStyleSheet("font-size: 15px; font-weight: 700; letter-spacing: 1.7px;")
        nav.addWidget(brand)
        nav.addWidget(label("C H E S S  S T U D I O", "eyebrow"))
        nav.addSpacing(35)
        self.play_nav = button("◈   Play", lambda: self._workspace(False), "nav")
        self.analysis_nav = button("⌁   Analysis", lambda: self._workspace(True), "nav")
        self.play_nav.setCheckable(True)
        self.analysis_nav.setCheckable(True)
        nav_group = QButtonGroup(self)
        nav_group.addButton(self.play_nav)
        nav_group.addButton(self.analysis_nav)
        self.play_nav.setChecked(True)
        nav.addWidget(self.play_nav)
        nav.addWidget(self.analysis_nav)
        nav.addWidget(button("▤   Library", self._library, "nav"))
        nav.addWidget(button("◷   Engine lab", self._engine_lab, "nav"))
        nav.addStretch()
        nav.addWidget(label("A quieter place\nto think.", "muted"))
        nav.addSpacing(18)
        nav.addWidget(button("⚙   Settings", self._settings, "nav"))
        nav.addWidget(label(f"v{__version__}  ·  OFFLINE", "eyebrow"))
        layout.addWidget(sidebar)
        content = QVBoxLayout()
        content.setContentsMargins(25, 22, 25, 12)
        content.setSpacing(15)
        top = QHBoxLayout()
        heading = QVBoxLayout()
        self.title_label = label("Your next move.", "title")
        self.subtitle_label = label("Find your focus. Enjoy the game.", "subtitle")
        heading.addWidget(self.title_label)
        heading.addWidget(self.subtitle_label)
        top.addLayout(heading)
        top.addStretch()
        top.addWidget(button("＋  New game", self._new_game, "primary"))
        content.addLayout(top)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        arena = QWidget()
        board_layout = QVBoxLayout(arena)
        board_layout.setContentsMargins(0, 0, 0, 0)
        board_layout.setSpacing(0)
        self.top_card, self.top_name, self.top_detail, self.top_clock = self._player_card()
        board_layout.addWidget(self.top_card)
        self.board_view = BoardWidget()
        self.board_view.move_requested.connect(self._human_move)
        board_row = QHBoxLayout()
        board_row.setContentsMargins(0, 0, 0, 0)
        board_row.setSpacing(0)
        self.eval_bar = EvaluationBar()
        self.eval_bar.board_view = self.board_view
        board_row.addWidget(self.eval_bar)
        board_row.addWidget(self.board_view, 1)
        board_layout.addLayout(board_row, 1)
        self.bottom_card, self.bottom_name, self.bottom_detail, self.bottom_clock = self._player_card()
        board_layout.addWidget(self.bottom_card)
        board_tools = QHBoxLayout()
        board_tools.addWidget(label("Drag a piece or select a square", "muted"))
        board_tools.addStretch()
        board_tools.addWidget(button("⇅  Flip", self._flip, "quiet"))
        board_tools.addWidget(button("Copy FEN", self._copy_fen, "quiet"))
        board_layout.addLayout(board_tools)
        splitter.addWidget(arena)
        self.panel = QFrame()
        self.panel.setObjectName("panel")
        self.panel.setMinimumWidth(310)
        self.panel.setMaximumWidth(420)
        side = QVBoxLayout(self.panel)
        side.setContentsMargins(20, 16, 20, 12)
        side.setSpacing(10)
        side.addWidget(label("THE GAME", "eyebrow"))
        self.mode_label = label("Two players", "score")
        side.addWidget(self.mode_label)
        self.status_label = label("White to move", "subtitle", True)
        side.addWidget(self.status_label)
        self.tabs = QTabWidget()
        moves_page = QWidget()
        moves_layout = QVBoxLayout(moves_page)
        moves_layout.setContentsMargins(0, 10, 0, 0)
        self.history = QTableWidget(0, 3)
        self.history.setHorizontalHeaderLabels(["#", "White", "Black"])
        self.history.verticalHeader().hide()
        self.history.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.history.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.history.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history.setShowGrid(False)
        self.history.cellClicked.connect(self._history_clicked)
        moves_layout.addWidget(self.history, 1)
        navigation = QHBoxLayout()
        self.first_button = button("|‹", lambda: self._navigate(0))
        self.undo_button = button("‹", self._undo)
        self.redo_button = button("›", self._redo)
        self.last_button = button("›|", lambda: self._navigate(len(self.game.moves)))
        for widget, name in ((self.first_button, "First position"), (self.undo_button, "Take back"),
                             (self.redo_button, "Next move"), (self.last_button, "Latest position")):
            widget.setAccessibleName(name)
        for widget in (self.first_button, self.undo_button, self.redo_button, self.last_button):
            navigation.addWidget(widget)
        moves_layout.addLayout(navigation)
        self.tabs.addTab(moves_page, "Moves")
        engine_page = QWidget()
        engine_page_layout = QVBoxLayout(engine_page)
        engine_page_layout.setContentsMargins(0, 12, 0, 0)
        engine_page_layout.setSpacing(8)
        engine_scroll = QScrollArea()
        engine_scroll.setWidgetResizable(True)
        engine_scroll.setFrameShape(QFrame.Shape.NoFrame)
        engine_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        engine_detail = QWidget()
        self.engine_layout = QVBoxLayout(engine_detail)
        self.engine_layout.setContentsMargins(0, 15, 0, 0)
        self.eval_label = label("—", "score")
        self.engine_layout.addWidget(self.eval_label)
        self.engine_state = label("Nocturne engine", "subtitle", True)
        self.engine_layout.addWidget(self.engine_state)
        self.telemetry = label("Independent rules · native desktop", "muted", True)
        self.engine_layout.addWidget(self.telemetry)
        self.pv_label = label("", "muted", True)
        self.engine_layout.addWidget(self.pv_label)
        self.engine_layout.addWidget(label("SAMPLED EVALUATION · WHITE", "eyebrow"))
        self.graph = EvaluationGraph()
        self.graph.position_requested.connect(self._navigate)
        self.engine_layout.addWidget(self.graph)
        self.engine_layout.addStretch()
        engine_scroll.setWidget(engine_detail)
        engine_page_layout.addWidget(engine_scroll, 1)
        self.analysis_source = QComboBox()
        self.analysis_source.addItem("Nocturne · independent engine", "custom")
        engine_page_layout.addWidget(self.analysis_source)
        self.analyze_button = button("Analyze position", self._analyze, "primary")
        engine_page_layout.addWidget(self.analyze_button)
        self.tabs.addTab(engine_page, "Engine")
        pgn_page = QWidget()
        pgn_layout = QVBoxLayout(pgn_page)
        pgn_layout.setContentsMargins(0, 10, 0, 0)
        pgn_layout.addWidget(label("Paste PGN or a line of SAN moves, then apply.", "muted", True))
        self.pgn_editor = QPlainTextEdit()
        self.pgn_editor.installEventFilter(self)
        self.pgn_editor.setAccessibleName("PGN game text")
        self.pgn_editor.setPlaceholderText("1. e4 e5 2. Nf3 Nc6 *")
        self.pgn_editor.setMinimumHeight(100)
        pgn_layout.addWidget(self.pgn_editor, 1)
        self.apply_pgn_button = button("Apply PGN", self._apply_pgn, "primary")
        self.load_pgn_button = button("Load current", self._load_current_pgn)
        self.load_pgn_button.setAccessibleName("Load current game into PGN editor")
        pgn_actions = QHBoxLayout()
        pgn_actions.addWidget(self.apply_pgn_button)
        pgn_actions.addWidget(self.load_pgn_button)
        pgn_layout.addLayout(pgn_actions)
        self.tabs.addTab(pgn_page, "PGN")
        self._pgn_game_id = None
        side.addWidget(self.tabs, 1)
        self.pause_button = button("Pause", self._pause)
        side.addWidget(self.pause_button)
        actions = QHBoxLayout()
        self.draw_button = button("Draw", self._draw)
        self.resign_button = button("Resign", self._resign)
        actions.addWidget(self.draw_button)
        actions.addWidget(self.resign_button)
        side.addLayout(actions)
        io = QHBoxLayout()
        io.addWidget(button("Paste FEN / PGN", self._load_clipboard, "quiet"))
        io.addWidget(button("Copy PGN", self._copy_pgn, "quiet"))
        side.addLayout(io)
        self.save_label = label("Games stay on this device", "eyebrow")
        self.save_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side.addWidget(self.save_label)
        splitter.addWidget(self.panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([720, 350])
        content.addWidget(splitter, 1)
        layout.addLayout(content, 1)
        self.statusBar().showMessage("Ready · Nocturne Chess · Offline by design")

    def _player_card(self):
        frame = QFrame()
        frame.setObjectName("playerCard")
        row = QHBoxLayout(frame)
        row.setContentsMargins(17, 12, 17, 12)
        avatar = label("♙")
        avatar.setStyleSheet("font-size: 27px; color: #a8c397;")
        row.addWidget(avatar)
        names = QVBoxLayout()
        names.setSpacing(4)
        name = label("White")
        name.setStyleSheet("font-size: 15px; font-weight: 600;")
        detail = label("Ready", "muted")
        names.addWidget(name)
        names.addWidget(detail)
        row.addLayout(names, 1)
        clock = label("∞", "clock")
        row.addWidget(clock)
        return frame, name, detail, clock

    def _shortcuts(self):
        self.menuBar().setNativeMenuBar(False)
        self.menu_actions = {}
        self.display_actions = {}

        def add(menu, text, callback, keys=None, name=None):
            action = QAction(text, self)
            if keys:
                action.setShortcut(QKeySequence(keys))
            action.triggered.connect(callback)
            menu.addAction(action)
            self.menu_actions[name or text] = action
            return action

        file = self.menuBar().addMenu("&File")
        add(file, "New game…", self._new_game, "Ctrl+N")
        add(file, "Open PGN…", self._open_pgn, "Ctrl+O")
        add(file, "Load FEN / PGN from clipboard", self._load_clipboard, "Ctrl+Shift+V", "load_clipboard")
        add(file, "Edit / paste PGN…", self._show_pgn, "Ctrl+I")
        add(file, "Enter FEN / PGN…", self._import_menu)
        file.addSeparator()
        add(file, "Save this game as PGN…", self._export, "Ctrl+E")
        add(file, "Write PGN to clipboard", self._copy_pgn, "Ctrl+Shift+P", "copy_pgn")
        add(file, "Write FEN to clipboard", self._copy_fen, "Ctrl+Shift+C")
        add(file, "Save to library", self._save, "Ctrl+S")
        add(file, "Game library…", self._library)
        file.addSeparator()
        add(file, "Quit", self.close, "Ctrl+Q")

        tree = self.menuBar().addMenu("&Tree")
        add(tree, "Root", lambda: self._navigate(0), "Home")
        add(tree, "End", lambda: self._navigate(len(self.game.moves)), "End")
        add(tree, "Backward", self._undo, "Left")
        add(tree, "Forward", self._redo, "Right")

        analysis = self.menuBar().addMenu("&Analysis")
        add(analysis, "Go", self._start_analysis, "Ctrl+G")
        add(analysis, "Halt", self._halt_analysis, "Ctrl+H")
        add(analysis, "Engine performance…", self._engine_lab)

        display = self.menuBar().addMenu("&Display")
        add(display, "Flip board", self._flip, "F")
        add(display, "Clear arrows and marks", self.board_view.clear_annotations, "Escape")
        display.addSeparator()
        for key, text in (("coordinates", "Coordinates"), ("overlays", "Analysis overlays"),
                          ("animations", "Move animations"), ("light", "Light appearance")):
            action = add(display, text, lambda checked, k=key: self._set_display(k, checked))
            action.setCheckable(True)
            self.display_actions[key] = action
        add(display, "Board appearance…", self._settings)

        engine = self.menuBar().addMenu("&Engine")
        add(engine, "Choose engine…", self._choose_engine)
        add(engine, "Engine settings…", self._settings)
        play = self.menuBar().addMenu("&Play")
        add(play, "New game…", self._new_game)
        add(play, "Pause / continue", self._pause, "Space")
        add(play, "Offer / claim draw…", self._draw)
        add(play, "Resign…", self._resign)
        # Retain explicit references for menu state and interaction checks.
        self.menus = {"File": file, "Tree": tree, "Analysis": analysis,
                      "Display": display, "Engine": engine, "Play": play}

    def _set_display(self, key, value):
        self.config[key] = value
        self._apply_settings()
        self._save()

    def eventFilter(self, watched, event):
        if (watched is getattr(self, "pgn_editor", None)
                and event.type() == QEvent.Type.ShortcutOverride
                and event.modifiers() in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier)):
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def _choose_engine(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose UCI engine", "", "Executables (*.exe);;All files (*)")
        if path:
            self._stop_engine()
            self.config["external_path"] = path
            self._apply_settings()
            self.analysis_source.setCurrentIndex(1)
            self._save()
            self._schedule_engine()

    def _apply_settings(self):
        QApplication.instance().setStyleSheet(stylesheet(self.config.get("light", False)))
        self.board_view.theme = self.config.get("theme", "Forest")
        self.board_view.coordinates = self.config.get("coordinates", True)
        self.board_view.animations = self.config.get("animations", True)
        self.board_view.overlays = self.config.get("overlays", True)
        self.graph.light = self.config.get("light", False)
        self.eval_bar.setVisible(self.board_view.overlays)
        for key, action in self.display_actions.items():
            action.setChecked(bool(self.config.get(key, False)))
        self.analysis_source.clear()
        self.analysis_source.addItem("Nocturne · independent engine", "custom")
        if self.config.get("external_path"):
            self.analysis_source.addItem("External UCI engine", "external")
        self.board_view.update()

    def _human_move(self, move: Move):
        if not self.board_view.interactive:
            return
        self._stop_engine()
        if not self.analysis_mode:
            self.game.start_clock()
        try:
            self.game.play(move)
        except ValueError as exc:
            self.statusBar().showMessage(str(exc), 4000)
            return
        self._refresh(animate=True)
        self._save()
        self._schedule_engine()

    def _refresh(self, animate=False):
        if self._pgn_game_id != self.game.id or not self.pgn_editor.document().isModified():
            text = self.game.pgn()
            if self.pgn_editor.toPlainText() != text:
                self.pgn_editor.setPlainText(text)
            self.pgn_editor.document().setModified(False)
            self._pgn_game_id = self.game.id
        last = self.game.moves[self.game.cursor - 1] if self.game.cursor else None
        self.board_view.set_position(self.game.board, last, animate)
        outcome = self.game.outcome
        self.board_view.interactive = not outcome and not self.paused and (self.analysis_mode or not self._is_engine_turn())
        turn = "White" if self.game.board.turn == 1 else "Black"
        status = f"{outcome.result} · {outcome.reason}" if outcome else f"{turn} to move" + (" · Check" if self.game.board.in_check() else "")
        self.status_label.setText(status)
        mode = self.config.get("mode", "human_ai")
        self.mode_label.setText("Analysis" if self.analysis_mode else {
            "human_ai": "Play Nocturne" if self.config.get("black_engine", "custom") == "custom" else "Play UCI engine",
            "human": "Two players", "ai_ai": "Engine theatre", "analysis": "Analysis"}.get(mode, "Two players"))
        if self.paused and not outcome:
            self.status_label.setText("Paused · Continue when you're ready")
        self.graph.set_samples(self.game.evaluations, self.game.cursor, len(self.game.moves))
        if not self.engine.busy:
            self.eval_bar.set_score(self.game.evaluations.get(self.game.cursor))
        signature = tuple(self.game.sans)
        if signature != self._history_signature:
            self._history_signature = signature
            # Honor a FEN that starts with Black to move or at a later move number.
            initial = Board(self.game.initial_fen)
            self._history_cells = {}
            self.history.setRowCount(0)
            row = -1
            for index, notation in enumerate(self.game.sans):
                if initial.turn == 1 or row == -1:
                    row += 1
                    self.history.insertRow(row)
                    self.history.setItem(row, 0, QTableWidgetItem(str(initial.fullmove)))
                column = 1 if initial.turn == 1 else 2
                self.history.setItem(row, column, QTableWidgetItem(notation))
                self._history_cells[(row, column)] = index + 1
                initial.push(self.game.moves[index])
        self.history.clearSelection()
        for (row, column), cursor in getattr(self, "_history_cells", {}).items():
            if cursor == self.game.cursor:
                self.history.setCurrentCell(row, column)
                self.history.scrollToItem(self.history.item(row, column))
        takebacks = self.analysis_mode or self.config.get("takebacks", True)
        self.undo_button.setEnabled(self.game.cursor > 0 and takebacks)
        self.first_button.setEnabled(self.game.cursor > 0 and takebacks)
        self.redo_button.setEnabled(self.game.cursor < len(self.game.moves))
        self.last_button.setEnabled(self.game.cursor < len(self.game.moves))
        for widget in (self.draw_button, self.resign_button, self.pause_button):
            widget.setEnabled(not outcome and not self.analysis_mode)
        self._update_players()

    def _update_players(self):
        top_color = 1 if self.board_view.flipped else -1
        values = self.game.clock_values()
        material = sum((1 if self.game.board.cells[s] > 0 else -1) * (0, 1, 3, 3, 5, 9, 0)[abs(self.game.board.cells[s])]
                       for s in SQUARES if self.game.board.cells[s])
        for color, name, detail, clock in ((top_color, self.top_name, self.top_detail, self.top_clock),
                                            (-top_color, self.bottom_name, self.bottom_detail, self.bottom_clock)):
            name.setText(self.game.headers.get("White" if color == 1 else "Black", "Player"))
            balance = material * color
            detail.setText(("White pieces" if color == 1 else "Black pieces") + (f"  ·  +{balance}" if balance > 0 else ""))
            clock.setText(self._clock_text(values[color]) if self.game.time_control.seconds else "∞")
            active = self.game.running and self.game.board.turn == color
            style = "activeClock" if active else "clock"
            if clock.objectName() != style:
                clock.setObjectName(style)
                clock.style().unpolish(clock)
                clock.style().polish(clock)

    @staticmethod
    def _clock_text(seconds):
        minutes = int(seconds) // 60
        return f"{minutes:02d}:{int(seconds) % 60:02d}" if seconds >= 10 else f"0:{seconds:04.1f}"

    def _tick(self):
        if self.game.running and self.game.tick():
            self._stop_engine()
            self._refresh()
            self._save()
        self._update_players()

    def _new_game(self):
        self._stop_engine()
        self.game.pause_clock()
        dialog = NewGameDialog(self.config, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            if not self.paused and not self.analysis_mode:
                self.game.start_clock()
            self._schedule_engine()
            return
        self._save()
        self.config.update(dialog.config())
        self._create_game()

    def _create_game(self):
        self._stop_engine()
        mode = self.config.get("mode", "human_ai")
        if self.config.get("human_color", 1) == 0:
            self.config["human_color"] = random.choice((1, -1))
        control = TimeControl() if mode == "analysis" else TimeControl(self.config.get("seconds", 0), self.config.get("increment", 0))
        self.game = Game(time_control=control)
        names = {1: self.config.get("white_name", "White"), -1: self.config.get("black_name", "Black")}
        if mode == "human_ai":
            human = self.config.get("human_color", 1)
            if names[human] in ("White", "Black", ""):
                names[human] = "You"
            if names[-human] in ("White", "Black", ""):
                names[-human] = "Nocturne" if self.config.get("black_engine", "custom") == "custom" else "UCI engine"
        elif mode == "ai_ai":
            for color in (1, -1):
                if names[color] in ("White", "Black", ""):
                    key = "white_engine" if color == 1 else "black_engine"
                    names[color] = "Nocturne" if self.config.get(key, "custom") == "custom" else "UCI engine"
        self.game.headers.update({"White": names[1], "Black": names[-1]})
        self.game.metadata = self.config.copy()
        self.paused = False
        self.pause_button.setText("Pause")
        self._history_signature = None
        self.board_view.flipped = mode == "human_ai" and self.config.get("human_color") == -1
        self.eval_bar.flipped = self.board_view.flipped
        self._workspace(mode == "analysis")
        if mode != "analysis":
            self.game.start_clock()
        self._refresh()
        self._save()
        self._schedule_engine()

    def _workspace(self, analysis):
        self._stop_engine()
        if analysis:
            self._ensure_analysis_copy()
        self.analysis_mode = analysis
        self._analysis_enabled = analysis
        if analysis:
            self.paused = False
            self.pause_button.setText("Pause")
            self.game.pause_clock()
        elif not self.paused:
            if self.config.get("mode") == "analysis":
                self.config["mode"] = "human"
            self.game.metadata["mode"] = self.config.get("mode", "human")
            self.game.start_clock()
        self.analysis_nav.setChecked(analysis)
        self.play_nav.setChecked(not analysis)
        self.title_label.setText("Room to explore." if analysis else "Your next move.")
        self.subtitle_label.setText("Follow an idea. Try another line." if analysis else "Find your focus. Enjoy the game.")
        self._refresh()
        self._schedule_engine()

    def _undo(self):
        if not self.analysis_mode and not self.config.get("takebacks", True):
            return
        self._stop_engine()
        if self.game.undo():
            if not self.analysis_mode and self.config.get("mode") == "human_ai":
                if self.game.board.turn != self.config.get("human_color", 1) and self.game.cursor:
                    self.game.undo()
            self._refresh()
            self._save()
            self._schedule_engine()

    def _redo(self):
        if self.game.cursor >= len(self.game.moves):
            return
        self._stop_engine()
        self._ensure_analysis_copy()
        if self.game.redo():
            if not self.analysis_mode:
                self.analysis_mode = True
                self._analysis_enabled = True
            self.paused = False
            self._refresh()
            self._save()
            self._schedule_engine()

    def _navigate(self, cursor):
        if not self.analysis_mode and not self.config.get("takebacks", True):
            return
        self._stop_engine()
        self._ensure_analysis_copy()
        self.game.navigate(cursor)
        self.analysis_mode = True
        self._analysis_enabled = True
        self.paused = False
        self.analysis_nav.setChecked(True)
        self.title_label.setText("Room to explore.")
        self._refresh()
        self._schedule_engine()

    def _history_clicked(self, row, column):
        if cursor := getattr(self, "_history_cells", {}).get((row, column)):
            self._navigate(cursor)

    def _flip(self):
        self.board_view.flip()
        self.eval_bar.flipped = self.board_view.flipped
        self.eval_bar.update()
        self._update_players()

    def _pause(self):
        self._stop_engine()
        self.paused = not self.paused
        if self.paused:
            self.game.pause_clock()
        else:
            self.game.start_clock()
        self.pause_button.setText("Continue" if self.paused else "Pause")
        self._refresh()
        self._schedule_engine()

    def _draw(self):
        reasons = self.game.board.claimable_draws()
        if reasons:
            self._stop_engine()
            self.game.claim_draw()
        else:
            menu = QMenu(self)
            claim = menu.addAction("Claim with an intended move…")
            offer = menu.addAction("Offer a draw")
            action = menu.exec(self.draw_button.mapToGlobal(self.draw_button.rect().bottomLeft()))
            if action == claim:
                dialog = TextDialog("Claim a draw", "Enter the intended legal move in SAN or UCI. A valid claim ends the game without playing the move.", parent=self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                text = dialog.editor.toPlainText().strip()
                try:
                    try:
                        move = self.game.board.parse_uci(text)
                    except ValueError:
                        move = parse_san(self.game.board, text)
                    self.game.claim_draw(move)
                except ValueError as exc:
                    self._error("Draw claim unavailable", str(exc))
                    return
                self._stop_engine()
            elif action == offer:
                if self.config.get("mode") == "human_ai":
                    if self.config.get("black_engine", "custom") == "external":
                        self.statusBar().showMessage("UCI has no draw-offer protocol. Valid draw claims remain available.", 5000)
                        return
                    engine_color = -self.config.get("human_color", 1)
                    if evaluate(self.game.board) * self.game.board.turn * engine_color > 20:
                        self.statusBar().showMessage("Nocturne declines the draw offer", 4000)
                        return
                elif QMessageBox.question(self, "Offer a draw", "Does the other player accept a draw?") != QMessageBox.StandardButton.Yes:
                    return
                self._stop_engine()
                self.game.agree_draw()
            else:
                return
        self._refresh()
        self._save()

    def _resign(self):
        if QMessageBox.question(self, "Resign", "Resign this game?") == QMessageBox.StandardButton.Yes:
            self._stop_engine()
            self.game.resign(self.config.get("human_color", 1) if self.config.get("mode") == "human_ai" else None)
            self._refresh()
            self._save()

    def _copy_fen(self):
        QApplication.clipboard().setText(self.game.board.fen())
        self.statusBar().showMessage("FEN copied to clipboard", 3000)

    def _copy_pgn(self):
        QApplication.clipboard().setText(self.game.pgn())
        self.statusBar().showMessage("PGN copied to clipboard", 3000)

    def _show_pgn(self):
        self.tabs.setCurrentIndex(2)
        self.pgn_editor.setFocus()

    def _load_current_pgn(self):
        self.pgn_editor.setPlainText(self.game.pgn())
        self.pgn_editor.document().setModified(False)
        self._pgn_game_id = self.game.id

    def _apply_pgn(self):
        self._import_text(self.pgn_editor.toPlainText())

    def _load_clipboard(self):
        if self._import_text(QApplication.clipboard().text()):
            self._show_pgn()

    def _open_pgn(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open PGN", "", "PGN games (*.pgn);;All files (*)")
        if path:
            try:
                text = Path(path).read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError) as exc:
                self._error("Cannot open PGN", str(exc))
                return
            self._import_text(text)

    def _import_menu(self):
        dialog = TextDialog("Import position or game", "Paste a six-field FEN or a single PGN game.", parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._import_text(dialog.editor.toPlainText())

    def _import_text(self, text):
        text = text.strip()
        try:
            if not text:
                raise ValueError("Paste a PGN game, SAN moves, or a six-field FEN first.")
            first = text.split()[0] if text else ""
            game = Game(text) if first.count("/") == 7 else Game.from_pgn(text)
        except ValueError as exc:
            self._error("Cannot import", str(exc))
            return False
        self._save()
        self._stop_engine()
        self.game = game
        self.game.metadata["mode"] = "analysis"
        self._history_signature = None
        self._workspace(True)
        self.paused = False
        self._refresh()
        self._save()
        return True

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export PGN", "nocturne-game.pgn", "PGN games (*.pgn)")
        if path:
            try:
                Path(path).write_text(self.game.pgn(), encoding="utf-8")
                self.statusBar().showMessage("PGN exported", 3000)
            except OSError as exc:
                self._error("Export failed", str(exc))

    def _save(self):
        if not self.store:
            return
        try:
            self.store.save(self.game)
            self.store.set("settings", self.config)
            self.save_label.setText("SAVED ON THIS DEVICE")
        except StorageError as exc:
            self.save_label.setText("SAVE FAILED · SEE STATUS")
            self.statusBar().showMessage(str(exc))

    def _library(self):
        if not self.store:
            self._error("Library unavailable", self._storage_message)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Your library")
        dialog.resize(640, 430)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Every game has a story.", "title"))
        listing = QListWidget()
        try:
            games = self.store.list_games()
        except StorageError as exc:
            self._error("Library unavailable", str(exc))
            return
        for record in games:
            item = QListWidgetItem(f"{record['title']}\n{record['updated'][:16].replace('T', ' ')} UTC · {record['plies']} plies · {record['result']}")
            item.setData(Qt.ItemDataRole.UserRole, record["id"])
            listing.addItem(item)
        layout.addWidget(listing)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
        open_button = buttons.button(QDialogButtonBox.StandardButton.Open)
        open_button.setEnabled(False)
        listing.currentItemChanged.connect(lambda current, _: open_button.setEnabled(current is not None))
        if listing.count():
            listing.setCurrentRow(0)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        listing.itemDoubleClicked.connect(lambda _: dialog.accept())
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted and listing.currentItem():
            try:
                game = self.store.load(listing.currentItem().data(Qt.ItemDataRole.UserRole))
            except StorageError as exc:
                self._error("Cannot restore", str(exc))
                return
            self._save()
            self._stop_engine()
            self.game = game
            self._load_game_config()
            self.analysis_mode = self.config.get("mode") == "analysis"
            self._analysis_enabled = self.analysis_mode
            self._history_signature = None
            self.paused = True
            if self.analysis_mode:
                self.paused = False
            self.pause_button.setText("Continue" if self.paused else "Pause")
            self._refresh()
            self._schedule_engine()

    def _settings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._stop_engine()
            self.config.update(dialog.config())
            self._apply_settings()
            self._save()
            self._schedule_engine()

    def _analyze(self):
        if self._job and self._job["kind"] == "analysis":
            self._halt_analysis()
            return
        self._start_analysis()

    def _halt_analysis(self):
        self._analysis_enabled = False
        self._stop_engine()
        self.analyze_button.setText("Analyze position")

    def _start_analysis(self):
        self._workspace(True)
        self._analysis_enabled = True
        self.tabs.setCurrentIndex(1)
        self._schedule_engine()

    def _engine_lab(self):
        self._open_engine_lab()

    def _load_game_config(self):
        for key in ("mode", "human_color", "difficulty", "seconds", "increment", "takebacks",
                    "white_engine", "black_engine", "white_name", "black_name"):
            if key in self.game.metadata:
                self.config[key] = self.game.metadata[key]
        self.config = normalize(self.config)

    def _ensure_analysis_copy(self):
        if not self.analysis_mode and self.game.metadata.get("mode") != "analysis":
            self.game.pause_clock()
            self._save()
            self.game = self.game.fork_for_analysis()
            self._history_signature = None

    def _is_engine_turn(self):
        mode = self.config.get("mode", "human_ai")
        return mode == "ai_ai" or (mode == "human_ai" and self.game.board.turn != self.config.get("human_color", 1))

    def _position_identity(self):
        return self.game.id, self.game.cursor, self.game.board.key

    def _stop_engine(self):
        old_job = self._job
        if hasattr(self, "engine"):
            self.engine.stop()
        self._job = None
        if hasattr(self, "analyze_button"):
            self.analyze_button.setText("Analyze position")
        if old_job and old_job["kind"] != "benchmark":
            self.engine_state.setText("Search canceled")
            self.statusBar().showMessage("Search canceled", 3000)

    def _schedule_engine(self):
        if self._closing or not hasattr(self, "engine") or self.engine.busy or self.paused or self.game.outcome:
            return
        if self.analysis_mode:
            if not self._analysis_enabled:
                return
            kind = "analysis"
            limits = SearchLimits(depth=self.config.get("analysis_depth", 8),
                                  seconds=self.config.get("analysis_seconds", 3),
                                  hash_mb=self.config.get("hash_mb", 32))
            external = self.config.get("external_path", "") if self.analysis_source.currentData() == "external" else ""
        elif self._is_engine_turn():
            kind = "play"
            self.game.start_clock()
            available = self.game.clock_values()[self.game.board.turn] if self.game.time_control.seconds else None
            limits = difficulty_limits(self.config.get("difficulty", "Intermediate"),
                                       self.config.get("hash_mb", 32), available, self.game.time_control.increment)
            key = "black_engine" if self.config.get("mode") == "human_ai" else (
                "white_engine" if self.game.board.turn == 1 else "black_engine")
            external = self.config.get("external_path", "") if self.config.get(key) == "external" else ""
            if self.config.get(key) == "external" and not external:
                self.paused = True
                self.game.pause_clock()
                self.pause_button.setText("Continue")
                self.statusBar().showMessage("Select the installed UCI engine in Settings before continuing.")
                self._refresh()
                return
        else:
            return
        try:
            generation = self.engine.start(self.game, limits, external)
        except (OSError, RuntimeError) as exc:
            self._error("Cannot start engine", str(exc))
            self.paused = True
            self.game.pause_clock()
            return
        self._job = {"generation": generation, "kind": kind, "identity": self._position_identity(),
                     "turn": self.game.board.turn, "external": bool(external)}
        self.engine_state.setText(("External UCI engine" if external else f"Nocturne {__version__}") + " · thinking")
        self.statusBar().showMessage("Analyzing position…" if kind == "analysis" else "Engine is thinking…")
        self.analyze_button.setText("Stop analysis" if kind == "analysis" else "Analyze position")
        self.board_view.interactive = kind == "analysis"

    def _engine_message(self, generation: int, kind: str, payload: dict):
        if self._closing:
            return
        job = self._job
        if not job or generation != job["generation"] or generation != self.engine.generation:
            return
        if job["identity"] != self._position_identity():
            self._stop_engine()
            return
        if kind == "benchmark_progress":
            if self._lab:
                self._lab["text"].appendPlainText(self._benchmark_line(payload))
            return
        if kind == "benchmark":
            self._benchmark_report = payload
            self._job = None
            if self._lab:
                self._lab["run"].setEnabled(True)
                self._lab["stop"].setEnabled(False)
                self._lab["export"].setEnabled(True)
                self._lab["text"].appendPlainText("\nFinished. Time-capped rows are not fixed-depth comparisons.")
            if self.store:
                try:
                    self.store.set("last_benchmark", payload)
                except StorageError as exc:
                    self.statusBar().showMessage(str(exc), 5000)
            return
        if kind == "error":
            self._job = None
            self.engine_state.setText("Engine stopped · " + payload["message"])
            self.statusBar().showMessage(payload["message"])
            if job["kind"] == "play":
                self.paused = True
                self.game.pause_clock()
                self.pause_button.setText("Continue")
            else:
                self._analysis_enabled = False
            self._refresh()
            if self._lab:
                self._lab["run"].setEnabled(True)
                self._lab["stop"].setEnabled(False)
            return
        info = payload if kind == "info" else payload.get("info", {})
        self._show_info(info, job)
        if kind != "result":
            return
        self._job = None
        self.analyze_button.setText("Analyze position")
        self.engine_state.setText(("External UCI engine" if job["external"] else f"Nocturne {__version__}") + " · search complete")
        self.statusBar().showMessage(f"Search complete · depth {info['depth']} · {info['nodes']:,} nodes · evaluation from White's perspective")
        self.game.evaluations[self.game.cursor] = info["score"] * job["turn"]
        self.graph.set_samples(self.game.evaluations, self.game.cursor, len(self.game.moves))
        if job["kind"] == "play" and not self.paused:
            try:
                if payload.get("claim_draw"):
                    self.game.claim_draw()
                elif payload.get("move"):
                    self.game.play(self.game.board.parse_uci(payload["move"]))
            except ValueError as exc:
                self.paused = True
                self.game.pause_clock()
                self.pause_button.setText("Continue")
                self.statusBar().showMessage(f"Move was not applied: {exc}")
            self._refresh(animate=True)
            delay = self.config.get("watch_delay_ms", 500) if self.config.get("mode") == "ai_ai" else 80
            QTimer.singleShot(delay, self._schedule_engine)
        self._save()

    def _show_info(self, info, job):
        if not info:
            return
        self._last_info = info.copy()
        white_score = info["score"] * job["turn"]
        self.eval_label.setText(score_text(white_score))
        self.eval_bar.set_score(white_score)
        duration = info.get("seconds", 0)
        self.telemetry.setText(
            f"Depth {info['depth']}  ·  selective {info['seldepth']}\n"
            f"{info['nodes']:,} nodes  ·  {info.get('nps', 0):,} nodes/sec\n"
            f"{duration:.2f} seconds  ·  hash {info.get('hashfull', 0) / 10:.1f}%\n"
            f"Hash budget {self.config.get('hash_mb', 32)} MB  ·  1 thread")
        position = self.game.board.copy()
        line = []
        first = None
        for text in info.get("pv", [])[:10]:
            try:
                move = position.parse_uci(text)
                if first is None:
                    first = move
                line.append(san(position, move))
                position.push(move)
            except ValueError:
                break
        self.pv_label.setText("Principal variation\n" + ("  ".join(line) or "—"))
        self.board_view.best_move = first
        self.board_view.update()
        if self._lab:
            self._lab["current"].setText(self.telemetry.text() + f"\nEvaluation {score_text(white_score)} · White's perspective")

    @staticmethod
    def _benchmark_line(row):
        cap = " [time cap]" if row.get("stopped") else ""
        return (f"{row['position']:<19} d{row['depth']}  {row['nodes']:>8,} nodes  "
                f"{row['seconds']:>6.3f}s  {row.get('nps', 0):>7,} nps{cap}")

    def _open_engine_lab(self):
        self._stop_engine()
        self.game.pause_clock()
        self.paused = True
        self.pause_button.setText("Continue")
        self._refresh()
        dialog = QDialog(self)
        dialog.setWindowTitle("Nocturne · Engine lab")
        dialog.resize(750, 590)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.addWidget(label("Measure. Compare. Improve.", "title"))
        layout.addWidget(label(f"NOCTURNE {__version__} · INDEPENDENT ENGINE · 1 THREAD", "eyebrow"))
        current = label(self.telemetry.text(), "muted", True)
        layout.addWidget(current)
        if self.store:
            try:
                stats = self.store.match_stats()
                layout.addWidget(label(f"Saved engine games · White {stats['white_wins']} wins · Black {stats['black_wins']} wins · "
                                       f"{stats['draws']} draws · {stats['unfinished']} unfinished", "muted", True))
            except StorageError:
                pass
        layout.addWidget(label("Five reproducible positions · fresh hash each run · 5 sec cap per position", "subtitle", True))
        options = QHBoxLayout()
        options.addWidget(label("Target depth"))
        depth = QSpinBox()
        depth.setRange(1, 6)
        depth.setValue(3)
        options.addWidget(depth)
        options.addStretch()
        run = QPushButton("Run benchmark")
        run.setObjectName("primary")
        options.addWidget(run)
        stop = QPushButton("Stop")
        stop.setEnabled(False)
        options.addWidget(stop)
        export = QPushButton("Export JSON")
        export.setEnabled(self._benchmark_report is not None)
        options.addWidget(export)
        layout.addLayout(options)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet("font-family: 'Cascadia Mono', 'Consolas', monospace; font-size: 12px;")
        text.setPlainText("Search speed alone does not establish playing strength.\nUse the CLI match harness to compare engine variants.\n")
        layout.addWidget(text, 1)
        self._lab = {"text": text, "current": current, "run": run, "stop": stop, "export": export}

        def start_benchmark():
            self._stop_engine()
            run.setEnabled(False)
            stop.setEnabled(True)
            text.setPlainText("Benchmark started. Exact FENs and environment are included in the JSON.\n")
            limits = SearchLimits(depth=depth.value(), seconds=5, hash_mb=self.config.get("hash_mb", 32))
            generation = self.engine.start(self.game, limits, kind="benchmark")
            self._job = {"generation": generation, "kind": "benchmark", "identity": self._position_identity(),
                         "turn": self.game.board.turn, "external": False}

        def stop_benchmark():
            self._stop_engine()
            run.setEnabled(True)
            stop.setEnabled(False)
            text.appendPlainText("Stopped. A partial run is not saved as a completed benchmark.")

        def export_benchmark():
            path, _ = QFileDialog.getSaveFileName(dialog, "Export benchmark", "nocturne-benchmark.json", "JSON (*.json)")
            if path and self._benchmark_report:
                try:
                    Path(path).write_text(json.dumps(self._benchmark_report, indent=2) + "\n", encoding="utf-8")
                except OSError as exc:
                    self._error("Export failed", str(exc))

        run.clicked.connect(start_benchmark)
        stop.clicked.connect(stop_benchmark)
        export.clicked.connect(export_benchmark)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()
        self._stop_engine()
        self._lab = None

    def _error(self, title, text):
        QMessageBox.warning(self, title, text)

    def closeEvent(self, event):
        self._closing = True
        self.timer.stop()
        self.autosave_timer.stop()
        self.engine.close()
        self.game.pause_clock()
        self._save()
        if self.store:
            self.store.close()
        event.accept()
