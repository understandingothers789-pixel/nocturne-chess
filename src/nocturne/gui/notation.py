"""Lichess chess-notation glyph rendering shared by move views."""
from html import escape

from PySide6.QtCore import QRectF
from PySide6.QtGui import QFontDatabase, QFont, QPainter, QPalette
from PySide6.QtWidgets import QStyle, QStyleOptionToolButton, QStylePainter, QToolButton

from pathlib import Path
ASSETS = Path(__file__).resolve().parents[1] / "assets"

_FAMILY = None
_PIECES = frozenset("KQRBN")


def family():
    global _FAMILY
    if _FAMILY is None:
        font_id = QFontDatabase.addApplicationFont(str(ASSETS / "fonts/lichess-notation.ttf"))
        names = QFontDatabase.applicationFontFamilies(font_id)
        _FAMILY = names[0] if names else "Segoe UI Symbol"
    return _FAMILY


def html(text, *, size=17):
    face = escape(family(), quote=True)
    return "".join(f'<span style="font-family:{face};font-size:{size}px;">{c}</span>'
                   if c in _PIECES else escape(c) for c in str(text))


def draw(painter: QPainter, x: float, y: float, text: str):
    """Draw SAN with its piece glyphs and ordinary text on one baseline."""
    regular = painter.font()
    piece_font = QFont(family(), regular.pointSize())
    piece_font.setPixelSize(max(12, regular.pixelSize() or regular.pointSize() * 4 // 3))
    for char in str(text):
        active = piece_font if char in _PIECES else regular
        painter.setFont(active)
        painter.drawText(QRectF(x, y - painter.fontMetrics().ascent(), 2000,
                                painter.fontMetrics().height()), char)
        x += painter.fontMetrics().horizontalAdvance(char)
    painter.setFont(regular)


class FigurineToolButton(QToolButton):
    """A normal tool button whose visible SAN uses Lichess piece glyphs."""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self._notation = str(text)
        self.setText("")
        self.setAccessibleName(self._notation)

    def paintEvent(self, event):
        option = QStyleOptionToolButton()
        self.initStyleOption(option)
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ToolButton, option)
        painter.end()

        painter = QPainter(self)
        painter.setPen(self.palette().color(QPalette.ColorRole.ButtonText))
        font = self.font()
        font.setPixelSize(14)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(self._notation)
        draw(painter, (self.width() - width) / 2, (self.height() + metrics.ascent() - metrics.descent()) / 2,
             self._notation)
