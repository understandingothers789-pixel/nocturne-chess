"""Flowing move text with reversible hover and explicit click signals."""

from html import escape

from PySide6.QtCore import QEvent, Signal, Qt
from PySide6.QtWidgets import QTextBrowser


class MoveText(QTextBrowser):
    move_hovered = Signal(int)
    move_clicked = Signal(int)
    preview_ended = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
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
            self.preview_ended.emit()
            self.move_clicked.emit(int(text[5:]))

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
        color = "#21372c" if light else "#e3ecd8"
        tokens = []
        for text, index in self._items:
            style = "color: #19291c; background-color: #b5d99d;" if index == current else f"color: {color};"
            tokens.append(f'<a href="move:{index}" style="{style} text-decoration:none;">{escape(text)}</a>')
        self.setHtml('<div style="font-family:Consolas,monospace; font-size:14px; line-height:160%;">'
                     + " &nbsp; ".join(tokens) + "</div>")

    def cancel_preview(self):
        self._hovered = None
        self.preview_ended.emit()
