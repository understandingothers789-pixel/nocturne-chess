"""Flowing move text with reversible hover and explicit click signals."""

from html import escape
import math

from PySide6.QtCore import QEvent, QPoint, Signal, Qt, QUrl
from PySide6.QtGui import QTextDocument, QTextCursor, QTextOption
from PySide6.QtWidgets import QTextBrowser, QToolTip
from .theme import palette
from .notation import html as notation_html
from .wheel import WheelSteps


class MoveText(QTextBrowser):
    wheel_navigated = Signal(int)
    move_hovered = Signal(int)
    move_clicked = Signal(int)
    preview_ended = Signal()
    preview_gap_ended = Signal()
    pointer_moved = Signal(QPoint)
    manual_navigation = Signal()

    def __init__(self, parent=None, *, auto_fit=False, reserved_lines=0):
        super().__init__(parent)
        self.font_increase = 0
        self.continuous_preview = False
        self._figurines = False
        self._auto_fit = auto_fit
        self._reserved_lines = reserved_lines
        self._reserved_measurement = None
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAccessibleName("Moves")
        self._items = []
        self._current = None
        self._light = False
        self._hovered = None
        self._last_pointer_hovered = None
        self.wheel_preview_ply = None
        self.candidate_rank = None
        self.candidate_turn = 1
        self.candidate_depth = None
        self.candidate_historical = False
        self.candidate_evaluation = ""
        self._candidate_style = None
        self._book_departure = None
        self._book_departures = {}
        self._pressed_move = None
        self.wheel_navigation = True
        self._wheel_steps = WheelSteps()
        if auto_fit:
            self.document().setDocumentMargin(2)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.document().documentLayout().documentSizeChanged.connect(self._fit_height)
        self.highlighted.connect(self._highlight)
        self.anchorClicked.connect(self._click)

    def _highlight(self, url):
        text = url.toString()
        index = int(text[5:]) if text.startswith("move:") and text[5:].isdigit() else None
        if index is None and self.continuous_preview and self._hovered is not None:
            return
        if index == self._hovered:
            return
        self._hovered = index
        if index is None:
            (self.preview_gap_ended if self.candidate_rank is not None else self.preview_ended).emit()
        else:
            self.move_hovered.emit(index)

    def _click(self, url):
        text = url.toString()
        if text.startswith("move:") and text[5:].isdigit():
            # Activate the displayed snapshot before ending hover can apply a
            # queued engine update. Otherwise a click could play another PV.
            self.move_clicked.emit(int(text[5:]))
            self.cancel_preview()

    def leaveEvent(self, event):
        self._wheel_steps.reset()
        self.wheel_preview_ply = None
        self._hovered = None
        self._last_pointer_hovered = None
        (self.preview_gap_ended if self.candidate_rank is not None else self.preview_ended).emit()
        super().leaveEvent(event)

    def focusOutEvent(self, event):
        self.wheel_preview_ply = None
        self._hovered = None
        self._last_pointer_hovered = None
        self.preview_ended.emit()
        super().focusOutEvent(event)

    def hideEvent(self, event):
        self.cancel_preview()
        super().hideEvent(event)

    def viewportEvent(self, event):
        if event.type() == QEvent.Type.ToolTip and self.candidate_depth is not None:
            cursor = self.document().find(f"d{self.candidate_depth}")
            if not cursor.isNull():
                start = QTextCursor(cursor)
                start.setPosition(cursor.selectionStart())
                end = QTextCursor(cursor)
                end.setPosition(cursor.selectionEnd())
                rect = self.cursorRect(start).united(self.cursorRect(end)).adjusted(-2, -2, 2, 2)
                if rect.contains(event.pos()):
                    QToolTip.showText(event.globalPos(), f"Depth {self.candidate_depth}", self.viewport(), rect)
                    return True
        if event.type() == QEvent.Type.Leave:
            self.cancel_preview(pointer=True)
        return super().viewportEvent(event)

    def set_moves(self, items, current=None, light=False, *, book_departure=None, book_departures=None, figurines=False):
        signature = (list(items), current, light, figurines)
        candidate_style = (self.candidate_rank, self.candidate_turn, self.candidate_evaluation, self.candidate_historical, self.candidate_depth)
        departures = dict(book_departures or {})
        if book_departure is not None and book_departure not in departures:
            departures[book_departure] = "Lichess Masters: first position with no games found"
        if (signature == (self._items, self._current, self._light, self._figurines)
                and candidate_style == self._candidate_style and book_departure == self._book_departure
                and departures == self._book_departures):
            return
        self.preview_ended.emit()
        self._hovered = None
        self._last_pointer_hovered = None
        self._items, self._current, self._light = signature[:3]
        self._figurines = figurines
        self._candidate_style = candidate_style
        self._book_departure = book_departure
        self._book_departures = departures
        self.viewport().setToolTip("")
        if self.candidate_rank is not None:
            self.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        colors = palette(light)
        color = colors["history"]
        tokens = []
        if self.candidate_rank is not None and self.candidate_evaluation:
            metric_color = colors["historical_metric"] if self.candidate_historical else colors["metric"]
            tokens.append(f'<span style="color:{metric_color};">'
                          f'{escape(self.candidate_evaluation)}</span> ')
        if self.candidate_depth is not None:
            tokens.append(f'<span title="Depth {self.candidate_depth}" style="color:{colors["historical_metric"] if self.candidate_historical else colors["metadata"]};">d{self.candidate_depth}</span> ')
        for offset, (text, index) in enumerate(self._items):
            if index is None:
                tokens.append(escape(text) + (" " if self.continuous_preview else ""))
                continue
            move_color = color
            if self.candidate_rank is not None:
                side = self.candidate_turn if index % 2 else -self.candidate_turn
                move_color = (colors["historical_white" if side > 0 else "historical_black"] if self.candidate_historical else
                              colors["analysis_white" if side > 0 else "analysis_black"])
            style = (f'color: {colors["selected_text"]}; background-color: {colors["selection"]};'
                     if index == current else f"color: {move_color};")
            if index in departures:
                tint = "#87713f" if light else "#c3b07c"
                style += f"color: {tint};"
            label = text
            decoration = "text-decoration:none;"
            tooltip = f' title="{escape(departures[index], quote=True)}"' if index in departures else ""
            gap = " " if (self.candidate_rank is not None or self.continuous_preview) and offset < len(self._items) - 1 else ""
            tokens.append(f'<a href="move:{index}" style="{style} {decoration}"{tooltip}>{notation_html(label, size=17 * (1 + self.font_increase / 100) if self.candidate_rank is not None else 17) if figurines else escape(label)}{gap}</a>')
        size, spacing = (16, 155) if self._auto_fit else (14, 140)
        if self.candidate_rank is not None:
            size *= 1 + self.font_increase / 100
        self.setHtml(f'<div style="font-family:Consolas,monospace; font-size:{size}px; line-height:{spacing}%;">'
                     + ("" if self.candidate_rank is not None or self.continuous_preview else " ").join(tokens) + "</div>")

    def set_font_increase(self, percent):
        if self.font_increase == percent:
            return
        self.font_increase = percent
        self._reserved_measurement = None
        self._candidate_style = None
        self.set_moves(self._items, self._current, self._light, figurines=self._figurines)
        self._fit_height()

    def _move_at(self, point):
        """Include the padding above and below each candidate anchor."""
        block = self.document().begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().isAnchor():
                    cursor = QTextCursor(self.document())
                    cursor.setPosition(fragment.position())
                    start = self.cursorRect(cursor)
                    cursor.setPosition(fragment.position() + fragment.length())
                    end = self.cursorRect(cursor)
                    rect = start.united(end).adjusted(0, -2, 1, 2)
                    if (self.candidate_rank is not None and self._reserved_lines == 1
                            and rect.intersects(self.viewport().rect())):
                        rect.setTop(0)
                        rect.setBottom(self.viewport().height())
                    if rect.contains(point):
                        return QUrl(fragment.charFormat().anchorHref())
                iterator += 1
            block = block.next()
        return QUrl()

    def mouseMoveEvent(self, event):
        self.pointer_moved.emit(event.globalPosition().toPoint())
        if self.candidate_rank is None:
            anchor = self.anchorAt(event.position().toPoint())
            index = int(anchor[5:]) if anchor.startswith("move:") and anchor[5:].isdigit() else None
            self.viewport().setToolTip(self._book_departures.get(index, ""))
            return super().mouseMoveEvent(event)
        url = self._move_at(event.position().toPoint())
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if not url.isEmpty()
                                  else Qt.CursorShape.ArrowCursor)
        index = int(url.toString()[5:]) if url.toString().startswith("move:") else None
        # Qt emits mouse-move events for tiny pointer jitters too. Keep the
        # scroll preview until the pointer actually crosses into another move.
        if index == self._last_pointer_hovered:
            return
        self._last_pointer_hovered = index
        self.wheel_preview_ply = None
        self._highlight(url)

    def mousePressEvent(self, event):
        if self.candidate_rank is None or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self._pressed_move = self._move_at(event.position().toPoint())
        event.accept()

    def mouseReleaseEvent(self, event):
        if self.candidate_rank is None or event.button() != Qt.MouseButton.LeftButton:
            return super().mouseReleaseEvent(event)
        url = self._move_at(event.position().toPoint())
        pressed, self._pressed_move = self._pressed_move, None
        if url == pressed and not url.isEmpty():
            self._click(url)
        event.accept()

    def wheelEvent(self, event):
        steps = self._wheel_steps.consume(event) if self.wheel_navigation else None
        if steps is None:
            return super().wheelEvent(event)
        self.manual_navigation.emit()
        event.accept()
        if not steps:
            return
        if self.candidate_rank is None:
            self.cancel_preview()
            self.wheel_navigated.emit(steps)
            return
        last = max((index for _, index in self._items if index is not None), default=0)
        if not last:
            return
        ply = max(0, min(last, (self._hovered or 0) + steps))
        self.wheel_preview_ply = ply
        self._highlight(QUrl(f"move:{ply}"))
        # Wheel browsing advances the board preview, not the notation viewport.
        # Keep the evaluation and opening moves at the front of the row.
        self.verticalScrollBar().setValue(0)
        self.horizontalScrollBar().setValue(0)

    def cancel_preview(self, *, pointer=False):
        self._wheel_steps.reset()
        self.wheel_preview_ply = None
        self._hovered = None
        self._last_pointer_hovered = None
        if self.candidate_rank is not None:
            self.verticalScrollBar().setValue(0)
            self.horizontalScrollBar().setValue(0)
        (self.preview_gap_ended if pointer and self.candidate_rank is not None else self.preview_ended).emit()

    def _fit_height(self, *_):
        if self._auto_fit:
            if self._reserved_lines:
                key = (self.font().key(), self.logicalDpiY(), self._reserved_lines)
                if not self._reserved_measurement or self._reserved_measurement[0] != key:
                    probe = QTextDocument()
                    probe.setDocumentMargin(self.document().documentMargin())
                    probe.setHtml(f'<div style="font-family:Consolas,monospace; font-size:{16 * (1 + self.font_increase / 100)}px; line-height:155%;">'
                                  + '<br/>'.join(['Hg'] * self._reserved_lines) + '</div>')
                    probe.size()  # Force Qt to lay out the reserved sample lines.
                    layout = probe.begin().layout()
                    last = layout.lineAt(layout.lineCount() - 1)
                    height = math.ceil(last.y() + last.height() + 2 * probe.documentMargin()) + 4
                    self._reserved_measurement = (key, height)
                height = self._reserved_measurement[1]
                self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            else:
                self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                height = max(25, math.ceil(self.document().size().height()) + 4)
            if height != self.height():
                self.setFixedHeight(height)

    def reserve_lines(self, count):
        self._reserved_lines = count
        self._fit_height()

    def wrapped_line_count(self):
        """Return the PV's current visual line count at this widget's width."""
        if not self._auto_fit:
            return 0
        # Force the rich text document to lay out against the visible width;
        # the candidate expander is shown when the reserved row clips it.
        document = self.document()
        document.setTextWidth(max(1, self.viewport().width()))
        document.documentLayout().documentSize()
        block = document.begin()
        return block.layout().lineCount() if block.isValid() and block.layout() else 0

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_height()
