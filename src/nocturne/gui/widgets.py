"""Small native visualizations, driven exclusively by actual engine samples."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget
from .theme import palette


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
        p.fillRect(rect, QColor("#282828"))
        fraction = 0.5 if self.score is None else 1 / (1 + math.exp(-max(-2000, min(2000, self.score)) / 250))
        if self.flipped:
            white = QRectF(rect.x(), rect.y(), rect.width(), rect.height() * fraction)
        else:
            white = QRectF(
                rect.x(), rect.bottom() - rect.height() * fraction, rect.width(), rect.height() * fraction
            )
        p.fillRect(white, QColor("#f2f2f0") if self.score is not None else QColor("#898989"))
        p.setClipping(False)
        p.setPen(QPen(QColor("#999999"), 1))
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
        self.setMouseTracking(True)
        self.view_start = 0.0
        self.view_end = None
        self.hover_ply = None
        self._pan_x = None

    def set_samples(self, samples: dict[int, int], cursor: int, total: int):
        self.samples = samples.copy()
        if total != self.total:
            self.view_start = 0.0
            self.view_end = None
        self.cursor, self.total = cursor, total
        self.update()

    def _point(self, ply, score):
        end = self.total if self.view_end is None else self.view_end
        return QPointF(
            8 + (self.width() - 16) * (ply - self.view_start) / max(1, end - self.view_start),
            self.height() / 2 - math.tanh(score / 500) * (self.height() / 2 - 12),
        )

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = palette(self.light)
        p.setPen(QPen(QColor(colors["border"]), 1, Qt.PenStyle.DashLine))
        p.drawLine(8, self.height() // 2, self.width() - 8, self.height() // 2)
        if not self.samples:
            p.setPen(QColor(colors["muted"]))
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Evaluation samples appear here")
            return
        path = QPainterPath()
        points = [(ply, self._point(ply, score)) for ply, score in sorted(self.samples.items())]
        path.moveTo(points[0][1])
        for _, point in points[1:]:
            path.lineTo(point)
        accent = QColor(colors["accent"])
        p.setPen(QPen(accent, 2))
        p.drawPath(path)
        p.setBrush(accent)
        p.setPen(Qt.PenStyle.NoPen)
        for ply, point in points:
            p.drawEllipse(point, 4 if ply == self.cursor else 2.3, 4 if ply == self.cursor else 2.3)
        x = self._point(self.cursor, 0).x()
        p.setPen(QPen(QColor(colors["muted"]), 1))
        p.drawLine(QPointF(x, 8), QPointF(x, self.height() - 8))
        if self.hover_ply is not None and self.hover_ply in self.samples:
            value = self.samples[self.hover_ply]
            text = (
                f"Ply {self.hover_ply} · White {value / 100:+.2f}"
                if abs(value) < 29000
                else f"Ply {self.hover_ply} · mate score"
            )
            p.setFont(QFont("Segoe UI", 9))
            p.setPen(accent)
            p.drawText(QRectF(8, 0, self.width() - 16, 20), Qt.AlignmentFlag.AlignRight, text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_x = event.position().x()
            return
        if self.samples and event.button() == Qt.MouseButton.LeftButton:
            nearest = min(self.samples, key=lambda ply: abs(self._point(ply, 0).x() - event.position().x()))
            self.position_requested.emit(nearest)

    def mouseMoveEvent(self, event):
        if self._pan_x is not None:
            end = self.total if self.view_end is None else self.view_end
            span = max(1, end - self.view_start)
            delta = (self._pan_x - event.position().x()) * span / max(1, self.width() - 16)
            start = min(max(0, self.view_start + delta), max(0, self.total - span))
            self.view_start, self.view_end = start, start + span
            self._pan_x = event.position().x()
        if self.samples:
            self.hover_ply = min(
                self.samples, key=lambda ply: abs(self._point(ply, 0).x() - event.position().x())
            )
        self.update()

    def mouseReleaseEvent(self, event):
        self._pan_x = None

    def leaveEvent(self, event):
        self.hover_ply = None
        self._pan_x = None
        self.update()

    def wheelEvent(self, event):
        if self.total < 2:
            return
        end = self.total if self.view_end is None else self.view_end
        span = max(1, end - self.view_start)
        fraction = min(1, max(0, (event.position().x() - 8) / max(1, self.width() - 16)))
        center = self.view_start + fraction * span
        span = min(self.total, max(2, span * (0.75 if event.angleDelta().y() > 0 else 1.33)))
        self.view_start = min(max(0, center - fraction * span), self.total - span)
        self.view_end = self.view_start + span
        self.update()
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.view_start = 0
        self.view_end = None
        self.update()
