"""Flowing move text with reversible hover and explicit click signals."""

from html import escape
import math

from PySide6.QtCore import QEvent, QPoint, Signal, Qt, QUrl
from PySide6.QtGui import QTextDocument, QTextCursor, QTextOption
from PySide6.QtWidgets import QTextBrowser
from .theme import palette
from .wheel import WheelSteps


class MoveText(QTextBrowser):
    wheel_navigated = Signal(int)
    move_hovered = Signal(int)
    move_clicked = Signal(int)
    preview_ended = Signal()
    pointer_moved = Signal(QPoint)
    manual_navigation = Signal()

    def __init__(self, parent=None, *, auto_fit=False, reserved_lines=0):
        super().__init__(parent)
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
        if index == self._hovered:
            return
        self._hovered = index
        if index is None:
            self.preview_ended.emit()
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
        self.preview_ended.emit()
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
        if event.type() == QEvent.Type.Leave:
            self.cancel_preview()
        return super().viewportEvent(event)

    def set_moves(self, items, current=None, light=False, *, book_departure=None, book_departures=None):
        signature = (list(items), current, light)
        candidate_style = (self.candidate_rank, self.candidate_turn, self.candidate_evaluation)
        departures = dict(book_departures or {})
        if book_departure is not None and book_departure not in departures:
            departures[book_departure] = "Lichess Masters: first position with no games found"
        if (signature == (self._items, self._current, self._light)
                and candidate_style == self._candidate_style and book_departure == self._book_departure
                and departures == self._book_departures):
            return
        self.preview_ended.emit()
        self._hovered = None
        self._last_pointer_hovered = None
        self._items, self._current, self._light = signature
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
            tokens.append(f'<span style="color:{colors["metric"]};">'
                          f'{escape(self.candidate_evaluation)}</span>')
        for text, index in self._items:
            if index is None:
                tokens.append(escape(text))
                continue
            move_color = color
            if self.candidate_rank is not None:
                side = self.candidate_turn if index % 2 else -self.candidate_turn
                move_color = colors["analysis_white" if side > 0 else "analysis_black"]
            style = (f'color: {colors["selected_text"]}; background-color: {colors["selection"]};'
                     if index == current else f"color: {move_color};")
            if index in departures:
                tint = "#87713f" if light else "#c3b07c"
                style += f"color: {tint};"
            # Keep SAN slots identical across candidates and updates. Nonbreaking
            # padding belongs to the anchor, so the whole slot is interactive.
            label = ("\u00a0" + text + "\u00a0" * max(1, 8 - len(text))
                     if self.candidate_rank is not None else text)
            decoration = "text-decoration:none;"
            tooltip = f' title="{escape(departures[index], quote=True)}"' if index in departures else ""
            tokens.append(f'<a href="move:{index}" style="{style} {decoration}"{tooltip}>{escape(label)}</a>')
        size, spacing = (16, 155) if self._auto_fit else (14, 140)
        self.setHtml(f'<div style="font-family:Consolas,monospace; font-size:{size}px; line-height:{spacing}%;">'
                     + " ".join(tokens) + "</div>")

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
                    cursor.setPosition(fragment.position() + fragment.length() - 1)
                    end = self.cursorRect(cursor)
                    rect = start.united(end).adjusted(0, -3, 9, 3)
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
        # Keep the previewed move visible even when the three-row slot scrolls.
        block = self.document().begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().anchorHref() == f"move:{ply}":
                    cursor = QTextCursor(self.document())
                    cursor.setPosition(fragment.position())
                    self.setTextCursor(cursor)
                    self.ensureCursorVisible()
                    return
                iterator += 1
            block = block.next()

    def cancel_preview(self):
        self.wheel_preview_ply = None
        self._hovered = None
        self._last_pointer_hovered = None
        self.preview_ended.emit()

    def _fit_height(self, *_):
        if self._auto_fit:
            if self._reserved_lines:
                key = (self.font().key(), self.logicalDpiY(), self._reserved_lines)
                if not self._reserved_measurement or self._reserved_measurement[0] != key:
                    probe = QTextDocument()
                    probe.setDocumentMargin(self.document().documentMargin())
                    probe.setHtml('<div style="font-family:Consolas,monospace; font-size:16px; line-height:155%;">'
                                  + '<br/>'.join(['Hg'] * self._reserved_lines) + '</div>')
                    probe.size()  # Force Qt to lay out the three sample lines.
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
        # the candidate expander is shown only when the two fixed rows clip it.
        document = self.document()
        document.setTextWidth(max(1, self.viewport().width()))
        document.documentLayout().documentSize()
        block = document.begin()
        return block.layout().lineCount() if block.isValid() and block.layout() else 0

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_height()
