"""Interactive engine candidate rows. Only actual, legally validated PV data is shown."""

from html import escape
import math

from shiboken6 import isValid

from PySide6.QtCore import QPoint, Signal, Qt, QTimer, QSize
from PySide6.QtGui import QTextDocument, QCursor
from PySide6.QtWidgets import (
    QLabel, QMenu, QVBoxLayout, QWidget, QLayout, QSizePolicy, QGridLayout, QToolButton,
)
from ..engine.uci_types import score_label
from ..explorer import chessdb_score
from ..maia import percentage
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

    def __init__(self, primary, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.font_increase = 20
        self.expanded = False
        self.multipv = 1
        self.default_pv_lines = self._lines_for_multipv(self.multipv)
        self.wheel_navigation = True
        self.primary = primary
        self.primary.reserve_lines(0 if self.expanded else self.default_pv_lines)
        self.rows = {}
        self.maia_labels = {}
        self.footers = {}
        self.expand_buttons = {}
        self.expanded_ranks = set()
        self.maia_policy = {}
        self.maia_enabled = False
        self.maia_rating = 1800
        self.light = False
        self.show_seldepth = False
        self.show_details = False
        self.database = None
        self.details = {}
        self.lines = {}
        self.pinned = set()
        self.turn = 1
        self.slot_count = 0
        self._header_row_height = None
        self.hovered = None
        self._leave_timer = QTimer(self)
        self._leave_timer.setSingleShot(True)
        self._leave_timer.setInterval(140)
        self._leave_timer.timeout.connect(self._end_pointer_hover)
        self.pending = {}
        self._clearing = False
        self._revision = 0

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())

    def clear(self):
        self._leave_timer.stop()
        self._clearing = True
        self._revision += 1
        self.hovered = None
        self.pending.clear()
        self.preview_end.emit()
        if set(self.rows) == set(range(1, self.multipv + 1)):
            # Retain browser widgets and their layout/scrollbar geometry across
            # position changes, rather than tearing down every PV row.
            self.lines.clear()
            self.details.clear()
            self.pinned.clear()
            self.expanded_ranks.clear()
            for rank, (_, header, moves) in self.rows.items():
                moves.cancel_preview()
                moves.setViewportMargins(0, 0, 0, 0)
                moves.reserve_lines(0 if self.expanded else self.default_pv_lines)
                moves.set_moves([])
                header.clear()
                self.maia_labels[rank].clear()
                self.footers[rank].clear()
                self.footers[rank].hide()
                self._refresh_expander(rank)
            self._clearing = False
            self.changed.emit()
            return
        for rank, widgets in self.rows.items():
            widgets[2].cancel_preview()
            if rank == 1:
                self.primary.setParent(self)
            self.layout.removeWidget(widgets[0])
            widgets[0].hide()
            widgets[0].setParent(None)
            widgets[0].deleteLater()
        self.rows = {}
        self.maia_labels = {}
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
        # Keep the compact analysis slots present on unanalysed positions so
        # the game line below cannot jump away from the scrolling cursor.
        for rank in range(1, self.multipv + 1):
            self._make_row(rank)
        self.slot_count = self.multipv
        self._clearing = False
        self.changed.emit()

    def set_font_increase(self, percent):
        self.font_increase = percent
        for _, _, moves in self.rows.values():
            moves.set_font_increase(percent)
        self.changed.emit()

    def set_wheel_navigation(self, enabled):
        self.wheel_navigation = bool(enabled)
        self.primary.wheel_navigation = self.wheel_navigation
        for _, _, moves in self.rows.values():
            moves.wheel_navigation = self.wheel_navigation

    def set_expanded(self, expanded):
        self.expanded = bool(expanded)
        for rank in self.rows:
            self._apply_expansion(rank)

    @staticmethod
    def _lines_for_multipv(count):
        return DEFAULT_PV_LINES

    def set_multipv(self, count):
        """Keep compact candidate rows sized for the selected MultiPV count."""
        count = max(1, min(32, int(count)))
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
        count = max(self.multipv, max(1, min(32, count)))
        if count < self.slot_count:
            self.clear()
        for rank in range(self.slot_count + 1, count + 1):
            self._make_row(rank)
        self.slot_count = count

    def _make_row(self, rank):
        frame = QWidget()
        frame.setObjectName("candidateRow")
        frame.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        frame.setProperty("alternate", rank % 2 == 0)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(2)
        header = QLabel("")
        header.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setWordWrap(True)
        header.setStyleSheet(
            f"color: {palette(self.light)['metadata']};"
            "font-family: Consolas, monospace; font-size: 16px;"
        )
        if self._header_row_height is None:
            self._header_row_height = self._header_height(header)
        header.setFixedHeight(self._header_row_height)
        header.setVisible(self.show_details)
        moves = self.primary if rank == 1 else MoveText(
            auto_fit=True, reserved_lines=self.default_pv_lines
        )
        moves.reserve_lines(0 if self.expanded or rank in self.expanded_ranks else self.default_pv_lines)
        moves.wheel_navigation = self.wheel_navigation
        moves.candidate_rank = rank
        moves.set_font_increase(self.font_increase)
        moves.setViewportMargins(0, 0, 0, 0)
        moves.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        pv_area = QWidget()
        pv_area.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        pv_layout = QGridLayout(pv_area)
        pv_layout.setContentsMargins(0, 0, 0, 0)
        pv_layout.setSpacing(0)
        pv_layout.setColumnStretch(0, 1)
        pv_layout.setColumnMinimumWidth(1, EXPANDER_WIDTH)
        pv_layout.setColumnMinimumWidth(2, 84)
        expand_button = QToolButton(pv_area)
        expand_button.setAutoRaise(True)
        expand_button.setFixedSize(EXPANDER_WIDTH, 22)
        expand_button.setArrowType(Qt.ArrowType.UpArrow if rank in self.expanded_ranks
                                   else Qt.ArrowType.DownArrow)
        expand_button.setAccessibleName(f"Expand candidate {rank} full principal variation")
        self._style_expander(expand_button)
        expand_button.clicked.connect(lambda checked=False, r=rank: self.toggle_expansion(r))
        pv_layout.addWidget(moves, 0, 0)
        # A separate column keeps the browser viewport from covering the
        # button or intercepting its mouse events. It also stays put on expand.
        pv_layout.addWidget(expand_button, 0, 1, Qt.AlignmentFlag.AlignTop)
        probability = QLabel("")
        probability.setFixedWidth(84)
        probability.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        probability.setStyleSheet("color: #b9b4df; font-family: Consolas; padding-right: 3px;")
        probability.setVisible(self.maia_enabled)
        pv_layout.addWidget(probability, 0, 2, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self.maia_labels[rank] = probability
        layout.addWidget(pv_area)
        layout.addWidget(header)
        footer = QLabel()
        footer.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        footer.setTextFormat(Qt.TextFormat.RichText)
        footer.setWordWrap(True)
        footer.setStyleSheet(
            f"color: {palette(self.light)['metadata']}; font-size: 13px;"
        )
        footer.setFixedHeight(self._footer_height(footer))
        layout.addWidget(footer)
        footer.hide()
        moves.show()
        # The primary widget survives clear/reuse, so wire it exactly once.
        if rank != 1 or not getattr(self, "_primary_connected", False):
            moves.move_hovered.connect(lambda ply, r=rank: self._hover(r, ply))
            moves.preview_ended.connect(lambda r=rank: self._end_hover(r))
            moves.preview_gap_ended.connect(lambda r=rank: self._defer_end_hover(r))
            moves.move_clicked.connect(lambda ply, r=rank: self.navigate.emit(r, ply))
            moves.pointer_moved.connect(self.pointer_moved)
            moves.manual_navigation.connect(self.manual_navigation)
            if rank == 1:
                self._primary_connected = True
        for widget in (frame, header, moves, footer, expand_button):
            widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            if widget is self.primary and getattr(self, "_primary_menu_connected", False):
                continue
            widget.customContextMenuRequested.connect(
                lambda point, r=rank, w=widget: self._menu(r, w.mapToGlobal(point))
            )
            if widget is self.primary:
                self._primary_menu_connected = True
        self.rows[rank] = (frame, header, moves)
        self.footers[rank] = footer
        self.expand_buttons[rank] = expand_button
        self._refresh_expander(rank)
        QTimer.singleShot(0, self, lambda r=rank: self._refresh_expander(r))
        self.layout.addWidget(frame)

    def recolor(self, light):
        if self.light == light:
            return
        self.light = light
        for rank, (_, header, _) in self.rows.items():
            header.setStyleSheet(
                f"color: {palette(light)['metadata']};"
                "font-family: Consolas, monospace; font-size: 16px;"
            )
            self.footers[rank].setStyleSheet(
                f"color: {palette(light)['metadata']}; font-size: 13px;"
            )
            self._style_expander(self.expand_buttons[rank])
            self._render_header(rank)
            self._render_maia(rank)

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
        self._leave_timer.stop()
        if self.hovered is not None and self.hovered != rank:
            self._end_hover(self.hovered, notify=False)
        self.hovered = rank
        self.preview.emit(rank, ply)

    def _end_pointer_hover(self):
        position = QCursor.pos()
        views = [row[2].viewport() for row in self.rows.values()]
        # Inter-row padding belongs to the candidate list: retain the board even
        # if the user pauses there. Empty space after a row's last move can exit.
        between_rows = (self.isVisible() and self.rect().contains(self.mapFromGlobal(position))
                        and not any(view.rect().contains(view.mapFromGlobal(position)) for view in views)
                        and any(0 <= view.mapFromGlobal(position).x() < view.width() for view in views))
        if between_rows:
            self._leave_timer.start()
        else:
            self._end_hover(self.hovered)

    def _defer_end_hover(self, rank):
        if not self._clearing and self.hovered == rank:
            self._leave_timer.start()

    def _end_hover(self, rank, notify=True):
        if rank is None or self._clearing or self.hovered != rank:
            return
        self._leave_timer.stop()
        self.hovered = None
        if rank in self.rows:
            self.rows[rank][2].cancel_preview()
        if notify:
            self.preview_end.emit()
        if rank in self.pending:
            revision = self._revision
            QTimer.singleShot(0, self, lambda: self._flush(rank, revision))

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
        self._render_maia(rank)
        frame, header, moves = self.rows[rank]
        moves.candidate_turn = turn
        moves.candidate_evaluation = score_label(info, turn)
        moves.set_moves([(text, i + 1) for i, text in enumerate(info["san"])], light=light, figurines=True)
        if (previous and previous.get("pv")
                and (not info.get("pv") or previous["pv"][0] != info["pv"][0])):
            self.expanded_ranks.discard(rank)
            self._apply_expansion(rank)
        self._refresh_expander(rank)
        QTimer.singleShot(0, self, lambda r=rank: self._refresh_expander(r))
        self.changed.emit()

    def set_maia(self, policy=None, rating=1800, enabled=True):
        self.maia_policy = policy or {}
        self.maia_rating = rating
        self.maia_enabled = enabled
        for rank in self.maia_labels:
            self._render_maia(rank)

    def _render_maia(self, rank):
        label = self.maia_labels.get(rank)
        if label is None:
            return
        pv = self.lines.get(rank, {}).get("pv", [])
        probability = self.maia_policy.get(pv[0]) if pv else None
        colors = palette(self.light)
        label.setStyleSheet(f"color: {colors['maia']}; background: {colors['maia_soft']}; "
                           "border-radius: 4px; font-family: Consolas; font-size: 12px; "
                           "font-weight: 600; padding: 3px 5px;")
        label.setVisible(self.maia_enabled)
        label.setText(percentage(probability) if pv else "")
        label.setToolTip(f"Maia-3 79M · {self.maia_rating} vs {self.maia_rating} Lichess blitz\n"
                         + (f"{pv[0]}: {probability * 100:.8g}% predicted likelihood" if probability is not None
                            else "Waiting for this position’s policy; no probability has been substituted."))

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

    def set_detailed(self, enabled):
        self.show_details = bool(enabled)
        for rank, (_, header, _) in self.rows.items():
            header.setVisible(self.show_details)
            self.details[rank] = self.show_details
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
        depth = f"{info['depth']}/{info['seldepth']}" if self.show_seldepth else str(info["depth"])
        first = f"<span style=\"color:{colors['metadata']};\">Depth {depth}</span>"
        if rank in self.pinned:
            first += " ★"
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
                    source += " · " + ("No scored move" if query.source == "chessdb" else "No games found")
        metadata += (f" &nbsp; API win ({side}) {blue(win)} &nbsp; Freq {blue(frequency)}"
                     f"{sample} &nbsp; {escape(source)}{cloud_score}")
        header.setText(
            f'<div>{first} &nbsp; <span style="color:{colors["metadata"]}; font-size:13px;">'
            f'{metadata}</span></div>'
        )
        header.setAccessibleName(f"Candidate {rank} evaluation, depth and database metrics")
        footer = self.footers[rank]
        footer.setText("")
        footer.setAccessibleName(f"Candidate {rank} WDL and database metrics")

    def _header_height(self, header):
        # Measure the combined evaluation, depth and metadata row at a fixed
        # worst-case width so rows stay aligned as PVs and database data update.
        probe = QTextDocument()
        probe.setDefaultFont(header.font())
        probe.setDocumentMargin(0)
        probe.setHtml(
            '<div>+123.45 ★ &nbsp; Depth 128/256 &nbsp; '
            '<span style="font-size:13px;">W/D/L 100.0/100.0/100.0% White &nbsp; '
            '9,999,999,999 nodes &nbsp; API win (Black) 100.0% &nbsp; Freq 100.0% '
            '[999,999,999 / 999,999,999 games] &nbsp; Lichess players · Cached · '
            'No games found</span></div>'
        )
        probe.setTextWidth(max(160, self.width()))
        return math.ceil(probe.size().height()) + 6

    def _footer_height(self, footer):
        probe = QTextDocument()
        probe.setDefaultFont(footer.font())
        probe.setDocumentMargin(0)
        probe.setHtml("<div>W/D/L 100.0/100.0/100.0% White &nbsp; 9,999,999,999 nodes"
                      " &nbsp; API win (White) 100.0% &nbsp; Freq 100.0%"
                      " [999,999,999 / 999,999,999 games]"
                      " &nbsp; Lichess players · Cached · no move sample</div>")
        probe.setTextWidth(max(160, self.width()))
        return math.ceil(probe.size().height()) + 4

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._header_row_height = self._header_height(next(iter(self.rows.values()))[1]) if self.rows else None
        for rank, (_, header, _) in self.rows.items():
            header.setFixedHeight(self._header_row_height)
            self.footers[rank].setFixedHeight(self._footer_height(self.footers[rank]))
            QTimer.singleShot(0, self, lambda r=rank: self._refresh_expander(r))

    def _apply_expansion(self, rank):
        if rank not in self.rows:
            return
        moves = self.rows[rank][2]
        expanded = self.expanded or rank in self.expanded_ranks
        moves.reserve_lines(0 if expanded else self.default_pv_lines)
        button = self.expand_buttons.get(rank)
        if button:
            button.setArrowType(Qt.ArrowType.UpArrow if rank in self.expanded_ranks
                                else Qt.ArrowType.DownArrow)
            button.setAccessibleName(
                f"Collapse candidate {rank} principal variation" if rank in self.expanded_ranks
                else f"Expand candidate {rank} full principal variation"
            )
            button.setVisible(not self.expanded)
        self._refresh_expander(rank)

    def _refresh_expander(self, rank):
        button = self.expand_buttons.get(rank)
        if button is None or not isValid(button):
            return
        if rank not in self.lines:
            button.hide()
            return
        moves = self.rows[rank][2]
        if not isValid(moves):
            return
        expanded = rank in self.expanded_ranks
        button.setVisible(not self.expanded and
                          (expanded or moves.wrapped_line_count() > self.default_pv_lines))

    def toggle_expansion(self, rank):
        if self.expanded or rank not in self.lines:
            return
        if rank in self.expanded_ranks:
            self.expanded_ranks.remove(rank)
        else:
            self.expanded_ranks.add(rank)
        self._apply_expansion(rank)
        self.changed.emit()

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
