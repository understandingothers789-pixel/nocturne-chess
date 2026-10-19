"""The desktop shell. The game model remains the sole rules authority."""

from __future__ import annotations

from html import escape
from pathlib import Path
import random

from PySide6.QtCore import QEvent, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QDoubleSpinBox,
    QFormLayout,
    QInputDialog,
    QLineEdit,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..core.board import Move, SQUARES
from ..core.rules import Board
from ..core.game import Game, TimeControl
from ..core.notation import pgn_clock
from ..core.notation import parse_san
from ..engine.uci_types import AnalysisLimits as SearchLimits, score_label, plot_score_label as score_text
from ..settings import normalize
from ..storage import Store, StorageError
from .board import BoardWidget
from .dialogs import NewGameDialog, SettingsDialog, TextDialog
from .engine import EngineController
from .engine_manager import EngineManager
from .engine_resources import EngineResources, validate_resource
from .candidates import CandidatePanel
from .review_panel import ReviewPanel
from ..review import classify, chance
from .explorer_panel import OpeningExplorer
from ..explorer import RATINGS, SPEEDS
from .moves import MoveText
from .hover_preview import HoverPreview
from .wheel import WheelSteps
from .theme import ASSETS, palette, stylesheet
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
        self.setAcceptDrops(True)
        location = data_dir or Path(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        )
        self.data_directory = location
        self.store: Store | None = None
        self._storage_message = ""
        try:
            self.store = Store(location / "nocturne.db")
        except (StorageError, OSError) as exc:
            self._storage_message = str(exc)
        self.config = normalize(self.store.get("settings", {}) if self.store else {})
        self.profiles = self.store.get("engine_profiles", []) if self.store else []
        if not isinstance(self.profiles, list):
            self.profiles = []
        self.profiles = [
            p
            for p in self.profiles
            if isinstance(p, dict)
            and all(k in p for k in ("id", "path", "values"))
            and isinstance(p["id"], str)
            and isinstance(p["path"], str)
            and isinstance(p["values"], dict)
            and isinstance(p.get("options", {}), dict)
            and isinstance(p.get("arguments", []), list)
            and all(isinstance(a, str) and "\0" not in a for a in p.get("arguments", []))
        ]
        if not self.profiles and self.config.get("external_path"):
            self.profiles = [
                {
                    "id": "migrated",
                    "path": self.config["external_path"],
                    "name": "External UCI engine",
                    "values": {},
                    "options": {},
                }
            ]
        self._candidate_identity = None
        self._analysis_context = None
        self._review = None
        self.config.setdefault("mode", "analysis")
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
        self._study_games = {self.game.id: self.game}
        if self.store:
            open_ids = self.store.get("open_studies", [])
            for key in (open_ids if isinstance(open_ids, list) else [])[:20]:
                if key not in self._study_games:
                    try:
                        self._study_games[key] = self.store.load(key)
                    except StorageError:
                        pass
        self.analysis_mode = self.config.get("mode") == "analysis"
        if self.analysis_mode:
            self.paused = False
        self._analysis_enabled = self.analysis_mode
        self._auto_play_active = False
        self._job = None
        self._lab = None
        self._benchmark_report = None
        self._last_info = None
        self._last_info_turn = 1
        self._history_signature = None
        self._analysis_layout_active = None
        self._pv_root = None
        self._pv_moves = []
        self._pv_identity = None
        self._preview_source = None
        self._build()
        self.hover_preview = HoverPreview(self)
        self.candidates.pointer_moved.connect(self._move_cursor_preview)
        self.analysis_history.pointer_moved.connect(self._move_cursor_preview)
        self.engine = EngineController(self)
        self.engine.message.connect(self._engine_message)
        self.engine.discovered.connect(self._engine_discovered)
        self.engine.status.connect(self.engine_state.setText)
        self.engine.connection.configured.connect(self.resource_controls.refresh)
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
        self.archive_timer = QTimer(self)
        self.archive_timer.setInterval(40)
        self.archive_timer.timeout.connect(self._archive_previous_pgn)
        self._start_pgn_archive_migration()
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
        self.sidebar = sidebar
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
        nav.addWidget(button("◷   Engine log", self._diagnostics, "nav"))
        nav.addStretch()
        nav.addWidget(label("A quieter place\nto think.", "muted"))
        nav.addSpacing(18)
        nav.addWidget(button("⚙   Settings", self._settings, "nav"))
        nav.addWidget(label(f"v{__version__}  ·  OFFLINE", "eyebrow"))
        layout.addWidget(sidebar)
        content = QVBoxLayout()
        self.content_layout = content
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
        self.workspace_header = QWidget()
        self.workspace_header.setLayout(top)
        content.addWidget(self.workspace_header)
        study_row = QHBoxLayout()
        self.study_tabs = QTabBar()
        self.study_tabs.setTabsClosable(True)
        self.study_tabs.setExpanding(False)
        for study in self._study_games.values():
            index = self.study_tabs.addTab(study.headers.get("Event") or "Study")
            self.study_tabs.setTabData(index, study.id)
        self.study_tabs.setCurrentIndex(
            next(i for i in range(self.study_tabs.count()) if self.study_tabs.tabData(i) == self.game.id)
        )
        self.study_tabs.currentChanged.connect(self._switch_study)
        self.study_tabs.tabCloseRequested.connect(self._close_study)
        study_row.addWidget(self.study_tabs, 1)
        study_row.addWidget(button("＋", self._new_study, "quiet"))
        self.quick_analysis_button = button("Analyze", self._analyze, "primary")
        study_row.addWidget(self.quick_analysis_button)
        content.addLayout(study_row)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter = splitter
        splitter.setChildrenCollapsible(False)
        arena = QWidget()
        self.arena = arena
        board_layout = QVBoxLayout(arena)
        board_layout.setContentsMargins(0, 0, 0, 0)
        board_layout.setSpacing(0)
        self.top_card, self.top_name, self.top_detail, self.top_clock = self._player_card()
        board_layout.addWidget(self.top_card)
        self.analysis_clocks = QFrame()
        self.analysis_clocks.setObjectName("clockStrip")
        clock_row = QHBoxLayout(self.analysis_clocks)
        clock_row.setContentsMargins(12, 4, 12, 4)
        self.analysis_clock_names = {}
        self.analysis_clock_values = {}
        for color, title in ((1, "White"), (-1, "Black")):
            caption, value = label(title, "muted"), label("∞", "analysisClock")
            value.setAccessibleName(title + " chess clock")
            clock_row.addWidget(caption)
            clock_row.addWidget(value)
            self.analysis_clock_names[color] = caption
            self.analysis_clock_values[color] = value
            if color == 1:
                clock_row.addStretch()
        board_layout.addWidget(self.analysis_clocks)
        self.board_view = BoardWidget()
        self.board_view.move_requested.connect(self._human_move)
        self.board_view.wheel_navigated.connect(self._wheel_game)
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
        self.board_hint = label("Drag a piece or select a square", "muted", True)
        board_tools.addWidget(self.board_hint)
        board_tools.addStretch()
        board_tools.addWidget(button("⇅  Flip", self._flip, "quiet"))
        board_tools.addWidget(button("Copy FEN", self._copy_fen, "quiet"))
        board_layout.addLayout(board_tools)
        splitter.addWidget(arena)
        self.panel = QScrollArea()
        self.panel.setWidgetResizable(True)
        self.panel.setFrameShape(QFrame.Shape.NoFrame)
        self.panel.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.panel_body = QFrame()
        self.panel_body.setObjectName("panel")
        self.panel.setWidget(self.panel_body)
        self.panel.setMinimumWidth(310)
        self.panel.setMaximumWidth(420)
        side = QVBoxLayout(self.panel_body)
        side.setContentsMargins(20, 16, 20, 12)
        side.setSpacing(10)
        self.panel_caption = label("THE GAME", "eyebrow")
        side.addWidget(self.panel_caption)
        self.mode_label = label("Two players", "score")
        side.addWidget(self.mode_label)
        self.status_label = label("White to move", "subtitle", True)
        side.addWidget(self.status_label)
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._analysis_tab_changed)
        moves_page = QWidget()
        moves_layout = QVBoxLayout(moves_page)
        moves_layout.setContentsMargins(0, 10, 0, 0)
        self.history = QTableWidget(0, 3)
        self._history_wheel = WheelSteps()
        self.history.viewport().installEventFilter(self)
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
        for widget, name in (
            (self.first_button, "First position"),
            (self.undo_button, "Take back"),
            (self.redo_button, "Next move"),
            (self.last_button, "Latest position"),
        ):
            widget.setAccessibleName(name)
        for widget in (self.first_button, self.undo_button, self.redo_button, self.last_button):
            navigation.addWidget(widget)
        moves_layout.addLayout(navigation)
        self.tabs.addTab(moves_page, "Moves")
        engine_page = QWidget()
        engine_page_layout = QVBoxLayout(engine_page)
        engine_page_layout.setContentsMargins(0, 0, 0, 0)
        engine_page_layout.setSpacing(4)
        self.engine_state = label("Select your UCI engine", "subtitle", True)
        self.eval_label = label("—")
        self.eval_label.setStyleSheet("font-size: 20px; font-weight: 600;")
        headline = QHBoxLayout()
        headline.addWidget(self.engine_state, 1)
        headline.addWidget(button("Game Review", self._show_review, "quiet"))
        headline.addWidget(self.eval_label)
        engine_page_layout.addLayout(headline)
        self.telemetry = label("Offline analysis · engine supplied by you", "muted", True)
        engine_page_layout.addWidget(self.telemetry)
        self.tablebase_label = label("Syzygy: not configured", "muted", True)
        engine_page_layout.addWidget(self.tablebase_label)
        self.analysis_scope = ""
        self.engine_scroll = QScrollArea()
        self.engine_scroll.setWidgetResizable(True)
        self.engine_scroll.setMinimumHeight(0)
        self.engine_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.engine_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        engine_detail = QWidget()
        self.engine_layout = QVBoxLayout(engine_detail)
        self.engine_layout.setContentsMargins(0, 0, 0, 0)
        self.engine_layout.setSpacing(0)
        self.pv_label = MoveText(auto_fit=True)
        self.pv_label.setAccessibleName("Principal variation moves")
        self.pv_label.preview_ended.connect(lambda: self._end_preview("pv"))
        self.candidates = CandidatePanel(self.pv_label)
        self.candidates.preview.connect(self._preview_candidate)
        self.candidates.preview_end.connect(lambda: self._end_preview("candidate"))
        self.candidates.navigate.connect(self._insert_candidate)
        self.candidates.action.connect(self._candidate_action)
        self.candidates.changed.connect(self._sync_candidate_markers)
        self.engine_layout.addWidget(self.candidates)
        self.engine_layout.addStretch()
        self.engine_scroll.setWidget(engine_detail)
        self.analysis_detail_splitter = QSplitter(Qt.Orientation.Vertical)
        self.analysis_detail_splitter.setChildrenCollapsible(False)
        self.analysis_detail_splitter.addWidget(self.engine_scroll)
        self.explorer = OpeningExplorer(self.data_directory / "opening-cache.sqlite3")
        self.explorer.statistics_changed.connect(self._sync_candidate_database)
        self.explorer.move_selected.connect(self._explorer_move)
        self.explorer.move_hovered.connect(self._preview_explorer)
        self.explorer.preview_ended.connect(lambda: self._end_preview("explorer"))
        self.explorer.close_requested.connect(lambda: self._set_explorer_option("explorer_enabled", False))
        self.analysis_detail_splitter.addWidget(self.explorer)
        self.explorer.hide()
        self._explorer_active = False
        engine_page_layout.addWidget(self.analysis_detail_splitter, 1)
        self.graph = EvaluationGraph()
        self.graph.setMinimumHeight(60)
        self.graph.setMaximumHeight(85)
        self.graph.position_requested.connect(self._navigate)
        engine_page_layout.addWidget(self.graph)
        self.resource_controls = EngineResources(
            self._profile,
            lambda: self.engine.connection if hasattr(self, "engine") else None,
            self._set_engine_resource,
            self._restart_engine,
            self,
        )
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
        self.review_panel = ReviewPanel()
        self.review_panel.seconds.setValue(self.config.get("review_seconds", 3))
        self.review_panel.run_requested.connect(self._begin_review)
        self.review_panel.pause_requested.connect(self._pause_review)
        self.review_panel.cancel_requested.connect(self._cancel_review)
        self.review_panel.move_requested.connect(self._review_navigate)
        self.review_panel.before_requested.connect(self._review_navigate)
        self.review_panel.back_requested.connect(lambda: self.tabs.setCurrentIndex(1))
        self.tabs.addTab(self.review_panel, "Game Review")
        self.raw_pgn_page = QWidget()
        raw_layout = QVBoxLayout(self.raw_pgn_page)
        raw_layout.setContentsMargins(0, 10, 0, 0)
        raw_layout.addWidget(label("Raw PGN · saved comments, clocks and annotations", "muted", True))
        self.raw_pgn_text = QPlainTextEdit()
        self.raw_pgn_text.installEventFilter(self)
        self.raw_pgn_text.setReadOnly(True)
        self.raw_pgn_text.setAccessibleName("Raw PGN data")
        raw_layout.addWidget(self.raw_pgn_text, 1)
        raw_layout.addWidget(button("Copy complete PGN", self._copy_pgn, "quiet"))
        self.tabs.addTab(self.raw_pgn_page, "Raw PGN")
        self.tabs.setTabVisible(self.tabs.indexOf(self.raw_pgn_page), False)
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
        self.io_bar = QWidget()
        self.io_bar.setLayout(io)
        side.addWidget(self.io_bar)
        self.save_label = label("Games stay on this device", "eyebrow")
        self.save_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side.addWidget(self.save_label)
        splitter.addWidget(self.panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([720, 350])
        self.workspace_splitter = QSplitter(Qt.Orientation.Vertical)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.addWidget(splitter)
        self.analysis_moves_panel = QFrame()
        self.analysis_moves_panel.setObjectName("panel")
        self.analysis_moves_panel.setMinimumHeight(90)
        history_layout = QVBoxLayout(self.analysis_moves_panel)
        history_layout.setContentsMargins(10, 5, 10, 5)
        history_layout.setSpacing(2)
        history_tools = QHBoxLayout()
        history_tools.addWidget(label("GAME MOVES", "eyebrow"))
        history_tools.addStretch()
        for text, callback in (
            ("|‹", lambda: self._navigate(0)),
            ("‹", self._undo),
            ("›", self._redo),
            ("›|", lambda: self._navigate(len(self.game.moves))),
        ):
            control = button(text, callback, "quiet")
            control.setFixedHeight(22)
            control.setStyleSheet("padding: 1px 8px;")
            history_tools.addWidget(control)
        history_layout.addLayout(history_tools)
        self.analysis_history = MoveText()
        self.analysis_history.setAccessibleName("Analysis game moves")
        self.analysis_history.setMinimumHeight(36)
        self.analysis_history.move_hovered.connect(self._preview_history)
        self.analysis_history.move_clicked.connect(self._navigate_node)
        self.analysis_history.wheel_navigated.connect(self._wheel_game)
        self.analysis_history.preview_ended.connect(lambda: self._end_preview("history"))
        history_layout.addWidget(self.analysis_history, 1)
        self.workspace_splitter.addWidget(self.analysis_moves_panel)
        self.workspace_splitter.setStretchFactor(0, 1)
        self.workspace_splitter.setStretchFactor(1, 0)
        self.analysis_moves_panel.hide()
        content.addWidget(self.workspace_splitter, 1)
        layout.addLayout(content, 1)
        self.statusBar().showMessage("Ready · Nocturne Chess · Offline by design")

    def _player_card(self):
        frame = QFrame()
        frame.setObjectName("playerCard")
        row = QHBoxLayout(frame)
        row.setContentsMargins(17, 12, 17, 12)
        avatar = label("♙")
        avatar.setStyleSheet("font-size: 27px;")
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
        clock.setMargin(6)
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
            key = name or text
            if key in self.menu_actions:
                key = menu.title().replace("&", "") + "/" + key
            self.menu_actions[key] = action
            return action

        file = self.menuBar().addMenu("&File")
        add(file, "New game…", self._new_game, "Ctrl+N")
        add(file, "Open PGN…", self._open_pgn, "Ctrl+O")
        add(file, "New study tab", self._new_study, "Ctrl+T")
        add(file, "Rename study…", self._rename_study)
        add(file, "Set up position…", self._setup_position)
        add(file, "New Chess960 position…", self._new_chess960)
        add(file, "Load FEN / PGN from clipboard", self._load_clipboard, "Ctrl+Shift+V", "load_clipboard")
        add(file, "Edit / paste PGN…", self._show_pgn, "Ctrl+I")
        add(file, "Enter FEN / PGN…", self._import_menu)
        file.addSeparator()
        add(file, "Save this game as PGN…", self._export, "Ctrl+E")
        add(file, "Write PGN to clipboard", self._copy_pgn, "Ctrl+Shift+P", "copy_pgn")
        add(file, "Write FEN to clipboard", self._copy_fen, "Ctrl+Shift+C")
        add(file, "Save to library", self._save, "Ctrl+S")
        add(file, "Saved PGNs / game library…", self._library, name="Game library…")
        add(file, "Open saved PGN folder", self._open_pgn_folder)
        file.addSeparator()
        add(file, "Quit", self.close, "Ctrl+Q")

        tree = self.menuBar().addMenu("&Tree")
        add(tree, "Root", lambda: self._navigate(0), "Home")
        add(tree, "End", lambda: self._navigate(len(self.game.moves)), "End")
        add(tree, "Backward", self._undo, "Left")
        add(tree, "Forward", self._redo, "Right")
        tree.addSeparator()
        add(
            tree,
            "Return to main line",
            lambda: self._navigate_node(self.game.mainline_node(self.game.cursor)),
        )
        add(tree, "Previous variation", lambda: self._sibling(-1))
        add(tree, "Next variation", lambda: self._sibling(1))
        add(tree, "Promote variation to main line", self._promote_line)
        self.delete_line_action = add(tree, "Delete current line", self._delete_line, "Backspace")
        self.delete_line_action.setAutoRepeat(False)
        add(tree, "Edit comment / annotations…", self._edit_annotation, "Ctrl+M")

        analysis = self.menuBar().addMenu("&Analysis")
        add(analysis, "Game Review…", self._show_review)
        analysis.addSeparator()
        add(analysis, "Go", self._start_analysis, "Ctrl+G")
        add(analysis, "Halt", self._halt_analysis, "Ctrl+H")
        add(analysis, "Analyze entire line…", self._analyze_game)
        add(analysis, "Pause / resume game analysis", self._pause_review)
        add(analysis, "Cancel game analysis", self._cancel_review)
        add(analysis, "Analyze all legal moves again", self._clear_focus)
        add(analysis, "Engine diagnostics…", self._diagnostics)

        display = self.menuBar().addMenu("&Display")
        add(display, "Flip board", self._flip, "F")
        add(display, "Clear arrows and marks", self.board_view.clear_annotations, "Escape")
        display.addSeparator()
        for key, text in (
            ("coordinates", "Coordinates"),
            ("show_clocks", "Clocks"),
            ("overlays", "Analysis overlays"),
            ("show_eval_graph", "Evaluation graph"),
            ("animations", "Move animations"),
            ("light", "Light appearance"),
        ):
            action = add(display, text, lambda checked, k=key: self._set_display(k, checked))
            action.setCheckable(True)
            self.display_actions[key] = action
        add(display, "Board appearance…", self._settings)
        add(display, "Classic Nibbler layout", lambda: self._set_layout("classic"))
        add(display, "Analysis on the left", lambda: self._set_layout("analysis-left"))
        add(display, "Save board image…", self._save_board_image)
        add(display, "Command palette…", self._command_palette, "Ctrl+K")
        add(display, "Keyboard shortcuts…", self._shortcut_editor)
        for key, text in [
            ("smart_move", "Smart Move · click recommended destinations"),
            ("branch_arrows", "Show saved continuation arrows"),
            ("details", "Detailed analysis statistics"),
            ("show_seldepth", "Show selective depth (seldepth)"),
            ("wheel_game_moves", "Wheel navigates game moves"),
            ("wheel_analysis_moves", "Wheel previews analysis moves"),
        ]:
            action = add(display, text, lambda checked, k=key: self._set_display(k, checked))
            action.setCheckable(True)
            self.display_actions[key] = action
        markers = display.addMenu("Candidate markers")
        self.marker_actions = {}
        for key, title in (("arrows", "Arrows · Lichess style"), ("lines", "Lines · Nibbler style")):
            action = add(markers, title, lambda checked=False, k=key: self._set_display("candidate_style", k))
            action.setCheckable(True)
            self.marker_actions[key] = action
        for rank in range(1, 4):
            add(
                analysis,
                f"Execute candidate {rank}",
                lambda checked=False, r=rank: self._execute_rank(r),
                f"Alt+{rank}",
            )

        engine = self.menuBar().addMenu("&Engine")
        add(engine, "Choose engine…", self._choose_engine)
        add(engine, "Choose Syzygy folder…", self._choose_tablebase)
        add(engine, "Engine profiles and options…", self._manage_engines)
        engine.addSeparator()
        engine.addMenu(self.resource_controls.menus["Threads"])
        engine.addMenu(self.resource_controls.menus["Hash"])
        self.multipv_menu = engine.addMenu("MultiPV")
        self.profile_menu = engine.addMenu("Active engine")
        self.search_mode_menu = engine.addMenu("Analysis limits")
        self.normal_limit_menu = engine.addMenu("Normal nodes per position")
        self.auto_eval_limit_menu = engine.addMenu("Auto-evaluation nodes per position")
        self.auto_play_limit_menu = engine.addMenu("Auto-play nodes per move")
        self.resource_status_action = engine.addAction("")
        self.resource_status_action.setEnabled(False)
        engine.addSeparator()
        add(engine, "Auto-play engines from this position", self._start_auto_play, "F11")
        add(engine, "Auto-evaluate entire line", self._auto_evaluate_line, "F12")
        engine.addSeparator()
        self.expand_pv_action = add(engine, "Expand all analysis lines", self._set_expand_pv)
        self.expand_pv_action.setCheckable(True)
        self.cursor_preview_action = add(
            engine, "Preview moves on a small board near cursor", self._set_cursor_preview
        )
        self.cursor_preview_action.setCheckable(True)
        engine.aboutToShow.connect(self._refresh_engine_menus)
        engine.addSeparator()
        add(engine, "Restart selected engine", self._restart_engine)
        add(engine, "Engine diagnostics…", self._diagnostics)
        database = self.menuBar().addMenu("&Database")
        self.explorer_enabled_action = add(database, "Show database explorer", lambda checked: self._set_explorer_option("explorer_enabled", checked))
        self.explorer_enabled_action.setCheckable(True)
        self.explorer_statistics_action = add(database, "Enable database statistics", lambda checked: self._set_explorer_option("explorer_statistics", checked))
        self.explorer_statistics_action.setCheckable(True)
        self.explorer_actions = {}
        for source, title in (("masters", "Masters database"), ("lichess", "Lichess players (Amateurs)"),
                              ("chessdb", "ChessDB · cloud analysis")):
            action = add(database, title, lambda checked=False, s=source: self._choose_explorer(s))
            action.setCheckable(True)
            self.explorer_actions[("explorer_source", source)] = action
        speeds = database.addMenu("Lichess game speed")
        ratings = database.addMenu("Lichess rating groups")
        for value in ("all", *SPEEDS):
            action = add(speeds, "All speeds" if value == "all" else value, lambda checked=False, v=value: self._set_explorer_option("explorer_speed", v))
            action.setCheckable(True)
            self.explorer_actions[("explorer_speed", value)] = action
        for value in RATINGS:
            action = add(ratings, "All ratings" if value == 0 else f"{value}+", lambda checked=False, v=value: self._set_explorer_option("explorer_rating", v))
            action.setCheckable(True)
            self.explorer_actions[("explorer_rating", value)] = action
        self.explorer_filter_menus = (speeds, ratings)
        database.addSeparator()
        add(database, "Lichess access token…", self._lichess_token_dialog)
        add(database, "Create a Lichess access token…", lambda: QDesktopServices.openUrl(
            QUrl("https://lichess.org/account/oauth/token/create?description=Nocturne%20database%20explorer")))
        self.clear_lichess_token_action = add(database, "Clear session access token", self._clear_lichess_token)
        add(database, "Refresh database results", self.explorer.refresh)
        play = self.menuBar().addMenu("&Play")
        add(play, "New game…", self._new_game)
        add(play, "Pause / continue", self._pause, "Space")
        add(play, "Offer / claim draw…", self._draw)
        add(play, "Resign…", self._resign)
        dev = self.menuBar().addMenu("&Dev")
        self.raw_pgn_action = add(dev, "Show raw PGN data", self._set_raw_pgn)
        self.raw_pgn_action.setCheckable(True)
        self.reanalyze_navigation_action = add(
            dev,
            "Automatically analyze when selecting a position",
            self._set_reanalyze_navigation,
        )
        self.reanalyze_navigation_action.setCheckable(True)
        add(dev, "Engine diagnostics…", self._diagnostics)
        # Retain explicit references for menu state and interaction checks.
        self.shortcut_overrides = self.store.get("shortcuts", {}) if self.store else {}
        for name, value in self.shortcut_overrides.items():
            if name in self.menu_actions and isinstance(value, str):
                self.menu_actions[name].setShortcut(QKeySequence(value))
        self.menus = {
            "File": file,
            "Tree": tree,
            "Analysis": analysis,
            "Display": display,
            "Engine": engine,
            "Database": database,
            "Play": play,
            "Dev": dev,
        }

    def _set_cursor_preview(self, enabled):
        for view in {self.analysis_history, self.pv_label, *(row[2] for row in self.candidates.rows.values())}:
            view.cancel_preview()
        self.explorer._end_preview()
        self._clear_move_preview()
        self.config["cursor_preview"] = bool(enabled)
        self.cursor_preview_action.setChecked(bool(enabled))
        self._save()

    def _set_expand_pv(self, enabled):
        self.config["expand_pv"] = bool(enabled)
        self.config["expand_pv_version"] = 1
        self.candidates.set_expanded(enabled)
        self.expand_pv_action.setChecked(bool(enabled))
        self._save()

    def _move_cursor_preview(self, point):
        if self.hover_preview.isVisible():
            self.hover_preview.move_near(point)

    def _set_raw_pgn(self, enabled):
        self.config["show_raw_pgn"] = bool(enabled)
        self._sync_raw_pgn()
        if enabled:
            self.tabs.setCurrentWidget(self.raw_pgn_page)
        self._analysis_tab_changed()
        self._save()

    def _set_reanalyze_navigation(self, enabled):
        self.config["reanalyze_on_navigation"] = bool(enabled)
        self.reanalyze_navigation_action.setChecked(bool(enabled))
        self._save()

    def _sync_raw_pgn(self):
        enabled = self.config.get("show_raw_pgn", False)
        index = self.tabs.indexOf(self.raw_pgn_page)
        if not enabled and self.tabs.currentWidget() is self.raw_pgn_page:
            self.tabs.setCurrentIndex(1 if self.analysis_mode else 0)
        self.tabs.setTabVisible(index, enabled)
        self.raw_pgn_action.setChecked(enabled)
        self._refresh_raw_pgn()

    def _refresh_raw_pgn(self):
        if not self.config.get("show_raw_pgn", False) or not hasattr(self, "raw_pgn_text"):
            return
        text = self.game.pgn()
        if self.raw_pgn_text.toPlainText() != text:
            scroll = self.raw_pgn_text.verticalScrollBar().value()
            self.raw_pgn_text.setPlainText(text)
            self.raw_pgn_text.verticalScrollBar().setValue(scroll)

    def _set_display(self, key, value):
        self.config[key] = value
        self._apply_settings()
        self._save()

    def _choose_explorer(self, source):
        self.config["explorer_source"] = source
        self.config["explorer_statistics"] = True
        self._workspace(True)
        self.tabs.setCurrentIndex(1)
        self._sync_explorer()
        self._save()

    def _lichess_token_dialog(self):
        token, accepted = QInputDialog.getText(
            self, "Lichess access token", "Paste a personal access token with no extra permissions.\n"
            "It stays in memory until you close Nocturne; it is never saved in games or settings.",
            QLineEdit.EchoMode.Password)
        if accepted:
            try:
                self.explorer.client.set_lichess_token(token)
            except ValueError as exc:
                self._error("Invalid access token", str(exc))
                return
            self._sync_explorer()
            if self.explorer.query and self.explorer.query.source != "chessdb":
                self.explorer.refresh()

    def _clear_lichess_token(self):
        self.explorer.client.set_lichess_token("")
        if self.explorer.query and self.explorer.query.source != "chessdb":
            self.explorer.client.cancel()
            self.explorer.status_label.setText("Session token cleared · cached results remain available")
        self._sync_explorer()

    def _set_explorer_option(self, key, value):
        self.config[key] = value
        if key == "explorer_enabled" and value:
            self.config["explorer_statistics"] = True
            self._workspace(True)
            self.tabs.setCurrentIndex(1)
        self._sync_explorer()
        self._save()

    def _sync_explorer(self):
        if not hasattr(self, "explorer") or self._closing:
            return
        enabled = bool(self.config.get("explorer_enabled"))
        active = enabled and self.analysis_mode and self.tabs.currentIndex() == 1
        lookup = bool(self.config.get("explorer_statistics")) and self.analysis_mode and self.tabs.currentIndex() == 1
        if hasattr(self, "explorer_actions"):
            self.clear_lichess_token_action.setEnabled(self.explorer.client.has_lichess_token)
            self.explorer_enabled_action.setChecked(enabled)
            self.explorer_statistics_action.setChecked(bool(self.config.get("explorer_statistics")))
            for (key, value), action in self.explorer_actions.items():
                action.setChecked(self.config.get(key) == value)
            for menu in self.explorer_filter_menus:
                menu.setEnabled(self.config.get("explorer_source") == "lichess")
        if self._explorer_active and not active:
            self.explorer._end_preview()
        self.explorer.setVisible(active)
        self.explorer.set_position(self.game.board, self._position_identity(), lookup,
                                   self.config.get("explorer_source", "masters"),
                                   self.config.get("explorer_speed", "all"),
                                   self.config.get("explorer_rating", 0))
        if active and not self._explorer_active:
            self.analysis_detail_splitter.setSizes([500, 220])
        self._explorer_active = active
        self._sync_candidate_database()

    def _sync_candidate_database(self):
        explorer = self.explorer
        if (explorer.query and explorer.identity == self._position_identity()
                and self._candidate_identity == self._position_identity()):
            self.candidates.set_database(explorer.query, explorer.statistics, explorer.statistics_origin,
                                         explorer.statistics_status)
        else:
            self.candidates.set_database()

    def _explorer_move(self, identity, text):
        if not self.analysis_mode or not self._explorer_active or identity != self._position_identity():
            return
        try:
            move = self.game.board.parse_uci(text)
        except ValueError:
            return
        self._end_preview("explorer")
        self._human_move(move)

    def _preview_explorer(self, identity, text):
        if not self.analysis_mode or not self._explorer_active or identity != self._position_identity():
            return
        position = self.game.board.copy()
        try:
            move = position.parse_uci(text)
            position.push(move)
        except ValueError:
            return
        self._show_move_preview("explorer", position, move, "Opening database preview")

    def eventFilter(self, watched, event):
        if hasattr(self, "history") and watched is self.history.viewport():
            if event.type() == QEvent.Type.Leave:
                self._history_wheel.reset()
            if event.type() == QEvent.Type.Wheel and self.config.get("wheel_game_moves", True):
                steps = self._history_wheel.consume(event)
                if steps is not None:
                    event.accept()
                    if steps:
                        self._wheel_game(steps)
                    return True

        if (
            watched in (getattr(self, "pgn_editor", None), getattr(self, "raw_pgn_text", None))
            and event.type() == QEvent.Type.ShortcutOverride
            and event.modifiers() in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier)
        ):
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def _register_study(self):
        if not hasattr(self, "study_tabs"):
            return
        self._study_games[self.game.id] = self.game
        self.study_tabs.blockSignals(True)
        existing = {self.study_tabs.tabData(i): i for i in range(self.study_tabs.count())}
        for key, game in self._study_games.items():
            if key not in existing:
                index = self.study_tabs.addTab(game.headers.get("Event") or "Study")
                self.study_tabs.setTabData(index, key)
                existing[key] = index
        self.study_tabs.setCurrentIndex(existing[self.game.id])
        self.study_tabs.setTabText(existing[self.game.id], (self.game.headers.get("Event") or "Study")[:32])
        self.study_tabs.blockSignals(False)

    def _switch_study(self, index):
        if index < 0 or not hasattr(self, "engine"):
            return
        key = self.study_tabs.tabData(index)
        if key == self.game.id or key not in self._study_games:
            return
        self._cancel_review()
        self._stop_engine()
        self.game.pause_clock()
        self._save()
        self.game = self._study_games[key]
        self.analysis_mode = True
        self._analysis_enabled = True
        self._history_signature = None
        self.paused = False
        self._refresh()
        self._save()
        self._schedule_engine()

    def _new_study(self):
        self._cancel_review()
        self._stop_engine()
        self._save()
        self.game = Game()
        self.game.metadata["mode"] = "analysis"
        self._workspace(True)
        self._refresh()
        self._save()

    def _close_study(self, index):
        key = self.study_tabs.tabData(index)
        if self.study_tabs.count() == 1:
            return
        if key == self.game.id:
            other = 0 if index else 1
            self._switch_study(other)
        self._study_games.pop(key, None)
        self.study_tabs.blockSignals(True)
        self.study_tabs.removeTab(index)
        self.study_tabs.blockSignals(False)
        self._save()

    def _rename_study(self):
        from PySide6.QtWidgets import QInputDialog

        text, ok = QInputDialog.getText(self, "Study name", "Name", text=self.game.headers.get("Event", ""))
        if ok:
            self.game.headers["Event"] = text[:200]
            self._register_study()
            self._save()

    def _setup_position(self):
        from .setup_position import PositionDialog

        dialog = PositionDialog(self.game.board.fen(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._import_text(dialog.result_fen)

    def _new_chess960(self):
        import chess
        from PySide6.QtWidgets import QInputDialog

        index, ok = QInputDialog.getInt(self, "Chess960", "Starting position number (0–959)", 518, 0, 959)
        if ok:
            self._import_text(chess.Board.from_chess960_pos(index).fen(shredder=True))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = Path(url.toLocalFile())
                if path.suffix.lower() == ".pgn":
                    try:
                        self._import_text(path.read_text(encoding="utf-8-sig"))
                    except (OSError, UnicodeError) as exc:
                        self._error("Cannot open PGN", str(exc))
        else:
            self._import_text(event.mimeData().text())
        event.acceptProposedAction()

    def _shortcut_editor(self):
        from PySide6.QtWidgets import QKeySequenceEdit
        import json

        dialog = QDialog(self)
        dialog.setWindowTitle("Keyboard shortcuts")
        dialog.resize(700, 550)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["Command", "Shortcut"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(table)
        edits = {}
        for name, action in self.menu_actions.items():
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(action.text()))
            edit = QKeySequenceEdit(action.shortcut())
            table.setCellWidget(row, 1, edit)
            edits[name] = edit

        def values():
            return {
                name: edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
                for name, edit in edits.items()
            }

        def export():
            file, _ = QFileDialog.getSaveFileName(
                dialog, "Export shortcuts", "nocturne-shortcuts.json", "JSON (*.json)"
            )
            if file:
                Path(file).write_text(json.dumps(values(), indent=2), encoding="utf-8")

        def load():
            file, _ = QFileDialog.getOpenFileName(dialog, "Import shortcuts", "", "JSON (*.json)")
            if not file:
                return
            try:
                data = json.loads(Path(file).read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("Expected shortcut object")
                for name, value in data.items():
                    if name in edits and isinstance(value, str):
                        edits[name].setKeySequence(QKeySequence(value))
            except (OSError, ValueError) as exc:
                QMessageBox.warning(dialog, "Invalid shortcut file", str(exc))

        row = QHBoxLayout()
        row.addWidget(button("Import…", load))
        row.addWidget(button("Export…", export))
        layout.addLayout(row)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(buttons)

        def accept():
            data = values()
            used = {}
            for name, value in data.items():
                if not value:
                    continue
                if value.casefold() in used:
                    QMessageBox.warning(
                        dialog,
                        "Shortcut conflict",
                        value + " is used by both " + used[value.casefold()] + " and " + name,
                    )
                    return
                used[value.casefold()] = name
            for name, value in data.items():
                self.menu_actions[name].setShortcut(QKeySequence(value))
            if self.store:
                self.store.set("shortcuts", data)
            dialog.accept()

        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        dialog.exec()

    def _set_layout(self, value):
        self.config["layout"] = value
        self._sync_workspace_layout()
        self._save()

    def _preview_candidate(self, rank, ply):
        if self._candidate_identity != self._position_identity() or rank not in self.candidates.lines:
            return
        board = self.game.board.copy()
        try:
            for text in self.candidates.lines[rank]["pv"][:ply]:
                board.push(board.parse_uci(text))
        except ValueError:
            return
        self._show_move_preview("candidate", board, caption=f"Candidate preview · ply {ply}")

    def _sync_candidate_markers(self):
        if self._candidate_identity != self._position_identity():
            return
        entries = []
        for rank, line in self.candidates.lines.items():
            try:
                entries.append((self.game.board.parse_uci(line["pv"][0]), rank,
                                score_label(line, self.game.board.turn)))
            except (ValueError, IndexError):
                continue
        self.board_view.set_recommendations(entries)

    def _insert_candidate(self, rank, ply=None):
        if self._candidate_identity != self._position_identity() or rank not in self.candidates.lines:
            return
        moves = self.candidates.lines[rank]["pv"][:ply]
        board = self.game.board.copy()
        try:
            parsed = []
            for text in moves:
                move = board.parse_uci(text)
                parsed.append(move)
                board.push(move)
                if board.outcome():
                    break
        except ValueError:
            return
        self._stop_engine()
        for move in parsed:
            self.game.play(move)
        self._refresh(animate=len(parsed) == 1)
        self._save()
        self._schedule_engine()

    def _candidate_action(self, rank, action):
        if self._candidate_identity != self._position_identity() or rank not in self.candidates.lines:
            return
        line = self.candidates.lines[rank]
        if action == "insert":
            self._insert_candidate(rank)
        elif action == "focus":
            self._stop_engine()
            self.config["searchmoves"] = [line["pv"][0]]
            self.statusBar().showMessage("Targeted analysis: " + line["san"][0])
            self._schedule_engine()
        elif action in ("san", "uci"):
            QApplication.clipboard().setText(" ".join(line[action if action == "san" else "pv"]))

    def _clear_focus(self):
        self.config["searchmoves"] = []
        self._stop_engine()
        self._schedule_engine()

    def _execute_rank(self, rank):
        if not self.board_view.smart_move or self.board_view.selected is not None:
            return
        self._insert_candidate(rank, 1)

    def _store_analysis(self, game, node_id, info, turn, context):
        if not info or info.get("bound", "exact") != "exact":
            return
        value = info["score"] * turn
        node = game.nodes[node_id]
        node.evaluation = value
        from datetime import datetime, timezone

        node.analysis = {
            **info,
            "white_value": info.get("score_value", info["score"]) * turn,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "profile": context.get("profile", ""),
            "options": dict(context.get("options", {})),
        }
        if node_id in game._line_nodes:
            game.evaluations[game._line_nodes.index(node_id)] = value

    def _edit_annotation(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Move comment and annotations")
        dialog.resize(580, 380)
        layout = QVBoxLayout(dialog)
        node = self.game.nodes[self.game.current_node]
        comment = QPlainTextEdit(node.comment)
        layout.addWidget(comment, 1)
        symbols = QComboBox()
        for title, value in [
            ("No glyph", 0),
            ("! good move", 1),
            ("? mistake", 2),
            ("!! brilliant", 3),
            ("?? blunder", 4),
            ("!? interesting", 5),
            ("?! dubious", 6),
        ]:
            symbols.addItem(title, value)
        symbols.setCurrentIndex(
            next((i for i in range(symbols.count()) if symbols.itemData(i) in node.nags), 0)
        )
        layout.addWidget(symbols)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            node.comment = comment.toPlainText()
            self.game.has_pgn_clocks = any(pgn_clock(item.comment) is not None for item in self.game.nodes)
            node.nags = [n for n in node.nags if n not in range(1, 7)]
            if symbols.currentData():
                node.nags.append(symbols.currentData())
            self._refresh()
            self._save()

    def _save_board_image(self):
        file, _ = QFileDialog.getSaveFileName(
            self, "Save board image", "nocturne-position.png", "PNG (*.png)"
        )
        if file and not self.board_view.grab().save(file, "PNG"):
            self._error("Cannot save image", "Choose a writable PNG file path.")

    def _command_palette(self):
        from PySide6.QtWidgets import QLineEdit

        dialog = QDialog(self)
        dialog.setWindowTitle("Commands")
        dialog.resize(580, 420)
        layout = QVBoxLayout(dialog)
        query = QLineEdit()
        query.setPlaceholderText("Type a command…")
        layout.addWidget(query)
        results = QListWidget()
        layout.addWidget(results)
        actions = [
            a for menu in self.menus.values() for a in menu.actions() if not a.isSeparator() and a.isEnabled()
        ]

        def update(text):
            results.clear()
            for action in actions:
                if text.casefold() in action.text().casefold():
                    item = QListWidgetItem(action.text() + "   " + action.shortcut().toString())
                    item.setData(Qt.ItemDataRole.UserRole, action)
                    results.addItem(item)
            results.setCurrentRow(0)

        def run(item=None):
            item = item or results.currentItem()
            if item:
                action = item.data(Qt.ItemDataRole.UserRole)
                dialog.accept()
                action.trigger()

        query.textChanged.connect(update)
        query.returnPressed.connect(lambda: run())
        results.itemActivated.connect(run)
        update("")
        dialog.exec()

    def _show_review(self):
        if not self.analysis_mode:
            self._workspace(True)
        self.tabs.setCurrentWidget(self.review_panel)
        self._update_review_panel()

    def _update_review_panel(self):
        if hasattr(self, "review_panel") and self.tabs.currentWidget() is self.review_panel:
            self.review_panel.update_game(self.game, self._review, self._profile(), self._appearance_config().get("light", False))

    def _review_navigate(self, node_id):
        # Review navigation must not turn halted analysis back on.
        if not 0 <= node_id < len(self.game.nodes):
            return
        self._stop_engine()
        self._analysis_enabled = False
        if node_id in self.game._line_nodes:
            self.game.navigate(self.game._line_nodes.index(node_id))
        else:
            self.game.select_node(node_id)
        self._refresh()
        self._save()

    def _auto_evaluate_line(self):
        if self._review and self._review.get("kind") == "auto_eval":
            self._pause_review()
            return
        if not self._profile():
            self._manage_engines()
            return
        self._cancel_review()
        self._stop_engine()
        self._ensure_analysis_copy()
        self.analysis_mode = True
        self.paused = False
        self._analysis_enabled = False
        self.game.pause_clock()
        self._review = {
            "kind": "auto_eval",
            "game_id": self.game.id,
            "line": self.game._line_nodes.copy(),
            "index": 0,
            "stage": "best",
            "seconds": 600,
            "paused": False,
            "info": None,
            "generation": None,
            "depth": 128,
            "nodes": self.config.get("auto_eval_nodes") or None,
            "multipv": self._effective_multipv(),
        }
        self.analysis_nav.setChecked(True)
        self.play_nav.setChecked(False)
        self._refresh()
        self.quick_analysis_button.setText("Stop auto-evaluation")
        self._render_move_history()
        self._save()
        self._review_next()

    def _start_auto_play(self):
        if self._auto_play_active:
            self.paused = not self.paused
            if self.paused:
                self.engine.stop()
                self.quick_analysis_button.setText("Resume auto-play")
                self.pause_button.setText("Continue")
                self.statusBar().showMessage("Auto-play paused · press F11 to resume")
            else:
                self.quick_analysis_button.setText("Pause auto-play")
                self.pause_button.setText("Pause")
                self.statusBar().showMessage("Auto-play resumed")
                self._schedule_engine()
            self._save()
            return
        if not self._profile():
            self._manage_engines()
            return
        self._cancel_review()
        self._stop_engine()
        self._ensure_analysis_copy()
        self.analysis_mode = True
        self.paused = False
        self._analysis_enabled = False
        self._auto_play_active = True
        self.game.pause_clock()
        self.analysis_nav.setChecked(True)
        self.play_nav.setChecked(False)
        self._refresh()
        self.quick_analysis_button.setText("Pause auto-play")
        self._save()
        self._schedule_engine()

    def _analyze_game(self):
        from PySide6.QtWidgets import QInputDialog

        if not self._profile():
            self._manage_engines()
            return
        seconds, ok = QInputDialog.getDouble(
            self,
            "Analyze entire line",
            "Seconds per position / targeted move",
            self.config.get("review_seconds", 3),
            0.05,
            600,
            2,
        )
        if not ok:
            return
        self._show_review()
        self._begin_review(seconds)

    def _begin_review(self, seconds):
        if not self._profile():
            self._manage_engines()
            self._update_review_panel()
            return
        if len(self.game._line_nodes) < 2:
            return
        self._cancel_review()
        self._stop_engine()
        self._analysis_enabled = False
        self.config["review_seconds"] = seconds
        self.review_panel.seconds.setValue(seconds)
        # Freeze the line and node identities; the displayed position is free to move.
        self.game._sync_tree_state()
        self._review = {
            "game_id": self.game.id,
            "line": self.game._line_nodes.copy(),
            "index": 0,
            "stage": "best",
            "seconds": seconds,
            "paused": False,
            "info": None,
            "generation": None,
            "depth": self.config.get("analysis_depth", 24),
            "nodes": self.config.get("analysis_nodes") or None,
        }
        if not isinstance(self.game.metadata.get("review"), dict):
            self.game.metadata["review"] = {}
        records = self.game.metadata["review"]
        for node_id in self._review["line"][1:]:
            records.pop(str(node_id), None)
        self._render_move_history()
        self._update_review_panel()
        self._save()
        self._review_next()

    def _review_next(self):
        if self._closing:
            self._review = None
            return
        state = self._review
        if not state or state["paused"]:
            return
        if state.get("generation") is not None and self.engine.busy:
            return
        if state["game_id"] != self.game.id:
            self._cancel_review()
            return
        if state["index"] >= len(state["line"]):
            self._review = None
            self.quick_analysis_button.setText("Analyze")
            message = (
                "Auto-evaluation complete · MultiPV results saved for every position"
                if state.get("kind") == "auto_eval"
                else "Game analysis complete · evaluations and review evidence saved"
            )
            self.statusBar().showMessage(message)
            self._save()
            self._render_move_history()
            self._update_review_panel()
            return
        node_id = state["line"][state["index"]]
        position = self.game.position_at_node(node_id)
        if position.outcome():
            state["index"] += 1
            state["stage"] = "best"
            QTimer.singleShot(0, self._review_next)
            return
        from types import SimpleNamespace

        path = self.game.node_path(node_id)
        temporary = SimpleNamespace(
            initial_fen=self.game.initial_fen,
            id=self.game.id,
            moves=[self.game.nodes[i].move for i in path[1:]],
            cursor=len(path) - 1,
            board=position,
        )
        profile = self._profile()
        if not profile:
            self._cancel_review()
            return
        searchmoves = None
        if state["stage"] == "played":
            searchmoves = [self.game.nodes[state["line"][state["index"] + 1]].move.uci()]
        limits = SearchLimits(
            depth=state["depth"],
            seconds=state["seconds"],
            nodes=state["nodes"],
        )
        try:
            generation = self.engine.start(
                temporary,
                limits,
                profile["path"],
                options=profile.get("values", {}),
                multipv=state.get("multipv", 1),
                infinite=state.get("kind") == "auto_eval" and state["nodes"] is None,
                nodes_only=state.get("kind") == "auto_eval",
                kind="analysis",
                searchmoves=searchmoves,
                arguments=profile.get("arguments", []),
                tablebase_path=self.config.get("syzygy_path", ""),
            )
        except (OSError, ValueError, RuntimeError) as exc:
            self._error("Game analysis stopped", str(exc))
            self._cancel_review()
            return
        state["generation"] = generation
        state["info"] = None
        state.pop("message", None)
        state["turn"] = position.turn
        state["profile"] = profile["id"]
        state["options"] = dict(profile.get("values", {}))
        self.quick_analysis_button.setText(
            "Pause auto-evaluation" if state.get("kind") == "auto_eval" else "Pause review"
        )
        if state.get("kind") == "auto_eval":
            self.statusBar().showMessage(
                f"Auto-evaluating position {state['index'] + 1}/{len(state['line'])}"
            )
        else:
            self.statusBar().showMessage(
                f"Game analysis {state['index'] + 1}/{len(state['line'])} · {state['stage']} search"
            )
        self._update_review_panel()

    def _review_message(self, generation, kind, payload):
        state = self._review
        if state and state["game_id"] != self.game.id:
            self.engine.stop()
            self._review = None
            return True
        if not state or generation != state.get("generation"):
            return False
        if kind == "error":
            state["paused"] = True
            state["generation"] = None
            state["message"] = payload["message"] + " · review paused"
            self.statusBar().showMessage(payload["message"])
            self._update_review_panel()
            return True
        if kind == "info":
            state["info"] = payload.copy()
            return True
        if kind != "result":
            return True
        info = payload.get("info") or state["info"]
        valid = chance(info) is not None and bool(info.get("pv"))
        if valid and state["stage"] == "played":
            valid = info["pv"][0] == self.game.nodes[state["line"][state["index"] + 1]].move.uci()
        if not valid:
            state["paused"] = True
            state["generation"] = None
            state["message"] = "No exact score for the requested move; review paused."
            self.statusBar().showMessage(state["message"])
            self._update_review_panel()
            return True
        index = state["index"]
        state["generation"] = None
        line = state["line"]
        node_id = line[index]
        if state.get("kind") == "auto_eval":
            lines = payload.get("lines") or {1: info}
            self._store_analysis(self.game, node_id, info, state["turn"], state)
            self.game.nodes[node_id].analysis["multipv_lines"] = [
                dict(lines[rank]) for rank in sorted(lines)
            ]
            state["index"] += 1
            self.graph.set_samples(self.game.evaluations, self.game.cursor, len(self.game.moves))
            self._save()
            self._render_move_history()
            QTimer.singleShot(0, self._review_next)
            return True
        if state["stage"] == "best":
            self._store_analysis(self.game, node_id, info, state["turn"], state)
            state["best"] = info.copy()
            if index + 1 < len(line):
                played = self.game.nodes[line[index + 1]].move.uci()
                if info["pv"][0] != played:
                    state["stage"] = "played"
                    QTimer.singleShot(0, self._review_next)
                    self._save()
                    return True
                self._classify_review(line[index + 1], info, info)
        else:
            self._classify_review(line[index + 1], state["best"], info)
        state["index"] += 1
        state["stage"] = "best"
        self.graph.set_samples(self.game.evaluations, self.game.cursor, len(self.game.moves))
        self._save()
        self._render_move_history()
        self._update_review_panel()
        QTimer.singleShot(0, self._review_next)
        return True

    def _classify_review(self, node_id, best, played):
        node = self.game.nodes[node_id]
        state = self._review or {}
        record = classify(self.game.position_at_node(node.parent), node.move, best, played, {
            "profile": state.get("profile", ""), "options": state.get("options", {}),
            "seconds": state.get("seconds"), "depth": state.get("depth"),
            "nodes": state.get("nodes"),
            "engine": best.get("engine", "UCI"),
        })
        if record is None:
            return
        self.game.metadata.setdefault("review", {})[str(node_id)] = record
        self.statusBar().showMessage(self.game.nodes[node_id].san + " · " + record["label"])

    def _pause_review(self):
        if not self._review:
            return
        self._review["paused"] = not self._review["paused"]
        if self._review["paused"]:
            self.engine.stop()
            self._review["generation"] = None
            self.quick_analysis_button.setText(
                "Resume auto-evaluation"
                if self._review.get("kind") == "auto_eval"
                else "Resume review"
            )
            self._save()
        else:
            self._review_next()
        self._update_review_panel()

    def _cancel_review(self):
        if self._review:
            self.engine.stop()
            self._review = None
            self.quick_analysis_button.setText("Analyze")
            self._save()
        self._update_review_panel()

    def _choose_engine(self):
        self._manage_engines()

    def _profile(self):
        return next((p for p in self.profiles if p["id"] == self.config.get("engine_id", "")), None)

    def _manage_engines(self):
        self._cancel_review()
        self._stop_engine()
        dialog = EngineManager(
            self.profiles, self.config.get("engine_id", ""), self,
            allocated_hash=self.resource_controls.allocated_hash(),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.profiles = dialog.profiles
        self.config["engine_id"] = dialog.selected
        self._apply_settings()
        self._save()
        self._schedule_engine()

    def _select_profile(self, profile_id):
        if profile_id == self.config.get("engine_id"):
            return
        self._cancel_review()
        self.config["engine_id"] = profile_id
        self.resource_controls.refresh()
        if hasattr(self, "engine"):
            self._stop_engine()
            self._save()
            self._schedule_engine()

    def _set_engine_resource(self, name, value):
        profile = self._profile()
        try:
            number = validate_resource(profile, name, value, self.resource_controls.allocated_hash())
        except (TypeError, ValueError) as exc:
            self._error("Cannot apply engine setting", str(exc))
            return
        if value is not None and profile["values"].get(name) == number:
            self.resource_controls.refresh()
            return
        self._cancel_review()
        self._stop_engine()
        if value is None:
            profile["values"].pop(name, None)
        else:
            profile["values"][name] = number
        self._analysis_context = None
        self._clear_analysis_output()
        self._save()
        self.resource_controls.refresh()
        self._schedule_engine()

    def _effective_multipv(self):
        profile = self._profile()
        option = profile.get("options", {}).get("MultiPV") if profile else None
        maximum = min(32, int(option["maximum"])) if option else (1 if profile and profile.get("options_detected") else 32)
        return max(1, min(maximum, self.config.get("multipv", 1)))

    def _set_multipv(self, count):
        profile = self._profile()
        option = profile.get("options", {}).get("MultiPV") if profile else None
        maximum = min(32, int(option["maximum"])) if option else 1
        if not 1 <= count <= maximum:
            self._error("MultiPV unavailable", f"Choose 1–{maximum} lines for this engine")
            return
        self._cancel_review()
        self._stop_engine()
        self.config["multipv"] = count
        self.config.pop("searchmoves", None)
        self._analysis_context = None
        self._clear_analysis_output()
        self._save()
        self._refresh_engine_menus()
        self._schedule_engine()

    def _custom_multipv(self):
        profile = self._profile()
        option = profile.get("options", {}).get("MultiPV") if profile else None
        if not option:
            return
        maximum = min(32, int(option["maximum"]))
        count, accepted = QInputDialog.getInt(self, "MultiPV", "Number of analysis lines:", self._effective_multipv(), 1, maximum)
        if accepted and self._profile() is profile:
            self._set_multipv(count)

    def _set_analysis_limit(self, mode):
        self._cancel_review()
        self._stop_engine()
        self.config["analysis_kind"] = mode
        self._analysis_context = None
        self._clear_analysis_output()
        self._save()
        self._refresh_engine_menus()
        self._schedule_engine()

    def _set_auto_eval_limit(self, nodes):
        self._set_node_limit("auto_eval_nodes", nodes)

    def _set_node_limit(self, key, nodes):
        self.config[key] = int(nodes)
        if key == "auto_eval_nodes":
            self.config["auto_eval_limit_version"] = 2
        self._save()
        self._refresh_engine_menus()
        # Normal bounded analysis can adopt the new cap immediately. The two
        # batch modes read their caps when the next run starts.
        if key == "analysis_nodes" and self.analysis_mode and self._analysis_enabled and self.config.get("analysis_kind") == "bounded":
            self._stop_engine()
            self._schedule_engine()

    def _custom_node_limit(self, key, title, minimum=0):
        if key == "auto_play_nodes":
            minimum = 1
        nodes, accepted = QInputDialog.getInt(
            self, title, "Maximum engine nodes per position (0 means unlimited):",
            self.config.get(key, 0), minimum, 2_000_000_000, 1_000_000,
        )
        if accepted:
            self._set_node_limit(key, nodes)

    def _populate_node_limit_menu(self, menu, key, label, values, allow_unlimited=True):
        current = self.config.get(key, 0)
        current_label = "Unlimited" if current == 0 else f"{current:,}"
        menu.setTitle(f"{label} · {current_label}")
        if allow_unlimited:
            action = menu.addAction("Unlimited · stop manually")
            action.setCheckable(True)
            action.setChecked(current == 0)
            action.triggered.connect(lambda checked=False, k=key: self._set_node_limit(k, 0))
        for nodes in values:
            action = menu.addAction(f"{nodes:,}")
            action.setCheckable(True)
            action.setChecked(current == nodes)
            action.triggered.connect(lambda checked=False, k=key, n=nodes: self._set_node_limit(k, n))
        menu.addSeparator()
        menu.addAction("Custom…", lambda checked=False, k=key, t=label: self._custom_node_limit(k, t))

    def _edit_analysis_limits(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Analysis limits")
        form = QFormLayout(dialog)
        depth, seconds, nodes = QSpinBox(), QDoubleSpinBox(), QSpinBox()
        depth.setRange(1, 128)
        depth.setValue(self.config["analysis_depth"])
        seconds.setRange(0.05, 600)
        seconds.setDecimals(2)
        seconds.setValue(self.config["analysis_seconds"])
        seconds.setSuffix(" seconds")
        nodes.setRange(0, 2_000_000_000)
        nodes.setSpecialValueText("Unlimited")
        nodes.setValue(self.config["analysis_nodes"])
        form.addRow("Depth", depth)
        form.addRow("Time", seconds)
        form.addRow("Nodes", nodes)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config.update(analysis_depth=depth.value(), analysis_seconds=seconds.value(), analysis_nodes=nodes.value())
            self._set_analysis_limit("bounded")

    def _refresh_engine_menus(self):
        self.resource_controls.refresh()
        self.resource_status_action.setText(self.resource_controls.summary)
        self.profile_menu.clear()
        for profile in self.profiles:
            action = self.profile_menu.addAction(profile.get("label") or profile.get("name", Path(profile["path"]).stem))
            action.setCheckable(True)
            action.setChecked(profile["id"] == self.config.get("engine_id"))
            action.triggered.connect(lambda checked=False, p=profile["id"]: self._select_profile(p))
        if not self.profiles:
            self.profile_menu.addAction("Choose an engine first").setEnabled(False)
        self.search_mode_menu.clear()
        for title, mode in (("Continuous", "infinite"), ("Bounded", "bounded")):
            action = self.search_mode_menu.addAction(title)
            action.setCheckable(True)
            action.setChecked((self.config.get("analysis_kind") == "bounded") == (mode == "bounded"))
            action.triggered.connect(lambda checked=False, m=mode: self._set_analysis_limit(m))
        self.search_mode_menu.addSeparator()
        self.search_mode_menu.addAction("Set limits…", self._edit_analysis_limits)
        for menu in (self.normal_limit_menu, self.auto_eval_limit_menu, self.auto_play_limit_menu):
            menu.clear()
        standard_nodes = [*range(100_000_000, 1_000_000_001, 100_000_000),
                          50_000_000, 10_000_000, 1_000_000, 100_000, 10_000]
        self._populate_node_limit_menu(
            self.normal_limit_menu, "analysis_nodes", "Normal nodes per position", standard_nodes
        )
        self._populate_node_limit_menu(
            self.auto_eval_limit_menu, "auto_eval_nodes", "Auto-evaluation nodes per position", standard_nodes
        )
        self._populate_node_limit_menu(
            self.auto_play_limit_menu, "auto_play_nodes", "Auto-play nodes per move",
            [*standard_nodes, 1_000], allow_unlimited=False,
        )
        self.multipv_menu.clear()
        profile = self._profile()
        option = profile.get("options", {}).get("MultiPV") if profile else None
        current = self._effective_multipv()
        self.multipv_menu.setTitle(f"MultiPV ({current})")
        if not option:
            self.multipv_menu.addAction("Not advertised by this engine" if profile and profile.get("options_detected") else "Choose / detect an engine first").setEnabled(False)
            return
        maximum = min(32, int(option["maximum"]))
        for count in sorted({n for n in (1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 24, 32, current) if n <= maximum}):
            action = self.multipv_menu.addAction(str(count))
            action.setData(count)
            action.setCheckable(True)
            action.setChecked(count == current)
            action.triggered.connect(lambda checked=False, n=count: self._set_multipv(n))
        self.multipv_menu.addSeparator()
        self.multipv_menu.addAction("Custom…", self._custom_multipv)
        self.multipv_menu.addAction("More lines divide search effort").setEnabled(False)
        self.multipv_menu.addAction(f"Display range: 1–{maximum}").setEnabled(False)

    def _engine_discovered(self, data):
        from dataclasses import asdict

        matching = [p for p in self.profiles if Path(p["path"]).resolve() == Path(data["path"]).resolve()]
        profile = next((p for p in matching if p is self._profile()), next(iter(matching), None))
        if profile:
            profile["name"] = data["name"]
            profile["options"] = {n: asdict(o) for n, o in data["options"].items()}
            profile["options_detected"] = True
            count = self._effective_multipv()
            restart = self._job and self._job.get("multipv", 1) != count and not self.config.get("searchmoves")
            self.config["multipv"] = count
            if restart:
                self._stop_engine()
                self._analysis_context = None
                QTimer.singleShot(0, self._schedule_engine)
            if self.config.get("syzygy_path"):
                self.tablebase_label.setText(
                    "Syzygy path sent to engine"
                    if "SyzygyPath" in data["options"]
                    else "Engine does not advertise SyzygyPath"
                )
            self._save()
            self._refresh_engine_menus()

    def _restart_engine(self):
        self._analysis_context = None
        if profile := self._profile():
            self._stop_engine()
            try:
                self.engine.connect_engine(profile["path"], profile.get("arguments", []))
            except ValueError as exc:
                self._error("Cannot connect engine", str(exc))
            self._schedule_engine()

    def _diagnostics(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Engine diagnostics")
        dialog.resize(850, 550)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText("\n".join(self.engine.connection.log))
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _choose_tablebase(self):
        path = QFileDialog.getExistingDirectory(
            self, "Choose Syzygy tablebase folder", self.config.get("syzygy_path", "")
        )
        if path:
            self._stop_engine()
            self.config["syzygy_path"] = path
            self.tablebase_label.setText("Syzygy: folder selected; awaiting probe")
            self._save()
            self._schedule_engine()

    def _appearance_config(self):
        return getattr(self, "_appearance_preview", None) or self.config

    def _preview_appearance(self, appearance):
        self._appearance_preview = appearance
        self._apply_appearance(appearance)

    def _apply_appearance(self, appearance):
        light = appearance.get("light", False)
        QApplication.instance().setStyleSheet(stylesheet(light))
        self.board_view.theme = appearance.get("theme", "Classic")
        self.board_view.set_piece_set(appearance.get("piece_set", "Nibbler"))
        self.board_view.coordinates = appearance.get("coordinates", True)
        self.board_view.animations = appearance.get("animations", True)
        self.board_view.overlays = appearance.get("overlays", True)
        self.history.setStyleSheet(f"QTableWidget {{ color: {palette(light)['history']}; }}")
        self.eval_label.setStyleSheet(f"color: {palette(light)['metric']};")
        self.telemetry.setStyleSheet(f"color: {palette(light)['metadata']};")
        self.telemetry.setTextFormat(Qt.TextFormat.RichText)
        self.graph.light = self.board_view.light = light
        self.graph.setVisible(self.config.get("show_eval_graph", True))
        self.graph.update()
        self.eval_bar.setVisible(self.board_view.overlays)
        self._render_move_history()
        self.candidates.recolor(light)
        for view in {self.pv_label, *(widgets[2] for widgets in self.candidates.rows.values())}:
            view.set_moves(view._items, view._current, light=light)
        self.board_view.update()

    def _apply_settings(self):
        self._apply_appearance(self._appearance_config())
        self.candidates.set_show_seldepth(self.config.get("show_seldepth", False))
        if self._last_info:
            self._render_telemetry(self._last_info, self._last_info_turn)
        self.tablebase_label.setVisible(bool(self.config.get("syzygy_path")))
        self.board_view.smart_move = self.config.get("smart_move", True)
        self.board_view.candidate_style = self.config.get("candidate_style", "lines")
        for key, action in self.marker_actions.items():
            action.setChecked(key == self.board_view.candidate_style)
        for key, action in self.display_actions.items():
            action.setChecked(bool(self.config.get(key, False)))
        if hasattr(self, "reanalyze_navigation_action"):
            self.reanalyze_navigation_action.setChecked(
                bool(self.config.get("reanalyze_on_navigation", False))
            )
        if not self._profile() and self.profiles:
            self.config["engine_id"] = self.profiles[0]["id"]
        self._refresh_engine_menus()
        self._update_players()

        self.board_view.wheel_navigation = self.config.get("wheel_game_moves", True)
        self.analysis_history.wheel_navigation = self.config.get("wheel_game_moves", True)
        self.candidates.set_wheel_navigation(self.config.get("wheel_analysis_moves", True))
        self._sync_explorer()
        self._sync_raw_pgn()
        self.candidates.set_expanded(self.config.get("expand_pv", False))
        self.expand_pv_action.setChecked(self.config.get("expand_pv", False))
        self.cursor_preview_action.setChecked(self.config.get("cursor_preview", False))

    def _sync_workspace_layout(self):
        analysis = self.analysis_mode
        signature = (analysis, self.config.get("layout", "classic"))
        if self._analysis_layout_active == signature:
            return
        self._analysis_layout_active = signature
        self._clear_move_preview()
        for widget in (
            self.sidebar,
            self.workspace_header,
            self.top_card,
            self.bottom_card,
            self.board_hint,
            self.pause_button,
            self.draw_button,
            self.resign_button,
        ):
            widget.setVisible(not analysis)
        self.analysis_moves_panel.setVisible(analysis)
        self.tabs.setTabVisible(0, not analysis)
        self.panel_caption.setText("ENGINE ANALYSIS" if analysis else "THE GAME")
        self.panel_caption.setVisible(not analysis)
        self.io_bar.setVisible(not analysis)
        self.save_label.setVisible(not analysis)
        self.mode_label.setVisible(not analysis)
        self.status_label.setVisible(not analysis)
        self.content_layout.setContentsMargins(*( (12, 6, 12, 6) if analysis else (25, 22, 25, 12) ))
        self.content_layout.setSpacing(6 if analysis else 15)
        self.panel_body.layout().setContentsMargins(*( (8, 4, 8, 4) if analysis else (20, 16, 20, 12) ))
        self.panel_body.layout().setSpacing(2 if analysis else 10)
        self.panel.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff if analysis else Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._analysis_tab_changed()
        self.panel.setMaximumWidth(16777215 if analysis else 420)
        left = analysis and self.config.get("layout", "classic") == "analysis-left"
        self.main_splitter.insertWidget(0 if left else 1, self.panel)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 1 if analysis else 0)
        if analysis:
            self.tabs.setCurrentIndex(1)
            self.main_splitter.setSizes([1020, 780] if left else [780, 1020])
            self.workspace_splitter.setSizes([800, 90])
        else:
            self.main_splitter.setSizes([720, 350])

    def _analysis_tab_changed(self, index=None):
        if hasattr(self, "tabs"):
            self.tabs.tabBar().setVisible(not self.analysis_mode or self.tabs.currentIndex() != 1)
            self.panel.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded if self.tabs.currentWidget() is getattr(self, "review_panel", None)
                or not self.analysis_mode else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            if self.tabs.currentWidget() is getattr(self, "review_panel", None):
                self._update_review_panel()
            if self.tabs.currentWidget() is getattr(self, "raw_pgn_page", None):
                self._refresh_raw_pgn()
        self._sync_explorer()

    def _render_move_history(self):
        tokens = self.game.tree_tokens()
        self.analysis_history.set_moves(tokens, self.game.current_node, self._appearance_config().get("light", False))
        self._refresh_raw_pgn()

    def _end_preview(self, source):
        if self._preview_source == source:
            self._clear_move_preview()

    def _clear_move_preview(self):
        self._preview_source = None
        self.board_view.clear_preview()
        self.hover_preview.hide()

    def _show_move_preview(self, source, position, last_move=None, caption="Move preview"):
        self._preview_source = source
        if self.config.get("cursor_preview", False):
            self.board_view.clear_preview()
            self.hover_preview.show_position(position, last_move, self.board_view, caption)
        else:
            self.hover_preview.hide()
            self.board_view.show_preview(position, last_move, caption)

    def _preview_history(self, node_id):
        if not self.analysis_mode or not 1 <= node_id < len(self.game.nodes):
            return
        node = self.game.nodes[node_id]
        position = self.game.position_at_node(node_id)
        self._show_move_preview("history", position, node.move, f"History preview · {node.san}")

    def _preview_pv(self, ply):
        if (
            not self.analysis_mode
            or self._pv_root is None
            or self._pv_identity != self._position_identity()
            or not 1 <= ply <= len(self._pv_moves)
        ):
            return
        position = self._pv_root.copy(history=False)
        for move in self._pv_moves[:ply]:
            position.push(move)
        self._show_move_preview("pv", position, self._pv_moves[ply - 1], f"Suggested line preview · ply {ply}")

    def changeEvent(self, event):
        if (
            event.type() == QEvent.Type.ActivationChange
            and not self.isActiveWindow()
            and hasattr(self, "board_view")
        ):
            self._clear_move_preview()
        super().changeEvent(event)

    def hideEvent(self, event):
        if hasattr(self, "hover_preview"):
            self._clear_move_preview()
        super().hideEvent(event)

    def _human_move(self, move: Move):
        if not self.board_view.interactive or self.board_view.preview_board is not None:
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
        self.delete_line_action.setEnabled(self.analysis_mode and self.game.current_node != 0)
        self._register_study()
        self._update_review_panel()
        self._sync_workspace_layout()
        self._clear_move_preview()
        if self._pgn_game_id != self.game.id or not self.pgn_editor.document().isModified():
            text = self.game.pgn()
            if self.pgn_editor.toPlainText() != text:
                self.pgn_editor.setPlainText(text)
            self.pgn_editor.document().setModified(False)
            self._pgn_game_id = self.game.id
        last = self.game.moves[self.game.cursor - 1] if self.game.cursor else None
        self.board_view.set_position(self.game.board, last, animate)
        next_game_move = (
            self.game.moves[self.game.cursor]
            if self.game.cursor < len(self.game.moves)
            else None
        )
        self.board_view.set_game_move(next_game_move)
        self._render_move_history()
        if self._pv_identity != self._position_identity():
            self._pv_root = None
            self._pv_moves = []
            self.pv_label.set_moves([])
            self.candidates.clear()
            self._candidate_identity = None
            self.config["searchmoves"] = []
            self.tablebase_label.setText(
                "Syzygy: awaiting probe" if self.config.get("syzygy_path") else "Syzygy: not configured"
            )
        outcome = self.game.outcome
        self.board_view.branch_moves = (
            [self.game.nodes[c].move for c in self.game.nodes[self.game.current_node].children]
            if self.config.get("branch_arrows", True)
            else []
        )
        self.board_view.interactive = (
            not outcome and not self.paused and (self.analysis_mode or not self._is_engine_turn())
        )
        self._sync_explorer()
        turn = "White" if self.game.board.turn == 1 else "Black"
        status = (
            f"{outcome.result} · {outcome.reason}"
            if outcome
            else f"{turn} to move" + (" · Check" if self.game.board.in_check() else "")
        )
        self.status_label.setText(status)
        mode = self.config.get("mode", "human_ai")
        self.mode_label.setText(
            "Analysis"
            if self.analysis_mode
            else {
                "human_ai": "Play Nocturne"
                if self.config.get("black_engine", "custom") == "custom"
                else "Play UCI engine",
                "human": "Two players",
                "ai_ai": "Engine theatre",
                "analysis": "Analysis",
            }.get(mode, "Two players")
        )
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
        clocks_visible = self.config.get("show_clocks", True)
        self.analysis_clocks.setVisible(self.analysis_mode and clocks_visible)
        self.top_clock.setVisible(clocks_visible)
        self.bottom_clock.setVisible(clocks_visible)
        top_color = 1 if self.board_view.flipped else -1
        values = self.game.clock_values()
        pgn_values = self.game.pgn_clock_values()
        for color, value in self.analysis_clock_values.items():
            title = "White" if color == 1 else "Black"
            self.analysis_clock_names[color].setText(title)
            if self.game.time_control.seconds:
                value.setText(self._clock_text(values[color]))
            elif pgn_values[color] is not None:
                value.setText(pgn_values[color][1])
            elif self.game.has_pgn_clocks:
                value.setText("—")
            else:
                value.setText("∞")
        material = sum(
            (1 if self.game.board.cells[s] > 0 else -1) * (0, 1, 3, 3, 5, 9, 0)[abs(self.game.board.cells[s])]
            for s in SQUARES
            if self.game.board.cells[s]
        )
        for color, name, detail, clock in (
            (top_color, self.top_name, self.top_detail, self.top_clock),
            (-top_color, self.bottom_name, self.bottom_detail, self.bottom_clock),
        ):
            name.setText(self.game.headers.get("White" if color == 1 else "Black", "Player"))
            balance = material * color
            detail.setText(
                ("White pieces" if color == 1 else "Black pieces")
                + (f"  ·  +{balance}" if balance > 0 else "")
            )
            clock.setText(self._clock_text(values[color]) if self.game.time_control.seconds else "∞")
            active = self.game.running and self.game.board.turn == color
            style = "activeClock" if active else "clock"
            if clock.objectName() != style:
                clock.setObjectName(style)
                clock.style().unpolish(clock)
                clock.style().polish(clock)
                clock.updateGeometry()

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
        self._cancel_review()
        self._stop_engine()
        mode = self.config.get("mode", "human_ai")
        if self.config.get("human_color", 1) == 0:
            self.config["human_color"] = random.choice((1, -1))
        control = (
            TimeControl()
            if mode == "analysis"
            else TimeControl(self.config.get("seconds", 0), self.config.get("increment", 0))
        )
        self.game = Game(time_control=control)
        names = {1: self.config.get("white_name", "White"), -1: self.config.get("black_name", "Black")}
        if mode == "human_ai":
            human = self.config.get("human_color", 1)
            if names[human] in ("White", "Black", ""):
                names[human] = "You"
            if names[-human] in ("White", "Black", ""):
                names[-human] = (
                    "Nocturne" if self.config.get("black_engine", "custom") == "custom" else "UCI engine"
                )
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
        if not analysis:
            self._cancel_review()
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
        self.subtitle_label.setText(
            "Follow an idea. Try another line." if analysis else "Find your focus. Enjoy the game."
        )
        self._refresh()
        self._schedule_engine()

    def _navigation_should_analyze(self):
        return bool(
            self.config.get("reanalyze_on_navigation", False)
            or (self.analysis_mode and self._analysis_enabled and not self.paused)
        )

    def _undo(self):
        if not self.analysis_mode and not self.config.get("takebacks", True):
            return
        analyze = self._navigation_should_analyze()
        self._stop_engine()
        if self.game.undo():
            if not self.analysis_mode and self.config.get("mode") == "human_ai":
                if self.game.board.turn != self.config.get("human_color", 1) and self.game.cursor:
                    self.game.undo()
            self._refresh()
            self._save()
            self._analysis_enabled = analyze
            if analyze:
                self.paused = False
            self._schedule_engine()

    def _redo(self):
        if self.game.cursor >= len(self.game.moves):
            return
        analyze = self._navigation_should_analyze()
        self._stop_engine()
        self._ensure_analysis_copy()
        if self.game.redo():
            if not self.analysis_mode:
                self.analysis_mode = True
            self._analysis_enabled = analyze
            if analyze:
                self.paused = False
            self._refresh()
            self._save()
            self._schedule_engine()

    def _wheel_game(self, steps):
        cursor = max(0, min(len(self.game.moves), self.game.cursor + steps))
        if cursor != self.game.cursor:
            self._navigate(cursor)

    def _navigate(self, cursor):
        if not self.analysis_mode and not self.config.get("takebacks", True):
            return
        analyze = self._navigation_should_analyze()
        previous = self.game.cursor
        self._stop_engine()
        self._ensure_analysis_copy()
        self.game.navigate(cursor)
        # A normal rewind onto the shared main line should make its recorded
        # continuation active, rather than resuming the branch we rewound from.
        if cursor < previous and self.game.current_node == self.game.mainline_node(cursor):
            self.game.select_node(self.game.current_node)
        self.analysis_mode = True
        self._analysis_enabled = analyze
        if analyze:
            self.paused = False
        self.analysis_nav.setChecked(True)
        self.title_label.setText("Room to explore.")
        self._refresh()
        self._schedule_engine()

    def _navigate_node(self, node_id):
        if not self.analysis_mode and not self.config.get("takebacks", True):
            return
        analyze = self._navigation_should_analyze()
        self._stop_engine()
        self._ensure_analysis_copy()
        self.game.select_node(node_id)
        self.analysis_mode = True
        self._analysis_enabled = analyze
        if analyze:
            self.paused = False
        self._refresh()
        self._save()
        self._schedule_engine()

    def _sibling(self, direction):
        node = self.game.nodes[self.game.current_node]
        if node.parent is None:
            return
        siblings = self.game.nodes[node.parent].children
        index = siblings.index(self.game.current_node) + direction
        if 0 <= index < len(siblings):
            self._navigate_node(siblings[index])

    def _promote_line(self):
        self._stop_engine()
        self._ensure_analysis_copy()
        self.game.promote_current_line()
        self._refresh()
        self._save()
        self._schedule_engine()

    def _delete_line(self):
        if not self.analysis_mode or self.game.current_node == 0:
            return
        self._cancel_review()
        self._stop_engine()
        if self.game.delete_current_line():
            self._refresh()
            self._save()
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
                dialog = TextDialog(
                    "Claim a draw",
                    "Enter the intended legal move in SAN or UCI. A valid claim ends the game without playing the move.",
                    parent=self,
                )
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
                if self.config.get("mode") in ("human_ai", "ai_ai"):
                    self.statusBar().showMessage(
                        "UCI has no draw-offer protocol. Valid draw claims remain available.", 5000
                    )
                    return
                if (
                    QMessageBox.question(self, "Offer a draw", "Does the other player accept a draw?")
                    != QMessageBox.StandardButton.Yes
                ):
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
            self.game.resign(
                self.config.get("human_color", 1) if self.config.get("mode") == "human_ai" else None
            )
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
        dialog = TextDialog(
            "Import position or game", "Paste a six-field FEN or a single PGN game.", parent=self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._import_text(dialog.editor.toPlainText())

    def _import_text(self, text):
        text = text.strip()
        try:
            if not text:
                raise ValueError("Paste a PGN game, SAN moves, or a six-field FEN first.")
            first = text.split()[0] if text else ""
            if first.count("/") == 7:
                games = [Game(text)]
            else:
                from ..core.notation import read_pgns, write_pgn

                games = [Game.from_pgn(write_pgn(parsed)) for parsed in read_pgns(text)]
            game = games[0]
        except ValueError as exc:
            self._error("Cannot import", str(exc))
            return False
        self._save()
        self._stop_engine()
        self._cancel_review()
        for imported in games:
            imported.metadata["mode"] = "analysis"
            self._study_games[imported.id] = imported
            if self.store:
                try:
                    self.store.save(imported, autosave=False)
                except StorageError as exc:
                    self.statusBar().showMessage(str(exc))
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
            self.store.set("settings", self.config)
            self.store.set("engine_profiles", self.profiles)
            self.store.set("open_studies", list(self._study_games)[-20:])
            self.store.save(self.game)
            self.save_label.setText("SAVED ON THIS DEVICE")
        except StorageError as exc:
            self.save_label.setText("SAVE FAILED · SEE STATUS")
            self.statusBar().showMessage(str(exc))

    def _library(self):
        if not self.store:
            self._error("Library unavailable", self._storage_message)
            return
        dialog = QDialog(self)
        self._save()
        dialog.setWindowTitle("Saved PGNs and games")
        dialog.resize(640, 430)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Saved PGNs & games", "title"))
        layout.addWidget(label("Games and studies are saved automatically on this device.", "muted", True))
        layout.addWidget(button("Open PGN folder", self._open_pgn_folder))
        listing = QListWidget()
        try:
            games = self.store.list_games()
        except StorageError as exc:
            self._error("Library unavailable", str(exc))
            return
        for record in games:
            item = QListWidgetItem(
                f"{record['title']}\n{record['updated'][:16].replace('T', ' ')} UTC · {record['plies']} plies · {record['result']}"
            )
            item.setData(Qt.ItemDataRole.UserRole, record["id"])
            listing.addItem(item)
        layout.addWidget(listing)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel
        )
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
            self._cancel_review()
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

    def _start_pgn_archive_migration(self):
        if not self.store:
            return
        try:
            self._archive_pending = iter(self.store.game_ids())
            self.archive_timer.start()
        except StorageError as exc:
            self.statusBar().showMessage(str(exc))

    def _archive_previous_pgn(self):
        if self._closing or not self.store:
            self.archive_timer.stop()
            return
        game_id = next(self._archive_pending, None)
        if game_id is None:
            self.archive_timer.stop()
            return
        try:
            if not self.store.pgn_path(game_id).exists():
                self.store.archive_pgn(self.store.load(game_id))
        except StorageError as exc:
            self.statusBar().showMessage(str(exc))

    def _open_pgn_folder(self):
        if not self.store:
            self._error("PGN folder unavailable", self._storage_message)
            return
        self._save()
        try:
            directory = self.store.pgn_directory
            directory.mkdir(parents=True, exist_ok=True)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory.absolute()))):
                self._error("Cannot open PGN folder", str(directory))
        except OSError as exc:
            self._error("Cannot open PGN folder", str(exc))

    def _settings(self):
        dialog = SettingsDialog(self.config, self)
        dialog.appearance_changed.connect(self._preview_appearance)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self._appearance_preview = None
        if accepted:
            self._cancel_review()
            self._stop_engine()
            self.config.update(dialog.config())
            self._apply_settings()
            self._save()
            self._schedule_engine()
        else:
            self._apply_appearance(self.config)
        dialog.deleteLater()

    def _analyze(self):
        if self._auto_play_active:
            self._start_auto_play()
            return
        if not self._profile():
            self._manage_engines()
            return
        if self._review:
            self._pause_review()
            return
        if self._job and self._job["kind"] == "analysis":
            self._halt_analysis()
            return
        self._start_analysis()

    def _halt_analysis(self):
        if self._auto_play_active:
            self._auto_play_active = False
            self.quick_analysis_button.setText("Analyze")
        if self._review:
            if not self._review["paused"]:
                self._pause_review()
            return
        self._analysis_enabled = False
        self._stop_engine()

    def _start_analysis(self):
        self._workspace(True)
        self._analysis_enabled = True
        self.tabs.setCurrentIndex(1)
        self._schedule_engine()

    def _engine_lab(self):
        self._diagnostics()

    def _load_game_config(self):
        for key in (
            "mode",
            "human_color",
            "difficulty",
            "seconds",
            "increment",
            "takebacks",
            "white_engine",
            "black_engine",
            "white_name",
            "black_name",
        ):
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
        return mode == "ai_ai" or (
            mode == "human_ai" and self.game.board.turn != self.config.get("human_color", 1)
        )

    def _position_identity(self):
        return self.game.id, self.game.cursor, self.game.board.key, self.game.current_node

    def _active_engine_name(self):
        """Prefer the complete name advertised by this profile's UCI engine."""
        profile = self._profile()
        if profile and getattr(self, "engine", None):
            connection = self.engine.connection
            try:
                same_engine = bool(connection.path) and Path(connection.path).resolve() == Path(profile["path"]).resolve()
            except (OSError, KeyError, TypeError):
                same_engine = False
            if same_engine and connection.name:
                return connection.name
        if profile:
            return profile.get("name") or Path(profile["path"]).stem
        return "UCI engine"

    def _stop_engine(self):
        self._auto_play_active = False
        if self._review and not self._review.get("paused") and self._job is None:
            self.board_view.set_recommendations([])
            return
        old_job = self._job
        if hasattr(self, "engine"):
            self.engine.stop()
            self.board_view.set_recommendations([])
        self._job = None
        if hasattr(self, "quick_analysis_button"):
            self.quick_analysis_button.setText("Analyze")
        if old_job and old_job.get("identity") == self._position_identity() and self._last_info:
            self._store_analysis(self.game, self.game.current_node, self._last_info, old_job["turn"], old_job)
        if old_job and old_job["kind"] != "benchmark":
            self.engine_state.setText("Search canceled")
            self.statusBar().showMessage("Search canceled", 3000)

    def _schedule_engine(self):
        if (
            self._closing
            or not hasattr(self, "engine")
            or self.engine.busy
            or self.paused
            or self.game.outcome
        ):
            return
        if self._review:
            return
        if self._auto_play_active:
            kind = "play"
        elif self.analysis_mode:
            if not self._analysis_enabled:
                return
            kind = "analysis"
        elif self._is_engine_turn():
            kind = "play"
            self.game.start_clock()
        else:
            return
        profile = self._profile()
        if not profile:
            self.engine_state.setText("No engine selected · Engine → Choose engine…")
            self.statusBar().showMessage(
                "Board and studies are available. Select your UCI engine for analysis."
            )
            return
        infinite = kind == "analysis" and self.config.get("analysis_kind") != "bounded"
        limits = SearchLimits(
            depth=128 if self._auto_play_active else self.config.get("analysis_depth", 128),
            seconds=600 if self._auto_play_active else self.config.get("analysis_seconds", 600),
            nodes=(self.config.get("auto_play_nodes", 10_000_000) if self._auto_play_active
                   else None if infinite else (self.config.get("analysis_nodes") or None)),
        )
        count = self._effective_multipv() if kind == "analysis" else 1
        focus = tuple(self.config.get("searchmoves", []))
        if focus:
            count = 1
            self.analysis_scope = "Targeted analysis · " + " ".join(focus)
        else:
            self.analysis_scope = f"{count} PV" if count > 1 else ""
        options = dict(profile.get("values", {}))
        options.setdefault("UCI_ShowWDL", True)
        context = (
            self._position_identity(),
            profile["id"],
            self.config.get("analysis_kind"),
            count,
            focus,
            tuple(sorted((k, str(v)) for k, v in options.items())),
            limits.depth,
            limits.seconds,
            limits.nodes,
        )
        if context != self._analysis_context:
            self._clear_analysis_output()
            self._analysis_context = context
        self.candidates.set_multipv(count)
        self.candidates.reserve_slots(count)
        try:
            generation = self.engine.start(
                self.game,
                limits,
                profile["path"],
                options=options,
                kind=kind,
                infinite=infinite,
                arguments=profile.get("arguments", []),
                multipv=count,
                searchmoves=self.config.get("searchmoves", []),
                tablebase_path=self.config.get("syzygy_path", ""),
                nodes_only=self._auto_play_active,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            self._error("Cannot start engine", str(exc))
            return
        self._job = {
            "generation": generation,
            "kind": kind,
            "identity": self._position_identity(),
            "turn": self.game.board.turn,
            "external": True,
            "profile": profile["id"],
            "options": dict(profile.get("values", {})),
            "multipv": count,
        }
        self.engine_state.setText(self._active_engine_name() + " · connecting / analyzing")
        self.quick_analysis_button.setText("Pause auto-play" if self._auto_play_active else "Stop" if kind == "analysis" else "Analyze")
        self.board_view.interactive = kind == "analysis"

    def _clear_analysis_output(self):
        self.board_view.best_move = None
        self.board_view.set_recommendations([])
        self.candidates.clear()
        self.pv_label.set_moves([])
        self._candidate_identity = None
        self._pv_root = None
        self._pv_moves = []
        self._last_info = None
        self._last_info_turn = 1
        self._pv_identity = None
        self.eval_label.setText("—")
        self.telemetry.setText("Waiting for engine output")

    def _engine_message(self, generation: int, kind: str, payload: dict):
        if self._closing:
            return
        if self._review and self._review_message(generation, kind, payload):
            return
        job = self._job
        if not job or generation != job["generation"] or generation != self.engine.generation:
            return
        if job["identity"] != self._position_identity():
            self._stop_engine()
            return
        if kind == "tablebase":
            self.tablebase_label.setText(payload["message"])
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
        if kind == "info" and info.get("multipv", 1) != 1:
            return
        if kind != "result":
            return
        self._job = None
        self.quick_analysis_button.setText("Analyze")
        self.engine_state.setText(self._active_engine_name() + " · search complete")
        self.statusBar().showMessage("Search complete · evaluation from White’s perspective")
        if info:
            self._store_analysis(self.game, self.game.current_node, info, job["turn"], job)
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
            if self.game.outcome:
                self._auto_play_active = False
                self.quick_analysis_button.setText("Analyze")
            else:
                delay = self.config.get("watch_delay_ms", 500) if self._auto_play_active or self.config.get("mode") == "ai_ai" else 80
                QTimer.singleShot(delay, self._schedule_engine)
        self._save()

    def _show_info(self, info, job):
        if not info:
            return
        if "score_type" in info and info.get("multipv", 1) > job.get("multipv", self._effective_multipv()):
            return
        self.candidates.set_multipv(job.get("multipv", self._effective_multipv()))
        if info.get("multipv", 1) in self.candidates.pinned:
            return
        if "score_type" in info:
            self._candidate_identity = self._position_identity()
            self._sync_candidate_database()
            self.candidates.update_line(
                info, job["turn"], self._appearance_config().get("light", False), self.config.get("details", False)
            )
            if info.get("multipv", 1) != 1:
                return
        self._last_info = info.copy()
        self._last_info_turn = job["turn"]
        if "score_type" in info:
            self._store_analysis(self.game, self.game.current_node, info, job["turn"], job)
            self.graph.set_samples(self.game.evaluations, self.game.cursor, len(self.game.moves))
        white_score = info["score"] * job["turn"]
        self.eval_label.setText(
            score_label(info, job["turn"]) if "score_type" in info else score_text(white_score)
        )
        self.eval_bar.set_score(white_score)
        evaluation = (score_label(info, job["turn"]) if "score_type" in info
                      else score_text(white_score))
        self._render_telemetry(info, job["turn"], evaluation)
        position = self.game.board.copy()
        self._pv_root = self.game.board.copy(history=False)
        self._pv_identity = self._position_identity()
        self._pv_moves = []
        first = None
        for text in info.get("pv", [])[:128]:
            try:
                move = position.parse_uci(text)
                if first is None:
                    first = move
                self._pv_moves.append(move)
                position.push(move)
            except ValueError:
                break
        self.board_view.best_move = first
        self.board_view.update()

    def _render_telemetry(self, info, turn=1, evaluation=None):
        colors = palette(self._appearance_config().get("light", False))
        depth = str(info["depth"])
        if self.config.get("show_seldepth", False):
            depth += f"/{info['seldepth']}"
        if evaluation is None:
            evaluation = (score_label(info, turn) if "score_type" in info
                          else score_text(info.get("score", 0) * turn))

        def metric(label_text, value):
            return (
                f'<span style="color:{colors["metadata"]};">{label_text} </span>'
                f'<span style="color:{colors["metric"]};font-size:15px;'
                f'font-weight:600;">{value}</span>'
            )

        separator = f'<span style="color:{colors["metadata"]};"> · </span>'
        values = [
            f'<span style="color:{colors["metric"]};font-size:15px;'
            f'font-weight:600;">{escape(str(evaluation))}</span>',
            metric("Depth", depth),
            metric("Nodes", f"{info['nodes']:,}"),
            metric("Nodes/second", f"{info.get('nps', 0):,}"),
        ]
        if not self.config.get("details", False):
            values.append(
                f'<span style="color:{colors["metadata"]};">TB hits '
                f'{info.get("tbhits", 0)}</span>'
            )
        if self.analysis_scope:
            values.append(f'<span style="color:{colors["metadata"]};">{self.analysis_scope}</span>')
        text = separator.join(values)
        if self.config.get("details", False):
            extra = (
                f'{info.get("seconds", 0):.2f} seconds  ·  '
                f'hash full {info.get("hashfull", 0) / 10:.1f}%  ·  '
                f'TB hits {info.get("tbhits", 0)}'
            )
            text += f'<br><span style="color:{colors["metadata"]};">{extra}</span>'
        self.telemetry.setText(f"<div>{text}</div>")

    def _error(self, title, text):
        QMessageBox.warning(self, title, text)

    def closeEvent(self, event):
        self._closing = True
        self._clear_move_preview()
        self._explorer_active = False
        self.timer.stop()
        self.autosave_timer.stop()
        self.archive_timer.stop()
        self.explorer.close_client()
        self.engine.close()
        self.game.pause_clock()
        self._save()
        if self.store:
            self.store.close()
        event.accept()
