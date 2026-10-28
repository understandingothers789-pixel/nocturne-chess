"""Compact opening statistics, separate from engine ranking and evaluation."""

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QStyledItemDelegate, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..explorer import ExplorerCache, ExplorerQuery, chessdb_score
from .explorer_client import ExplorerClient


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

    def __init__(self, cache_path, parent=None):
        super().__init__(parent)
        self.client = ExplorerClient(ExplorerCache(cache_path), self)
        self.client.result.connect(self._result)
        self.client.status.connect(self._status)
        self.query = None
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
        self.title = QLabel("Database explorer")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        header.addWidget(self.title, 1)
        refresh = QPushButton("↻")
        refresh.setAccessibleName("Refresh database explorer")
        refresh.setFixedWidth(36)
        refresh.clicked.connect(self.refresh)
        close = QPushButton("×")
        close.setAccessibleName("Close database explorer")
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
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setItemDelegateForColumn(2, ResultsDelegate(self.table))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)
        self.table.viewport().installEventFilter(self)
        self.table.cellClicked.connect(self._click)
        self.table.cellEntered.connect(self._preview)
        layout.addWidget(self.table, 1)
        self.status_label = QLabel("Online when enabled · service data")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("muted")
        layout.addWidget(self.status_label)

    def _clear_statistics(self):
        self.statistics = None
        self.statistics_origin = ""
        self.statistics_status = ""
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

    def set_position(self, board, identity, enabled, source="masters", speed="all", rating=0):
        if not enabled:
            self._set_compact_empty(False)
            self.client.cancel()
            self.query = None
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
            query = ExplorerQuery(board.fen(), source, speed, rating)
        except ValueError as exc:
            self.client.cancel()
            self.query = None
            self._clear_statistics()
            self.rows = []
            self.table.setRowCount(0)
            self._end_preview()
            self.summary.setText(str(exc))
            self.status_label.setText("No request sent")
            return
        if self.query and self.query.key == query.key:
            return
        self._end_preview()
        self._set_compact_empty(False)
        self.query = query
        self._clear_statistics()
        self.rows = []
        self.table.setRowCount(0)
        self.title.setText("ChessDB · cloud analysis" if source == "chessdb" else "Masters" if source == "masters" else
                           f"Lichess players · {speed} · " + (f"{rating}+" if rating else "all ratings"))
        self.table.setHorizontalHeaderLabels(["Move", "Score · White", "Database note"] if source == "chessdb" else
                                            ["Move", "Games", "White / Draw / Black"])
        self.summary.setText("Cloud analysis · White's perspective" if source == "chessdb" else "Opening statistics · " + (
            "master games" if source == "masters" else f"{speed} speeds · " + (f"{rating}+" if rating else "all ratings")))
        self.client.load(query)

    def refresh(self):
        if self.query:
            self.client.load(self.query, force=True)

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
        self.summary.setText(name + f"{data['total']:,} games · most played first" if data["total"] else "No games found for this position and filters")
        self.status_label.setText(origin)

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
        if watched is self.table.viewport():
            if event.type() == QEvent.Type.Leave or (event.type() == QEvent.Type.MouseMove and not self.table.indexAt(event.position().toPoint()).isValid()):
                self._end_preview()
        return super().eventFilter(watched, event)

    def close_client(self):
        self.client.close()
