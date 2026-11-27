"""Small native visualizations, driven exclusively by actual engine samples."""

import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, Signal, QSize, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QStylePainter
from .theme import palette


class ElidedLabel(QLabel):
    """Show one line with the complete text available on hover."""

    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)

    def paintEvent(self, event):
        painter = QStylePainter(self)
        text = self.fontMetrics().elidedText(
            self.text(), Qt.TextElideMode.ElideRight, self.contentsRect().width()
        )
        painter.drawItemText(self.contentsRect(), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                             self.palette(), self.isEnabled(), text, self.foregroundRole())


class AnalysisHeader(QWidget):
    """Keep the full engine name readable alongside review and evaluation."""

    def __init__(self, state, review, evaluation, parent=None):
        super().__init__(parent)
        self.state, self.review, self.evaluation = state, review, evaluation
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.state.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._narrow = None
        self._arrange(False)

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        ancestor = self.parentWidget()
        available = self.width()
        while ancestor is not None:
            if isinstance(ancestor, QScrollArea):
                available = ancestor.viewport().width()
                break
            ancestor = ancestor.parentWidget()
        self._arrange(available < 430)

    def _arrange(self, narrow):
        if narrow == self._narrow:
            return
        self._narrow = narrow
        while self.grid.count():
            self.grid.takeAt(0)
        for column in range(3):
            self.grid.setColumnStretch(column, 0)
        if narrow:
            self.grid.addWidget(self.state, 0, 0, 1, 2)
            self.grid.addWidget(self.review, 1, 0, Qt.AlignmentFlag.AlignLeft)
            self.grid.addWidget(self.evaluation, 1, 1, Qt.AlignmentFlag.AlignRight)
            self.grid.setColumnStretch(0, 1)
        else:
            for column, widget in enumerate((self.state, self.review, self.evaluation)):
                self.grid.addWidget(widget, 0, column)
            self.grid.setColumnStretch(0, 1)


class EngineLineHeading(QWidget):
    """Keep history actions and the Maia label readable on one line."""

    def __init__(self, engine, history, details, maia, parent=None):
        super().__init__(parent)
        self.history, self.details = history, details
        self._compact = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(engine, 1)
        layout.addWidget(history)
        layout.addWidget(details)
        layout.addSpacing(12)
        layout.addWidget(maia)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._set_compact(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._set_compact(event.size().width() < 365)

    def _set_compact(self, compact):
        if compact == self._compact:
            return
        self._compact = compact
        self.history.setText("History" if compact else "Analysis history")
        self.details.setText("Options" if compact else "More details")


class EvaluationBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(25)
        self.setAccessibleName("Board evaluation bar")
        self.score: int | None = None
        self.flipped = False
        self.light = False
        self.board_view = None
        self._fraction = 0.5
        self._slide = QVariantAnimation(self)
        self._slide.setDuration(210)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide.valueChanged.connect(self._slide_to)

    def set_score(self, score: int | None):
        if self.score == score:
            return
        self.score = score
        self._slide.stop()
        if score is not None:
            cp = (math.copysign((21 - min(10, 30000 - abs(score))) * 100, score)
                  if 29001 <= abs(score) <= 30000 else max(-1000, min(1000, score)))
            fraction = (1 + math.tanh(0.00184104 * cp)) / 2
            self._slide.setStartValue(self._fraction)
            self._slide.setEndValue(fraction)
            self._slide.start()
        self.update()

    def _slide_to(self, fraction):
        self._fraction = fraction
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.board_view is not None:
            board_rect, _ = self.board_view._geometry()
            rect = QRectF(3, board_rect.y(), self.width() - 6, board_rect.height())
        else:
            rect = QRectF(3, 6, self.width() - 6, self.height() - 12)
        path = QPainterPath()
        path.addRoundedRect(rect, 4, 4)
        if self.score is None:
            p.setOpacity(0.5)
        p.setClipPath(path)
        p.fillRect(rect, QColor("#606060" if self.light else "#444444"))
        height = rect.height() * self._fraction
        white = QRectF(rect.x(), rect.y() if self.flipped else rect.bottom() - height, rect.width(), height)
        p.fillRect(white, QColor("#ffffff" if self.light else "#c0c0c0"))
        for tick in range(1, 8):
            y = rect.top() + rect.height() * tick / 8
            if tick == 4:
                p.setPen(QPen(QColor("#479ed0"), 3))
            else:
                p.setPen(QPen(QColor(120, 120, 120, 125), 1))
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        p.setClipping(False)
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


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
        # Engine telemetry often changes without changing a plotted score.
        # Avoid copying the history and scheduling an identical repaint.
        if (samples == self.samples and cursor == self.cursor
                and total == self.total and context == self._context):
            return
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
