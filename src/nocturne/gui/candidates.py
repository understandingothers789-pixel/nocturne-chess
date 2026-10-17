"""Interactive engine candidate rows. Only actual, legally validated PV data is shown."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget, QLayout
from ..engine.uci_types import score_label
from .moves import MoveText


class CandidatePanel(QWidget):
    preview = Signal(int, int)
    preview_end = Signal()
    navigate = Signal(int, int)
    action = Signal(int, str)

    def __init__(self, primary, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.primary = primary
        self.rows = {}
        self.lines = {}
        self.pinned = set()
        self.turn = 1

    def clear(self):
        for rank, widgets in self.rows.items():
            if rank == 1:
                self.primary.setParent(self)
            widgets[0].deleteLater()
        self.rows = {}
        self.lines = {}
        self.pinned.clear()

    def update_line(self, info, turn, light=False, detailed=False):
        rank = info.get("multipv", 1)
        if rank in self.pinned:
            return
        self.lines[rank] = info.copy()
        self.turn = turn
        if rank not in self.rows:
            frame = QWidget()
            frame.setMinimumHeight(165 if detailed else 115)
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(0, 4, 0, 8)
            header = QLabel()
            header.setWordWrap(True)
            layout.addWidget(header)
            moves = self.primary if rank == 1 else MoveText()
            moves.setFixedHeight(70 if detailed else 40)
            layout.addWidget(moves)
            if rank != 1:
                moves.move_hovered.connect(lambda ply, r=rank: self.preview.emit(r, ply))
                moves.preview_ended.connect(self.preview_end)
            moves.move_clicked.connect(lambda ply, r=rank: self.navigate.emit(r, ply))
            row = QHBoxLayout()
            row.setSpacing(3)
            for title, action in [
                ("Insert", "insert"),
                ("Pin", "pin"),
                ("SAN", "san"),
                ("UCI", "uci"),
                ("Focus", "focus"),
            ]:
                b = QPushButton(title)
                b.setObjectName("quiet")
                b.clicked.connect(lambda checked=False, r=rank, a=action: self._action(r, a))
                row.addWidget(b)
            layout.addLayout(row)
            self.rows[rank] = (frame, header, moves)
            self.layout.addWidget(frame)
        frame, header, moves = self.rows[rank]
        wdl = info.get("wdl")
        if wdl and turn < 0:
            wdl = wdl[::-1]
        extra = f" · W/D/L {wdl[0] / 10:.1f}/{wdl[1] / 10:.1f}/{wdl[2] / 10:.1f}% White" if wdl else ""
        header.setText(
            f"#{rank}   {score_label(info, turn)}   d{info['depth']}/{info['seldepth']} · {info['nodes']:,} nodes"
            + extra
        )
        header.setAccessibleName(f"Candidate {rank} evaluation and search metrics")
        moves.set_moves([(text, i + 1) for i, text in enumerate(info["san"])], light=light)

    def _action(self, rank, action):
        if action == "pin":
            if rank in self.pinned:
                self.pinned.remove(rank)
            else:
                self.pinned.add(rank)
            frame, header, moves = self.rows[rank]
            buttons = frame.findChildren(QPushButton)
            buttons[1].setText("Unpin" if rank in self.pinned else "Pin")
        else:
            self.action.emit(rank, action)
