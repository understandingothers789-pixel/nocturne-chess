"""Compact Maia controls and the optional legal-move view inside analysis."""
from PySide6.QtCore import Signal, Qt, QSize, QEvent
from PySide6.QtWidgets import QStylePainter, QToolTip
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QGridLayout, QSizePolicy, QScrollArea,
)
from ..maia import RATINGS, percentage
from ..engine.uci_types import score_label
from .wheel import WheelSteps


class StatusLabel(QLabel):
    """Keep live status updates from shifting the candidate rows below."""

    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)

    def paintEvent(self, event):
        painter = QStylePainter(self)
        text = self.fontMetrics().elidedText(
            self.text(), Qt.TextElideMode.ElideRight, self.contentsRect().width()
        )
        painter.drawItemText(self.contentsRect(), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                             self.palette(), self.isEnabled(), text, self.foregroundRole())


class RatingDragBox(QComboBox):
    """Click for the rating list, or scrub horizontally in 200 Elo steps."""

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().x()
            self._drag_rating = self.currentData()
            self._dragging = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and hasattr(self, "_drag_origin"):
            delta = event.globalPosition().x() - self._drag_origin
            if abs(delta) >= 12:
                self._dragging = True
            if self._dragging:
                rating = max(min(RATINGS), min(max(RATINGS), self._drag_rating + int(delta / 24) * 200))
                index = self.findData(rating)
                if index >= 0:
                    self.setCurrentIndex(index)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and hasattr(self, "_drag_origin"):
            if not self._dragging:
                self.showPopup()
            del self._drag_origin
            event.accept()
            return
        super().mouseReleaseEvent(event)


