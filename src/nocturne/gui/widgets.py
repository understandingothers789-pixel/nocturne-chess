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
        self._extent = 2.0
        self._context = None
        self.setAccessibleName("Evaluation history · White perspective · linear near zero, logarithmic beyond one pawn")

    def set_samples(self, samples: dict[int, int], cursor: int, total: int, *, context=None):
        self.samples = samples.copy()
        if total != self.total or context != self._context:
            self.view_start = 0.0
            self.view_end = None
        elif self.view_end is not None and cursor != self.cursor:
            # Keep a manually zoomed range useful while the game cursor moves:
            # follow the cursor at either edge without changing the zoom level.
            span = max(2.0, self.view_end - self.view_start)
            if cursor > self.view_end:
                self.view_end = float(cursor)
                self.view_start = max(0.0, self.view_end - span)
            elif cursor < self.view_start:
                self.view_start = float(cursor)
                self.view_end = self.view_start + span
        self.cursor, self.total = cursor, total
        self._context = context
        self._update_extent()
        if self.hover_ply not in self._visible_samples():
            self.hover_ply = None
        self.update()

    def _view_bounds(self):
        return self.view_start, (max(1, self.cursor) if self.view_end is None else self.view_end)

    def _visible_samples(self):
        start, end = self._view_bounds()
        return {ply: score for ply, score in self.samples.items() if start <= ply <= end}

    def _update_extent(self):
        ordinary = [abs(score) for score in self._visible_samples().values() if abs(score) < 29000]
        self._extent = max(2.0, self._compressed(max(ordinary, default=0)) * 1.12)

    @staticmethod
    def _compressed(score):
        pawns = abs(score) / 100
        distance = pawns if pawns <= 1 else 1 + math.log2(pawns)
        return math.copysign(distance, score)

    def _plot_rect(self):
        return QRectF(39, 12, max(1, self.width() - 47), max(1, self.height() - 24))

    def _point(self, ply, score):
        # In the default view, reveal the graph only through the selected ply.
        # This gives opening and middle-game positions a useful horizontal scale
        # instead of reserving most of the width for moves the user has not reached.
        start, end = self._view_bounds()
        rect = self._plot_rect()
        # Mate sentinels sit at the edge; they never flatten normal cp samples.
        fraction = math.copysign(1.0, score) if abs(score) >= 29000 else self._compressed(score) / self._extent
        return QPointF(
            rect.left() + rect.width() * (ply - start) / max(1, end - start),
            rect.center().y() - fraction * rect.height() / 2,
        )

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = palette(self.light)
        rect = self._plot_rect()
        p.setFont(QFont("Segoe UI", 8))
        for score, label in ((100, "+1.00"), (-100, "−1.00")):
            y = self._point(0, score).y()
            p.setPen(QPen(QColor(colors["metadata"]), 1, Qt.PenStyle.DotLine))
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            label_y = min(y - 8, rect.center().y() - 18) if score > 0 else max(y - 8, rect.center().y() + 2)
            p.drawText(QRectF(0, label_y, 34, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
            if abs(label_y + 8 - y) > 1:
                p.setPen(QPen(QColor(colors["border"]), 1))
                p.drawLine(QPointF(35, label_y + 8), QPointF(rect.left(), y))
        center_line = QColor(colors["border"])
        center_line.setAlpha(95)
        p.setPen(QPen(center_line, 1))
        p.drawLine(QPointF(rect.left(), rect.center().y()), QPointF(rect.right(), rect.center().y()))
        x = self._point(self.cursor, 0).x()
        if rect.left() <= x <= rect.right():
            p.setPen(QPen(QColor(colors["metric"]), 1, Qt.PenStyle.DotLine))
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        visible = self._visible_samples()
        if not visible:
            p.setPen(QColor(colors["muted"]))
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No evaluations in this range")
            return
        p.save()
        p.setClipRect(rect.adjusted(-1, -3, 1, 3))
        path = QPainterPath()
        points = [(ply, self._point(ply, score)) for ply, score in sorted(visible.items())]
        path.moveTo(points[0][1])
        for index in range(1, len(points)):
            prior = points[index - 1][1]
            current = points[index][1]
            middle = (prior.x() + current.x()) / 2
            path.cubicTo(QPointF(middle, prior.y()), QPointF(middle, current.y()), current)
        accent = QColor(colors["accent"])
        fill = QPainterPath(path)
        fill.lineTo(points[-1][1].x(), rect.bottom())
        fill.lineTo(points[0][1].x(), rect.bottom())
        fill.closeSubpath()
        accent_fill = QColor(accent)
        accent_fill.setAlpha(22)
        p.fillPath(fill, accent_fill)
        p.setPen(QPen(accent, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
        p.setBrush(accent)
        p.setPen(Qt.PenStyle.NoPen)
        for ply, point in points:
            if ply == self.cursor:
                p.setBrush(QColor(colors["panel"]))
                p.setPen(QPen(accent, 1.8))
                p.drawEllipse(point, 3.4, 3.4)
                p.setBrush(accent)
                p.setPen(Qt.PenStyle.NoPen)
            else:
                p.setBrush(accent_fill)
                p.drawEllipse(point, 1.8, 1.8)
        p.restore()
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
        visible = self._visible_samples()
        if visible and event.button() == Qt.MouseButton.LeftButton and self._plot_rect().contains(event.position()):
            nearest = min(visible, key=lambda ply: abs(self._point(ply, 0).x() - event.position().x()))
            self.position_requested.emit(nearest)

    def mouseMoveEvent(self, event):
        if self._pan_x is not None:
            start, end = self._view_bounds()
            span = max(1, end - start)
            delta = (self._pan_x - event.position().x()) * span / self._plot_rect().width()
            start = min(max(0, start + delta), max(0, self.total - span))
            self.view_start, self.view_end = start, start + span
            self._pan_x = event.position().x()
            self._update_extent()
        visible = self._visible_samples()
        self.hover_ply = None
        if visible:
            self.hover_ply = min(
                visible, key=lambda ply: abs(self._point(ply, 0).x() - event.position().x())
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
        start, end = self._view_bounds()
        span = max(1, end - start)
        rect = self._plot_rect()
        fraction = min(1, max(0, (event.position().x() - rect.left()) / rect.width()))
        center = start + fraction * span
        span = min(self.total, max(2, span * (0.75 if event.angleDelta().y() > 0 else 1.33)))
        self.view_start = min(max(0, center - fraction * span), self.total - span)
        self.view_end = self.view_start + span
        self._update_extent()
        self.update()
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.view_start = 0
        self.view_end = None
        self._update_extent()
        self.update()
