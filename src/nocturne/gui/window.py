"""The desktop shell. The game model remains the sole rules authority."""

from __future__ import annotations

from html import escape
from pathlib import Path
import random
import os
import sys
import time

from PySide6.QtCore import QByteArray, QEvent, QProcess, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractButton,
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
    QSizePolicy,
    QSpinBox,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
    QToolTip,
)

from .. import __version__
from ..maia import RATINGS as MAIA_RATINGS
from ..maia.controller import MaiaController
from .maia import MaiaControls
from .maia_insights import MaiaInsights
from ..maia.risk import assess_moves
from ..core.board import Move, SQUARES
from ..core.rules import Board
from ..core.game import Game, TimeControl
from ..core.variation import mainline
from ..core.notation import pgn_clock
from ..core.notation import parse_san
from ..engine.uci_types import AnalysisLimits as SearchLimits, score_label, plot_score_label as score_text
from ..settings import DEFAULTS, normalize
from ..analysis_jobs import checkpoint as checkpoint_job, restore as restore_job
from ..snapshots import position_key
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
from .opening_coverage import OpeningCoverage
from .snapshot_dialog import SnapshotDialog
from ..explorer import RATINGS, SPEEDS
from .moves import MoveText
from .game_line import GameLine
from .saved_game_preview import SavedGameMoves
from .study_tabs import StudyTabBar
from .hover_preview import HoverPreview, MiniBoard
from .wheel import WheelSteps
from .workspace import DockWorkspace
from .theme import ASSETS, palette, stylesheet
from .widgets import AnalysisHeader, EvaluationBar, EvaluationGraph


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
        self._last_save_at = None
        self._gpu_hardware_detected = False
        self._gpu_hash_default_profiles = set()
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
        # Access tokens are session-only. Start with the public database even
        # when a previous session saved a Lichess source.
        self.config["explorer_source"] = "chessdb"
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
        resumed = None
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
        saved_tab_order = self.store.get("study_tab_order", []) if self.store else []
        self._study_tab_order = list(dict.fromkeys(
            item for item in saved_tab_order if isinstance(saved_tab_order, list) and isinstance(item, str)
        )) if isinstance(saved_tab_order, list) else []
        if self.store:
            open_ids = self.store.get("open_studies", [])
            for key in (open_ids if isinstance(open_ids, list) else [])[:20]:
                if key not in self._study_games:
                    try:
                        self._study_games[key] = self.store.load(key)
                    except StorageError:
                        pass
        self._order_studies_by_saved_tabs()
        self.analysis_mode = self.config.get("mode") == "analysis"
        if self.analysis_mode:
            self.paused = False
        self._analysis_enabled = self.analysis_mode and resumed is None
        self._review = restore_job(self.game)
        self._auto_play_active = False
        self._auto_play_paused = False
        self._maia_suspended_for_auto_play = False
        self._job = None
        self._lab = None
        self._benchmark_report = None
        self._last_info = None
        self._last_info_turn = 1
        self._history_signature = None
        self._analysis_layout_active = None
        self._dock_workspace = None
        self._pv_root = None
        self._pv_moves = []
        self._pv_identity = None
        self._preview_source = None
        self._secondary_identity = None
        self._secondary_timer = QTimer(self)
        self._secondary_timer.setSingleShot(True)
        self._secondary_timer.setInterval(250)
        self._secondary_timer.timeout.connect(self._flush_secondary_analysis)
        self._build()
        self.hover_preview = HoverPreview(self)
        self.candidates.pointer_moved.connect(self._move_cursor_preview)
        self.analysis_history.pointer_moved.connect(self._move_cursor_preview)
        self.engine = EngineController(self)
        self.engine.message.connect(self._engine_message)
        self.engine.discovered.connect(self._engine_discovered)
        self.engine.status.connect(self.engine_state.setText)
        self.engine.connection.configured.connect(self.resource_controls.refresh)
        self.maia = MaiaController(self.data_directory, self)
        self.maia.device_mode = self.config.get("maia_device", "auto")
        self.maia.changed.connect(self._maia_changed)
        self.maia.status.connect(self.maia_controls.status.setText)
        self._shortcuts()
        QApplication.instance().installEventFilter(self)
        self._apply_settings()
        self.pause_button.setText("Continue" if self.paused else "Pause")
        self._refresh()
        if self._review:
            self.quick_analysis_button.setText("Resume auto-evaluation")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(100)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(lambda: self._save(force=True))
        self.autosave_timer.start(60000)
        self.archive_timer = QTimer(self)
        self.archive_timer.setInterval(40)
        self.archive_timer.timeout.connect(self._archive_previous_pgn)
        self._start_pgn_archive_migration()
        self._restore_workspace_layout()
        if self._storage_message:
            QTimer.singleShot(0, self, lambda: self._error("Library unavailable", self._storage_message))
        QTimer.singleShot(100, self, self._schedule_engine)
        QTimer.singleShot(0, self, self._probe_gpu_hardware)

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
        self.study_tabs = StudyTabBar()
        self.study_tabs.setTabsClosable(True)
        self.study_tabs.setExpanding(False)
        self.study_tabs.setMovable(True)
        for study in self._study_games.values():
            index = self.study_tabs.addTab(study.headers.get("Event") or "Study")
            self.study_tabs.setTabData(index, study.id)
        self.study_tabs.setCurrentIndex(
            next(i for i in range(self.study_tabs.count()) if self.study_tabs.tabData(i) == self.game.id)
        )
        self.study_tabs.currentChanged.connect(self._switch_study)
        self.study_tabs.tabCloseRequested.connect(self._close_study)
        self.study_tabs.tabMoved.connect(self._save_study_tab_order)
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
        self.board_view.manual_input.connect(self._interrupt_automation)
        board_row = QHBoxLayout()
        board_row.setContentsMargins(0, 0, 0, 0)
        board_row.setSpacing(0)
        self.eval_bar = EvaluationBar()
        self.eval_bar.board_view = self.board_view
        board_row.addWidget(self.board_view, 1)
        board_row.addWidget(self.eval_bar)
        board_layout.addLayout(board_row, 1)
        self.bottom_card, self.bottom_name, self.bottom_detail, self.bottom_clock = self._player_card()
        board_layout.addWidget(self.bottom_card)
        board_tools = QHBoxLayout()
        self.board_hint = label("Drag a piece or select a square", "muted", True)
        board_tools.addWidget(self.board_hint)
        board_tools.addStretch()
        board_tools.addWidget(button("⇅  Flip", self._flip, "quiet"))
        board_tools.addWidget(button("Copy FEN", self._copy_fen, "quiet"))
        guide = button("?", self._show_board_guide, "quiet")
        guide.setAccessibleName("Board symbols guide")
        guide.setToolTip("Click to learn what the Stockfish arrows, numbered Maia rods and percentages mean.")
        guide.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)
        guide.setToolTipDuration(15000)
        self.board_guide_button = guide
        guide.installEventFilter(self)
        board_tools.addWidget(guide)
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
        self.engine_page_layout = engine_page_layout
        engine_page_layout.setContentsMargins(0, 0, 0, 0)
        engine_page_layout.setSpacing(4)
        self.engine_state = label("Select your UCI engine", "subtitle", True)
        self.eval_label = label("—")
        self.eval_label.setObjectName("engineEval")
        self.telemetry = label("Offline analysis · engine supplied by you", "muted", True)
        self.telemetry.setObjectName("telemetryStrip")
        headline = AnalysisHeader(self.telemetry, button("Game Review", self._show_review, "quiet"), self.eval_label)
        engine_page_layout.addWidget(headline)
        engine_page_layout.addWidget(self.engine_state)
        self.tablebase_label = label("Syzygy: not configured", "muted", True)
        engine_page_layout.addWidget(self.tablebase_label)
        self.analysis_scope = ""
        self.engine_scroll = QScrollArea()
        self.engine_scroll.setWidgetResizable(True)
        self.engine_scroll.setMinimumHeight(0)
        self.engine_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.engine_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        engine_detail = QWidget()
        engine_detail.setMinimumWidth(0)
        engine_detail.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.engine_layout = QVBoxLayout(engine_detail)
        self.engine_layout.setContentsMargins(0, 0, 0, 0)
        self.engine_layout.setSpacing(0)
        column_titles = QHBoxLayout()
        column_titles.addWidget(label("STOCKFISH", "eyebrow"), 1)
        self.maia_column_title = label("MAIA · 1800", "maiaHeading")
        self.maia_column_title.setAlignment(Qt.AlignmentFlag.AlignRight)
        column_titles.addWidget(self.maia_column_title)
        self.engine_layout.addLayout(column_titles)
        self.pv_label = MoveText(auto_fit=True)
        self.pv_label.setAccessibleName("Principal variation moves")
        self.pv_label.preview_ended.connect(lambda: self._end_preview("pv"))
        self.candidates = CandidatePanel(self.pv_label)
        self.candidates.preview.connect(self._preview_candidate)
        self.candidates.manual_navigation.connect(self._interrupt_automation)
        self.candidates.preview_end.connect(lambda: self._end_preview("candidate"))
        self.candidates.navigate.connect(self._insert_candidate)
        self.candidates.action.connect(self._candidate_action)
        self.candidates.changed.connect(self._sync_candidate_markers)
        self.candidates.layout_changed.connect(self._protect_analysis_chart)
        self.candidates.changed.connect(self._queue_secondary_analysis)
        self.candidate_splitter = QSplitter(Qt.Orientation.Vertical)
        self.candidate_splitter.setChildrenCollapsible(False)
        self.candidate_splitter.setHandleWidth(7)
        self.candidate_splitter.setStyleSheet(
            "QSplitter::handle:vertical {background:rgba(130,150,160,65); height:7px;}"
            "QSplitter::handle:vertical:hover {background:rgba(130,150,160,150);}")
        self.candidate_splitter.addWidget(self.candidates)
        self.engine_layout.addWidget(self.candidate_splitter, 1)
        self.inline_history = GameLine()
        self.inline_history.setMinimumHeight(160)
        self.inline_history.setMaximumHeight(16777215)
        self.inline_history.setAccessibleName("Move tree below engine analysis")
        self.inline_history.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.inline_history.customContextMenuRequested.connect(self._inline_history_menu)
        self.inline_history.move_clicked.connect(self._navigate_node)
        self.inline_history.move_hovered.connect(self._preview_history)
        self.inline_history.preview_ended.connect(lambda: self._end_preview("history"))
        self.game_line_panel = QWidget()
        game_line_layout = QVBoxLayout(self.game_line_panel)
        game_line_layout.setContentsMargins(0, 0, 0, 0)
        game_line_layout.addWidget(label("GAME LINE", "gameLineHeading"))
        game_line_layout.addWidget(self.inline_history, 1)
        self.candidate_splitter.addWidget(self.game_line_panel)
        self.candidate_splitter.handle(1).setToolTip("Drag to resize Stockfish and the section below")
        self.candidate_splitter.setStretchFactor(1, 1)
        self._rating_game_line_swapped = False
        self.engine_scroll.setWidget(engine_detail)
        self.analysis_detail_splitter = QSplitter(Qt.Orientation.Vertical)
        self.analysis_detail_splitter.setChildrenCollapsible(False)
        self.analysis_detail_splitter.addWidget(self.engine_scroll)
        self.explorer = OpeningExplorer(self.data_directory / "opening-cache.sqlite3")
        self.explorer.statistics_changed.connect(self._sync_candidate_database)
        self.explorer.compact_changed.connect(self._resize_empty_explorer)
        self.explorer.client.status.connect(self._lichess_connection_status)
        self.explorer.move_selected.connect(self._explorer_move)
        self.explorer.move_hovered.connect(self._preview_explorer)
        self.explorer.preview_ended.connect(lambda: self._end_preview("explorer"))
        self.explorer.close_requested.connect(lambda: self._set_explorer_option("explorer_enabled", False))
        self.analysis_detail_splitter.addWidget(self.explorer)
        self.explorer.hide()
        self._explorer_active = False
        self.opening_coverage = OpeningCoverage(self.data_directory / "opening-cache.sqlite3", self)
        self.opening_coverage.changed.connect(self._update_opening_coverage)
        self.opening_coverage.client.status.connect(self._lichess_connection_status)
        self.maia_controls = MaiaControls()
        self.maia_controls.move_limit_changed.connect(self._set_maia_move_limit)
        self.maia_controls.range_changed.connect(self._set_maia_range)
        self.engine_state.hide()
        self.tablebase_label.hide()
        self.maia_controls.details.toggled.connect(self.engine_state.setVisible)
        self.maia_controls.details.toggled.connect(self.tablebase_label.setVisible)
        self.maia_controls.rating_changed.connect(self._set_maia_rating)
        self.maia_controls.enabled_changed.connect(self._set_maia_enabled)
        self.maia_controls.settings_requested.connect(self._manage_engines)
        self.maia_controls.move_selected.connect(self._maia_move)
        self.maia_controls.preview_requested.connect(self._preview_maia_line)
        self.maia_controls.preview_ended.connect(lambda: self._end_preview("maia-all"))
        self.maia_controls.pointer_moved.connect(self._move_cursor_preview)
        engine_page_layout.insertWidget(0, self.maia_controls)
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
        self.pgn_page = pgn_page
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
        for control in (self.apply_pgn_button, self.load_pgn_button):
            control.setMinimumHeight(30)
        self.load_pgn_button.setAccessibleName("Load current game into PGN editor")
        self.apply_pgn_button.setToolTip(
            "Import the text in this editor as a new study and show its moves on the board and in Game Moves."
        )
        self.load_pgn_button.setToolTip(
            "Copy the currently open game into this editor for viewing or editing. "
            "This replaces the editor text; it does not change the game."
        )
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
        self.maia_insights = MaiaInsights()
        splitter.addWidget(self.maia_insights)
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
        self.bottom_moves_title = label("GAME MOVES", "eyebrow")
        self.bottom_moves_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.bottom_moves_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        history_tools.addWidget(self.bottom_moves_title)
        self.opening_coverage_label = label("", "muted")
        self.opening_coverage_label.setTextFormat(Qt.TextFormat.RichText)
        self.opening_coverage_label.linkActivated.connect(lambda node: self._navigate_node(int(node)))
        self.opening_coverage_label.setWordWrap(True)
        history_tools.addWidget(self.opening_coverage_label, 1)
        self.bottom_navigation_controls = []
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
            self.bottom_navigation_controls.append(control)
        self.bottom_moves_toggle = button("▾", self._toggle_bottom_moves, "quiet")
        self.bottom_moves_toggle.setFixedSize(26, 22)
        history_tools.addWidget(self.bottom_moves_toggle)
        history_layout.addLayout(history_tools)
        self.analysis_history = MoveText()
        self.analysis_history.continuous_preview = True
        self.analysis_history.setAccessibleName("Analysis game moves")
        self.analysis_history.setMinimumHeight(36)
        self.analysis_history.move_hovered.connect(self._preview_history)
        self.analysis_history.move_clicked.connect(self._navigate_node)
        self.analysis_history.wheel_navigated.connect(self._wheel_game)
        self.analysis_history.preview_ended.connect(lambda: self._end_preview("history"))
        self.analysis_history.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.analysis_history.customContextMenuRequested.connect(self._history_context_menu)
        history_layout.addWidget(self.analysis_history, 1)
        self.workspace_splitter.addWidget(self.analysis_moves_panel)
        self.workspace_splitter.setCollapsible(1, True)
        self.workspace_splitter.splitterMoved.connect(self._bottom_splitter_moved)
        self.bottom_moves_handle = self.workspace_splitter.handle(1)
        self.bottom_moves_handle.setToolTip("Drag down to collapse Game Moves; drag up to reopen")
        self.workspace_splitter.setStretchFactor(0, 1)
        self.workspace_splitter.setStretchFactor(1, 0)
        self.analysis_moves_panel.hide()
        content.addWidget(self.workspace_splitter, 1)
        layout.addLayout(content, 1)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().messageChanged.connect(self._sync_status_space)
        self.statusBar().showMessage("Ready · Nocturne Chess · Offline by design")

    def _sync_status_space(self, message=None):
        message = self.statusBar().currentMessage() if message is None else message
        analysis = self.analysis_mode
        self.statusBar().setStyleSheet("QStatusBar {font-size:11px; padding:0; margin:0;} QStatusBar::item {border:0;}" if analysis else "")
        self.statusBar().setMaximumHeight(16 if analysis else 16777215)
        self.statusBar().setVisible(not analysis or bool(message and not message.startswith("Ready")))

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
        add(tree, "Bookmark this position…", self._edit_bookmark, "Ctrl+B")
        self.bookmarks_menu = tree.addMenu("Position bookmarks")
        self.bookmarks_menu.aboutToShow.connect(self._populate_bookmarks)

        analysis = self.menuBar().addMenu("&Analysis")
        add(analysis, "Game Review…", self._show_review)
        analysis.addSeparator()
        add(analysis, "Go", self._start_analysis, "Ctrl+G")
        add(analysis, "Halt", self._halt_analysis, "Ctrl+H")
        add(analysis, "Analyze entire line…", self._analyze_game)
        add(analysis, "Pause / resume game analysis", self._pause_review)
        add(analysis, "Cancel game analysis", self._cancel_review)
        self.confirm_review_action = add(analysis, "Confirm mistakes with deeper analysis", self._set_review_confirmation)
        self.confirm_review_action.setCheckable(True)
        add(analysis, "Analyze all legal moves again", self._clear_focus)
        add(analysis, "Engine diagnostics…", self._diagnostics)

        display = self.menuBar().addMenu("&Display")
        add(display, "Flip board", self._flip, "F")
        add(display, "Clear arrows and marks", self._escape, "Escape").setToolTip(
            "Clear board annotations and stop active automation")
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
        font_menu = display.addMenu("Stockfish variation text size")
        font_action = QWidgetAction(font_menu)
        font_widget = QWidget()
        font_layout = QVBoxLayout(font_widget)
        self.pv_font_label = QLabel()
        self.pv_font_slider = QSlider(Qt.Orientation.Horizontal)
        self.pv_font_slider.setRange(0, 100)
        self.pv_font_slider.setSingleStep(1)
        self.pv_font_slider.setMinimumWidth(240)
        self.pv_font_slider.setAccessibleName("Stockfish variation font increase percent")
        self.pv_font_slider.setToolTip("Increase Stockfish variation text by 0–100%. Default: +20%.")
        font_layout.addWidget(self.pv_font_label)
        font_layout.addWidget(self.pv_font_slider)
        font_action.setDefaultWidget(font_widget)
        font_menu.addAction(font_action)
        self.pv_font_slider.valueChanged.connect(self._set_pv_font_increase)
        add(display, "Board appearance…", self._settings)
        display.addSeparator()
        self.arrange_panels_action = add(display, "Arrange panels", self._arrange_panels)
        self.arrange_panels_action.setCheckable(True)
        add(display, "Reset layout", self._reset_workspace_layout)
        add(display, "Classic Nibbler layout", lambda: self._set_layout("classic"))
        add(display, "Analysis on the left", lambda: self._set_layout("analysis-left"))
        display.addSeparator()
        add(display, "Save board image…", self._save_board_image)
        add(display, "Command palette…", self._command_palette, "Ctrl+K")
        add(display, "Keyboard shortcuts…", self._shortcut_editor)
        for key, text in [
            ("smart_move", "Smart Move · click recommended destinations"),
            ("branch_arrows", "Show saved continuation arrows"),
            ("show_maia_insights", "Show Maia insights"),
            ("show_game_line_notes", "Show Game Line notes"),
            ("reserve_five_candidate_rows", "Always show five Stockfish rows"),
            ("details", "Detailed analysis statistics"),
            ("show_seldepth", "Show selective depth (seldepth)"),
            ("wheel_game_moves", "Wheel navigates game moves"),
            ("wheel_analysis_moves", "Wheel previews analysis moves"),
        ]:
            action = add(display, text, lambda checked, k=key: self._set_display(k, checked))
            action.setCheckable(True)
            self.display_actions[key] = action
        self.marker_actions = {}
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
        self.cpu_budget_menu = engine.addMenu("Stockfish CPU budget")
        self.cpu_budget_menu.setToolTipsVisible(True)
        self.cpu_budget_menu.aboutToShow.connect(self._refresh_cpu_budget_menu)
        self._refresh_cpu_budget_menu()
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
        add(engine, "Auto-play engines from this position", self._start_auto_play, "F11").setAutoRepeat(False)
        add(engine, "Auto-evaluate entire line", self._auto_evaluate_line, "F12").setAutoRepeat(False)
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
        maia_menu = engine.addMenu("Maia-3 79M")
        self.maia_enabled_action = add(maia_menu, "Enable local Maia predictions", self._set_maia_enabled)
        self.maia_enabled_action.setCheckable(True)
        self.maia_arrows_action = add(maia_menu, "Show Maia rods (moves above 10%)", self._set_maia_arrows)
        self.maia_arrows_action.setCheckable(True)
        device_menu = maia_menu.addMenu("Inference device")
        self.maia_device_actions = {}
        for key, title in (("auto", "Auto · GPU when available"), ("cpu", "CPU only")):
            action = add(device_menu, title, lambda checked=False, value=key: self._set_maia_device(value))
            action.setCheckable(True)
            action.setChecked(self.config.get("maia_device", "auto") == key)
            self.maia_device_actions[key] = action
        add(device_menu, "Set up optional GPU runtime…", self._install_maia_gpu)
        rating_menu = maia_menu.addMenu("Lichess blitz rating (equal-rated opponent)")
        self.maia_rating_actions = {}
        for elo in MAIA_RATINGS:
            action = add(rating_menu, str(elo), lambda checked=False, r=elo: self._set_maia_rating(r))
            action.setCheckable(True)
            self.maia_rating_actions[elo] = action
        database = self.menuBar().addMenu("&Database")
        self.explorer_enabled_action = add(database, "Show database explorer", lambda checked: self._set_explorer_option("explorer_enabled", checked))
        self.explorer_enabled_action.setCheckable(True)
        self.explorer_statistics_action = add(database, "Enable database statistics", lambda checked: self._set_explorer_option("explorer_statistics", checked))
        self.explorer_statistics_action.setCheckable(True)
        self.explorer_actions = {}
        for source, title in (("masters", "Lichess Masters database (Recommended)"), ("lichess", "Lichess players (Amateurs)"),
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
        self.lichess_token_action = QWidgetAction(database)
        self.lichess_token_row = QPushButton()
        self.lichess_token_row.setAccessibleName("Lichess access token")
        self.lichess_token_action.setDefaultWidget(self.lichess_token_row)
        self.lichess_token_action.triggered.connect(self._lichess_token_dialog)
        self.lichess_token_row.clicked.connect(lambda: (database.close(), self.lichess_token_action.trigger()))
        database.addAction(self.lichess_token_action)
        self.menu_actions["Lichess access token…"] = self.lichess_token_action
        database.aboutToShow.connect(lambda: self._set_lichess_token_warning(True))
        self._set_lichess_token_warning(True)
        add(database, "Create a Lichess access token…", lambda: QDesktopServices.openUrl(
            QUrl("https://lichess.org/account/oauth/token/create?description=Nocturne%20database%20explorer")))
        self.clear_lichess_token_action = add(database, "Clear session access token", self._clear_lichess_token)
        add(database, "Refresh database results", self.explorer.refresh)
        self.opening_scan_action = add(database, "Find where this line leaves the database", self._scan_opening_coverage)
        self.opening_cancel_action = add(database, "Cancel database coverage scan", lambda: self.opening_coverage.cancel(False))
        play = self.menuBar().addMenu("&Play")
        add(play, "New game…", self._new_game)
        add(play, "Pause / continue", self._pause, "Space")
        add(play, "Offer / claim draw…", self._draw)
        add(play, "Resign…", self._resign)
        dev = self.menuBar().addMenu("&Dev")
        self.snapshot_capture_action = add(dev, "Save analysis snapshots at node milestones", self._set_snapshot_capture)
        self.snapshot_capture_action.setCheckable(True)
        add(dev, "Compare saved analysis snapshots…", self._compare_snapshots)
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
        self.config["cursor_preview_version"] = 1
        self.cursor_preview_action.setChecked(bool(enabled))
        self._save()

    def _set_expand_pv(self, enabled):
        self.config["expand_pv"] = bool(enabled)
        self.config["expand_pv_version"] = 2
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
        if key == "show_maia_insights":
            self._request_maia()
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
            self.opening_coverage.client.set_lichess_token(token)
            self._set_lichess_token_warning(False)
            if not self.explorer.client.has_lichess_token:
                self.config["explorer_source"] = "chessdb"
            elif self.config.get("explorer_source") == "chessdb":
                self.config["explorer_source"] = "masters"
            # Retry coverage that may have stopped before authentication.
            self.opening_coverage.cancel()
            self._sync_explorer()
            if self.explorer.query and self.explorer.query.source != "chessdb":
                self.explorer.refresh()
            self._save()

    def _clear_lichess_token(self):
        self.explorer.client.set_lichess_token("")
        self.opening_coverage.cancel()
        self.opening_coverage.client.set_lichess_token("")
        self._set_lichess_token_warning(False)
        if self.explorer.query and self.explorer.query.source != "chessdb":
            self.explorer.client.cancel()
        self.config["explorer_source"] = "chessdb"
        self._sync_explorer()
        self._save()

    def _lichess_connection_status(self, key, message):
        """Refresh the token setup hint when a Lichess request reports status."""
        if not hasattr(self, "lichess_token_action"):
            return
        clients = (self.explorer.client, self.opening_coverage.client)
        query = next((client.query for client in clients
                      if client.query is not None and client.query.key == key), None)
        if query is None or query.source not in ("masters", "lichess"):
            return
        if self.explorer.client.has_lichess_token:
            self._set_lichess_token_warning(False)
        elif "access token required" in message.casefold():
            self._set_lichess_token_warning(True)

    def _set_lichess_token_warning(self, warning):
        self._lichess_token_warning = not self.explorer.client.has_lichess_token
        action = self.lichess_token_action
        action.setText("⚠ Lichess access token required…" if self._lichess_token_warning
                       else "Lichess access token…")
        font = action.font()
        font.setBold(self._lichess_token_warning)
        action.setFont(font)
        action.setToolTip("No Lichess access token is set. Click here to add a token for Lichess databases."
                          if self._lichess_token_warning else "")
        self.lichess_token_row.setText(action.text())
        self.lichess_token_row.setToolTip(action.toolTip())
        self.lichess_token_row.setStyleSheet(
            "QPushButton { text-align:left; padding:8px 20px; background:#694b20; color:#ffe2a6; border:0; font-weight:bold; }"
            "QPushButton:hover, QPushButton:focus { background:#89652d; }"
            if self._lichess_token_warning else "QPushButton { text-align:left; padding:8px 20px; border:0; }")

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
        engine_visible = self._dock_workspace is not None or self.tabs.currentIndex() == 1
        active = enabled and self.analysis_mode and engine_visible
        lookup = bool(self.config.get("explorer_statistics")) and self.analysis_mode and engine_visible
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
        if active and not self._explorer_active and self._dock_workspace is None:
            self.right_detail_splitter.setSizes([500, 220, 70])
        self._explorer_active = active
        self._sync_docked_visibility()
        self._sync_candidate_database()
        self._update_opening_coverage()

        # Follow the PGN in the selected source; each source retains its results.
        # A stable context also prevents navigation from restarting the scan.
        coverage = self.opening_coverage
        if self._book_highlight_enabled():
            signature = coverage.signature(self.game, self.config.get("explorer_source", "chessdb"),
                                           self.config.get("explorer_speed", "all"),
                                           self.config.get("explorer_rating", 0))
            if coverage.context != signature:
                self._scan_opening_coverage(force=False)
        elif coverage.running:
            coverage.cancel()

    def _book_highlight_enabled(self):
        return (bool(self.config.get("explorer_statistics"))
                and (self.config.get("explorer_source", "chessdb") == "chessdb"
                     or self.explorer.client.has_lichess_token))

    def _scan_opening_coverage(self, checked=False, *, force=True):
        self.opening_coverage.start(
            self.game, self.config.get("explorer_source", "masters"),
            self.config.get("explorer_speed", "all"), self.config.get("explorer_rating", 0),
            self.explorer.client._lichess_token,
            force=force,
        )

    def _update_opening_coverage(self):
        if not hasattr(self, "opening_coverage_label"):
            return
        coverage = self.opening_coverage
        signature = coverage.signature(self.game, self.config.get("explorer_source", "masters"),
                                       self.config.get("explorer_speed", "all"), self.config.get("explorer_rating", 0))
        if coverage.context is not None and coverage.context != signature:
            coverage.cancel()
        text = escape(coverage.message)
        if coverage.departure is not None:
            node_id = coverage.departure
            node = self.game.nodes[node_id]
            if node.parent is None:
                title = "Starting position"
            else:
                before = self.game.position_at_node(node.parent)
                title = f"{before.fullmove}{'.' if before.turn == 1 else '…'} {node.san}"
            text = f'Database departure: <a href="{node_id}">{escape(title)}</a> · {text}'
        self.opening_coverage_label.setText(text)
        self.opening_scan_action.setEnabled(not coverage.running and self._book_highlight_enabled())
        self.opening_cancel_action.setEnabled(coverage.running)
        self._render_move_history()

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

    def keyPressEvent(self, event):
        # Qt can deliver keys before Windows has activated a newly shown
        # native window. Use the same actions as a fallback when its shortcut
        # map did not consume these global analysis/navigation keys.
        titles = {Qt.Key.Key_F11: "Auto-play engines from this position",
                  Qt.Key.Key_F12: "Auto-evaluate entire line",
                  Qt.Key.Key_Backspace: "Delete current line"}
        if event.key() == Qt.Key.Key_Backspace and isinstance(QApplication.focusWidget(), (QPlainTextEdit, QLineEdit)):
            super().keyPressEvent(event)
            return
        title = titles.get(event.key())
        action = self.menu_actions.get(title) if title and hasattr(self, "menu_actions") else None
        if (action is not None and action.isEnabled() and not event.isAutoRepeat()
                and action.shortcut().matches(QKeySequence(event.keyCombination()))
                == QKeySequence.SequenceMatch.ExactMatch):
            action.trigger()
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched, event):
        if self._closing:
            return super().eventFilter(watched, event)
        if (watched is getattr(self, "bottom_moves_handle", None)
                or (hasattr(self, "workspace_splitter") and watched is self.workspace_splitter.handle(1))):
            if (event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton
                    and self.config.get("bottom_moves_collapsed", False)):
                self.analysis_moves_panel.setMaximumHeight(16777215)
            elif event.type() == QEvent.Type.MouseButtonRelease and self.config.get("bottom_moves_collapsed", False):
                self.analysis_moves_panel.setMaximumHeight(34)
        in_bottom = (hasattr(self, "analysis_moves_panel") and isinstance(watched, QWidget) and
                     (watched is self.analysis_moves_panel or self.analysis_moves_panel.isAncestorOf(watched)
                      or watched is self.workspace_splitter.handle(1)))
        if in_bottom and not isinstance(watched, QAbstractButton):
            if (event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton
                    and (self.config.get("bottom_moves_collapsed", False)
                         or (watched is self.analysis_moves_panel and
                             event.position().y() <= self.bottom_moves_title.geometry().bottom()))):
                self._bottom_click_origin = event.globalPosition().toPoint()
            elif event.type() == QEvent.Type.MouseButtonRelease:
                origin = getattr(self, "_bottom_click_origin", None)
                self._bottom_click_origin = None
                if (origin is not None
                        and (event.globalPosition().toPoint() - origin).manhattanLength() < 6):
                    self._toggle_bottom_moves()
        if watched is getattr(self, "board_guide_button", None):
            if event.type() == QEvent.Type.Enter:
                QToolTip.showText(watched.mapToGlobal(watched.rect().bottomLeft()), watched.toolTip(), watched)
            elif event.type() == QEvent.Type.Leave:
                QToolTip.hideText()
        if self._closing:
            return super().eventFilter(watched, event)
        if watched is getattr(self, "board_view", None) and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self, self._fit_analysis_columns)
        if (isinstance(watched, QWidget) and event.type() in (QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride)
                and event.key() == Qt.Key.Key_Escape):
            # Modal settings and popups consume Escape themselves. Stop the
            # job too, then let the focused control close normally.
            owner = watched
            while owner is not None and owner is not self:
                owner = owner.parent()
            if owner is self:
                self._interrupt_automation()
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
            and event.key() not in (Qt.Key.Key_F11, Qt.Key.Key_F12, Qt.Key.Key_Escape)
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
        self._save_study_tab_order()

    def _order_studies_by_saved_tabs(self):
        if not self._study_tab_order:
            return
        ordered = {key: self._study_games[key] for key in self._study_tab_order if key in self._study_games}
        ordered.update((key, game) for key, game in self._study_games.items() if key not in ordered)
        self._study_games = ordered

    def _save_study_tab_order(self, *_):
        if not hasattr(self, "study_tabs"):
            return
        self._study_tab_order = [
            self.study_tabs.tabData(index) for index in range(self.study_tabs.count())
            if isinstance(self.study_tabs.tabData(index), str)
        ]
        if self.store:
            try:
                self.store.set("study_tab_order", self._study_tab_order)
            except StorageError as exc:
                self.statusBar().showMessage(str(exc))

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
        self._analysis_enabled = bool(self.config.get("reanalyze_on_navigation", False))
        self._review = restore_job(self.game)
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
        self._save_study_tab_order()
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
        self._reset_workspace_layout(preset=value)

    def _arrange_panels(self, checked=True):
        if self._dock_workspace is None and checked:
            self._activate_docked_workspace()
        if self._dock_workspace is not None:
            self._dock_workspace.set_editable(checked)
        self.arrange_panels_action.setChecked(checked)
        self._save()

    def _activate_docked_workspace(self):
        self._clear_move_preview()
        self.workspace_splitter.hide()
        self.graph.setMaximumHeight(16777215)
        self.panel.setMaximumWidth(16777215)
        workspace = DockWorkspace({
            "board": ("Board", self.arena),
            "analysis": ("Analysis / PGN", self.panel),
            "moves": ("Game moves", self.analysis_moves_panel),
            "database": ("Database explorer", self.explorer),
            "graph": ("Evaluation graph", self.graph),
            "insights": ("Game Line", self.maia_insights),
        }, self, analysis_left=self.config.get("layout") == "analysis-left")
        self._dock_workspace = workspace
        workspace.finished.connect(lambda: self._arrange_panels(False))
        workspace.reset_requested.connect(self._reset_workspace_layout)
        workspace.panel_closed.connect(self._docked_panel_closed)
        self.content_layout.addWidget(workspace, 1)
        workspace.show()
        self._analysis_layout_active = None
        self._sync_workspace_layout()
        self._sync_explorer()

    def _docked_panel_closed(self, name):
        if self._closing:
            return
        if name == "database":
            self._set_explorer_option("explorer_enabled", False)
        elif name == "graph":
            self._set_display("show_eval_graph", False)

    def _sync_docked_visibility(self):
        if self._dock_workspace is not None:
            self._dock_workspace.set_panel_visible("insights", self.analysis_mode)
            self._dock_workspace.set_panel_visible("moves", self.analysis_mode)
            self._dock_workspace.set_panel_visible("database", self._explorer_active)
            self._dock_workspace.set_panel_visible("graph", self.config.get("show_eval_graph", True))

    def _restore_workspace_layout(self):
        if self.store and self.store.get("analysis_columns_version") != 2:
            self.store.set("analysis_columns_version", 2)
            self.store.set("workspace_layout", None)
            return
        state = self.store.get("workspace_layout") if self.store else None
        if not isinstance(state, dict) or state.get("version") != 1:
            return
        self._activate_docked_workspace()
        if not self._dock_workspace.restore(state):
            self._reset_workspace_layout()
            return
        geometry = state.get("window_geometry")
        if isinstance(geometry, str) and len(geometry) <= 65536:
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii", errors="ignore")))
        self._dock_workspace.keep_floating_panels_on_screen()
        self._dock_workspace.set_editable(False)
        self._sync_docked_visibility()

    def _reset_workspace_layout(self, checked=False, *, preset="classic"):
        self.config["layout"] = preset
        workspace, self._dock_workspace = self._dock_workspace, None
        if workspace is not None:
            workspace.release(self)
            self.content_layout.removeWidget(workspace)
            self.main_splitter.insertWidget(0, self.arena)
            self.main_splitter.insertWidget(1, self.panel)
            self.main_splitter.addWidget(self.maia_insights)
            self.workspace_splitter.addWidget(self.analysis_moves_panel)
            self.workspace_splitter.setCollapsible(1, True)
            self.right_detail_splitter.addWidget(self.explorer)
            self.right_detail_splitter.addWidget(self.graph)
            self.graph.setMaximumHeight(85)
            self.arena.show()
            self.panel.show()
            self.graph.setVisible(self.config.get("show_eval_graph", True))
            workspace.deleteLater()
        self.arrange_panels_action.setChecked(False)
        self.workspace_splitter.show()
        self._analysis_layout_active = None
        self._sync_workspace_layout()
        self._sync_explorer()
        self._save()

    def _preview_candidate(self, rank, ply):
        if self._candidate_identity != self._position_identity() or not self.candidates.display_line(rank):
            return
        board = self.game.board.copy()
        try:
            for text in self.candidates.display_line(rank)["pv"][:ply]:
                board.push(board.parse_uci(text))
        except ValueError:
            return
        self._show_move_preview("candidate", board, caption=f"Candidate preview · ply {ply}")

    def _set_maia_arrows(self, enabled):
        self.config["maia_arrows"] = bool(enabled)
        self._maia_changed(self.maia.policies)
        self._save()

    def _set_maia_device(self, device):
        self.config["maia_device"] = device
        self.maia.stop()
        self.maia.device_mode = device
        if device == "auto":
            # A deliberate Auto selection also retries a previously failed setup.
            try:
                (self.data_directory / "maia-gpu-auto-attempted").unlink(missing_ok=True)
            except OSError:
                pass
        for key, action in self.maia_device_actions.items():
            action.setChecked(key == device)
        self._request_maia()
        self._save()

    def _ensure_maia_gpu(self):
        if (self._closing or "--smoke-test" in sys.argv
                or not getattr(sys, "frozen", False) or sys.platform != "win32"
                or not self.analysis_mode or not self.config.get("maia_enabled", True)
                or self.config.get("maia_device", "auto") != "auto"):
            return
        runtime = self.data_directory / "maia-gpu"
        if (runtime / "ready.json").is_file() and (runtime / "Scripts/python.exe").is_file():
            return
        if getattr(self, "_gpu_setup", None) is not None:
            return
        attempted = self.data_directory / "maia-gpu-auto-attempted"
        if attempted.exists():
            return
        try:
            self.data_directory.mkdir(parents=True, exist_ok=True)
            attempted.write_text("Automatic GPU setup attempted; select Auto again to retry.\n", encoding="utf-8")
        except OSError:
            return
        self._install_maia_gpu()

    def _install_maia_gpu(self):
        if getattr(self, "_gpu_setup", None) is not None:
            self._gpu_setup.show()
            self._gpu_setup.raise_()
            return
        frozen = getattr(sys, "frozen", False)
        base = Path(sys.executable).parent / "Maia" if frozen else Path(__file__).resolve().parents[3]
        source = base / "gpu-source" if frozen else base / "src"
        script = base / "install_maia_gpu.py" if frozen else base / "scripts/install_maia_gpu.py"
        checkpoint = base / "maia3-79m.pt" if frozen else base / "models/maia3-79m.pt"
        dialog = QDialog(self)
        dialog.setWindowTitle("Maia GPU setup")
        dialog.resize(760, 430)
        layout = QVBoxLayout(dialog)
        log = QPlainTextEdit()
        log.setReadOnly(True)
        layout.addWidget(log)
        close = QPushButton("Close")
        close.setEnabled(False)
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        process = QProcess(dialog)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(lambda: log.appendPlainText(bytes(process.readAllStandardOutput()).decode("utf-8", "replace")))
        def finished(code, status):
            close.setEnabled(True)
            if code == 0:
                log.appendPlainText("GPU runtime ready. Auto will reuse this installation on future launches. Cached predictions are reused.")
                try:
                    (self.data_directory / "maia-gpu-auto-attempted").unlink(missing_ok=True)
                except OSError:
                    pass
                if self.config.get("maia_device", "auto") == "auto":
                    self._set_maia_device("auto")
            else:
                log.appendPlainText("GPU setup did not complete. CPU inference remains available.")
        process.finished.connect(finished)
        process.errorOccurred.connect(lambda error: (log.appendPlainText(process.errorString()), close.setEnabled(True)))
        dialog.reject = lambda: QDialog.reject(dialog) if process.state() == QProcess.ProcessState.NotRunning else None
        # Keep setup alive until completion, including when the window close button is used.
        dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self._gpu_setup = dialog
        dialog.finished.connect(lambda result: setattr(self, "_gpu_setup", None))
        dialog.show()
        log.appendPlainText("Auto GPU setup: detects NVIDIA/AMD and downloads the compatible runtime once. "
                            "Python 3.12 x64 is required; CPU inference stays available.")
        process.start("py", ["-3.12", str(script), str(self.data_directory / "maia-gpu"), str(source), str(checkpoint)])

    def _set_maia_enabled(self, enabled):
        self.config["maia_enabled"] = bool(enabled)
        if not enabled:
            self.maia.stop()
            self.maia_controls.status.setText("Maia disabled")
        self._request_maia()
        self._save()

    def _set_maia_range(self, low, high):
        if low >= high:
            self._sync_maia_range_controls()
            return
        self.config.update(maia_rating_min=low, maia_rating_max=high)
        self.config["maia_rating"] = max(low, min(high, self.config.get("maia_rating", 1800)))
        self.maia.set_rating_range(low, high)
        self._sync_maia_range_controls()
        self._request_maia()
        self._save()

    def _sync_maia_range_controls(self):
        low, high = self.config.get("maia_rating_min", 600), self.config.get("maia_rating_max", 3000)
        for control, value in ((self.maia_controls.range_min, low), (self.maia_controls.range_max, high)):
            control.blockSignals(True)
            control.setCurrentIndex(control.findData(value))
            control.blockSignals(False)
        self.maia_insights.chart.ratings = tuple(r for r in MAIA_RATINGS if low <= r <= high)
        for elo, action in self.maia_rating_actions.items():
            action.setEnabled(low <= elo <= high)
        for i in range(self.maia_controls.rating.count()):
            self.maia_controls.rating.model().item(i).setEnabled(low <= self.maia_controls.rating.itemData(i) <= high)

    def _set_maia_move_limit(self, count):
        self.config["maia_move_limit"] = count
        self.maia_controls._policy_signature = None
        self._maia_changed(self.maia.policies)
        self._save()

    def _resize_empty_explorer(self, empty, previous_height):
        if self._dock_workspace is not None or not hasattr(self, "right_detail_splitter"):
            return
        sizes = self.right_detail_splitter.sizes()
        if len(sizes) != 3:
            return
        if empty:
            self._database_expanded_height = max(170, previous_height)
        height = 88 if empty else getattr(self, "_database_expanded_height", 220)
        graph = sizes[2] if self.graph.isVisible() else 0
        self.right_detail_splitter.setSizes([max(160, sum(sizes) - height - graph), height, graph])

    def _bottom_splitter_moved(self, position, index):
        if self._dock_workspace is not None or not self.analysis_mode:
            return
        sizes = self.workspace_splitter.sizes()
        if len(sizes) == 2 and sizes[1] == 0:
            if not self.config.get("bottom_moves_collapsed", False):
                self.config["bottom_moves_collapsed"] = True
                self._sync_bottom_moves()
                self._save()
            self.workspace_splitter.setSizes([max(100, sum(sizes)-32), 32])
        elif len(sizes) == 2 and self.config.get("bottom_moves_collapsed", False) and sizes[1] > 48:
            self._bottom_expanded_height = max(90, sizes[1])
            self.config["bottom_moves_collapsed"] = False
            self._sync_bottom_moves()
            self._save()
        elif len(sizes) == 2 and not self.config.get("bottom_moves_collapsed", False):
            self._bottom_expanded_height = sizes[1]

    def _toggle_bottom_moves(self):
        collapsed = not self.config.get("bottom_moves_collapsed", False)
        self.config["bottom_moves_collapsed"] = collapsed
        self._sync_bottom_moves()
        self._save()

    def _sync_bottom_moves(self):
        collapsed = self.config.get("bottom_moves_collapsed", False)
        if collapsed == getattr(self, "_bottom_collapsed_state", None):
            return
        self._bottom_collapsed_state = collapsed
        if collapsed and self.analysis_moves_panel.isVisible() and not self.analysis_history.isHidden() and self.analysis_moves_panel.height() >= 90:
            self._bottom_expanded_height = self.analysis_moves_panel.height()
        for control in self.bottom_navigation_controls:
            control.setVisible(not collapsed)
        self.analysis_moves_panel.setCursor(Qt.CursorShape.PointingHandCursor if collapsed else Qt.CursorShape.ArrowCursor)
        self.analysis_history.setVisible(not collapsed)
        self.opening_coverage_label.setVisible(not collapsed)
        self.analysis_moves_panel.setMinimumHeight(32 if collapsed else 90)
        self.analysis_moves_panel.setMaximumHeight(34 if collapsed else 16777215)
        self.bottom_moves_toggle.setText("▴" if collapsed else "▾")
        self.bottom_moves_toggle.setVisible(collapsed)
        self.bottom_moves_toggle.setToolTip("Expand Game Moves" if collapsed else "Collapse Game Moves")
        self.bottom_moves_toggle.setAccessibleName(self.bottom_moves_toggle.toolTip())
        if self._dock_workspace is None:
            total = max(sum(self.workspace_splitter.sizes()),
                        self.workspace_splitter.height() - self.workspace_splitter.handleWidth())
            height = 33 if collapsed else getattr(self, "_bottom_expanded_height", 100)
            self.workspace_splitter.setSizes([max(100, total - height), height])

    def _set_maia_rating(self, rating):
        self.config["maia_rating"] = max(self.config.get("maia_rating_min", 600), min(self.config.get("maia_rating_max", 3000), rating))
        self._request_maia()
        self._save()

    def _request_maia(self):
        if not hasattr(self, "maia"):
            return
        self.maia.set_rating_range(self.config.get("maia_rating_min", 600), self.config.get("maia_rating_max", 3000))
        self._sync_maia_range_controls()
        enabled = self.config.get("maia_enabled", True)
        rating = self.config.get("maia_rating", 1800)
        self.maia_controls.enabled.blockSignals(True)
        self.maia_controls.enabled.setChecked(enabled)
        self.maia_controls.enabled.blockSignals(False)
        self.maia_controls.rating.blockSignals(True)
        self.maia_controls.rating.setCurrentIndex(self.maia_controls.rating.findData(rating))
        self.maia_controls.rating.blockSignals(False)
        self.maia_column_title.setText(f"MAIA · {rating}")
        self.maia_column_title.setVisible(enabled)
        self.maia_enabled_action.setChecked(enabled)
        self.maia_arrows_action.setChecked(self.config.get("maia_arrows", True))
        for elo, action in self.maia_rating_actions.items():
            action.setChecked(elo == rating)
        self.maia_controls.setVisible(self.analysis_mode)
        if self._auto_play_active:
            self._suspend_maia_for_auto_play()
            self._maia_changed({})
            return
        if enabled and self.analysis_mode and getattr(self.game.board, "chess960", False):
            self.maia.stop()
            self.maia_controls.status.setText("Maia predicts standard chess only; Stockfish remains available for Chess960.")
            self._maia_changed({})
            return
        if enabled and self.analysis_mode:
            QTimer.singleShot(0, self, self._ensure_maia_gpu)
            path = self.game.node_path(self.game.current_node)[1:]
            self.maia.request(self.game.initial_fen, [self.game.nodes[n].move.uci() for n in path], rating, sweep=self.config.get("show_maia_insights", True))
            self.maia.foreground_busy = lambda: self.engine.busy or self._closing or bool(self._review)
            continuation = []
            moves = [self.game.nodes[n].move.uci() for n in path]
            index = self.game.current_node
            selected_future = iter(self.game._line_nodes[self.game.cursor + 1:])
            while self.game.nodes[index].children:
                index = next(selected_future, self.game.nodes[index].children[0])
                continuation.append(self.game.nodes[index].move.uci())
            histories = (moves + continuation[:i] for i in range(1, len(continuation) + 1))
            self.maia.prefetch(self.game.initial_fen, histories, rating)
        self._maia_changed(self.maia.policies if enabled else {})

    def _maia_changed(self, policies):
        self._sync_insight_layout()
        if self._auto_play_active:
            policies = {}
        rating = self.config.get("maia_rating", 1800)
        policy = (policies.get(str(rating), {}) if self.analysis_mode and self.config.get("maia_enabled", True)
                  else {})
        self.candidates.set_maia(policy, rating, self.config.get("maia_enabled", True) and self.analysis_mode)
        self.maia_controls.set_policy(policy, self.game.board)
        self.maia_insights.outcome_bar.set_outcome(self.maia.outcomes.get(str(rating)) if self.analysis_mode and self.config.get("maia_enabled", True) else None)
        self.maia_insights.set_data(policies, self.game.board, rating, self._appearance_config())
        self._sync_blunder()
        self._protect_analysis_chart()
        if self._dock_workspace is not None:
            self._sync_docked_visibility()
        else:
            self.maia_insights.setVisible(self.analysis_mode)

    def _sync_blunder(self):
        if not hasattr(self, "maia"):
            return
        policy = (self.maia.policies.get(str(self.config.get("maia_rating", 1800)), {})
                  if self.analysis_mode and self.config.get("maia_enabled", True) else {})
        lines = self.candidates.lines if self._candidate_identity == self._position_identity() else {}
        assessments = self.maia_insights.set_analysis(policy, self.game.board, lines)
        self.maia_controls.set_stockfish(lines, self.game.board.turn)
        recommendations = []
        for uci, result in assessments.items():
            if result["probability"] <= 0.10:
                continue
            move = self.board_view.legal_by_uci.get(uci)
            if move is not None:
                recommendations.append((move, result["probability"], result["category"]))
        self.board_view.set_maia_recommendations(recommendations, enabled=self.config.get("maia_arrows", True))

    def _preview_maia_line(self, pv, ply, name):
        position = self.game.board.copy()
        last = None
        try:
            for move in pv[:ply]:
                last = position.parse_uci(move)
                position.push(last)
        except ValueError:
            self._end_preview("maia-all")
            return
        # The all-human-moves table always uses the small cursor board.
        self._preview_source = "maia-all"
        self.board_view.clear_preview()
        self.hover_preview.show_position(position, last, self.board_view,
                                         f"Stockfish variation · {name} · ply {ply}")

    def _maia_move(self, uci):
        try:
            move = self.game.board.parse_uci(uci)
        except ValueError:
            return
        self._human_move(move)

    def _queue_secondary_analysis(self):
        if self._closing:
            return
        self._secondary_identity = self._position_identity()
        if not self._secondary_timer.isActive():
            self._secondary_timer.start()

    def _flush_secondary_analysis(self):
        if self._closing or self._secondary_identity != self._position_identity():
            return
        self._sync_blunder()
        self._update_graph()
        self.inline_history.refresh_evaluation(self.game)
        self._protect_analysis_chart()

    def _sync_candidate_markers(self):
        self._queue_secondary_analysis()
        if self._candidate_identity != self._position_identity():
            return
        entries = []
        best = self.candidates.lines.get(1, {}).get("score")
        inferior_ranks = set()
        for rank, line in self.candidates.lines.items():
            if best is not None and line.get("score") is not None and best - line["score"] >= 50:
                inferior_ranks.add(rank)
            try:
                entries.append((self.board_view.legal_by_uci.get(line["pv"][0]) or
                                self.game.board.parse_uci(line["pv"][0]), rank,
                                score_label(line, self.game.board.turn)))
            except (ValueError, IndexError):
                continue
        self.board_view.set_recommendations(entries, inferior_ranks=inferior_ranks)

    def _insert_candidate(self, rank, ply=None):
        if self._candidate_identity != self._position_identity() or not self.candidates.display_line(rank):
            return
        moves = self.candidates.display_line(rank)["pv"][:ply]
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
        self._save(defer=True)
        self._schedule_engine()

    def _candidate_action(self, rank, action):
        if self._candidate_identity != self._position_identity() or not self.candidates.display_line(rank):
            return
        line = self.candidates.display_line(rank)
        if action == "insert":
            self._insert_candidate(rank)
        elif action == "focus":
            self._stop_engine()
            self.config["searchmoves"] = [line["pv"][0]]
            self.statusBar().showMessage("Targeted analysis: " + line["san"][0])
            self._schedule_engine()
        elif action in ("san", "uci"):
            QApplication.clipboard().setText(" ".join(line[action if action == "san" else "pv"]))
        elif action == "pgn":
            variation = Game(self.game.board.fen())
            variation.headers = self.game.headers.copy()
            variation.headers["Result"] = "*"
            try:
                for move in line["pv"][:128]:
                    variation.play(variation.board.parse_uci(move))
            except ValueError:
                return
            QApplication.clipboard().setText(variation.pgn())

    def _clear_focus(self):
        self.config["searchmoves"] = []
        self._stop_engine()
        self._schedule_engine()

    def _execute_rank(self, rank):
        if not self.board_view.smart_move or self.board_view.selected is not None:
            return
        self._insert_candidate(rank, 1)

    def _store_analysis(self, game, node_id, info, turn, context):
        if not info or "score" not in info:
            return
        value = info["score"] * turn
        node = game.nodes[node_id]
        previous_value = node.evaluation
        node.evaluation = value
        if node_id and game is self.game and previous_value != value:
            self._queue_secondary_analysis()
        from datetime import datetime, timezone

        node.analysis = {
            **info,
            "white_value": info.get("score_value", info["score"]) * turn,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "profile": context.get("profile", ""),
            "options": dict(context.get("options", {})),
        }
        lines = context.get("lines") or context.get("exact_lines")
        if lines:
            node.analysis["multipv_lines"] = [
                dict(lines[rank]) for rank in sorted(lines)
            ]
        if node_id in game._line_nodes:
            game.evaluations[game._line_nodes.index(node_id)] = value

    def _set_bookmark(self, name, note=""):
        key = str(self.game.current_node)
        records = self.game.metadata.setdefault("bookmarks", {})
        if not isinstance(records, dict):
            records = self.game.metadata["bookmarks"] = {}
        if name.strip():
            records[key] = {"name": name.strip()[:120], "note": note.strip()[:10000]}
        else:
            records.pop(key, None)
        self._save()

    def _populate_bookmarks(self):
        self.bookmarks_menu.clear()
        records = self.game.metadata.get("bookmarks", {})
        records = records if isinstance(records, dict) else {}
        for key, entry in records.items():
            if not key.isdigit() or not 0 <= int(key) < len(self.game.nodes) or not isinstance(entry, dict):
                continue
            if not isinstance(entry.get("name"), str):
                continue
            node_id = int(key)
            action = self.bookmarks_menu.addAction(entry["name"].replace("&", "&&"))
            action.setToolTip(str(entry.get("note", "")))
            action.triggered.connect(lambda checked=False, i=node_id: self._navigate_node(i))
        if self.bookmarks_menu.isEmpty():
            self.bookmarks_menu.addAction("No bookmarks yet · Ctrl+B to add").setEnabled(False)
        self.bookmarks_menu.setToolTipsVisible(True)

    def _edit_bookmark(self):
        records = self.game.metadata.get("bookmarks", {})
        saved = records.get(str(self.game.current_node), {}) if isinstance(records, dict) else {}
        saved = saved if isinstance(saved, dict) else {}
        dialog = QDialog(self)
        dialog.setWindowTitle("Position bookmark")
        dialog.resize(440, 300)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Name"))
        name = QLineEdit(str(saved.get("name", self.game.nodes[self.game.current_node].san or "Starting position")))
        layout.addWidget(name)
        layout.addWidget(QLabel("Notes"))
        note = QPlainTextEdit(str(saved.get("note", "")))
        layout.addWidget(note, 1)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(dialog.accept)
        controls.rejected.connect(dialog.reject)
        remove = controls.addButton("Delete bookmark", QDialogButtonBox.ButtonRole.DestructiveRole)
        remove.setEnabled(bool(saved))
        remove.clicked.connect(lambda: (name.clear(), dialog.accept()))
        layout.addWidget(controls)
        if dialog.exec():
            self._set_bookmark(name.text(), note.toPlainText())

    def _set_review_confirmation(self, enabled):
        self.config["review_confirm"] = bool(enabled)
        self._save()

    def _set_snapshot_capture(self, enabled):
        self.config["analysis_snapshots"] = bool(enabled)
        self.engine.set_snapshot_capture(enabled)
        self._save()

    def _compare_snapshots(self):
        if not self.store:
            self._error("Library unavailable", self._storage_message)
            return
        game_id, key = self.game.id, position_key(self.game)
        try:
            SnapshotDialog(lambda: self.store.snapshots(game_id, key),
                           self.config.get("light", False), self).exec()
        except StorageError as exc:
            self._error("Cannot read snapshots", str(exc))

    def _save_snapshot(self, generation, payload):
        if (not self.store or not self.config.get("analysis_snapshots", False)
                or generation != self.engine.generation):
            return
        state = self._review
        if (state and state.get("kind") == "auto_eval" and state.get("generation") == generation
                and state["game_id"] == self.game.id):
            node_id = state["line"][state["index"]]
            context = state
        elif (self._job and self._job["generation"] == generation and self._job["kind"] == "analysis"
              and self._job["identity"] == self._position_identity()):
            node_id, context = self.game.current_node, self._job
        else:
            return
        from datetime import datetime, timezone

        key = position_key(self.game, node_id)
        position = self.game.position_at_node(node_id)
        record = {"observed_nodes": payload["observed_nodes"], "lines": payload["lines"],
                  "requested_multipv": context.get("multipv", self._effective_multipv()),
                  "turn": position.turn, "fen": position.fen(), "profile": context.get("profile", ""),
                  "options": dict(context.get("options", {})),
                  "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        try:
            for milestone in payload["milestones"]:
                self.store.save_snapshot(self.game.id, key, record | {"milestone": milestone})
            lines = {info["multipv"]: info for info in payload["lines"]}
            if 1 in lines:
                self._store_analysis(self.game, node_id, lines[1], position.turn, context | {"lines": lines})
            # Save the displayed/frozen PGN as well, so a crash can recover it
            # together with a checkpoint written before the periodic autosave.
            self._save()
        except StorageError as exc:
            self.statusBar().showMessage(str(exc))

    def _clear_saved_analysis(self, node_ids):
        for node_id in node_ids:
            node = self.game.nodes[node_id]
            node.analysis = {}
            node.evaluation = None
            if self.store:
                try:
                    self.store.clear_snapshots(self.game.id, position_key(self.game, node_id))
                except StorageError as exc:
                    self.statusBar().showMessage(str(exc))
        self.game.evaluations = {ply: value for ply, value in self.game.evaluations.items()
                                 if self.game._line_nodes[ply] not in node_ids}
        self._clear_analysis_output()

    def _edit_annotation(self):
        self._edit_annotation_at_node(self.game.current_node)

    def _edit_annotation_at_node(self, node_id):
        dialog = QDialog(self)
        dialog.setWindowTitle("PGN note and move annotations")
        dialog.resize(580, 380)
        layout = QVBoxLayout(dialog)
        node = self.game.nodes[node_id]
        comment = QPlainTextEdit(node.comment)
        comment.setPlaceholderText("Write your PGN note here. Shown in Game Line and included in PGN exports.")
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
        self._save(defer=True)

    def _auto_evaluate_line(self):
        if self._review and self._review.get("kind") == "auto_eval":
            self.tabs.setCurrentIndex(1)
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
        start_index = self.game.cursor
        self._clear_saved_analysis(self.game._line_nodes[start_index:])
        self._review = {
            "kind": "auto_eval",
            "game_id": self.game.id,
            "line": self.game._line_nodes.copy(),
            "index": start_index,
            "stage": "best",
            "seconds": 600,
            "paused": False,
            "info": None,
            "generation": None,
            "depth": 128,
            "nodes": self.config.get("auto_eval_nodes") or None,
            "multipv": self._effective_multipv(),
            "job_profile": self._profile()["id"],
            "job_options": dict(self._profile().get("values", {})),
        }
        self.analysis_nav.setChecked(True)
        self.play_nav.setChecked(False)
        self.tabs.setCurrentIndex(1)
        self._refresh()
        self.quick_analysis_button.setText("Stop auto-evaluation")
        self._render_move_history()
        self._save()
        self._review_next()

    def _start_auto_play(self):
        if self._auto_play_active:
            self._auto_play_paused = not self._auto_play_paused
            if self._auto_play_paused:
                self.engine.stop()
                self.quick_analysis_button.setText("Resume auto-play")
                self.statusBar().showMessage("Auto-play paused · press F11 to resume")
            else:
                self.quick_analysis_button.setText("Pause auto-play")
                self.statusBar().showMessage("Auto-play resumed")
                self._schedule_engine()
            self._save(defer=True)
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
        self._auto_play_paused = False
        self._suspend_maia_for_auto_play()
        self.config.pop("searchmoves", None)
        self.game.pause_clock()
        self.analysis_nav.setChecked(True)
        self.play_nav.setChecked(False)
        self.tabs.setCurrentIndex(1)
        self._refresh()
        self.quick_analysis_button.setText("Pause auto-play")
        self._save(defer=True)
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
            QTimer.singleShot(0, self, self._review_next)
            return
        if state.get("kind") == "auto_eval":
            self.game.select_node(node_id)
            self._refresh()
            self.analysis_scope = f"{state['multipv']} PV · auto-evaluation {state['index'] + 1}/{len(state['line'])}"
            self.candidates.set_multipv(state["multipv"])
            self.candidates.reserve_slots(min(state["multipv"], sum(1 for _ in position.legal_moves())))
            self.engine_state.setText(self._active_engine_name() + " · auto-evaluating")
            state["identity"] = self._position_identity()
        from types import SimpleNamespace

        path = self.game.node_path(node_id)
        temporary = SimpleNamespace(
            initial_fen=self.game.initial_fen,
            id=self.game.id,
            moves=[self.game.nodes[i].move for i in path[1:]],
            cursor=len(path) - 1,
            board=position,
        )
        profile = (next((p for p in self.profiles if p["id"] == state.get("job_profile")), None)
                   if state.get("kind") == "auto_eval" and state.get("job_profile") else self._profile())
        if not profile:
            state["paused"] = True
            state["message"] = "Saved job's engine is unavailable · restore its engine profile or start a new analysis"
            self.statusBar().showMessage(state["message"])
            self._update_review_panel()
            return
        searchmoves = None
        if state["stage"] in ("played", "confirm_played"):
            searchmoves = [self.game.nodes[state["line"][state["index"] + 1]].move.uci()]
        confirming = state["stage"].startswith("confirm_")
        limits = SearchLimits(
            depth=state["depth"],
            seconds=state["seconds"],
            nodes=state["confirmation_nodes"] if confirming else state["nodes"],
        )
        options = dict(state.get("job_options", profile.get("values", {})))
        options.setdefault("UCI_ShowWDL", True)
        try:
            generation = self.engine.start(
                temporary,
                limits,
                profile["path"],
                options=options,
                multipv=state.get("multipv", 1),
                infinite=state.get("kind") == "auto_eval" and state["nodes"] is None,
                nodes_only=state.get("kind") == "auto_eval" or confirming,
                kind="analysis",
                ensure_pv_length=state.get("kind") == "auto_eval",
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
        state["lines"] = {}
        state.pop("message", None)
        state["turn"] = position.turn
        state["profile"] = profile["id"]
        state["options"] = dict(options)
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
        if kind == "tablebase":
            if state.get("kind") == "auto_eval":
                self.tablebase_label.setText(payload["message"])
            return True
        if kind == "info":
            state["info"] = payload.copy()
            if state.get("kind") == "auto_eval":
                if state.get("identity") != self._position_identity():
                    self._cancel_review()
                    return True
                state.setdefault("lines", {})[payload["multipv"]] = payload.copy()
                self._show_info(payload, state)
            return True
        if kind != "result":
            return True
        # Saving analysis accepts partial iterations, including bound scores.
        # Grading a move still needs exact evidence rather than an inequality.
        exact_lines = payload.get("exact_lines") or {}
        auto_eval = state.get("kind") == "auto_eval"
        info = ((payload.get("info") or state["info"]) if auto_eval else
                (exact_lines.get(1) or payload.get("info") or state["info"]))
        valid = bool(info and info.get("pv")) and (
            info.get("score_type") in ("cp", "mate") if auto_eval else chance(info) is not None
        )
        if valid and state["stage"] in ("played", "confirm_played"):
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
            lines = payload.get("lines") or exact_lines or {1: info}
            self._store_analysis(self.game, node_id, info, state["turn"], state)
            self.game.nodes[node_id].analysis["multipv_lines"] = [
                dict(lines[rank]) for rank in sorted(lines)
            ]
            state["index"] += 1
            self.engine_state.setText(self._active_engine_name() + " · position saved")
            self._update_graph()
            self._save(defer=True)
            self._render_move_history()
            QTimer.singleShot(0, self, self._review_next)
            return True
        if state["stage"] in ("best", "confirm_best"):
            self._store_analysis(self.game, node_id, info, state["turn"], state)
            state["best"] = info.copy()
            if index + 1 < len(line):
                played = self.game.nodes[line[index + 1]].move.uci()
                if info["pv"][0] != played:
                    state["stage"] = "confirm_played" if state["stage"] == "confirm_best" else "played"
                    QTimer.singleShot(0, self, self._review_next)
                    self._save(defer=True)
                    return True
                if self._classify_review(line[index + 1], info, info):
                    return True
        else:
            if self._classify_review(line[index + 1], state["best"], info):
                return True
        state["index"] += 1
        state["stage"] = "best"
        state.pop("confirmation_nodes", None)
        state.pop("initial_review", None)
        self._update_graph()
        self._save()
        self._render_move_history()
        self._update_review_panel()
        QTimer.singleShot(0, self, self._review_next)
        return True

    def _classify_review(self, node_id, best, played):
        node = self.game.nodes[node_id]
        state = self._review or {}
        record = classify(self.game.position_at_node(node.parent), node.move, best, played, {
            "profile": state.get("profile", ""), "options": state.get("options", {}),
            "seconds": None if state.get("confirmation_nodes") else state.get("seconds"),
            "depth": None if state.get("confirmation_nodes") else state.get("depth"),
            "nodes": state.get("confirmation_nodes", state.get("nodes")),
            "engine": best.get("engine", "UCI"),
        })
        if record is None:
            return False
        if (record["label"] in ("Mistake", "Blunder")
                and self.config.get("review_confirm", True)
                and not state.get("stage", "best").startswith("confirm_")):
            # Use actual work, since the first pass may have hit its time/depth
            # limit long before its configured node ceiling.
            state["confirmation_nodes"] = max(
                10_000_000, 4 * max(best.get("nodes", 0), played.get("nodes", 0))
            )
            state["initial_review"] = record
            state["stage"] = "confirm_best"
            state["message"] = f"Confirming {node.san} · {state['confirmation_nodes']:,} nodes per search"
            self.statusBar().showMessage(state["message"])
            self._update_review_panel()
            QTimer.singleShot(0, self, self._review_next)
            return True
        if state.get("initial_review"):
            record["context"]["confirmation"] = {
                "initial_label": state["initial_review"]["label"],
                "initial_best": state["initial_review"]["best"],
                "initial_played": state["initial_review"]["played"],
                "nodes_per_search": state["confirmation_nodes"],
            }
        self.game.metadata.setdefault("review", {})[str(node_id)] = record
        self.statusBar().showMessage(self.game.nodes[node_id].san + " · " + record["label"])
        return False

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
        self._maybe_apply_gpu_hash_default(self._profile())
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
            if name == "Hash":
                profile["gpu_hash_default_suppressed"] = True
        else:
            profile["values"][name] = number
            if name == "Hash":
                profile.pop("gpu_hash_default_suppressed", None)
        self._analysis_context = None
        self._clear_analysis_output()
        self._save()
        self.resource_controls.refresh()
        self._schedule_engine()

    def _probe_gpu_hardware(self):
        """Query Windows asynchronously so GPU detection never delays launch."""
        if sys.platform != "win32" or self._closing:
            return
        process = QProcess(self)
        self._gpu_inventory_process = process
        process.finished.connect(self._gpu_inventory_finished)
        process.start("powershell.exe", [
            "-NoProfile", "-NonInteractive", "-Command",
            "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name",
        ])

    def _gpu_inventory_finished(self, exit_code, _exit_status):
        process = self.sender()
        if process is None:
            return
        inventory = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        from .hardware import has_discrete_gpu

        self._gpu_hardware_detected = exit_code == 0 and has_discrete_gpu(inventory)
        if self._gpu_hardware_detected:
            self._maybe_apply_gpu_hash_default(self._profile())

    def _maybe_apply_gpu_hash_default(self, profile):
        """Use an 8 GB starting Hash on detected-GPU desktops, respecting overrides."""
        if (not self._gpu_hardware_detected or not profile or not profile.get("options_detected")
                or profile.get("gpu_hash_default_suppressed")
                or profile["id"] in self._gpu_hash_default_profiles):
            return
        option = profile.get("options", {}).get("Hash")
        if not isinstance(option, dict) or option.get("kind") != "spin":
            return
        saved = profile.get("values", {}).get("Hash")
        if saved is not None and str(saved) != str(option.get("default", "")):
            return

        from .hardware import hash_budget_mb

        minimum = int(option.get("minimum", 1))
        maximum = min(8192, int(option.get("maximum", 8192)))
        budget = hash_budget_mb(self.resource_controls.allocated_hash())
        if budget is not None:
            maximum = min(maximum, budget)
        if maximum < minimum:
            return
        target = maximum
        self._gpu_hash_default_profiles.add(profile["id"])
        profile["gpu_hash_defaulted"] = target
        if saved is not None and str(saved) == str(target):
            return
        if profile is self._profile():
            QTimer.singleShot(0, self, lambda p=profile, value=target: self._apply_gpu_hash_default(p, value))
        else:
            profile.setdefault("values", {})["Hash"] = target
            self._save()

    def _apply_gpu_hash_default(self, profile, value):
        if not self._closing and profile is self._profile():
            self._set_engine_resource("Hash", value)

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
        self.maia_controls.move_limit.setValue(count)
        self.maia_controls.all_moves.setText(f"Top {count} Maia moves")
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
        if mode == "nodes" and not self.config.get("analysis_nodes"):
            self.config["analysis_nodes"] = 1_000_000_000
        self._analysis_context = None
        self._clear_analysis_output()
        self._save()
        self._refresh_engine_menus()
        self._schedule_engine()

    def _set_auto_eval_limit(self, nodes):
        self._set_node_limit("auto_eval_nodes", nodes)

    def _set_node_limit(self, key, nodes):
        self.config[key] = int(nodes)
        if key == "analysis_nodes":
            self.config["analysis_kind"] = "nodes" if nodes else "infinite"
        if key == "auto_eval_nodes":
            self.config["auto_eval_limit_version"] = 2
        self._save()
        self._refresh_engine_menus()
        # A running normal search can adopt the new cap immediately. The two
        # batch modes read their caps when the next run starts.
        if key == "analysis_nodes" and self.analysis_mode and self._analysis_enabled and not self._review:
            self._stop_engine()
            self._analysis_context = None
            self._schedule_engine()

    def _custom_node_limit(self, key, title, minimum=0):
        if key == "auto_play_nodes":
            minimum = 1
        prompt = ("Maximum engine nodes per move:" if minimum else
                  "Maximum engine nodes per position (0 means unlimited):")
        nodes, accepted = QInputDialog.getInt(
            self, title, prompt,
            self.config.get(key, 0), minimum, 2_000_000_000, 1_000_000,
        )
        if accepted:
            self._set_node_limit(key, nodes)

    def _populate_node_limit_menu(self, menu, key, label, values, allow_unlimited=True):
        current = self.config.get(key, 0)
        if key == "analysis_nodes" and self.config.get("analysis_kind") in ("infinite", "explore"):
            current = 0
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
        menu.addAction(f"Reset to default · {DEFAULTS[key]:,}",
                       lambda checked=False, k=key: self._set_node_limit(k, DEFAULTS[k]))
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
        nodes.setSpecialValueText("No node cap")
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
        for title, mode in (("Continuous", "infinite"), ("Node limit", "nodes"),
                            ("Time / depth limits", "bounded")):
            action = self.search_mode_menu.addAction(title)
            action.setCheckable(True)
            current_mode = self.config.get("analysis_kind")
            action.setChecked((current_mode == mode) or (current_mode == "explore" and mode == "infinite"))
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
            self._maybe_apply_gpu_hash_default(profile)
            count = self._effective_multipv()
            restart = (self._job and self._job["kind"] == "analysis"
                       and self._job.get("multipv", 1) != count and not self.config.get("searchmoves"))
            self.config["multipv"] = count
            if restart:
                self._stop_engine()
                self._analysis_context = None
                QTimer.singleShot(0, self, self._schedule_engine)
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
        app = QApplication.instance()
        app.setProperty("nocturneLightAppearance", bool(light))
        style = stylesheet(light)
        if app.styleSheet() != style:
            app.setStyleSheet(style)
        self.board_view.theme = appearance.get("theme", "Classic")
        self.board_view.set_piece_set(appearance.get("piece_set", "Nibbler"))
        self.board_view.coordinates = appearance.get("coordinates", True)
        self.board_view.animations = appearance.get("animations", False)
        self.board_view.overlays = appearance.get("overlays", True)
        self.history.setStyleSheet(f"QTableWidget {{ color: {palette(light)['history']}; }}")
        self.eval_label.setStyleSheet(f"color: {palette(light)['metric']};")
        self.telemetry.setStyleSheet(f"color: {palette(light)['metadata']};")
        self.telemetry.setTextFormat(Qt.TextFormat.RichText)
        self.graph.light = self.board_view.light = light
        self.graph.setVisible(self.config.get("show_eval_graph", True))
        self._sync_docked_visibility()
        self.graph.update()
        self.eval_bar.setVisible(self.board_view.overlays)
        self._render_move_history()
        self.candidates.recolor(light)
        for view in {self.pv_label, *(widgets[2] for widgets in self.candidates.rows.values())}:
            view.set_moves(view._items, view._current, light=light)
        self.board_view.update()
        if hasattr(self, "maia"):
            self._maia_changed(self.maia.policies)

    def _refresh_cpu_budget_menu(self):
        self.cpu_budget_menu.clear()
        current = self.config.get("engine_cpu_budget", 100)
        self.cpu_budget_menu.setTitle(f"Stockfish CPU budget ({current}%)")
        for value in (10, 25, 50, 75, 100):
            action = self.cpu_budget_menu.addAction("Unrestricted (100%)" if value == 100 else f"{value}% of total CPU")
            action.setCheckable(True)
            action.setChecked(value == current)
            action.setEnabled(os.name == "nt")
            action.setToolTip("Limits the external UCI engine only. Threads stay unchanged. Lower budgets can reduce heat and fan noise.")
            action.triggered.connect(lambda checked=False, p=value: self._set_cpu_budget(p))
        if os.name != "nt":
            self.cpu_budget_menu.addAction("Available on Windows").setEnabled(False)

    def _set_cpu_budget(self, percent):
        try:
            self.engine.connection.set_cpu_budget(percent)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "CPU budget not applied", str(exc))
            return
        self.config["engine_cpu_budget"] = percent
        self._refresh_cpu_budget_menu()
        self._save()

    def _set_pv_font_increase(self, percent):
        self.config["pv_font_increase"] = percent
        self.pv_font_label.setText(f"Variation text: +{percent}%")
        self.candidates.set_font_increase(percent)
        self._save(defer=True)

    def _apply_settings(self):
        percent = self.config.get("pv_font_increase", 20)
        self.pv_font_slider.blockSignals(True)
        self.pv_font_slider.setValue(percent)
        self.pv_font_slider.blockSignals(False)
        self.pv_font_label.setText(f"Variation text: +{percent}%")
        self.candidates.set_font_increase(percent)
        self.candidates.set_reserve_five_rows(self.config.get("reserve_five_candidate_rows", False))
        self._sync_bottom_moves()
        self.inline_history.set_notes_visible(self.config.get("show_game_line_notes", True))
        self._sync_maia_range_controls()
        self.maia_controls.move_limit.blockSignals(True)
        self.maia_controls.move_limit.setValue(self._effective_multipv())
        self.maia_controls.move_limit.setEnabled(False)
        self.maia_controls.move_limit.setToolTip("Matches the engine MultiPV setting")
        self.maia_controls.all_moves.setText(f"Top {self._effective_multipv()} Maia moves")
        self.maia_controls.move_limit.blockSignals(False)
        self.engine.connection.cpu_budget = self.config.get("engine_cpu_budget", 100) if os.name == "nt" else 100
        self._sync_insight_layout()
        self._apply_appearance(self._appearance_config())
        self.candidates.set_show_seldepth(self.config.get("show_seldepth", False))
        self.candidates.set_detailed(self.config.get("details", False))
        if self._last_info:
            self._render_telemetry(self._last_info, self._last_info_turn)
        self.tablebase_label.setVisible(self.maia_controls.details.isChecked())
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
        self.cursor_preview_action.setChecked(self.config.get("cursor_preview", True))
        self.snapshot_capture_action.setChecked(self.config.get("analysis_snapshots", False))
        self.engine.set_snapshot_capture(self.config.get("analysis_snapshots", False))
        self.confirm_review_action.setChecked(self.config.get("review_confirm", True))

    def _sync_insight_layout(self):
        if not hasattr(self, "maia_insights"):
            return
        insights = self.maia_insights
        if not hasattr(self, "right_detail_splitter"):
            self.right_detail_splitter = QSplitter(Qt.Orientation.Vertical)
            self.right_detail_splitter.setChildrenCollapsible(False)
            self.right_detail_splitter.setHandleWidth(7)
            self.right_detail_splitter.addWidget(self.game_line_panel)
            insights.body_layout.insertWidget(0, self.right_detail_splitter, 1)
            self.candidate_splitter.addWidget(insights.trends_card)
            self.blunder_scroll = QScrollArea()
            self.blunder_scroll.setWidgetResizable(True)
            self.blunder_scroll.setFrameShape(QFrame.Shape.NoFrame)
            self.blunder_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.blunder_scroll.setMinimumHeight(0)
            self.blunder_scroll.setMaximumHeight(180)
            self.blunder_scroll.setWidget(insights.blunder)
            self.analysis_detail_splitter.addWidget(self.blunder_scroll)
            insights.chart.setMaximumHeight(16777215)
            insights.trends_card.content.setStretch(1, 1)
            self.game_line_panel.setMinimumHeight(160)
            self.candidate_splitter.setStretchFactor(0, 0)
            self.candidate_splitter.setStretchFactor(1, 1)
            self.analysis_detail_splitter.setStretchFactor(0, 1)
            self.analysis_detail_splitter.setStretchFactor(1, 0)
            self.right_detail_splitter.setStretchFactor(0, 1)
            self.right_detail_splitter.setStretchFactor(1, 0)
            self.candidate_splitter.setSizes([190, 300])
            self.analysis_detail_splitter.setSizes([650, 170])
        if self._dock_workspace is None and self.right_detail_splitter.indexOf(self.explorer) < 0:
            self.right_detail_splitter.addWidget(self.explorer)
        show_tools = (self.analysis_mode and self.config.get("maia_enabled", True)
                      and self.config.get("show_maia_insights", True))
        insights.trends_card.setVisible(show_tools)
        insights.blunder.setVisible(show_tools)
        self.blunder_scroll.setVisible(show_tools)
        if self._dock_workspace is None:
            self.right_detail_splitter.addWidget(self.graph)
            self.graph.setMaximumHeight(85)
            self.graph.setVisible(self.config.get("show_eval_graph", True))
        self._protect_analysis_chart()
        self.game_line_panel.show()
        self._rating_game_line_swapped = True

    def _protect_analysis_chart(self):
        if not hasattr(self, "blunder_scroll"):
            return
        trends = self.maia_insights.trends_card
        show = not trends.isHidden()
        trends.layout().activate()
        required = trends.minimumSizeHint().height() if show else 0
        trends.setMinimumHeight(required)
        required += max(self.candidates.minimumSizeHint().height(),
                        sum(row[0].minimumSizeHint().height() for row in self.candidates.rows.values() if not row[0].isHidden())) + 32
        # Reserve the entire chart and legend ahead of the scrollable meter.
        # The meter may shrink to nothing in a short window; its own scrollbar
        # handles longer move lists rather than covering the rating chart.
        self.engine_scroll.setMinimumHeight(min(max(100, required),
                                               max(360, self.screen().availableGeometry().height() - 260)))
        self.analysis_detail_splitter.setCollapsible(1, True)
        if (show and self.isVisible() and self.analysis_detail_splitter.height() > 200
                and not getattr(self, "_analysis_meter_sized", False)):
            self._analysis_meter_sized = True
            total = self.analysis_detail_splitter.height()
            self.analysis_detail_splitter.setSizes([max(100, total - 177), 170])

    def _show_board_guide(self):
        QMessageBox.information(self, "Board symbols guide",
            "Stockfish — transparent arrows\n"
            "Blue marks Stockfish's top recommendation; gray arrows show its other candidates. "
            "These are the moves in the Stockfish analysis lines.\n\n"
            "Maia — colored rods and numbered circles\n"
            "A rod appears for every move Maia predicts has more than a 10% chance of being played at the selected rating. "
            "The circle numbers are Maia likelihood rankings, not probabilities: 1 is the most likely human move. "
            "Each rod and circle matches that move's color in Moves by Rating. These colors identify moves, not quality.\n\n"
            "When both agree\n"
            "A Stockfish arrow and a Maia rod/circle can point to the same destination. "
            "The arrow shows the engine candidate; the rod shows the predicted human choice.\n\n"
            "Maia percentages and the Blunder Meter\n"
            "Percentages estimate human move choices. Green, yellow and red in the Blunder Meter "
            "describe Stockfish-assessed move quality; gray there means not evaluated.\n\n"
            "How to read both models\n"
            "Stockfish evaluates objective playing strength; Maia predicts human choices at the selected rating. "
            "A popular move is not necessarily a good move. Use the evaluations and Blunder Meter to judge quality.\n\n"
            "Play a marked move\n"
            "With destination-click moves enabled, click a Maia circle or Stockfish arrow destination to play it. "
            "When different moves share a square, Stockfish takes priority; otherwise the most likely Maia move is selected. "
            "Recorded continuations remain available where neither engine marks the destination. "
            "Select a piece first to choose a move manually.\n\n"
            "Scores and ratings\n"
            "Stockfish scores are from White's perspective: + favors White, − favors Black. "
            "Maia percentages are probabilities of choosing moves, not winning the game. The Maia outcome rail "
            "shows White's expected score: win probability plus half the draw probability.\n\n"
            "Rating curves\n"
            "Moves by Rating compares the same position across equal-rated opponents. "
            "Details → Calculate ratings controls which ratings Maia actually computes.\n\n"
            "Move previews\n"
            "Hover a variation and scroll to explore it on the preview board. The main board stays on your game position.")

    def _sync_workspace_layout(self):
        self._sync_insight_layout()
        analysis = self.analysis_mode
        signature = (analysis, self.config.get("layout", "classic"), self._dock_workspace is not None)
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
        self.maia_insights.setVisible(analysis)
        self.tabs.setTabVisible(0, not analysis)
        self.panel_caption.setText("ENGINE ANALYSIS" if analysis else "THE GAME")
        self.panel_caption.setVisible(not analysis)
        self.io_bar.setVisible(not analysis)
        self.save_label.setVisible(not analysis)
        self.mode_label.setVisible(not analysis)
        self.status_label.setVisible(not analysis)
        self.content_layout.setContentsMargins(*( (12, 6, 12, 0) if analysis else (25, 22, 25, 12) ))
        self.content_layout.setSpacing(6 if analysis else 15)
        self._sync_status_space()
        self.panel_body.layout().setContentsMargins(*( (8, 4, 8, 4) if analysis else (20, 16, 20, 12) ))
        self.panel_body.layout().setSpacing(2 if analysis else 10)
        self.panel.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff if analysis else Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._analysis_tab_changed()
        self.arena.setMaximumWidth(16777215)
        self.panel.setMaximumWidth(16777215 if analysis else 420)
        if self._dock_workspace is not None:
            if analysis:
                self.tabs.setCurrentIndex(1)
            self._sync_docked_visibility()
            return
        left = analysis and self.config.get("layout", "classic") == "analysis-left"
        self.main_splitter.insertWidget(0 if left else 1, self.panel)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 1 if analysis else 0)
        self.main_splitter.setStretchFactor(2, 1 if analysis else 0)
        if analysis:
            self.tabs.setCurrentIndex(1)
            # Compact analysis/database column: roughly twelve SAN moves on
            # one line at the default window size. The divider stays movable.
            self.main_splitter.setSizes([560, 900, 340] if left else [900, 560, 340])
            self.workspace_splitter.setSizes([800, 33 if self.config.get("bottom_moves_collapsed", False) else 90])
        else:
            self.main_splitter.setSizes([720, 350])
        QTimer.singleShot(0, self, self._fit_analysis_columns)

    def _fit_analysis_columns(self):
        if self._closing or not self.analysis_mode:
            return
        self._protect_analysis_chart()
        if self._dock_workspace is None and self.config.get("bottom_moves_collapsed", False):
            total = self.workspace_splitter.height() - self.workspace_splitter.handleWidth()
            if total > 33:
                self.workspace_splitter.setSizes([total - 33, 33])
        if getattr(self, "_telemetry_reserved_width", self.telemetry.width()) != self.telemetry.width():
            self.telemetry.setMinimumHeight(0)
            self._telemetry_reserved_width = self.telemetry.width()
        if self._dock_workspace is not None:
            self._dock_workspace.fit_columns()
            return
        # The square is height-limited. Extra desktop width must not inflate
        # its parent, otherwise the board acquires large black side margins.
        target = max(350, self.board_view.height() + self.arena.width() - self.board_view.width())
        if self.arena.maximumWidth() != target:
            self.arena.setMaximumWidth(target)

    def _sync_pgn_editor(self):
        """Build PGN only when the editor is displayed, preserving typed drafts."""
        if self._pgn_game_id != self.game.id or not self.pgn_editor.document().isModified():
            text = self.game.pgn()
            if self.pgn_editor.toPlainText() != text:
                self.pgn_editor.setPlainText(text)
            self.pgn_editor.document().setModified(False)
            self._pgn_game_id = self.game.id

    def _analysis_tab_changed(self, index=None):
        if hasattr(self, "tabs"):
            if self.tabs.currentWidget() is getattr(self, "pgn_page", None):
                self._sync_pgn_editor()
            # Inactive review pages have wide minimum hints. Let the active
            # engine page fit its viewport rather than clipping the Maia column.
            compact = self.analysis_mode and self.tabs.currentIndex() == 1
            self.tabs.setSizePolicy(QSizePolicy.Policy.Ignored if compact else QSizePolicy.Policy.Preferred,
                                    QSizePolicy.Policy.Expanding)
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
        departure = self.opening_coverage.departure if self._book_highlight_enabled() else None
        markers = (self.opening_coverage.markers(
            self.game, allow_lichess=self.explorer.client.has_lichess_token,
            speed=self.config.get("explorer_speed", "all"), rating=self.config.get("explorer_rating", 0))
            if self.config.get("explorer_statistics") else {})
        self.analysis_history.set_moves(tokens, self.game.current_node, self._appearance_config().get("light", False),
                                        book_departure=departure if departure else None, book_departures=markers)
        move_risks = {}
        current = self.game.current_node
        if current and self.analysis_mode and self.config.get("maia_enabled", True):
            node = self.game.nodes[current]
            parent = node.parent
            if node.evaluation is not None and abs(node.evaluation) < 400 and parent is not None:
                path = self.game.node_path(parent)[1:]
                history = [self.game.nodes[index].move.uci() for index in path]
                key = self.maia.position_key(self.game.initial_fen, history)
                rating = self.config.get("maia_rating", 1800)
                policy = self.maia.cache.get(key, {}).get(str(rating), {})
                saved = self.game.nodes[parent].analysis
                lines = saved.get("multipv_lines") or [saved]
                candidates = {line["pv"][0]: line for line in lines if isinstance(line, dict) and line.get("pv")}
                assessed = assess_moves(policy, candidates)
                green_share = sum(move["probability"] for move in assessed.values()
                                  if move["category"] == "best")
                if green_share < .5 and assessed.get(node.move.uci(), {}).get("category") == "blunder":
                    move_risks[current] = True
        self.inline_history.set_game(self.game, self._appearance_config().get("light", False),
                                     book_departures=markers, move_risks=move_risks)
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
        if self.config.get("cursor_preview", True):
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
        # Commit pixels before history formatting, persistence or analysis UI.
        # repaint() paints this widget only; it does not process queued input.
        self.board_view.set_position(self.game.board, move, animate=False)
        self.board_view.repaint()
        self._refresh(board_ready=True)
        self._save(defer=True)
        self._schedule_engine()

    def _refresh(self, animate=False, board_ready=False):
        self.delete_line_action.setEnabled(self.analysis_mode and self.game.current_node != 0)
        self._register_study()
        self._update_review_panel()
        self._sync_workspace_layout()
        self._clear_move_preview()
        if self.tabs.currentWidget() is self.pgn_page:
            self._sync_pgn_editor()
        last = self.game.moves[self.game.cursor - 1] if self.game.cursor else None
        if not board_ready:
            self.board_view.set_position(self.game.board, last, animate)
        next_game_move = (
            self.game.moves[self.game.cursor]
            if self.game.cursor < len(self.game.moves)
            else None
        )
        self.board_view.set_game_move(next_game_move)
        self._render_move_history()
        self._request_maia()
        if self._pv_identity != self._position_identity():
            self._clear_analysis_output()
            self.analysis_scope = ""
            self.config["searchmoves"] = []
            self.tablebase_label.setText(
                "Syzygy: awaiting probe" if self.config.get("syzygy_path") else "Syzygy: not configured"
            )
            self._restore_position_analysis()
        outcome = self.game.outcome
        self.board_view.branch_moves = (
            [self.game.nodes[c].move for c in self.game.nodes[self.game.current_node].children]
            if self.config.get("branch_arrows", True)
            else []
        )
        self.board_view.interactive = (
            not outcome and not self.paused and (self.analysis_mode or not self._is_engine_turn())
        )
        self._sync_candidate_markers()
        self._sync_blunder()  # Use cached policy and saved lines during the move refresh.
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
        self._update_graph()
        if not self.engine.busy:
            self.eval_bar.set_score(self.game.evaluations.get(self.game.cursor))
        signature = tuple(self.game.sans)
        if signature != self._history_signature:
            self._history_signature = signature
            # Honor a FEN that starts with Black to move or at a later move number.
            initial = Board(self.game.initial_fen)
            offset = int(initial.turn < 0)
            self._history_cells = {}
            self.history.setRowCount(0)
            row = -1
            for index, notation in enumerate(self.game.sans):
                ply = index + offset
                if ply % 2 == 0 or row == -1:
                    row += 1
                    self.history.insertRow(row)
                    self.history.setItem(row, 0, QTableWidgetItem(str(initial.fullmove + ply // 2)))
                column = 1 if ply % 2 == 0 else 2
                self.history.setItem(row, column, QTableWidgetItem(notation))
                self._history_cells[(row, column)] = index + 1
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

    def _restore_position_analysis(self):
        """Display saved engine lines without launching or rewriting a search."""
        cached = self.game.nodes[self.game.current_node].analysis
        count = self._effective_multipv()
        lines = cached.get("multipv_lines") or [cached]
        job = {"turn": self.game.board.turn, "multipv": count}
        for info in lines:
            if (not isinstance(info, dict) or not info.get("pv") or not info.get("san")
                    or not {"score", "score_type", "score_value", "depth", "seldepth", "nodes"} <= info.keys()):
                continue
            self._show_info(info, job, store=False)
        if self._last_info:
            self.engine_state.setText(self._last_info.get("engine", "Engine") + " · saved analysis")
        else:
            value = self.game.evaluations.get(self.game.cursor)
            self.eval_label.setText("—" if value is None else score_text(value))
            self.telemetry.setText("No saved analysis for this position")

    def _update_graph(self):
        self.graph.set_samples(
            self.game.evaluations, self.game.cursor, len(self.game.moves),
            context=(self.game.id, self.game._line_nodes[-1]),
        )

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
            if self.analysis_mode and self.game.current_node == self.game.mainline_node(self.game.cursor):
                self.game.select_node(self.game.current_node)
            self._refresh()
            self._save()
            self._analysis_enabled = analyze
            if analyze:
                self.paused = False
            self._schedule_engine()

    def _redo(self):
        self._interrupt_automation()
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
        self._interrupt_automation()
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

    def _inline_history_menu(self, position):
        menu = self._inline_history_context_menu(position)
        menu.exec(self.inline_history.mapToGlobal(position))

    def _inline_history_context_menu(self, position):
        menu = QMenu(self.inline_history)
        menu.addAction("Copy PGN", self._copy_pgn)
        anchor = self.inline_history.anchorAt(position)
        target = int(anchor[5:]) if anchor.startswith("move:") and anchor[5:].isdigit() else self.game.current_node
        menu.addAction("Edit PGN note…", lambda checked=False, target=target: self._edit_annotation_at_node(target))
        if anchor.startswith("move:") and anchor[5:].isdigit():
            node_id = int(anchor[5:])
            if node_id and node_id not in mainline(self.game.nodes):
                menu.addSeparator()
                menu.addAction("Make this variation the mainline",
                               lambda node_id=node_id: self._promote_node_line(node_id))
                menu.addAction("Make this variation the mainline and delete the previous mainline",
                               lambda node_id=node_id: self._promote_node_line(node_id, delete_previous=True))
        return menu

    def _promote_node_line(self, node_id, *, delete_previous=False):
        if not 0 < node_id < len(self.game.nodes):
            return
        self._stop_engine()
        self._ensure_analysis_copy()
        if self.game.promote_node_line(node_id, delete_previous=delete_previous):
            self._refresh()
            self._save()
            self._schedule_engine()

    def _history_context_menu(self, position):
        menu = QMenu(self.analysis_history)
        menu.addAction("Copy PGN", self._copy_pgn)
        menu.exec(self.analysis_history.mapToGlobal(position))

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
        self._import_text(QApplication.clipboard().text())

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
        self.tabs.setCurrentIndex(1)
        self.paused = False
        self._refresh()
        self._save(force=True)
        return True

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export PGN", "nocturne-game.pgn", "PGN games (*.pgn)")
        if path:
            try:
                Path(path).write_text(self.game.pgn(), encoding="utf-8")
                self.statusBar().showMessage("PGN exported", 3000)
            except OSError as exc:
                self._error("Export failed", str(exc))

    def _save(self, *, force=False, defer=False):
        if not self.store:
            return
        now = time.monotonic()
        if defer and not force and self._last_save_at is not None and now - self._last_save_at < 60000:
            self.save_label.setText("CHANGES PENDING · SAVED WITHIN 1 MINUTE")
            return
        saved_job = checkpoint_job(self._review)
        if saved_job:
            self.game.metadata["auto_eval_job"] = saved_job
        else:
            self.game.metadata.pop("auto_eval_job", None)
        try:
            workspace = self._dock_workspace
            state = workspace.state() if workspace is not None else None
            if state is not None:
                state["window_geometry"] = bytes(self.saveGeometry().toBase64()).decode("ascii")
            self.store.set("workspace_layout", state)
            self.store.set("settings", self.config)
            self.store.set("engine_profiles", self.profiles)
            studies = dict(self._study_games)
            studies[self.game.id] = self.game
            if force:
                saved_studies = list(studies.items())[-20:]
                if self.game.id not in dict(saved_studies):
                    saved_studies[-1] = (self.game.id, self.game)
            else:
                saved_studies = [(self.game.id, self.game)]
            self.store.set("open_studies", [key for key, _study in saved_studies])
            for _key, study in saved_studies:
                self.store.save(study)
            self._last_save_at = time.monotonic()
            if not self._closing and hasattr(self, "autosave_timer"):
                self.autosave_timer.start(60000)
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
        dialog.resize(980, 560)
        dialog.setMinimumSize(780, 480)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Saved PGNs & games", "title"))
        layout.addWidget(label("Games and studies are saved automatically on this device.", "muted", True))
        layout.addWidget(button("Open PGN folder", self._open_pgn_folder))
        try:
            games = self.store.list_games()
        except StorageError as exc:
            self._error("Library unavailable", str(exc))
            return
        content = QSplitter(Qt.Orientation.Horizontal)
        listing = QListWidget()
        listing.setMouseTracking(True)
        listing.setMinimumWidth(300)
        for record in games:
            item = QListWidgetItem(
                f"{record['title']}\n{record['updated'][:16].replace('T', ' ')} UTC · {record['plies']} plies · {record['result']}"
            )
            item.setData(Qt.ItemDataRole.UserRole, record["id"])
            listing.addItem(item)
        content.addWidget(listing)

        preview = QFrame()
        preview.setObjectName("panel")
        preview_layout = QHBoxLayout(preview)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        mini_board = MiniBoard(preview)
        mini_board.setMinimumSize(0, 0)
        mini_board.setFixedSize(244, 244)
        mini_board.coordinates = self.board_view.coordinates
        mini_board.interactive = mini_board.animations = mini_board.overlays = False
        mini_board.wheel_navigation = False
        mini_board.theme, mini_board.light = self.board_view.theme, self.board_view.light
        mini_board.set_piece_set(self.board_view.piece_set)
        preview_layout.addWidget(mini_board, 0, Qt.AlignmentFlag.AlignTop)

        move_preview = QVBoxLayout()
        preview_title = label("Hover over a saved game to preview it", "subtitle", True)
        move_preview.addWidget(preview_title)
        move_preview.addWidget(label("Click a move or scroll to preview a position · click blank space to return to the end",
                                     "eyebrow", True))
        opening = SavedGameMoves()
        opening.position_selected.connect(lambda ply: show_game_position(ply))
        move_preview.addWidget(opening, 1)
        preview_layout.addLayout(move_preview, 1)
        content.addWidget(preview)
        content.setStretchFactor(0, 4)
        content.setStretchFactor(1, 6)
        layout.addWidget(content, 1)

        preview_cache = {}
        preview_game = {"game": None}

        def show_game_position(ply):
            game = preview_game["game"]
            if game is None:
                return
            node_id = opening._line[max(0, min(len(opening._line) - 1, ply))]
            node = game.nodes[node_id]
            mini_board.set_position(game.position_at_node(node_id), node.move)
            final_ply = len(opening._line) - 1
            if ply >= final_ply:
                preview_title.setText(f"Final position · {game.metadata.get('title', 'Saved game')}")
            else:
                preview_title.setText(f"After {node.san} · {game.metadata.get('title', 'Saved game')}")

        def show_game_preview(item, *_):
            if item is None:
                return
            game_id = item.data(Qt.ItemDataRole.UserRole)
            try:
                game = preview_cache.get(game_id)
                if game is None:
                    game = preview_cache[game_id] = self.store.load(game_id)
            except StorageError as exc:
                preview_title.setText("Cannot preview this game")
                opening.setText(str(exc))
                return
            preview_game["game"] = game
            opening.set_game(game, self._appearance_config().get("light", False))
            show_game_position(opening.selected_ply)

        listing.itemEntered.connect(show_game_preview)
        listing.currentItemChanged.connect(show_game_preview)
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
            self._analysis_enabled = bool(self.config.get("reanalyze_on_navigation", False)) and self.analysis_mode
            self._review = restore_job(self.game)
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
        if self._review:
            if not self._review["paused"]:
                self._pause_review()
            return
        self._analysis_enabled = False
        self._stop_engine()

    def _start_analysis(self):
        self._cancel_review()
        self._stop_engine()
        self._workspace(True)
        self._clear_saved_analysis([self.game.current_node])
        self._analysis_enabled = True
        self.tabs.setCurrentIndex(1)
        self._save()
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
        was_auto_playing = self._auto_play_active
        self._auto_play_active = False
        self._auto_play_paused = False
        if self._review and not self._review.get("paused"):
            self._cancel_review()
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
        if was_auto_playing:
            self._resume_maia_after_auto_play()

    def _suspend_maia_for_auto_play(self):
        if self._maia_suspended_for_auto_play or not hasattr(self, "maia"):
            return
        self._maia_suspended_for_auto_play = True
        self.maia.stop()
        self.maia.policies = {}
        self.maia.outcomes = {}
        self._maia_changed({})

    def _resume_maia_after_auto_play(self):
        if not self._maia_suspended_for_auto_play:
            return
        self._maia_suspended_for_auto_play = False
        if not self._closing:
            self._request_maia()

    def _interrupt_automation(self):
        """Only deliberate board/history/PV input calls this, never menu scrolling."""
        if not self._auto_play_active and not self._review:
            return
        self._analysis_enabled = False
        self._stop_engine()
        self.board_view.interactive = bool(self.analysis_mode and not self.game.outcome)
        self.statusBar().showMessage("Automation stopped · manual control")

    def _escape(self):
        self._interrupt_automation()
        self._clear_move_preview()
        self.board_view.clear_annotations()

    def _schedule_engine(self):
        if (
            self._closing
            or not hasattr(self, "engine")
            or self.engine.busy
            or self.paused
            or (self._auto_play_active and self._auto_play_paused)
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
        infinite = kind == "analysis" and self.config.get("analysis_kind") in ("infinite", "explore")
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
                ensure_pv_length=kind == "analysis" and not self._auto_play_active,
                infinite=infinite,
                arguments=profile.get("arguments", []),
                multipv=count,
                searchmoves=self.config.get("searchmoves", []),
                tablebase_path=self.config.get("syzygy_path", ""),
                nodes_only=self._auto_play_active or (kind == "analysis" and self.config.get("analysis_kind") == "nodes"),
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
            "options": dict(options),
            "multipv": count,
        }
        self.engine_state.setText(self._active_engine_name() + " · connecting / analyzing")
        self.quick_analysis_button.setText("Pause auto-play" if self._auto_play_active else "Stop" if kind == "analysis" else "Analyze")
        self.board_view.interactive = kind == "analysis"

    def _clear_analysis_output(self):
        if self._last_info is not None:
            self.telemetry.setMinimumHeight(max(self.telemetry.minimumHeight(), self.telemetry.height()))
            self._telemetry_reserved_width = self.telemetry.width()
        self.board_view.best_move = None
        self.board_view.set_recommendations([])
        self.candidates.set_multipv(self._effective_multipv())
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
        if kind == "snapshot":
            self._save_snapshot(generation, payload)
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
                if self._auto_play_active:
                    self._auto_play_paused = True
                    self.quick_analysis_button.setText("Resume auto-play")
                else:
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
        self._update_graph()
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
                self._resume_maia_after_auto_play()
            else:
                delay = self.config.get("watch_delay_ms", 500) if self._auto_play_active or self.config.get("mode") == "ai_ai" else 80
                QTimer.singleShot(delay, self, self._schedule_engine)
        self._save(defer=True)

    def _show_info(self, info, job, *, store=True):
        if not info:
            return
        if "score_type" in info and info.get("multipv", 1) > job.get("multipv", self._effective_multipv()):
            return
        self.candidates.set_multipv(self._effective_multipv())
        if "score_type" in info:
            if store:
                rank = info.get("multipv", 1)
                job.setdefault("lines", {})[rank] = info.copy()
                if info.get("bound", "exact") == "exact":
                    job.setdefault("exact_lines", {})[rank] = info.copy()
            self._candidate_identity = self._position_identity()
            self._sync_candidate_database()
            self.candidates.update_line(
                info, job["turn"], self._appearance_config().get("light", False), self.config.get("details", False)
            )
            if info.get("multipv", 1) != 1:
                if store and 1 in job.get("lines", {}):
                    self._store_analysis(self.game, self.game.current_node, job["lines"][1], job["turn"], job)
                return
        self._last_info = info.copy()
        self._last_info_turn = job["turn"]
        if store and "score_type" in info:
            self._store_analysis(self.game, self.game.current_node, info, job["turn"], job)
            self._queue_secondary_analysis()
        white_score = info["score"] * job["turn"]
        self.eval_label.setText(
            score_label(info, job["turn"]) if "score_type" in info else score_text(white_score)
        )
        self.eval_bar.set_score(white_score)
        evaluation = (score_label(info, job["turn"]) if "score_type" in info
                      else score_text(white_score))
        self._render_telemetry(info, job["turn"], evaluation)
        identity = self._position_identity()
        texts = tuple(info.get("pv", [])[:128])
        if identity != self._pv_identity or texts != getattr(self, "_pv_texts", None):
            position = self.game.board.copy()
            self._pv_root = self.game.board.copy(history=False)
            self._pv_identity = identity
            self._pv_texts = texts
            self._pv_moves = []
            for text in texts:
                try:
                    move = position.parse_uci(text)
                    self._pv_moves.append(move)
                    position.push(move)
                except ValueError:
                    break
        first = self._pv_moves[0] if self._pv_moves else None
        if self.board_view.best_move != first:
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
        if self.engine.busy and self.config.get("analysis_snapshots", False):
            self.engine._flush_snapshot()
        self._closing = True
        self._secondary_timer.stop()
        QApplication.instance().removeEventFilter(self)
        setup = getattr(self, "_gpu_setup", None)
        if setup is not None:
            process = setup.findChild(QProcess)
            if process is not None and process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
                process.waitForFinished(1000)
        inventory = getattr(self, "_gpu_inventory_process", None)
        if inventory is not None and inventory.state() != QProcess.ProcessState.NotRunning:
            inventory.kill()
            inventory.waitForFinished(1000)
        self._clear_move_preview()
        self._explorer_active = False
        self.timer.stop()
        self.autosave_timer.stop()
        self.archive_timer.stop()
        self.explorer.close_client()
        self.opening_coverage.close()
        self.engine.close()
        self.maia.stop()
        self.game.pause_clock()
        self._save(force=True)
        if self._dock_workspace is not None:
            self._dock_workspace.hide_floating_panels()
        if self.store:
            self.store.close()
        event.accept()
