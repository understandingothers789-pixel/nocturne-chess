"""Native, interactive visualizations of the actual rating-conditioned policy."""
import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QLabel, QScrollArea, QToolButton, QVBoxLayout, QWidget, QToolTip,
    QComboBox, QSlider, QHBoxLayout, QProgressBar, QApplication,
)
from ..core.board import parse_square
from ..core.notation import san
from ..maia import RATINGS, percentage
from ..maia.blend import move_quality, blend_score
from .board import BoardWidget
from .theme import palette

COLORS = ("#7fbcd2", "#d6b46d", "#a5bc7b", "#bc9cce", "#d89182")


class RatingChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumHeight(165)
        self.setMaximumHeight(230)
        self.setMinimumWidth(210)
        self.policies = {}
        self.moves = []
        self.names = {}
        self.hidden_moves = set()
        self.rating = 1800
        self.points = []

    def sizeHint(self):
        return QSize(300, 190)

    def plot_rect(self):
        return QRectF(36, 10, max(1, self.width()-48), max(1, self.height()-48))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = palette(bool(QApplication.instance().property("nocturneLightAppearance")))
        plot = self.plot_rect()
        maximum = max((p.get(move, 0) for p in self.policies.values() for move in self.moves
                       if move not in self.hidden_moves), default=0)
        ceiling = min(1.0, max(0.25, math.ceil(maximum * 4) / 4))
        painter.setPen(QColor(colors["muted"]))
        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)
        for fraction in (0, 0.5, 1):
            y = plot.bottom()-fraction*plot.height()
            painter.setPen(QPen(QColor(colors["border"]), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(colors["muted"]))
            painter.drawText(QRectF(0, y-7, 32, 15), Qt.AlignmentFlag.AlignRight, f"{fraction*ceiling*100:.0f}%")
        for rating in (400, 1600, 3000):
            x = plot.left()+(rating-400)/2600*plot.width()
            painter.drawText(QRectF(x-20, plot.bottom()+5, 40, 16), Qt.AlignmentFlag.AlignCenter, str(rating))
        painter.drawText(QRectF(plot.left(), plot.bottom()+23, plot.width(), 16), Qt.AlignmentFlag.AlignCenter,
                         "Lichess blitz rating · equal-rated opponents")
        marker = plot.left()+(self.rating-400)/2600*plot.width()
        painter.setPen(QPen(QColor("#bca36a"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(marker, plot.top()), QPointF(marker, plot.bottom()))
        self.points = []
        for index, move in enumerate(self.moves):
            if move in self.hidden_moves:
                continue
            path = QPainterPath()
            started = False
            color = QColor(COLORS[index % len(COLORS)])
            for rating in RATINGS:
                policy = self.policies.get(str(rating))
                if policy is None:
                    started = False
                    continue
                probability = policy.get(move, 0)
                point = QPointF(plot.left()+(rating-400)/2600*plot.width(),
                                plot.bottom()-probability/ceiling*plot.height())
                if started:
                    path.lineTo(point)
                else:
                    path.moveTo(point)
                    started = True
                self.points.append((point, move, rating, probability))
            painter.setPen(QPen(color, 2))
            painter.drawPath(path)
            painter.setBrush(color)
            for point, uci, rating, probability in self.points:
                if uci == move:
                    painter.drawEllipse(point, 2.2 if rating == self.rating else 1.3,
                                        2.2 if rating == self.rating else 1.3)
        if not self.policies:
            painter.setPen(QColor(colors["muted"]))
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "Waiting for Maia predictions")

    def mouseMoveEvent(self, event):
        if self.points:
            nearest = min(self.points, key=lambda item: (item[0]-event.position()).manhattanLength())
            if (nearest[0]-event.position()).manhattanLength() < 28:
                _, move, rating, probability = nearest
                self.setToolTip(f"{self.names.get(move, move)} · {rating} vs {rating}\n{probability*100:.6g}% predicted likelihood")
                QToolTip.showText(event.globalPosition().toPoint(), self.toolTip(), self)
                return
        QToolTip.hideText()
        self.setToolTip("")


class MoveMap(BoardWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(170, 170)
        self.setMaximumHeight(250)
        self.coordinates = False
        self.interactive = False
        self.wheel_navigation = False
        self.policy = {}
        self.destinations = {}

    def sizeHint(self):
        return QSize(230, 230)

    def set_policy(self, board, policy):
        self.set_position(board)
        self.policy = policy
        self.destinations = {}
        for uci, probability in policy.items():
            square = parse_square(uci[2:4])
            self.destinations[square] = self.destinations.get(square, 0) + probability
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        _, unit = self._geometry()
        for square, probability in self.destinations.items():
            color = QColor("#b99dd9")
            color.setAlpha(round(90 * math.sqrt(probability)))
            painter.fillRect(self.square_rect(square).adjusted(1, 1, -1, -1), color)
        for uci, probability in sorted(self.policy.items(), key=lambda item: item[1], reverse=True)[:3]:
            color = QColor("#d5b2ff")
            color.setAlpha(100 + round(probability * 100))
            self._arrow(painter, parse_square(uci[:2]), parse_square(uci[2:4]), color, unit)

    def mouseMoveEvent(self, event):
        square = self.square_at(event.position())
        rows = []
        for uci, probability in sorted(self.policy.items(), key=lambda item: -item[1]):
            if parse_square(uci[2:4]) == square:
                try:
                    rows.append(f"{san(self.board, self.board.parse_uci(uci))}: {percentage(probability)}")
                except ValueError:
                    pass
        self.setToolTip("\n".join(rows))

    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()


class BlenderMeter(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(5)
        title = QLabel("Blender Meter")
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(title)
        self.move = QComboBox()
        self.move.setToolTip("Compare a move without changing the board. Unsearched moves retain unknown Stockfish quality.")
        layout.addWidget(self.move)
        self.human = QProgressBar()
        self.quality = QProgressBar()
        for bar in (self.human, self.quality):
            bar.setRange(0, 1000)
            bar.setFixedHeight(21)
            layout.addWidget(bar)
        self.human.setToolTip("Maia's predicted human move likelihood at the selected rating.")
        self.quality.setToolTip("Nocturne relative Stockfish quality: exp(−centipawn loss / 100).\nOnly searched moves with exact centipawn scores can be compared.")
        endpoints = QHBoxLayout()
        endpoints.addWidget(QLabel("Human"))
        self.weight = QSlider(Qt.Orientation.Horizontal)
        self.weight.setRange(0, 100)
        self.weight.setValue(50)
        self.weight.setToolTip("Blend weight: 0 = Maia likelihood, 100 = relative Stockfish quality.")
        endpoints.addWidget(self.weight, 1)
        endpoints.addWidget(QLabel("Engine"))
        layout.addLayout(endpoints)
        self.result = QLabel("Blend —")
        self.result.setStyleSheet("font-size: 17px; font-weight: 600; color: #b9b4df;")
        layout.addWidget(self.result)
        self.caption = QLabel("Nocturne blend = (1 − weight) × Maia probability + weight × SF quality.")
        self.caption.setObjectName("muted")
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)
        self.policy = {}
        self.lines = {}
        self.move.currentIndexChanged.connect(self.refresh)
        self.weight.valueChanged.connect(self.refresh)

    def set_data(self, policy, board, lines):
        self.policy, self.lines = policy, lines
        selected = self.move.currentData()
        choices = list(dict.fromkeys([line["pv"][0] for line in lines.values() if line.get("pv")]
                       + [uci for uci, _ in sorted(policy.items(), key=lambda item: -item[1])[:5]]))
        key = (board.fen(), tuple(choices))
        if getattr(self, "_choice_key", None) == key:
            self.refresh()
            return
        self._choice_key = key
        self.move.blockSignals(True)
        self.move.clear()
        for uci in choices:
            try:
                self.move.addItem(san(board, board.parse_uci(uci)), uci)
            except ValueError:
                pass
        index = self.move.findData(selected)
        self.move.setCurrentIndex(index if index >= 0 else 0)
        self.move.blockSignals(False)
        self.refresh()

    def refresh(self):
        uci = self.move.currentData()
        probability = self.policy.get(uci)
        quality, loss = move_quality(self.lines, uci)
        self.human.setValue(round((probability or 0)*1000))
        self.human.setFormat("Human likelihood · " + percentage(probability))
        self.quality.setValue(round((quality or 0)*1000))
        self.quality.setFormat(f"SF quality · {quality*100:.1f}% · {loss} cp loss" if quality is not None
                               else "SF quality · not established")
        weight = self.weight.value()/100
        value = blend_score(probability, quality, weight)
        self.result.setText(f"Blend {value*100:.1f}/100 · engine weight {weight:.0%}" if value is not None else "Blend —")


class MaiaInsights(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumWidth(240)
        self.setMaximumWidth(360)
        body = QFrame()
        body.setObjectName("panel")
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(10, 8, 10, 8)
        self.body_layout.setSpacing(6)
        title = QLabel("Moves by Rating")
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.body_layout.addWidget(title)
        self.chart = RatingChart()
        self.chart.setToolTip("Predicted move likelihood, not observed database frequency.\nHover a point for its exact percentage; click a legend to toggle that move.")
        self.body_layout.addWidget(self.chart)
        legend = QWidget()
        self.legend_layout = QGridLayout(legend)
        self.legend_layout.setContentsMargins(0, 0, 0, 0)
        self.legend_buttons = {}
        self.body_layout.addWidget(legend)
        map_title = QLabel("Move Map")
        map_title.setStyleSheet("font-size: 15px; font-weight: 600; padding-top: 5px;")
        self.body_layout.addWidget(map_title)
        self.map = MoveMap()
        self.map.setToolTip("Destination intensity sums Maia probabilities; arrows show the three likeliest moves.")
        self.body_layout.addWidget(self.map)
        caption = QLabel("Brighter destinations are more likely. Hover a square for its moves.")
        caption.setWordWrap(True)
        caption.setObjectName("muted")
        self.body_layout.addWidget(caption)
        self.blender = BlenderMeter()
        self.body_layout.addWidget(self.blender)
        self.body_layout.addStretch()
        self.setWidget(body)

    def set_data(self, policies, board, rating, appearance=None):
        policy = policies.get(str(rating), {})
        moves = [move for move, _ in sorted(policy.items(), key=lambda item: -item[1])[:5]]
        self.chart.policies = policies
        self.chart.rating = rating
        if moves != self.chart.moves:
            while self.legend_layout.count():
                item = self.legend_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self.legend_buttons = {}
            self.chart.moves = moves
            self.chart.names = {}
            for index, move in enumerate(moves):
                try:
                    name = san(board, board.parse_uci(move))
                except ValueError:
                    continue
                self.chart.names[move] = name
                button = QToolButton()
                button.setText(name)
                button.setCheckable(True)
                button.setChecked(move not in self.chart.hidden_moves)
                button.setStyleSheet(f"color: {COLORS[index]}; padding: 2px 5px;")
                button.toggled.connect(lambda checked, uci=move: self._toggle_curve(uci, checked))
                self.legend_layout.addWidget(button, index//3, index % 3)
                self.legend_buttons[move] = button
        self.chart.update()
        if appearance:
            self.map.theme = appearance.get("theme", "Classic")
            self.map.set_piece_set(appearance.get("piece_set", "Nibbler"))
        self.map.set_policy(board, policy)

    def _toggle_curve(self, uci, checked):
        if checked:
            self.chart.hidden_moves.discard(uci)
        else:
            self.chart.hidden_moves.add(uci)
        self.chart.update()
