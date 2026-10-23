"""Compact Maia controls and the optional legal-move view inside analysis."""
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtWidgets import QStylePainter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QGridLayout, QSizePolicy, QScrollArea,
)
from ..maia import RATINGS, percentage


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


class MaiaControls(QWidget):
    rating_changed = Signal(int)
    enabled_changed = Signal(bool)
    move_selected = Signal(str)
    settings_requested = Signal()

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
        self.rating = QComboBox()
        for rating in RATINGS:
            self.rating.addItem(f"{rating} Elo", rating)
        self.rating.setCurrentIndex(RATINGS.index(1800))
        self.rating.setToolTip("Lichess blitz rating; opponent uses the same rating.\n400–3000 are model inputs, not guaranteed accuracy at the extremes.")
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
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Move", "Maia probability"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setMinimumHeight(120)
        self.table.setMaximumHeight(190)
        self.table.hide()
        self.table.cellClicked.connect(self._select)
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

    def set_policy(self, policy, board):
        self.table.setRowCount(len(policy))
        for row, (uci, probability) in enumerate(sorted(policy.items(), key=lambda pair: -pair[1])):
            try:
                from ..core.notation import san
                text = san(board, board.parse_uci(uci))
            except ValueError:
                continue
            move = QTableWidgetItem(text)
            move.setData(Qt.ItemDataRole.UserRole, uci)
            self.table.setItem(row, 0, move)
            self.table.setItem(row, 1, QTableWidgetItem(percentage(probability)))
