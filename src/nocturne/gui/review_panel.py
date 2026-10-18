"""Opt-in game review with honest coverage and persistent per-move evidence."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDoubleSpinBox, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QTextBrowser, QVBoxLayout, QWidget,
)

from ..review import ERRORS, LABELS, rows, summarize
from ..engine.uci_types import score_label


class ReviewPanel(QWidget):
    run_requested = Signal(float)
    pause_requested = Signal()
    cancel_requested = Signal()
    move_requested = Signal(int)
    before_requested = Signal(int)
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = []
        self.game = None
        self._signature = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 4)
        heading = QHBoxLayout()
        title = QLabel("Game Review")
        title.setObjectName("brand")
        heading.addWidget(title, 1)
        back = QPushButton("Back to analysis")
        back.clicked.connect(self.back_requested)
        heading.addWidget(back)
        layout.addLayout(heading)
        self.status = QLabel("Review the selected line with your UCI engine.")
        self.status.setWordWrap(True)
        self.status.setObjectName("muted")
        layout.addWidget(self.status)
        controls = QHBoxLayout()
        self.seconds = QDoubleSpinBox()
        self.seconds.setRange(0.05, 600)
        self.seconds.setValue(3)
        self.seconds.setDecimals(2)
        self.seconds.setSuffix(" s / search")
        self.seconds.setAccessibleName("Game review seconds per search")
        self.run = QPushButton("Start review")
        self.run.setObjectName("primary")
        self.run.clicked.connect(lambda: self.run_requested.emit(self.seconds.value()))
        self.pause = QPushButton("Pause")
        self.pause.clicked.connect(self.pause_requested)
        self.cancel = QPushButton("Cancel")
        self.cancel.clicked.connect(self.cancel_requested)
        for widget in (self.seconds, self.run, self.pause, self.cancel):
            controls.addWidget(widget)
        layout.addLayout(controls)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        cards = QHBoxLayout()
        self.scores = {}
        for key, name in ((1, "WHITE"), (-1, "BLACK"), (None, "OVERALL")):
            card = QFrame()
            card.setObjectName("playerCard")
            inner = QVBoxLayout(card)
            caption, value, coverage = QLabel(name), QLabel("—"), QLabel("Not reviewed")
            caption.setObjectName("eyebrow")
            value.setObjectName("score")
            coverage.setObjectName("muted")
            for widget in (caption, value, coverage):
                inner.addWidget(widget)
            self.scores[key] = (value, coverage)
            cards.addWidget(card)
        layout.addLayout(cards)
        self.counts = QLabel()
        self.counts.setWordWrap(True)
        layout.addWidget(self.counts)
        self.errors_only = QCheckBox("Mistakes and inaccuracies only")
        self.errors_only.toggled.connect(self._render_rows)
        layout.addWidget(self.errors_only)
        self.table = QTableWidget(0, 4)
        self.table.setMinimumHeight(105)
        self.table.setHorizontalHeaderLabels(["Move", "Quality", "Accuracy", "Best move"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        for column in range(4):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        self.table.cellClicked.connect(self._clicked)
        layout.addWidget(self.table, 1)
        self.detail = QTextBrowser()
        self.detail.setMaximumHeight(105)
        self.detail.setMinimumHeight(65)
        self.detail.setPlainText("Select a reviewed move to see the engine evidence.")
        layout.addWidget(self.detail)
        self.before = QPushButton("Show position before selected move")
        self.before.setEnabled(False)
        self.before.clicked.connect(self._before)
        layout.addWidget(self.before)
        note = QLabel("Estimated accuracy · arithmetic mean of reviewed moves. Uses published score curves, "
                      "not Chess.com or Lichess game scores. Equal search limits can reach different depths.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)

    def update_game(self, game, state=None, profile=None, light=False):
        self.game = game
        self.entries = rows(game)
        total = summarize(self.entries)
        active = state is not None
        self.run.setEnabled(not active and bool(self.entries))
        self.run.setText("Start review" if profile else "Choose engine…")
        self.seconds.setEnabled(not active)
        self.pause.setEnabled(active)
        self.pause.setText("Resume" if active and state["paused"] else "Pause")
        self.cancel.setEnabled(active)
        self.progress.setRange(0, max(1, total["total"]))
        self.progress.setValue(total["reviewed"])
        self.progress.setFormat(f"{total['reviewed']} / {total['total']} moves reviewed")
        if active:
            message = state.get("message", "")
            self.status.setText(message or f"{'Paused' if state['paused'] else 'Reviewing'} · "
                                f"{min(state['index'], len(state['line']) - 1)}/{len(state['line']) - 1} moves on fixed line")
        else:
            self.status.setText("Review complete · selected line" if total["total"] and total["reviewed"] == total["total"]
                                else "Partial review · accuracy is provisional" if total["reviewed"]
                                else "Select an engine, then start review of the selected line." if self.entries
                                else "Import or play some moves to review a game.")
        for color, (value, coverage) in self.scores.items():
            summary = summarize(self.entries, color)
            value.setText(f"{summary['accuracy']:.1f}%" if summary["accuracy"] is not None else "—")
            coverage.setText(f"{summary['reviewed']}/{summary['total']} reviewed" +
                             (" · partial" if summary["reviewed"] < summary["total"] else ""))
        self.counts.setText("  ·  ".join(f"{label} {total['counts'][label]}" for label in LABELS))
        signature = (game.id, game.current_node, light, tuple((e["node"], e["san"], repr(e["record"])) for e in self.entries))
        if self._signature != signature:
            self._signature = signature
            self._light = light
            self._render_rows()

    def _render_rows(self):
        entries = [e for e in self.entries if not self.errors_only.isChecked()
                   or e["record"] and e["record"]["label"] in ERRORS]
        self.table.clearSelection()
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            record = entry["record"]
            move = f"{entry['number']}{'.' if entry['color'] == 1 else '…'} {entry['san']}"
            values = [move, record["label"] if record else "Not reviewed",
                      f"{record['accuracy']:.1f}%" if record else "—", record["best_san"] if record else "—"]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, entry["node"])
                if column == 1 and record:
                    colors = (["#397b58", "#397b58", "#637469", "#91733c", "#ae613d", "#ad4848"]
                              if getattr(self, "_light", False) else
                              ["#95c7a6", "#95c7a6", "#a6b7aa", "#cfb879", "#d59772", "#d98a88"])
                    item.setForeground(QColor(colors[LABELS.index(record["label"])]))
                self.table.setItem(row, column, item)
            if self.game and self.game.current_node == entry["node"]:
                self.table.selectRow(row)
        self._show_detail()

    def _clicked(self, row, column):
        item = self.table.item(row, 0)
        if item:
            self.move_requested.emit(item.data(Qt.ItemDataRole.UserRole))
            self._show_detail()

    def _show_detail(self):
        entry = next((e for e in self.entries if self.game and e["node"] == self.game.current_node), None)
        record = entry["record"] if entry else None
        self.before.setEnabled(entry is not None)
        if not record:
            self.detail.setPlainText("Select a reviewed move to see the engine evidence.")
            return
        best, played = record["best"], record["played"]
        cp = f" · {record['loss_cp'] / 100:.2f} pawns" if "loss_cp" in record else " · mate distances are not graded"
        self.detail.setPlainText(
            f"{entry['san']}: {record['label']} · {record['accuracy']:.1f}%\n"
            f"Best {record['best_san']} {score_label(best)} (depth {best.get('depth', '?')}); "
            f"played {score_label(played)} (depth {played.get('depth', '?')}). Scores favor the mover.\n"
            f"Outcome-proxy loss {record['loss_percent']:.2f} percentage points{cp}.\n"
            f"Engine: {best.get('engine', record['context'].get('engine', 'UCI'))}")

    def _before(self):
        if self.game and self.game.current_node:
            self.before_requested.emit(self.game.nodes[self.game.current_node].parent)
