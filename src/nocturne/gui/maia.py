"""Compact Maia controls and the optional legal-move view inside analysis."""
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from ..maia import RATINGS, percentage


class MaiaControls(QWidget):
    rating_changed = Signal(int)
    enabled_changed = Signal(bool)
    move_selected = Signal(str)
    settings_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(3)
        top = QHBoxLayout()
        settings = QPushButton("SF settings")
        settings.clicked.connect(self.settings_requested)
        top.addWidget(settings)
        self.enabled = QCheckBox("Maia-3 79M")
        self.enabled.setChecked(True)
        self.enabled.toggled.connect(self.enabled_changed)
        top.addWidget(self.enabled)
        self.rating = QComboBox()
        for rating in RATINGS:
            self.rating.addItem(str(rating), rating)
        self.rating.setCurrentIndex(RATINGS.index(1800))
        self.rating.setToolTip("Lichess blitz rating; opponent uses the same rating.\n400–3000 are model inputs, not guaranteed accuracy at the extremes.")
        self.rating.currentIndexChanged.connect(lambda: self.rating_changed.emit(self.rating.currentData()))
        top.addWidget(self.rating)
        top.addStretch()
        layout.addLayout(top)
        self.status = QLabel("Maia-3 79M · local human-move predictions")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.all_moves = QCheckBox("Inspect all Maia-ranked legal moves")
        self.all_moves.setToolTip("Show the full legal policy here, including moves outside Stockfish MultiPV.")
        layout.addWidget(self.all_moves)
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
