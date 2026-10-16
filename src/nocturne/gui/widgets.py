"""Small native visualizations, driven exclusively by actual engine samples."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class EvaluationBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(23)
        self.score: int | None = None
        self.flipped = False
        self.board_view = None

    def set_score(self, score: int | None):
        self.score = score
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.board_view is not None:
            board_rect, _ = self.board_view._geometry()
            rect = QRectF(5, board_rect.y(), 12, board_rect.height())
        else:
            rect = QRectF(5, 24, 12, self.height() - 48)
        path = QPainterPath()
        path.addRoundedRect(rect, 5, 5)
        p.setClipPath(path)
        p.fillRect(rect, QColor("#2b3e33"))
        fraction = .5 if self.score is None else 1 / (1 + math.exp(-max(-2000, min(2000, self.score)) / 250))
        if self.flipped:
            white = QRectF(rect.x(), rect.y(), rect.width(), rect.height() * fraction)
        else:
            white = QRectF(rect.x(), rect.bottom() - rect.height() * fraction, rect.width(), rect.height() * fraction)
        p.fillRect(white, QColor("#e6ebd9") if self.score is not None else QColor("#7d9081"))
        p.setClipping(False)
        p.setPen(QPen(QColor("#91b37d"), 1))
        p.drawLine(QPointF(2, rect.center().y()), QPointF(20, rect.center().y()))


class EvaluationGraph(QWidget):
    position_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(105)
        self.setMaximumHeight(135)
        self.samples: dict[int, int] = {}
        self.cursor = 0
        self.total = 0
        self.light = False

    def set_samples(self, samples: dict[int, int], cursor: int, total: int):
        self.samples = samples.copy()
        self.cursor, self.total = cursor, total
        self.update()

    def _point(self, ply, score):
        return QPointF(8 + (self.width() - 16) * ply / max(1, self.total),
                       self.height() / 2 - math.tanh(score / 500) * (self.height() / 2 - 12))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#c0ccba" if self.light else "#34493b"), 1, Qt.PenStyle.DashLine))
        p.drawLine(8, self.height() // 2, self.width() - 8, self.height() // 2)
        if not self.samples:
            p.setPen(QColor("#819386"))
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Evaluation samples appear here")
            return
        path = QPainterPath()
        points = [(ply, self._point(ply, score)) for ply, score in sorted(self.samples.items())]
        path.moveTo(points[0][1])
        for _, point in points[1:]:
            path.lineTo(point)
        accent = QColor("#507a3f" if self.light else "#b5d99d")
        p.setPen(QPen(accent, 2))
        p.drawPath(path)
        p.setBrush(accent)
        p.setPen(Qt.PenStyle.NoPen)
        for ply, point in points:
            p.drawEllipse(point, 4 if ply == self.cursor else 2.3, 4 if ply == self.cursor else 2.3)
        x = self._point(self.cursor, 0).x()
        p.setPen(QPen(QColor("#7b9a78"), 1))
        p.drawLine(QPointF(x, 8), QPointF(x, self.height() - 8))

    def mousePressEvent(self, event):
        if self.samples and event.button() == Qt.MouseButton.LeftButton:
            nearest = min(self.samples, key=lambda ply: abs(self._point(ply, 0).x() - event.position().x()))
            self.position_requested.emit(nearest)
