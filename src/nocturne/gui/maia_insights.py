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

COLORS = ("#8ed5ef", "#d6b46d", "#91c6a4", "#c2a7eb", "#e3a394")
LIGHT_COLORS = ("#197b9c", "#a16c22", "#377e56", "#7b50a8", "#b95844")


def curve_colors():
    return LIGHT_COLORS if QApplication.instance().property("nocturneLightAppearance") else COLORS


class InsightCard(QFrame):
    def __init__(self, number, title, parent=None):
        super().__init__(parent)
        self.setObjectName("insightCard")
        self.content = QVBoxLayout(self)
        self.content.setContentsMargins(10, 8, 10, 9)
        self.content.setSpacing(5)
        self.heading = QHBoxLayout()
        self.heading.setSpacing(7)
        index = QLabel(number)
        index.setObjectName("sectionNumber")
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        self.heading.addWidget(index)
        self.heading.addWidget(title_label, 1)
        self.content.addLayout(self.heading)



class RatingChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumHeight(140)
        self.setMaximumHeight(160)
        self.setMinimumWidth(210)
        self.policies = {}
        self.moves = []
        self.names = {}
        self.hidden_moves = set()
        self.rating = 1800
        self.points = []

    def sizeHint(self):
        return QSize(300, 150)

    def plot_rect(self):
        return QRectF(34, 12, max(1, self.width()-46), max(1, self.height()-42))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = palette(bool(QApplication.instance().property("nocturneLightAppearance")))
        plot = self.plot_rect()
        maximum = max((p.get(move, 0) for p in self.policies.values() for move in self.moves
                       if move not in self.hidden_moves), default=0)
        ceiling = min(1.0, max(0.25, math.ceil(maximum * 4) / 4))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors["soft"]))
        painter.drawRoundedRect(plot.adjusted(-3, -5, 3, 4), 5, 5)
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
            painter.drawText(QRectF(max(0, min(self.width()-40, x-20)), plot.bottom()+5, 40, 16), Qt.AlignmentFlag.AlignCenter, str(rating))

        marker = plot.left()+(self.rating-400)/2600*plot.width()
        painter.setPen(QPen(QColor("#bca36a"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(marker, plot.top()), QPointF(marker, plot.bottom()))
        self.points = []
        for index, move in enumerate(self.moves):
            if move in self.hidden_moves:
                continue
            path = QPainterPath()
            started = False
            color = QColor(curve_colors()[index % len(COLORS)])
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
        self.setMaximumHeight(190)
        self.setMaximumWidth(230)
        self.coordinates = False
        self.interactive = False
        self.wheel_navigation = False
        self.policy = {}
        self.destinations = {}

    def sizeHint(self):
        return QSize(190, 190)

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


class BlenderMeter(InsightCard):
    def __init__(self, parent=None):
        super().__init__("03", "Blender Meter", parent)
        layout = self.content
        self.move = QComboBox()
        self.move.setObjectName("blendChoice")
        self.move.setToolTip("Compare a move without changing the board. Unsearched moves retain unknown Stockfish quality.")
        layout.addWidget(self.move)
        self.human = QProgressBar()
        self.quality = QProgressBar()
        self.human.setObjectName("humanMeter")
        self.quality.setObjectName("qualityMeter")
        for bar in (self.human, self.quality):
            bar.setRange(0, 1000)
            bar.setFixedHeight(19)
            layout.addWidget(bar)
        self.human.setToolTip("Maia's predicted human move likelihood at the selected rating.")
        self.quality.setToolTip("Nocturne relative Stockfish quality: exp(−centipawn loss / 100).\nOnly searched moves with exact centipawn scores can be compared.")
        self.loss_label = QLabel()
        self.loss_label.setObjectName("sectionNote")
        self.loss_label.setWordWrap(True)
        layout.addWidget(self.loss_label)
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
        self.result.setObjectName("blendResult")
        layout.addWidget(self.result)
        self.weight_caption = QLabel()
        self.weight_caption.setObjectName("sectionNote")
        layout.addWidget(self.weight_caption)
        self.caption = QLabel("Nocturne comparison score · how it works ⓘ")
        self.caption.setObjectName("sectionNote")
        self.caption.setToolTip("Blend = 100 × ((1 − engine weight) × Maia probability + engine weight × SF quality).\n"
                                "SF quality = exp(−centipawn loss / 100). This is not a win probability or an official Maia statistic.")
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
        self.human.setFormat("Human likelihood  " + percentage(probability))
        self.quality.setValue(round((quality or 0)*1000))
        self.quality.setFormat(f"Engine quality  {quality*100:.1f}%" if quality is not None else "Engine quality  —")
        self.loss_label.setText(f"{loss} cp loss from the best searched move" if loss is not None
                                else "An exact Stockfish comparison is not available yet.")
        weight = self.weight.value()/100
        value = blend_score(probability, quality, weight)
        self.result.setText(f"{value*100:.1f} / 100" if value is not None else "— / 100")
        self.weight_caption.setText(f"{1-weight:.0%} human · {weight:.0%} engine")


class MaiaInsights(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumWidth(240)
        self.setMaximumWidth(360)
        body = QWidget()
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(8)
        trends = InsightCard("01", "Moves by Rating")
        self.rating_chip = QLabel("1800")
        self.rating_chip.setObjectName("sectionNumber")
        self.rating_chip.setToolTip("Selected Lichess blitz rating; opponent has the same rating.")
        trends.heading.addWidget(self.rating_chip)
        self.chart = RatingChart()
        self.chart.setToolTip("Predicted likelihood across equal-rated opponents. Hover a point for its exact percentage; click a legend to toggle a curve.")
        trends.content.addWidget(self.chart)
        legend = QWidget()
        self.legend_layout = QGridLayout(legend)
        self.legend_layout.setContentsMargins(0, 0, 0, 0)
        self.legend_layout.setSpacing(3)
        self.legend_buttons = {}
        trends.content.addWidget(legend)
        self.body_layout.addWidget(trends)
        move_map = InsightCard("02", "Move Map")
        self.map = MoveMap()
        self.map.setToolTip("Destination intensity sums Maia probabilities; arrows show the three likeliest moves.")
        move_map.content.addWidget(self.map, 0, Qt.AlignmentFlag.AlignHCenter)
        caption = QLabel("Brighter squares are more likely. Hover to inspect.")
        caption.setWordWrap(True)
        caption.setObjectName("sectionNote")
        move_map.content.addWidget(caption)
        self.body_layout.addWidget(move_map)
        self.blender = BlenderMeter()
        self.body_layout.addWidget(self.blender)
        self.body_layout.addStretch()
        self.setWidget(body)

    def set_data(self, policies, board, rating, appearance=None):
        policy = policies.get(str(rating), {})
        moves = [move for move, _ in sorted(policy.items(), key=lambda item: -item[1])[:5]]
        self.chart.policies = policies
        self.chart.rating = rating
        self.rating_chip.setText(str(rating))
        legend_key = (tuple(moves), board.fen(), bool(QApplication.instance().property("nocturneLightAppearance")))
        if legend_key != getattr(self, "_legend_key", None):
            self._legend_key = legend_key
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
                button.setObjectName("curveLegend")
                button.setText(name)
                button.setCheckable(True)
                button.setChecked(move not in self.chart.hidden_moves)
                button.setStyleSheet(f"color: {curve_colors()[index]};")
                button.toggled.connect(lambda checked, uci=move: self._toggle_curve(uci, checked))
                self.legend_layout.addWidget(button, index//3, index % 3)
                self.legend_buttons[move] = button
        self.chart.update()
        if appearance:
            self.map.light = appearance.get("light", False)
            self.map.theme = appearance.get("theme", "Classic")
            self.map.set_piece_set(appearance.get("piece_set", "Nibbler"))
        self.map.set_policy(board, policy)

    def _toggle_curve(self, uci, checked):
        if checked:
            self.chart.hidden_moves.discard(uci)
        else:
            self.chart.hidden_moves.add(uci)
        self.chart.update()
