"""Compact opening statistics, separate from engine ranking and evaluation."""

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QSizePolicy, QStyledItemDelegate, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..explorer import ExplorerCache, ExplorerQuery, chessdb_score, tablebase_outcome
from .explorer_client import ExplorerClient
from .explorer_dialogs import ExplorerGamesDialog
from .widgets import ElidedLabel


class ResultsDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index):
        counts = index.data(Qt.ItemDataRole.UserRole)
        if not counts or not sum(counts):
            super().paint(painter, option, index)
            return
        painter.save()
        rect = QRectF(option.rect.adjusted(3, 5, -3, -5))
        offset, total = rect.left(), sum(counts)
        for count, bg, fg in zip(counts, ("#eeeeec", "#858585", "#333333"), ("#262626", "#ffffff", "#f2f2f0")):
            width = rect.width() * count / total
            part = QRectF(offset, rect.top(), width, rect.height())
            painter.fillRect(part, QColor(bg))
            if width > 33:
                painter.setPen(QColor(fg))
                painter.drawText(part, Qt.AlignmentFlag.AlignCenter, f"{100 * count / total:.0f}%")
            offset += width
        painter.restore()


class OpeningExplorer(QWidget):
    statistics_changed = Signal()
    compact_changed = Signal(bool, int)
    move_selected = Signal(object, str)
    move_hovered = Signal(object, str)
    preview_ended = Signal()
    close_requested = Signal()
    filters_requested = Signal()
    game_import_requested = Signal(object)

    def __init__(self, cache_path, parent=None):
        super().__init__(parent)
        self.client = ExplorerClient(ExplorerCache(cache_path), self)
        self.client.result.connect(self._result)
        self.client.status.connect(self._status)
        self.client.unavailable.connect(self._fallback_to_opening)
        self.query = None
        self._opening_query = None
        self._tablebase_query = None
        self._failed_tablebase_key = None
        self.identity = None
        self.rows = []
        self.statistics = None
        self.statistics_origin = ""
        self.statistics_status = ""
        self._hover = None
        self._compact_empty = False
        self.setMinimumHeight(170)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(3)
        header = QHBoxLayout()
        self.title = ElidedLabel()
        self.title.setText("Database explorer")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setMinimumWidth(0)
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        header.addWidget(self.title, 1)
        self.filters_button = QPushButton("Filters")
        self.filters_button.setToolTip("Filter opening statistics by month and, for Lichess players, rating band.")
        self.filters_button.clicked.connect(self.filters_requested)
        self.games_button = QPushButton("Games")
        self.games_button.setToolTip("Browse games that reached this position with the current filters.")
        self.games_button.clicked.connect(self._show_games)
        for button in (self.filters_button, self.games_button):
            button.hide()
            header.addWidget(button)
        refresh = QPushButton("↻")
        refresh.setAccessibleName("Refresh database explorer")
        refresh.setToolTip("Fetch fresh statistics for this position. Saved results remain available while loading.")
        refresh.setFixedWidth(36)
        refresh.clicked.connect(self.refresh)
        close = QPushButton("×")
        close.setAccessibleName("Close database explorer")
        close.setToolTip("Hide the opening explorer. Reopen it from the Database menu.")
        close.setFixedWidth(36)
        close.clicked.connect(self.close_requested)
        header.addWidget(refresh)
        header.addWidget(close)
        layout.addLayout(header)
        self.summary = QLabel("Database → Masters or Lichess players")
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Move", "Games", "White / Draw / Black"])
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setMinimumSectionSize(24)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setItemDelegateForColumn(2, ResultsDelegate(self.table))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setToolTip("Click a move or select a row and press Enter to play it. Hover over a move to preview it.")
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)
        self.table.viewport().installEventFilter(self)
        self.table.installEventFilter(self)
        self.table.setAccessibleName("Opening database moves")
        self.table.cellClicked.connect(self._click)
        self.table.cellEntered.connect(self._preview)
        layout.addWidget(self.table, 1)
        self.status_label = ElidedLabel()
        self.status_label.setText("Online when enabled · service data")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.status_label.setObjectName("muted")
        layout.addWidget(self.status_label)

    def _clear_statistics(self):
        self.statistics = None
        self.statistics_origin = ""
        self.statistics_status = ""
        supported = bool(self.query and self.query.source in ("masters", "lichess"))
        self.filters_button.setVisible(supported)
        self.games_button.setVisible(supported)
        self.games_button.setEnabled(False)
        self.statistics_changed.emit()

    def _set_compact_empty(self, empty):
        empty = bool(empty)
        if empty == self._compact_empty:
            return
        previous_height = self.height()
        self._compact_empty = empty
        self.table.setVisible(not empty)
        self.status_label.setVisible(not empty)
        self.setMinimumHeight(0 if empty else 170)
        self.setMaximumHeight(88 if empty else 16777215)
        self.compact_changed.emit(empty, previous_height)

    def set_position(self, board, identity, enabled, source="masters", speed="all", rating=0, *,
                     endgame=False, since="", until="", groups=()):
        if not enabled:
            self._set_compact_empty(False)
            self.client.cancel()
            self.query = None
            self._opening_query = self._tablebase_query = None
            self._failed_tablebase_key = None
            self.identity = None
            self._clear_statistics()
            self.rows = []
            self.table.setRowCount(0)
            self._end_preview()
            return
        self.identity = identity
        try:
            if board.chess960:
                raise ValueError("Opening explorer supports standard chess; Chess960 is unavailable")
            query = ExplorerQuery(board.fen(), source, speed, rating, since, until, groups)
        except ValueError as exc:
            self.client.cancel()
            self.query = None
            self._opening_query = self._tablebase_query = None
            self._failed_tablebase_key = None
            self._clear_statistics()
            self.rows = []
            self.table.setRowCount(0)
            self._end_preview()
            self.summary.setText(str(exc))
            self.status_label.setText("No request sent")
            return
        self._opening_query = query
        self._tablebase_query = None
        if endgame and board.native.occupied.bit_count() <= 7 and not board.native.castling_rights:
            self._tablebase_query = ExplorerQuery(board.fen(), "tablebase")
        if self._tablebase_query and self._tablebase_query.key != self._failed_tablebase_key:
            query = self._tablebase_query
        elif not self._tablebase_query:
            self._failed_tablebase_key = None
        self._load_query(query)

    def _load_query(self, query, *, force=False):
        if not force and self.query == query:
            return
        self._end_preview()
        self._set_compact_empty(False)
        self.query = query
        self._clear_statistics()
        self.rows = []
        self.table.setRowCount(0)
        self.table.setMinimumHeight(0)
        source, speed = query.source, query.speed
        if source == "tablebase":
            self.title.setText("Endgame Tablebase")
            self.summary.setText("Lichess · results for the side to move")
            self.table.setHorizontalHeaderLabels(["Move", "Outcome", "DTZ"])
            self.table.horizontalHeaderItem(2).setToolTip(
                "Distance in half-moves to a capture or pawn move, or mate, from the position after this move."
            )
        else:
            self.title.setText("ChessDB · cloud analysis" if source == "chessdb" else "Masters" if source == "masters" else
                               f"Lichess players · {speed} · {query.rating_label}")
            self.table.setHorizontalHeaderLabels(["Move", "Score · White", "Database note"] if source == "chessdb" else
                                                ["Move", "Games", "White / Draw / Black"])
            self.table.horizontalHeaderItem(2).setToolTip("")
            self.summary.setText("Cloud analysis · White's perspective" if source == "chessdb" else "Opening statistics · " + (
                "master games" if source == "masters" else f"{speed} speeds · {query.rating_label}"))
        self.table.setAccessibleName("Endgame tablebase moves" if source == "tablebase" else "Opening database moves")
        self.client.load(query, force=force)

    def _fallback_to_opening(self, key):
        if self.query and self.query.source == "tablebase" and self.query.key == key and self._opening_query:
            self._failed_tablebase_key = key
            self._load_query(self._opening_query)

    def refresh(self):
        if self._tablebase_query and self.query != self._tablebase_query:
            self._failed_tablebase_key = None
            self._load_query(self._tablebase_query, force=True)
        elif self.query:
            self.client.load(self.query, force=True)

    def _show_games(self):
        if not self.query or self.query.source not in ("masters", "lichess") or not self.statistics:
            return
        dialog = ExplorerGamesDialog(self.client, self.query, self)
        dialog.load()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.game_import_requested.emit(dialog.game)
        dialog.deleteLater()

    def _result(self, key, data, origin):
        if not self.query or self.query.key != key:
            return
        self._end_preview()
        self.statistics = data
        self.statistics_origin = origin
        self.statistics_status = origin
        self.statistics_changed.emit()
        self.rows = data["moves"]
        self.table.setRowCount(len(self.rows))
        if self.query.source == "tablebase":
            self._set_compact_empty(not bool(self.rows))
            for i, row in enumerate(self.rows):
                distance = "—" if row["dtz"] is None else str(abs(row["dtz"]))
                values = (row["san"], tablebase_outcome(row["category"], after_move=True), distance)
                for column, value in enumerate(values):
                    self.table.setItem(i, column, QTableWidgetItem(value))
            side = "White" if self.query.fen.split()[1] == "w" else "Black"
            self.summary.setText(f"{side} to move · {tablebase_outcome(data['category'])}"
                                 + (" · moves ranked by Lichess" if self.rows else " · no legal moves"))
            self.status_label.setText(origin)
            self._reserve_rows()
            return
        if self.query.source == "chessdb":
            self._set_compact_empty(not bool(self.rows))
            for i, row in enumerate(self.rows):
                for column, value in enumerate((row["san"], chessdb_score(row["score"], self.query.fen), row["note"])):
                    self.table.setItem(i, column, QTableWidgetItem(value))
            self.summary.setText(f"{len(self.rows)} moves · service scores, White's perspective" if self.rows else {
                "unknown": "Position not yet known to ChessDB", "checkmate": "Checkmate · no moves",
                "stalemate": "Stalemate · no moves", "ok": "No scored moves available",
            }[data["status"]])
            self.status_label.setText(origin)
            self._reserve_rows()
            return
        self._set_compact_empty(not bool(self.rows))
        for i, row in enumerate(self.rows):
            self.table.setItem(i, 0, QTableWidgetItem(row["san"]))
            self.table.setItem(i, 1, QTableWidgetItem(f"{row['total']:,}"))
            values = [row[k] for k in ("white", "draws", "black")]
            item = QTableWidgetItem(" / ".join(str(n) for n in values))
            item.setData(Qt.ItemDataRole.UserRole, values)
            self.table.setItem(i, 2, item)
        opening = data.get("opening")
        name = (opening["eco"] + " · " + opening["name"] + " · ") if opening else ""
        message = name + f"{data['total']:,} games · most played first" if data["total"] else "No games found for this position and filters"
        if self.query.date_label:
            message += f" · {self.query.date_label}"
        self.summary.setText(message)
        self.games_button.setEnabled(bool(data["total"]))
        self.status_label.setText(origin)

        self._reserve_rows()

    def _reserve_rows(self):
        self.layout().activate()
        visible_rows = min(4, self.table.rowCount())
        if visible_rows:
            table_height = self.table.horizontalHeader().height() + sum(
                self.table.rowHeight(row) for row in range(visible_rows)) + 2 * self.table.frameWidth()
            self.table.setMinimumHeight(table_height + 3)
            self._fit_summary_height()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.oldSize().width() != event.size().width():
            self._fit_summary_height()

    def _fit_summary_height(self):
        if not self._compact_empty:
            height = max(170, self.layout().minimumHeightForWidth(self.width()))
            if height != self.minimumHeight():
                self.setMinimumHeight(height)

    def _status(self, key, message):
        if self.query and self.query.key == key:
            if self.statistics_status != message:
                self.statistics_status = message
                self.statistics_changed.emit()
            self.status_label.setText(message)

    def _click(self, row, column):
        if self.query and 0 <= row < len(self.rows):
            identity, move = self.identity, self.rows[row]["uci"]
            self._end_preview()
            self.move_selected.emit(identity, move)

    def _preview(self, row, column):
        if self.query and 0 <= row < len(self.rows) and row != self._hover:
            self._hover = row
            self.move_hovered.emit(self.identity, self.rows[row]["uci"])

    def _end_preview(self):
        self._hover = None
        self.preview_ended.emit()

    def eventFilter(self, watched, event):
        if (watched is self.table and event.type() == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)):
            self._click(self.table.currentRow(), self.table.currentColumn())
            return True
        if watched is self.table.viewport():
            if event.type() == QEvent.Type.Leave or (event.type() == QEvent.Type.MouseMove and not self.table.indexAt(event.position().toPoint()).isValid()):
                self._end_preview()
        return super().eventFilter(watched, event)

    def close_client(self):
        self.client.close()
