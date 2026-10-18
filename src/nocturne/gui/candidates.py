"""Interactive engine candidate rows. Only actual, legally validated PV data is shown."""

from html import escape
import math

from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QLabel, QMenu, QVBoxLayout, QWidget, QLayout, QSizePolicy
from ..engine.uci_types import score_label
from ..explorer import chessdb_score
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
        self.expanded = False
        self.wheel_navigation = True
        self.primary = primary
        self.primary.reserve_lines(3)
        self.rows = {}
        self.light = False
        self.database = None
        self.details = {}
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
        self.details.clear()
        self.pinned.clear()
        self.slot_count = 0
        self.primary.set_moves([])
        self._clearing = False
        self.changed.emit()

    def set_wheel_navigation(self, enabled):
        self.wheel_navigation = bool(enabled)
        self.primary.wheel_navigation = self.wheel_navigation
        for _, _, moves in self.rows.values():
            moves.wheel_navigation = self.wheel_navigation

    def set_expanded(self, expanded):
        self.expanded = bool(expanded)
        self.primary.reserve_lines(0 if self.expanded else 3)
        for _, _, moves in self.rows.values():
            moves.reserve_lines(0 if self.expanded else 3)

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
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setWordWrap(True)
        header.setFixedHeight(self._header_height(header))
        header.setStyleSheet(f"color: {palette(self.light)['metadata']};")
        layout.addWidget(header)
        moves = self.primary if rank == 1 else MoveText(auto_fit=True, reserved_lines=3)
        moves.reserve_lines(0 if self.expanded else 3)
        moves.wheel_navigation = self.wheel_navigation
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
        for rank, (_, header, _) in self.rows.items():
            header.setStyleSheet(f"color: {palette(light)['metadata']};")
            self._render_header(rank)

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
        self.details[rank] = detailed
        self._render_header(rank)
        frame, header, moves = self.rows[rank]
        moves.candidate_turn = turn
        moves.set_moves([(text, i + 1) for i, text in enumerate(info["san"])], light=light)
        self.changed.emit()

    def set_database(self, query=None, data=None, origin=""):
        value = (query, data, origin) if query else None
        if value == self.database:
            return
        self.database = value
        for rank in self.rows:
            self._render_header(rank)

    def _render_header(self, rank):
        if rank not in self.lines:
            return
        info = self.lines[rank]
        colors = palette(self.light)
        def blue(value):
            return f'<span style="color:{colors["metric"]};">{escape(str(value))}</span>'
        wdl = info.get("wdl")
        if wdl and self.turn < 0:
            wdl = wdl[::-1]
        first = ("★ " if rank in self.pinned else "") + blue(score_label(info, self.turn))
        first += f" &nbsp; Depth {info['depth']}/{info['seldepth']}"
        if wdl:
            first += f" &nbsp; W/D/L {wdl[0] / 10:.1f}/{wdl[1] / 10:.1f}/{wdl[2] / 10:.1f}% White"
        else:
            first += " &nbsp; W/D/L —"
        if self.details.get(rank):
            first += f" &nbsp; {info['nodes']:,} nodes"
        side = "White" if self.turn > 0 else "Black"
        win, frequency, sample = "—", "—", ""
        source = "Database off"
        cloud_score = ""
        if self.database:
            query, data, origin = self.database
            source = query.label + (" · Cached" if origin.startswith("Cached") else
                                    " · Live" if origin.startswith("Live") else "")
            if data is None:
                source += " · awaiting data"
            else:
                row = next((row for row in data["moves"] if info.get("pv") and row["uci"] == info["pv"][0]), None)
                if query.source == "chessdb":
                    cloud_score = " · DB White " + blue(chessdb_score(row["score"], query.fen) if row else "—")
                elif row and 0 < row["total"] <= data["total"]:
                    win = f'{100 * row["white" if self.turn > 0 else "black"] / row["total"]:.1f}%'
                    frequency = f'{100 * row["total"] / data["total"]:.1f}%'
                    sample = f' &nbsp; [{row["total"]:,} / {data["total"]:,} games]'
                elif row and row["total"] > data["total"]:
                    source += " · inconsistent counts"
                elif row and row["total"] == 0:
                    sample = " &nbsp; [0 games]"
                else:
                    source += " · no move sample"
        second = f"API win ({side}) {blue(win)} &nbsp; Freq {blue(frequency)}{sample} &nbsp; {escape(source)}{cloud_score}"
        header = self.rows[rank][1]
        header.setText(f"<div>{first} &nbsp; {second}</div>")
        header.setAccessibleName(f"Candidate {rank} evaluation, search and database metrics")

    def _header_height(self, header):
        # Reserve identical metadata space from width, never from arriving PVs.
        # This keeps hovered lower candidates in place during engine/API updates.
        probe = QTextDocument()
        probe.setDefaultFont(header.font())
        probe.setDocumentMargin(0)
        probe.setHtml("<div>★ +123.45 &nbsp; Depth 128/256 &nbsp; W/D/L 100.0/100.0/100.0% White"
                      " &nbsp; 9,999,999,999 nodes &nbsp; "
                      "API win (White) 100.0% &nbsp; Freq 100.0% &nbsp; "
                      "[999,999,999 / 999,999,999 games] &nbsp; Lichess players · Cached · no move sample</div>")
        probe.setTextWidth(max(160, self.width()))
        return math.ceil(probe.size().height()) + 6

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for _, header, _ in self.rows.values():
            header.setFixedHeight(self._header_height(header))

    def _action(self, rank, action):
        if action == "pin":
            if rank in self.pinned:
                self.pinned.remove(rank)
            else:
                self.pinned.add(rank)
            self._render_header(rank)
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
