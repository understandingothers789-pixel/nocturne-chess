"""Native, interactive visualizations of the actual rating-conditioned policy."""
import math
from collections import OrderedDict

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget, QToolTip,
    QComboBox, QHBoxLayout, QApplication,
)
from ..core.notation import san
from ..maia import RATINGS, percentage
from ..maia.risk import assess_moves
from .theme import palette
from .notation import FigurineToolButton, draw as draw_notation, html as notation_html, text_width

from .maia_colors import COLORS, curve_colors


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
        self.setMinimumHeight(220)
        self.setMaximumHeight(280)
        self.setMinimumWidth(210)
        self.policies = {}
        self.moves = []
        self.names = {}
        self.hidden_moves = set()
        self.rating = 1800
        self.ratings = RATINGS
        self.points = []
        self.label_hits = []

    def sizeHint(self):
        return QSize(340, 250)

    def plot_rect(self):
        font = QFont(self.font())
        font.setPixelSize(11)
        font.setBold(True)
        lane = max(64, max((text_width(name, font) + 20 for name in self.names.values()), default=0))
        return QRectF(42, 14, max(1, self.width() - 42 - lane), max(1, self.height()-46))

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
        for fraction in (0, 0.25, 0.5, 0.75, 1):
            y = plot.bottom()-fraction*plot.height()
            painter.setPen(QPen(QColor(colors["border"]), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(colors["muted"]))
            painter.drawText(QRectF(0, y-7, 32, 15), Qt.AlignmentFlag.AlignRight, f"{fraction*ceiling*100:.0f}%")
        low, high = self.ratings[0], self.ratings[-1]
        ticks = self.ratings[::2] if self.width() >= 340 else (low, self.ratings[len(self.ratings)//2], high)
        for rating in sorted(set((*ticks, high))):
            x = plot.left()+(rating-low)/(high-low)*plot.width()
            painter.drawText(QRectF(max(0, min(self.width()-40, x-20)), plot.bottom()+5, 40, 16), Qt.AlignmentFlag.AlignCenter, str(rating))

        marker = plot.left()+(self.rating-low)/(high-low)*plot.width()
        painter.setPen(QPen(QColor("#bca36a"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(marker, plot.top()), QPointF(marker, plot.bottom()))
        self.points = []
        self.label_hits = []
        labels = []
        for index, move in enumerate(self.moves):
            if move in self.hidden_moves:
                continue
            path = QPainterPath()
            started = False
            segments = []
            segment = []
            color = QColor(curve_colors()[index % len(COLORS)])
            for rating in self.ratings:
                policy = self.policies.get(str(rating))
                if policy is None:
                    if segment:
                        segments.append(segment)
                        segment = []
                    started = False
                    continue
                probability = policy.get(move, 0)
                point = QPointF(plot.left()+(rating-low)/(high-low)*plot.width(),
                                plot.bottom()-probability/ceiling*plot.height())
                if started:
                    path.lineTo(point)
                else:
                    path.moveTo(point)
                    started = True
                segment.append(point)
                self.points.append((point, move, rating, probability))
            if segment:
                segments.append(segment)
            # Fill each contiguous sample range to the baseline with low alpha.
            # Always clear the brush before stroking: point-marker brushes must
            # never implicitly close and fill the next open curve.
            painter.setPen(Qt.PenStyle.NoPen)
            fill = QColor(color)
            fill.setAlpha(22)
            painter.setBrush(fill)
            for sample in segments:
                area = QPainterPath(QPointF(sample[0].x(), plot.bottom()))
                for point in sample:
                    area.lineTo(point)
                area.lineTo(QPointF(sample[-1].x(), plot.bottom()))
                area.closeSubpath()
                painter.drawPath(area)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(color, 2))
            painter.drawPath(path)
            painter.setBrush(color)
            for point, uci, rating, probability in self.points:
                if uci == move:
                    painter.drawEllipse(point, 2.2 if rating == self.rating else 1.3,
                                        2.2 if rating == self.rating else 1.3)
            if segment:
                labels.append((segment[-1], move, self.names.get(move, move), color))
            elif segments:
                labels.append((segments[-1][-1], move, self.names.get(move, move), color))
        # Reserve a lane for labels; spread clustered endpoints vertically and
        # connect each label to its actual curve without moving any data points.
        labels.sort(key=lambda item: item[0].y())
        positions = []
        for point, move, name, color in labels:
            positions.append(max(plot.top() + 8, point.y(), positions[-1] + 16 if positions else plot.top() + 8))
        if positions and positions[-1] > plot.bottom() - 8:
            positions[-1] = plot.bottom() - 8
            for index in range(len(positions)-2, -1, -1):
                positions[index] = min(positions[index], positions[index+1]-16)
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        label_x = plot.right() + 12
        for (point, move, name, color), y in zip(labels, positions):
            painter.setPen(QPen(color, 1))
            painter.drawLine(point, QPointF(label_x-3, y))
            label_rect = QRectF(label_x, y-9, self.width()-label_x, 18)
            painter.save()
            painter.setClipRect(label_rect)
            draw_notation(painter, label_x, y+4, name)
            painter.restore()
            endpoint = next(item for item in reversed(self.points) if item[1] == move)
            self.label_hits.append((label_rect, endpoint))
        if not self.policies:
            painter.setPen(QColor(colors["muted"]))
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "Waiting for Maia predictions")

    def mouseMoveEvent(self, event):
        hit = next((data for rect, data in self.label_hits if rect.contains(event.position())), None)
        if hit is None and self.points:
            nearest = min(self.points, key=lambda item: (item[0]-event.position()).manhattanLength())
            if (nearest[0]-event.position()).manhattanLength() < 28:
                hit = nearest
        if hit is not None:
            _, move, rating, probability = hit
            self.setToolTip(f"{self.names.get(move, move)} · {rating} vs {rating}\n{probability*100:.6g}% predicted likelihood")
            QToolTip.showText(event.globalPosition().toPoint(), self.toolTip(), self)
            return
        QToolTip.hideText()
        self.setToolTip("")


CATEGORIES = ("best", "ok", "blunder", "unknown")
CATEGORY_NAMES = {"best": "Best moves", "ok": "OK moves", "blunder": "Blunders", "unknown": "Not evaluated"}
CATEGORY_COLORS = {"best": "#1a9850", "ok": "#fee08b", "blunder": "#d73027", "unknown": "#526171"}
METHOD_NOTE = ("Maia likelihood grouped by loss from the best exact searched Stockfish move.\n"
               "Best: 0–50 cp · OK: over 50–150 cp · Blunder: over 150 cp.\n"
               "Unsearched, bound-only and mate comparisons stay grey.\n"
               "Percentages use the full Maia policy, without rescaling partial coverage to 100%.")


def category_text_color(category):
    light = bool(QApplication.instance().property("nocturneLightAppearance"))
    return ({"best": "#267e49", "ok": "#916817", "blunder": "#b5352d", "unknown": "#637286"}
            if light else {"best": "#6ac58a", "ok": "#efd484", "blunder": "#ee8a80", "unknown": "#9aabbd"})[category]


class ProbabilityStrip(QWidget):
    """A full-policy bar: uncovered probability remains visibly grey."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(26)
        self.totals = {key: 0.0 for key in CATEGORIES}
        self.setToolTip(METHOD_NOTE)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0, 1, 0, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 6, 6)
        painter.setClipPath(path)
        painter.fillRect(rect, QColor(CATEGORY_COLORS["unknown"]))
        offset = 0.0
        for category in CATEGORIES:
            amount = self.totals[category]
            width = min(max(0, rect.width()-offset), rect.width()*amount)
            segment = QRectF(rect.left()+offset, rect.top(), width, rect.height())
            painter.fillRect(segment, QColor(CATEGORY_COLORS[category]))
            if width >= 39:
                painter.setPen(QColor("#fff5f3" if category in ("blunder", "unknown") else "#11251a"))
                painter.drawText(segment, Qt.AlignmentFlag.AlignCenter, percentage(amount))
            offset += width


class BlunderMeter(InsightCard):
    selection_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__("02", "Blunder Meter", parent)
        self.content.setContentsMargins(10, 5, 10, 5)
        self.assessments, self.names = {}, {}
        self.strip = ProbabilityStrip()
        summary = QHBoxLayout()
        self.move = QComboBox()
        self.move.setObjectName("riskChoice")
        self.move.setMaximumWidth(110)
        self.move.setToolTip("Inspect a move without playing it")
        summary.addWidget(self.move)
        summary.addWidget(self.strip, 1)
        self.content.addLayout(summary)
        self.category_labels = {}
        self.move_labels = {}
        columns = QGridLayout()
        columns.setHorizontalSpacing(12)
        columns.setVerticalSpacing(2)
        for index, category in enumerate(CATEGORIES):
            name = QLabel(CATEGORY_NAMES[category])
            name.setWordWrap(True)
            value = QLabel("—")
            columns.addWidget(name, 0, index)
            columns.addWidget(value, 1, index)
            columns.setColumnStretch(index, 1)
            self.category_labels[category] = (name, value)
            if category != "unknown":
                moves = QLabel("—")
                moves.setObjectName("sectionNote")
                moves.setWordWrap(True)
                columns.addWidget(moves, 2, index)
                self.move_labels[category] = moves
        self.content.addLayout(columns)
        self.coverage = QLabel("Waiting for Maia and Stockfish")
        self.coverage.setObjectName("sectionNote")
        self.coverage.setWordWrap(True)
        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.addWidget(self.coverage, 1)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setObjectName("sectionNote")
        footer.addWidget(self.detail, 1)
        self.content.addLayout(footer)
        self.content.setSpacing(3)
        self.setToolTip(METHOD_NOTE)
        self.move.currentIndexChanged.connect(self.refresh_selection)

    def set_data(self, assessments, names, position_key):
        signature = (position_key, tuple(sorted(names.items())),
                     tuple((uci, data["probability"], data["loss"], data["category"])
                           for uci, data in sorted(assessments.items())),
                     bool(QApplication.instance().property("nocturneLightAppearance")))
        if signature == getattr(self, "_data_signature", None):
            return
        self._data_signature = signature
        self.assessments, self.names = assessments, names
        totals = {category: sum(d["probability"] for d in assessments.values() if d["category"] == category)
                  for category in CATEGORIES}
        if assessments:
            totals["unknown"] = max(totals["unknown"], 1-sum(totals[c] for c in CATEGORIES if c != "unknown"))
        self.strip.totals = totals
        self.strip.update()
        for category, (name, value) in self.category_labels.items():
            style = f"color: {category_text_color(category)}; font-weight: 600;"
            if name.styleSheet() != style:
                name.setStyleSheet(style)
            if value.styleSheet() != style:
                value.setStyleSheet(style)
            value.setText(percentage(totals[category]) if assessments else "—")
            if category in self.move_labels:
                moves = [f"{notation_html(names[uci], size=14)} {percentage(data['probability'])}" for uci, data in
                         sorted(assessments.items(), key=lambda item: -item[1]["probability"])
                         if data["category"] == category]
                self.move_labels[category].setText(" · ".join(moves[:3]) or "—")
                self.move_labels[category].setToolTip("\n".join(moves))
        coverage = sum(totals[c] for c in CATEGORIES if c != "unknown")
        self.coverage.setText((f"{coverage:.1%} evaluated" if totals["unknown"] > .00001
                               else "All choices evaluated") if assessments else "Waiting for Maia predictions")
        inferred = sum(d["probability"] for d in assessments.values() if d.get("inferred"))
        if inferred:
            self.coverage.setText(f"{coverage - inferred:.1%} evaluated · {inferred:.1%} inferred")
        self.coverage.setToolTip(f"{coverage - inferred:.1%} evaluated; {inferred:.1%} inferred as blunders because an assessed blunder is present.")
        selected = self.move.currentData() if getattr(self, "_position_key", None) == position_key else None
        self._position_key = position_key
        choices = sorted(assessments, key=lambda uci: -assessments[uci]["probability"])
        choice_key = (position_key, tuple((uci, names[uci]) for uci in choices))
        if choice_key != getattr(self, "_choice_key", None):
            self._choice_key = choice_key
            self.move.blockSignals(True)
            self.move.clear()
            for uci in choices:
                self.move.addItem(names[uci], uci)
            self.move.setCurrentIndex(max(0, self.move.findData(selected)))
            self.move.setEnabled(bool(choices))
            self.move.blockSignals(False)
        self.refresh_selection()

    def select_move(self, uci):
        index = self.move.findData(uci)
        if index >= 0:
            self.move.setCurrentIndex(index)

    def refresh_selection(self):
        uci = self.move.currentData()
        data = self.assessments.get(uci)
        if data is None:
            self.detail.setText("Best ≤50 cp · OK ≤150 cp · Blunder >150 cp")
        else:
            loss = ("Inferred blunder · not evaluated by Stockfish" if data.get("inferred") else
                    f"{data['loss']/100:.2f} pawns loss" if data["loss"] is not None else "Stockfish loss unknown")
            self.detail.setText(f"{percentage(data['probability'])} Maia · {loss}")
        self.selection_changed.emit(uci or "")


class MaiaOutcomeBar(QWidget):
    """White-perspective model outcomes; grey remains explicitly draw probability."""
    def __init__(self, parent):
        super().__init__(parent)
        self.values = None
        self.white_expected_score = None
        self.label_visible = True
        self.setAccessibleName("Maia outcome prediction from White's perspective")
        self.set_outcome(None)

    def set_label_visible(self, visible):
        if self.label_visible != bool(visible):
            self.label_visible = bool(visible)
            self.update()

    def set_outcome(self, values):
        self.values = values
        self.white_expected_score = values[0] + values[1] / 2 if values else None
        self.setToolTip((f"Maia evaluation · White win {values[0]:.1%} · Draw {values[1]:.1%} · Black win {values[2]:.1%}"
                         f"\nWhite expected score: {self.white_expected_score:.1%} (win + half draws)")
                        if values else "Maia evaluation: predicted outcome unavailable or loading")
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        bar = QRectF(12, 4, 16, max(0, self.height()-38))
        if self.values:
            y = bar.top()
            for value, color in zip(reversed(self.values), ("#252a32", "#789097", "#edf0e8")):
                h = bar.height()*value
                p.fillRect(QRectF(bar.left(), y, bar.width(), h), QColor(color))
                y += h
            score = f"{100*self.white_expected_score:.0f}%"
        else:
            p.fillRect(bar, QColor("#46535d"))
            score = "—"
        if self.label_visible and bar.height() >= 64:
            p.save()
            font = QFont(p.font())
            font.setBold(True)
            font.setPixelSize(min(11, max(7, int(bar.height() / 10))))
            p.setFont(font)
            step = min(15.0, bar.height() / 9)
            for index, letter in enumerate("MAIA·EVAL"):
                top = bar.top() + 2 + index * step
                if self.values:
                    fraction = (top + step / 2 - bar.top()) / bar.height()
                    light = fraction >= self.values[2] + self.values[1] * 0.5
                else:
                    light = False
                p.setPen(QColor("#15232c" if light else "#e6f0ef"))
                p.drawText(QRectF(bar.left(), top, bar.width(), step), Qt.AlignmentFlag.AlignCenter, letter)
            p.restore()
        p.setPen(QColor("#9fc7cc"))
        p.drawText(QRectF(0, self.height()-28, self.width(), 22), Qt.AlignmentFlag.AlignCenter, score)
        p.end()


class MaiaInsights(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewportMargins(42, 0, 0, 0)
        self.outcome_bar = MaiaOutcomeBar(self)
        self.outcome_bar.show()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumWidth(240)
        self.setMaximumWidth(16777215)
        body = QWidget()
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(8)
        trends = InsightCard("01", "Moves by Rating")
        self.trends_card = trends
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
        self.blunder = BlunderMeter()
        self.body_layout.addWidget(self.blunder)
        self.body_layout.addStretch()
        self.setWidget(body)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.outcome_bar.setGeometry(0, 0, 40, self.height())

    def set_outcome_bar_visible(self, visible):
        self.outcome_bar.setVisible(bool(visible))
        self.setViewportMargins(42 if visible else 0, 0, 0, 0)

    def set_data(self, policies, board, rating, appearance=None):
        policies = {str(r): policies[str(r)] for r in self.chart.ratings if str(r) in policies}
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
                button = FigurineToolButton(name)
                button.setObjectName("curveLegend")
                button.setCheckable(True)
                button.setChecked(move not in self.chart.hidden_moves)
                button.setStyleSheet(f"color: {curve_colors()[index]};")
                button.toggled.connect(lambda checked, uci=move: self._toggle_curve(uci, checked))
                self.legend_layout.addWidget(button, index//3, index % 3)
                self.legend_buttons[move] = button
        self.chart.update()

    def set_analysis(self, policy, board, lines):
        # Reuse assessments only when both Maia policy and relevant engine
        # scores match; a new depth, score or root invalidates the snapshot.
        cache = getattr(self, "_assessment_cache", None)
        if cache is None:
            cache = self._assessment_cache = OrderedDict()
        position = board.fen()
        signature = (position, board.chess960, tuple(sorted(policy.items())),
                     tuple((rank, tuple(info.get("pv", [])[:1]), info.get("score_type"),
                            info.get("score_value"), info.get("bound"), info.get("depth"),
                            info.get("nodes")) for rank, info in sorted(lines.items())))
        cached = cache.get(signature)
        if cached is not None:
            cache.move_to_end(signature)
            assessments, names = cached
            if policy and lines:
                self.blunder.set_data(assessments, names, position)
                self.blunder.setToolTip("")
            elif getattr(self.blunder, "_data_signature", None):
                self.blunder.setToolTip("Showing the previous results while analysis loads for this position.")
            return assessments
        # Engine scores change much more often than the position or legal SAN.
        # Retain only the currently displayed position's move names.
        key = (board.fen(), board.chess960, frozenset(policy))
        if key != getattr(self, "_analysis_names_key", None):
            names = {}
            for uci in policy:
                try:
                    names[uci] = san(board, board.parse_uci(uci))
                except ValueError:
                    continue
            self._analysis_names_key = key
            self._analysis_names = names
        names = self._analysis_names
        assessments = assess_moves({uci: p for uci, p in policy.items() if uci in names}, lines)
        listed = {entry["pv"][0] for entry in lines.values() if entry.get("pv")}
        if any(data["category"] == "blunder" for data in assessments.values()):
            for uci, data in assessments.items():
                if uci not in listed and data["category"] == "unknown":
                    data["category"] = "blunder"
                    data["inferred"] = True
        cache[signature] = (assessments, names.copy())
        if len(cache) > 128:
            cache.popitem(last=False)
        # Keep the last complete display while this position's policy or engine
        # lines are arriving. Never reuse its moves for board recommendations.
        ready = bool(policy and lines)
        if ready or not getattr(self.blunder, "_data_signature", None):
            self.blunder.set_data(assessments, names, key[0])
            self.blunder.setToolTip("")
        else:
            self.blunder.setToolTip("Showing the previous results while analysis loads for this position.")
        return assessments

    def _toggle_curve(self, uci, checked):
        if checked:
            self.chart.hidden_moves.discard(uci)
        else:
            self.chart.hidden_moves.add(uci)
        self.chart.update()
