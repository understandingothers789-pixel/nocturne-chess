"""Flowing move text with reversible hover and explicit click signals."""

from html import escape
import math

from PySide6.QtCore import QEvent, Signal, Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QTextBrowser
from .theme import palette


class MoveText(QTextBrowser):
    move_hovered = Signal(int)
    move_clicked = Signal(int)
    preview_ended = Signal()

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
        self._hovered = None
        self.preview_ended.emit()
        super().leaveEvent(event)

    def focusOutEvent(self, event):
        self._hovered = None
        self.preview_ended.emit()
        super().focusOutEvent(event)

    def hideEvent(self, event):
        self.cancel_preview()
        super().hideEvent(event)

    def viewportEvent(self, event):
        if event.type() == QEvent.Type.Leave:
            self.cancel_preview()
        return super().viewportEvent(event)

    def set_moves(self, items, current=None, light=False):
        signature = (list(items), current, light)
        if signature == (self._items, self._current, self._light):
            return
        self.preview_ended.emit()
        self._hovered = None
        self._items, self._current, self._light = signature
        colors = palette(light)
        color = colors["text"]
        tokens = []
        for text, index in self._items:
            if index is None:
                tokens.append(escape(text))
                continue
            style = (f'color: {colors["selected_text"]}; background-color: {colors["selection"]};'
                     if index == current else f"color: {color};")
            tokens.append(f'<a href="move:{index}" style="{style} text-decoration:none;">{escape(text)}</a>')
        size, spacing = (16, 145) if self._auto_fit else (14, 160)
        self.setHtml(f'<div style="font-family:Consolas,monospace; font-size:{size}px; line-height:{spacing}%;">'
                     + " &nbsp; ".join(tokens) + "</div>")

    def cancel_preview(self):
        self._hovered = None
        self.preview_ended.emit()

    def _fit_height(self, *_):
        if self._auto_fit:
            if self._reserved_lines:
                key = (self.font().key(), self.logicalDpiY(), self._reserved_lines)
                if not self._reserved_measurement or self._reserved_measurement[0] != key:
                    probe = QTextDocument()
                    probe.setDocumentMargin(self.document().documentMargin())
                    probe.setHtml('<div style="font-family:Consolas,monospace; font-size:16px; line-height:145%;">'
                                  + '<br/>'.join(['Hg'] * self._reserved_lines) + '</div>')
                    self._reserved_measurement = (key, math.ceil(probe.size().height()) + 4)
                height = self._reserved_measurement[1]
                self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            else:
                height = max(25, math.ceil(self.document().size().height()) + 4)
            if height != self.height():
                self.setFixedHeight(height)

    def reserve_lines(self, count):
        self._reserved_lines = count
        self._fit_height()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_height()
