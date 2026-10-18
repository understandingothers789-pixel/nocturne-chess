"""Interactive engine candidate rows. Only actual, legally validated PV data is shown."""

from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtWidgets import QLabel, QMenu, QVBoxLayout, QWidget, QLayout, QSizePolicy
from ..engine.uci_types import score_label
from .moves import MoveText
from .theme import palette


class CandidatePanel(QWidget):
    preview = Signal(int, int)
    preview_end = Signal()
    navigate = Signal(int, int)
    action = Signal(int, str)
    changed = Signal()

    def __init__(self, primary, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.primary = primary
        self.primary.reserve_lines(3)
        self.rows = {}
        self.light = False
        self.lines = {}
        self.pinned = set()
        self.turn = 1
        self.slot_count = 0
        self.hovered = None
        self.pending = {}
        self._clearing = False
        self._revision = 0

    def clear(self):
        self._clearing = True
        self._revision += 1
        self.hovered = None
        self.pending.clear()
        self.preview_end.emit()
        for rank, widgets in self.rows.items():
            if rank == 1:
                self.primary.setParent(self)
            widgets[0].deleteLater()
        self.rows = {}
        self.lines = {}
        self.pinned.clear()
        self.slot_count = 0
        self.primary.set_moves([])
        self._clearing = False
        self.changed.emit()

    def reserve_slots(self, count):
        count = max(1, min(32, count))
        if count < self.slot_count:
            self.clear()
        for rank in range(self.slot_count + 1, count + 1):
            self._make_row(rank)
        self.slot_count = count

    def _make_row(self, rank):
        frame = QWidget()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 8, 0, 12)
        layout.setSpacing(2)
        header = QLabel("Waiting for engine")
        header.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        header.setFixedHeight(max(22, header.fontMetrics().height() + 6))
        header.setStyleSheet(f"color: {palette(self.light)['muted']};")
        layout.addWidget(header)
        moves = self.primary if rank == 1 else MoveText(auto_fit=True, reserved_lines=3)
        moves.candidate_rank = rank
        layout.addWidget(moves)
        moves.show()
        # The primary widget survives clear/reuse, so wire it exactly once.
        if rank != 1 or not getattr(self, "_primary_connected", False):
            moves.move_hovered.connect(lambda ply, r=rank: self._hover(r, ply))
            moves.preview_ended.connect(lambda r=rank: self._end_hover(r))
            moves.move_clicked.connect(lambda ply, r=rank: self.navigate.emit(r, ply))
            if rank == 1:
                self._primary_connected = True
        for widget in (frame, header, moves):
            widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            if widget is self.primary and getattr(self, "_primary_menu_connected", False):
                continue
            widget.customContextMenuRequested.connect(
                lambda point, r=rank, w=widget: self._menu(r, w.mapToGlobal(point))
            )
            if widget is self.primary:
                self._primary_menu_connected = True
        self.rows[rank] = (frame, header, moves)
        self.layout.addWidget(frame)

    def recolor(self, light):
        if self.light == light:
            return
        self.light = light
        for _, header, _ in self.rows.values():
            header.setStyleSheet(f"color: {palette(light)['muted']};")

    def _hover(self, rank, ply):
        if rank not in self.lines:
            return
        if self.hovered is not None and self.hovered != rank:
            self._end_hover(self.hovered)
        self.hovered = rank
        self.preview.emit(rank, ply)

    def _end_hover(self, rank):
        if self._clearing or self.hovered != rank:
            return
        self.hovered = None
        self.preview_end.emit()
        if rank in self.pending:
            revision = self._revision
            QTimer.singleShot(0, lambda: self._flush(rank, revision))

    def _flush(self, rank, revision):
        if revision != self._revision or self.hovered == rank or rank not in self.rows:
            return
        pending = self.pending.pop(rank, None)
        if pending:
            self.update_line(*pending)

    def update_line(self, info, turn, light=False, detailed=False):
        rank = info.get("multipv", 1)
        if rank in self.pinned:
            return
        if type(rank) is not int or not 1 <= rank <= 32:
            return
        if self.hovered == rank:
            self.pending[rank] = (info.copy(), turn, light, detailed)
            return
        if rank > self.slot_count:
            self.reserve_slots(rank)
        self.pending.pop(rank, None)
        self.lines[rank] = info.copy()
        self.turn = turn
        self.recolor(light)
        frame, header, moves = self.rows[rank]
        wdl = info.get("wdl")
        if wdl and turn < 0:
            wdl = wdl[::-1]
        extra = f" · W/D/L {wdl[0] / 10:.1f}/{wdl[1] / 10:.1f}/{wdl[2] / 10:.1f}% White" if wdl else ""
        header.setText(
            ("★ " if rank in self.pinned else "")
            + f"{score_label(info, turn)}   d{info['depth']}/{info['seldepth']}"
            + (f" · {info['nodes']:,} nodes" if detailed else "")
            + extra
        )
        header.setAccessibleName(f"Candidate {rank} evaluation and search metrics")
        moves.candidate_turn = turn
        moves.set_moves([(text, i + 1) for i, text in enumerate(info["san"])], light=light)
        self.changed.emit()

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
        if rank not in self.lines:
            return
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