class MaiaControls(QWidget):
    rating_changed = Signal(int)
    enabled_changed = Signal(bool)
    move_selected = Signal(str)
    settings_requested = Signal()
    preview_requested = Signal(object, int, str)
    preview_ended = Signal()
    pointer_moved = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("analysisTools")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(3)
        top = QGridLayout()
        top.setSpacing(6)
        self.tools_layout = top
        self._narrow = None
        settings = QPushButton("Stockfish settings")
        settings.clicked.connect(self.settings_requested)
        self.settings_button = settings
        top.addWidget(settings, 0, 0)
        self.enabled = QCheckBox("Maia-3 79M")
        self.enabled.setChecked(True)
        self.enabled.toggled.connect(self.enabled_changed)
        top.addWidget(self.enabled, 0, 1)
        self.rating = RatingDragBox()
        for rating in RATINGS:
            self.rating.addItem(f"{rating} Elo", rating)
        self.rating.setCurrentIndex(RATINGS.index(1800))
        self.rating.setToolTip("Drag left/right in 200 Elo steps, or click to choose a rating.\nLichess blitz rating; opponent uses the same rating.\n400–3000 are model inputs, not guaranteed accuracy at the extremes.")
        self.rating.currentIndexChanged.connect(lambda: self.rating_changed.emit(self.rating.currentData()))
        top.addWidget(self.rating, 0, 2)
        top.setColumnStretch(3, 1)
        layout.addLayout(top)
        self.status = StatusLabel()
        self.status.setText("Maia-3 79M · local human-move predictions")
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.status.setObjectName("sectionNote")
        self.all_moves = QCheckBox("All human moves")
        self.all_moves.setToolTip("Show the full legal policy here, including moves outside Stockfish MultiPV.")
        secondary = QHBoxLayout()
        secondary.setSpacing(8)
        secondary.addWidget(self.status, 1)
        secondary.addWidget(self.all_moves)
        layout.addLayout(secondary)
        self.table = QTableWidget(0, 3)
        self._stockfish = {}
        self._table_fen = None
        self._hover_move = None
        self._hover_pv = []
        self._hover_ply = 1
        self._shown_preview = None
        self._wheel = WheelSteps()
        self.table.setHorizontalHeaderLabels(["Move", "Stockfish eval", "Maia probability"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setMinimumHeight(120)
        self.table.setMaximumHeight(190)
        self.table.hide()
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)
        self.table.viewport().installEventFilter(self)
        self.table.cellClicked.connect(self._select)
        self.table.verticalScrollBar().valueChanged.connect(lambda value: self._end_hover())
        self.all_moves.toggled.connect(self.table.setVisible)
        layout.addWidget(self.table)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        available = self.width()
        ancestor = self.parentWidget()
        while ancestor is not None:
            if isinstance(ancestor, QScrollArea):
                available = ancestor.viewport().width()
                break
            ancestor = ancestor.parentWidget()
        narrow = available < 390
        if narrow == self._narrow:
            return
        self._narrow = narrow
        layout = self.tools_layout
        while layout.count():
            layout.takeAt(0)
        for column in range(4):
            layout.setColumnStretch(column, 0)
        if narrow:
            layout.addWidget(self.enabled, 0, 0)
            layout.addWidget(self.rating, 0, 1)
            layout.addWidget(self.settings_button, 1, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
            layout.setColumnStretch(1, 1)
        else:
            layout.addWidget(self.settings_button, 0, 0)
            layout.addWidget(self.enabled, 0, 1)
            layout.addWidget(self.rating, 0, 2)
            layout.setColumnStretch(3, 1)

    def _select(self, row, column):
        item = self.table.item(row, 0)
        if item:
            self.move_selected.emit(item.data(Qt.ItemDataRole.UserRole))

    def _end_hover(self):
        self._hover_move = None
        self._hover_pv = []
        self._hover_ply = 1
        self._shown_preview = None
        self._wheel.reset()
        self.preview_ended.emit()
        QToolTip.hideText()

    def eventFilter(self, watched, event):
        if watched is self.table.viewport():
            if event.type() in (QEvent.Type.Leave, QEvent.Type.Hide):
                self._end_hover()
            elif event.type() in (QEvent.Type.MouseMove, QEvent.Type.Wheel):
                index = self.table.indexAt(event.position().toPoint())
                item = self.table.item(index.row(), 0) if index.isValid() and index.column() == 0 else None
                if item is None:
                    self._end_hover()
                else:
                    uci = item.data(Qt.ItemDataRole.UserRole)
                    if uci != self._hover_move:
                        self._end_hover()
                        self._hover_move = uci
                        self._hover_pv = list(self._stockfish.get(uci, {}).get("pv", []))
                    if event.type() == QEvent.Type.Wheel:
                        steps = self._wheel.consume(event)
                        if steps is not None:
                            self._hover_ply = max(0, min(len(self._hover_pv), self._hover_ply + steps))
                    if self._hover_pv:
                        signature = (uci, tuple(self._hover_pv), self._hover_ply)
                        if signature != self._shown_preview:
                            self.preview_requested.emit(self._hover_pv, self._hover_ply, item.text())
                            self._shown_preview = signature
                        self.pointer_moved.emit(event.globalPosition().toPoint())
                    else:
                        QToolTip.showText(event.globalPosition().toPoint(),
                                          "No Stockfish variation available for this move.", self.table)
                    if event.type() == QEvent.Type.Wheel:
                        event.accept()
                        return True
        return super().eventFilter(watched, event)

    def set_stockfish(self, lines, turn):
        self._stockfish = {}
        for line in lines.values():
            if line.get("pv"):
                uci = line["pv"][0]
                previous = self._stockfish.get(uci, {})
                if (line.get("depth", 0), line.get("nodes", 0)) >= (previous.get("depth", 0), previous.get("nodes", 0)):
                    self._stockfish[uci] = line
        if self._hover_move and not self._hover_pv:
            self._hover_pv = list(self._stockfish.get(self._hover_move, {}).get("pv", []))
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            line = self._stockfish.get(item.data(Qt.ItemDataRole.UserRole)) if item else None
            has_score = line and line.get("score_type") in ("cp", "mate") and isinstance(line.get("score_value"), (int, float))
            score = QTableWidgetItem(score_label(line, turn) if has_score else "—")
            score.setToolTip("Stockfish evaluation · White's perspective" if line else "No Stockfish analysis for this move")
            self.table.setItem(row, 1, score)

    def set_policy(self, policy, board):
        if board.fen() != self._table_fen:
            self._end_hover()
            self._stockfish = {}
            self._table_fen = board.fen()
        ordered = sorted(policy.items(), key=lambda pair: -pair[1])
        old_order = [self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                     for row in range(self.table.rowCount()) if self.table.item(row, 0)]
        if old_order != [uci for uci, _ in ordered]:
            self._end_hover()
        self.table.setRowCount(len(policy))
        for row, (uci, probability) in enumerate(ordered):
            try:
                from ..core.notation import san
                text = san(board, board.parse_uci(uci))
            except ValueError:
                continue
            move = QTableWidgetItem(text)
            move.setData(Qt.ItemDataRole.UserRole, uci)
            self.table.setItem(row, 0, move)
            self.table.setItem(row, 2, QTableWidgetItem(percentage(probability)))
