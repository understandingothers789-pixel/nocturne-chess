"""Interactive engine candidate rows. Only actual, legally validated PV data is shown."""

from html import escape

from PySide6.QtCore import QEvent, QPoint, Signal, Qt, QTimer
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import (
    QLabel, QMenu, QVBoxLayout, QWidget, QLayout, QHBoxLayout, QToolButton, QFrame,
)
from ..engine.uci_types import score_label
from ..explorer import chessdb_score
from .moves import MoveText
from .theme import palette

DEFAULT_PV_LINES = 1
EXPANDER_WIDTH = 26


class CandidatePanel(QWidget):
    preview = Signal(int, int)
    preview_end = Signal()
    pointer_moved = Signal(QPoint)
    navigate = Signal(int, int)
    action = Signal(int, str)
    changed = Signal()
    manual_navigation = Signal()
    statistics_changed = Signal(str)

    def __init__(self, primary, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.expanded = False
        self.multipv = 1
        self.fullmove = 1
        self._popup = None
        self._popup_rank = None
        self.default_pv_lines = self._lines_for_multipv(self.multipv)
        self.wheel_navigation = True
        self.primary = primary
        self.primary.compact = True
        self.primary.reserve_lines(0 if self.expanded else self.default_pv_lines)
        self.rows = {}
        self.footers = {}
        self.expand_buttons = {}
        self.expanded_ranks = set()
        self.light = False
        self.show_seldepth = False
        self.database = None
        self.details = {}
        self.lines = {}
        self.pinned = set()
        self.turn = 1
        self.slot_count = 0
        self._header_row_height = None
        self.hovered = None
        self.pending = {}
        self._clearing = False
        self._revision = 0

    def clear(self):
        self._clearing = True
        if self._popup:
            self._popup.close()
        self._revision += 1
        self.hovered = None
        self.pending.clear()
        self.preview_end.emit()
        for rank, widgets in self.rows.items():
            widgets[2].cancel_preview()
            if rank == 1:
                self.primary.setParent(self)
            widgets[0].deleteLater()
        self.rows = {}
        self.footers = {}
        self.expand_buttons = {}
        self.expanded_ranks.clear()
        self.lines = {}
        self.details.clear()
        self.pinned.clear()
        self.slot_count = 0
        self.primary.setViewportMargins(0, 0, 0, 0)
        self.primary.reserve_lines(0 if self.expanded else self.default_pv_lines)
        self.primary.set_moves([])
        self._clearing = False
        self.changed.emit()

    def set_wheel_navigation(self, enabled):
        self.wheel_navigation = bool(enabled)
        self.primary.wheel_navigation = self.wheel_navigation
        for _, _, moves in self.rows.values():
            moves.wheel_navigation = self.wheel_navigation

    def set_expanded(self, expanded):
        self.expanded = False  # Saved expand-all no longer changes single-row height.
        for rank in self.rows:
            self._apply_expansion(rank)

    @staticmethod
    def _lines_for_multipv(count):
        return 1

    def set_multipv(self, count):
        """Keep compact candidate rows sized for the selected MultiPV count."""
        count = max(1, min(5, int(count)))
        lines = self._lines_for_multipv(count)
        if count == self.multipv and lines == self.default_pv_lines:
            return
        self.multipv = count
        self.default_pv_lines = lines
        if 1 not in self.expanded_ranks:
            self.primary.reserve_lines(0 if self.expanded else lines)
        for rank, (_, _, moves) in self.rows.items():
            expanded = self.expanded or rank in self.expanded_ranks
            moves.reserve_lines(0 if expanded else lines)
            self._refresh_expander(rank)
        self.changed.emit()

    def reserve_slots(self, count):
        count = max(1, min(5, count))
        if count < self.slot_count:
            self.clear()
        for rank in range(self.slot_count + 1, count + 1):
            self._make_row(rank)
        self.slot_count = count

    def _make_row(self, rank):
        frame = QWidget()
        frame.setFixedHeight(28)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(4)
        number = QLabel(str(rank))
        number.setFixedWidth(12)
        number.setStyleSheet("font-size:11px;color:#888888;")
        header = QLabel("—")
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setFixedWidth(76)
        header.setFixedHeight(24)
        header.setStyleSheet("font-family:Consolas,monospace;font-size:15px;font-weight:600;")
        moves = self.primary if rank == 1 else MoveText(auto_fit=True, reserved_lines=1)
        moves.compact = True
        moves.reserve_lines(1)
        moves.candidate_rank = rank
        moves.wheel_navigation = self.wheel_navigation
        button = QToolButton()
        button.setText("…")
        button.setAutoRaise(True)
        button.setFixedSize(22, 24)
        button.setStyleSheet("padding:0;border:none;background:transparent;color:#a3b6c5;font-size:18px;")
        button.setAccessibleName(f"Inspect candidate {rank} full principal variation")
        button.setToolTip("Inspect the complete variation; hover or scroll to explore its moves")
        button.clicked.connect(lambda checked=False, r=rank: self.toggle_expansion(r))
        for widget in (number, header, moves, button):
            layout.addWidget(widget, 1 if widget is moves else 0)
        footer = QLabel(frame)
        footer.hide()
        if rank != 1 or not getattr(self, "_primary_connected", False):
            self._wire_moves(moves, rank)
            if rank == 1:
                self._primary_connected = True
        for widget in (frame, header, moves):
            widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            if widget is self.primary and getattr(self, "_primary_menu_connected", False):
                continue
            widget.customContextMenuRequested.connect(
                lambda point, r=rank, w=widget: self._menu(r, w.mapToGlobal(point)))
            if widget is self.primary:
                self._primary_menu_connected = True
        self.rows[rank] = (frame, header, moves)
        self.footers[rank] = footer
        self.expand_buttons[rank] = button
        self.layout.addWidget(frame)

    def _wire_moves(self, moves, rank):
        moves.move_hovered.connect(lambda ply, r=rank: self._hover(r, ply))
        moves.preview_ended.connect(lambda r=rank: self._end_hover(r))
        moves.move_clicked.connect(lambda ply, r=rank: self.navigate.emit(r, ply))
        moves.pointer_moved.connect(self.pointer_moved)
        moves.manual_navigation.connect(self.manual_navigation)

    def recolor(self, light):
        if self.light == light:
            return
        self.light = light
        for rank, (_, header, _) in self.rows.items():
            header.setStyleSheet(
                f"color: {palette(light)['metadata']};"
                "font-family: Consolas, monospace; font-size: 15px;"
            )
            self.footers[rank].setStyleSheet(
                f"color: {palette(light)['metadata']}; font-size: 13px;"
            )
            self._style_expander(self.expand_buttons[rank])
            self._render_header(rank)

    def _style_expander(self, button):
        colors = palette(self.light)
        button.setStyleSheet(
            f"""QToolButton {{ color: {colors['metadata']}; border: none;
                background: transparent; padding: 1px; }}
                QToolButton:hover {{ background: {colors['hover']};
                border-radius: 4px; }}"""
        )

    def _hover(self, rank, ply):
        if rank not in self.lines:
            return
        if self.hovered is not None and self.hovered != rank:
            self._end_hover(self.hovered)
        self.hovered = rank
        self.rows[rank][0].setStyleSheet(f"background:{palette(self.light)['hover']};")
        self._render_header(rank)
        self.preview.emit(rank, ply)

    def _end_hover(self, rank):
        if self._clearing or self.hovered != rank:
            return
        self.hovered = None
        if rank in self.rows:
            self.rows[rank][0].setStyleSheet("")
        self.preview_end.emit()
        if rank in self.pending:
            revision = self._revision
            QTimer.singleShot(0, lambda: self._flush(rank, revision))

    def _flush(self, rank, revision):
        if revision != self._revision or self.hovered == rank or rank not in self.rows or self._popup_rank == rank:
            return
        pending = self.pending.pop(rank, None)
        if pending:
            self.update_line(*pending)

    def update_line(self, info, turn, light=False, detailed=False):
        rank = info.get("multipv", 1)
        if rank in self.pinned:
            return
        if type(rank) is not int or not 1 <= rank <= 5:
            return
        previous = self.lines.get(rank)
        moves = self.rows[rank][2] if rank in self.rows else None
        if moves and moves.wheel_preview_ply is not None:
            # Keep the displayed PV snapshot while the user scroll-browses a
            # candidate. Later engine updates must not pull the preview back to
            # ply one. A different root move means MultiPV rank order changed,
            # so end the old preview and show the candidate now occupying rank.
            old_root = previous.get("pv", [None])[0] if previous else None
            new_root = info.get("pv", [None])[0]
            if old_root == new_root:
                self.pending[rank] = (info.copy(), turn, light, detailed)
                return
            self.pending.pop(rank, None)
            moves.cancel_preview()
        if self.hovered == rank or self._popup_rank == rank:
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
        moves.candidate_fullmove = self.fullmove
        moves.set_moves([(text, i + 1) for i, text in enumerate(info["san"])], light=light)
        if (previous and previous.get("pv")
                and (not info.get("pv") or previous["pv"][0] != info["pv"][0])):
            self.expanded_ranks.discard(rank)
            self._apply_expansion(rank)
        self._refresh_expander(rank)
        QTimer.singleShot(0, lambda r=rank: self._refresh_expander(r))
        self.changed.emit()

    def set_database(self, query=None, data=None, origin="", status=""):
        value = (query, data, origin, status) if query else None
        if value == self.database:
            return
        self.database = value
        for rank in self.rows:
            self._render_header(rank)

    def set_show_seldepth(self, enabled):
        self.show_seldepth = bool(enabled)
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
        first = blue(score_label(info, self.turn))
        if rank in self.pinned:
            first += " ★"
        # Keep the first two things a player wants to scan close together:
        # evaluation, then depth. Avoid the old oversized gap before depth.
        depth = f"{info['depth']}/{info['seldepth']}" if self.show_seldepth else str(info["depth"])

        header = self.rows[rank][1]
        if wdl:
            metadata = f"W/D/L {wdl[0] / 10:.1f}/{wdl[1] / 10:.1f}/{wdl[2] / 10:.1f}% White"
        else:
            metadata = "W/D/L —"
        if self.details.get(rank):
            metadata += f" &nbsp; {info['nodes']:,} nodes"
        side = "White" if self.turn > 0 else "Black"
        win, frequency, sample = "—", "—", ""
        source = "Database off"
        cloud_score = ""
        if self.database:
            query, data, origin, status = self.database
            source = query.label + (" · Cached" if origin.startswith("Cached") else
                                    " · Live" if origin.startswith("Live") else "")
            if data is None:
                if status.lower().startswith("loading"):
                    source += " · Loading"
                elif status:
                    detail = status
                    if detail.startswith(query.label):
                        detail = detail[len(query.label):].strip(" ·")
                    source += " · " + (detail or "No games found")
                else:
                    source += " · Loading"
            else:
                row = next((row for row in data["moves"] if info.get("pv") and row["uci"] == info["pv"][0]), None)
                if data.get("indexing"):
                    source += " · Indexing player games; statistics are provisional"
                elif query.source == "chessdb":
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
                    source += " · " + ("No scored move" if query.source == "chessdb" else "No games found")
        metadata += (f" &nbsp; API win ({side}) {blue(win)} &nbsp; Freq {blue(frequency)}"
                     f"{sample} &nbsp; {escape(source)}{cloud_score}")
        header.setText(first)
        header.setAccessibleName(f"Candidate {rank} evaluation")
        probe = QTextDocument()
        probe.setHtml(f"Depth {depth} · {metadata}")
        detail = f"Candidate {rank} · " + probe.toPlainText()
        header.setToolTip(detail)
        self.rows[rank][0].setToolTip(detail)
        if rank == (self.hovered or 1):
            self.statistics_changed.emit(detail)

    def _header_height(self, header):
        return 24

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def _apply_expansion(self, rank):
        if rank in self.rows:
            self.rows[rank][2].reserve_lines(1)

    def _refresh_expander(self, rank):
        if rank in self.expand_buttons:
            self.expand_buttons[rank].setVisible(rank in self.lines)

    def toggle_expansion(self, rank):
        if rank not in self.lines:
            return
        if self._popup:
            self._popup.close()
        popup = QFrame(self, Qt.WindowType.Popup)
        popup.setObjectName("panel")
        popup.installEventFilter(self)
        layout = QVBoxLayout(popup)
        layout.addWidget(QLabel(f"Candidate {rank} · {score_label(self.lines[rank], self.turn)} · full variation"))
        moves = MoveText()
        moves.candidate_rank = rank
        moves.candidate_turn = self.turn
        moves.candidate_fullmove = self.fullmove
        moves.wheel_navigation = self.wheel_navigation
        moves.set_moves([(text, i+1) for i, text in enumerate(self.lines[rank]["san"])], light=self.light)
        self._wire_moves(moves, rank)
        layout.addWidget(moves, 1)
        self._popup, self._popup_rank = popup, rank
        available = self.screen().availableGeometry()
        popup.resize(min(720, available.width()-24), min(280, available.height()-24))
        point = self.rows[rank][0].mapToGlobal(QPoint(0, 28))
        point.setX(max(available.left(), min(point.x(), available.right()-popup.width())))
        point.setY(max(available.top(), min(point.y(), available.bottom()-popup.height())))
        popup.move(point)
        popup.show()

    def eventFilter(self, watched, event):
        if watched is self._popup and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.manual_navigation.emit()
        if watched is self._popup and event.type() == QEvent.Type.Hide:
            rank, self._popup_rank = self._popup_rank, None
            self._popup = None
            if rank is not None:
                self._end_hover(rank)
                revision = self._revision
                QTimer.singleShot(0, lambda: self._flush(rank, revision))
            watched.deleteLater()
        return super().eventFilter(watched, event)

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
            ("Copy PGN (this line)", "pgn"),
            ("Copy SAN (this line)", "san"),
            ("Copy UCI (this line)", "uci"),
            ("Analyze only this move", "focus"),
        ):
            item = menu.addAction(title)
            item.setData(action)
        chosen = menu.exec(position)
        action = chosen.data() if chosen else None
        menu.deleteLater()
        if action:
            self._action(rank, action)
