"""Interactive engine candidate rows. Only actual, legally validated PV data is shown."""

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QLabel, QMenu, QVBoxLayout, QWidget, QLayout
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
        self.layout.setSpacing(0)
        self.layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.primary = primary
        self.primary.move_clicked.connect(lambda ply: self.navigate.emit(1, ply))
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
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(0, 8, 0, 12)
            layout.setSpacing(2)
            header = QLabel()
            header.setWordWrap(True)
            layout.addWidget(header)
            moves = self.primary if rank == 1 else MoveText(auto_fit=True)
            layout.addWidget(moves)
            moves.show()
            if rank != 1:
                moves.move_hovered.connect(lambda ply, r=rank: self.preview.emit(r, ply))
                moves.preview_ended.connect(self.preview_end)
                moves.move_clicked.connect(lambda ply, r=rank: self.navigate.emit(r, ply))
            for widget in (frame, header, moves):
                widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                widget.customContextMenuRequested.connect(
                    lambda point, r=rank, w=widget: self._menu(r, w.mapToGlobal(point))
                )
            self.rows[rank] = (frame, header, moves)
            self.layout.addWidget(frame)
        frame, header, moves = self.rows[rank]
        wdl = info.get("wdl")
        if wdl and turn < 0:
            wdl = wdl[::-1]
        extra = f" · W/D/L {wdl[0] / 10:.1f}/{wdl[1] / 10:.1f}/{wdl[2] / 10:.1f}% White" if wdl else ""
        header.setText(
            ("★ " if rank in self.pinned else "")
            + f"#{rank}   {score_label(info, turn)}   d{info['depth']}/{info['seldepth']}"
            + (f" · {info['nodes']:,} nodes" if detailed else "")
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
            header.setText(("★ " + header.text()) if rank in self.pinned else header.text().removeprefix("★ "))
        else:
            self.action.emit(rank, action)

    def _menu(self, rank, position):
        menu = QMenu(self)
        for title, action in (
            ("Insert line", "insert"),
            ("Unpin line" if rank in self.pinned else "Pin line", "pin"),
            ("Copy SAN", "san"), ("Copy UCI", "uci"),
            ("Analyze only this move", "focus"),
        ):
            item = menu.addAction(title)
            item.setData(action)
        chosen = menu.exec(position)
        action = chosen.data() if chosen else None
        menu.deleteLater()
        if action:
            self._action(rank, action)
