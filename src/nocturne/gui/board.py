"""High-DPI vector chessboard with drag, click, animation and annotations."""

from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QMouseEvent, QPainter, QPainterPath, QPainterPathStroker, QPen, QPolygonF
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QMenu, QWidget

from ..core.board import Board, Move, PIECE_CHARS, SQUARES
from ..pieces import DEFAULT_PIECE_SET, PIECE_SET_NAMES, piece_path as asset_path
from .wheel import WheelSteps
from .maia_colors import curve_colors
from .theme import BOARD_THEMES, palette


class BoardWidget(QWidget):
    move_requested = Signal(object)
    wheel_navigated = Signal(int)
    manual_input = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(330, 330)
        self.setMouseTracking(True)
        self.board = Board()
        self.preview_board: Board | None = None
        self.preview_last_move: Move | None = None
        self.preview_caption = ""
        self.flipped = False
        self.coordinates = True
        self.theme = "Classic"
        self.wheel_navigation = True
        self._wheel_steps = WheelSteps()
        self.light = False
        self.interactive = True
        self.animations = False
        self.overlays = True
        self.last_move: Move | None = None
        self.best_move: Move | None = None
        self.game_move: Move | None = None
        self._position_revision = 0
        self.recommendations = []
        self.inferior_ranks = set()
        self.recommendation_fen = None
        self.smart_move = False
        self.maia_recommendations = []
        self.maia_arrows_enabled = True
        self.candidate_style = "lines"
        self.branch_moves = []
        self.selected: int | None = None
        self.legal: list[Move] = []
        self.arrows: set[tuple[int, int]] = set()
        self.marks: set[int] = set()
        self._right_from: int | None = None
        self._pressed: int | None = None
        self._press_pos = QPointF()
        self._drag_pos: QPointF | None = None
        self._anim_move: Move | None = None
        self._anim_progress = 0.0
        self._renderers = {}
        self._renderer_sets = {}
        self.piece_set = ""
        self.set_piece_set(DEFAULT_PIECE_SET)
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(170)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.valueChanged.connect(self._animate)
        self._animation.finished.connect(self._animation_finished)
        self.setAccessibleName("Chessboard")

    def piece_directory(self):
        return asset_path(self.piece_set, 1, PIECE_CHARS).parent

    def piece_path(self, piece):
        return asset_path(self.piece_set, piece, PIECE_CHARS)

    def set_piece_set(self, name):
        name = name if name in PIECE_SET_NAMES else DEFAULT_PIECE_SET
        if name == self.piece_set:
            return
        self.piece_set = name
        if name in self._renderer_sets:
            self._renderers = self._renderer_sets[name]
            self.update()
            return
        renderers = {}
        for color in (1, -1):
            for kind in range(1, 7):
                path = str(self.piece_path(color * kind))
                renderers[color * kind] = QSvgRenderer(path, self)
        self._renderer_sets[name] = self._renderers = renderers
        self.update()

    def sizeHint(self):
        return QSize(690, 690)

    def _geometry(self) -> tuple[QRectF, float]:
        # Coordinates are painted over the edge squares, so only a narrow
        # breathing room for the rounded board border is needed.
        edge = max(0, min(self.width(), self.height()) - 12)
        return QRectF((self.width() - edge) / 2, (self.height() - edge) / 2, edge, edge), edge / 8

    def square_rect(self, square: int) -> QRectF:
        rect, unit = self._geometry()
        file, rank = square & 7, square >> 4
        col, row = (7 - file, rank) if self.flipped else (file, 7 - rank)
        return QRectF(rect.x() + col * unit, rect.y() + row * unit, unit, unit)

    def square_at(self, point: QPointF) -> int | None:
        rect, unit = self._geometry()
        if not rect.contains(point):
            return None
        col, row = int((point.x() - rect.x()) / unit), int((point.y() - rect.y()) / unit)
        if not 0 <= col < 8 or not 0 <= row < 8:
            return None
        file, rank = (7 - col, row) if self.flipped else (col, 7 - row)
        return rank * 16 + file

    def set_position(self, board: Board, last_move: Move | None = None, animate=False):
        self._position_revision += 1
        self.clear_preview()
        self._animation.stop()
        self._anim_move = None
        self.board, self.last_move = board, last_move
        self.selected = self._pressed = None
        self._drag_pos = None
        self.legal = list(board.legal_moves())
        self.best_move = None
        self.game_move = None
        self.recommendations = []
        self.inferior_ranks = set()
        self.recommendation_fen = None
        self.branch_moves = []
        if animate and last_move and self.animations:
            self._anim_move = last_move
            self._animation.start()
        self.update()

    def set_recommendations(self, entries, *, inferior_ranks=()):
        legal = list(self.board.legal_moves())
        seen = set()
        self.recommendations = []
        self.inferior_ranks = set(inferior_ranks)
        for move, rank, text in sorted(entries, key=lambda entry: entry[1]):
            if move in legal and move not in seen and 1 <= rank <= 32:
                self.recommendations.append((move, rank, text))
                seen.add(move)
        self.recommendation_fen = self.board.fen()
        self.update()

    def set_game_move(self, move):
        """Make the recorded continuation playable by destination click."""
        self.game_move = move if move in self.legal else None
        if self.recommendation_fen is None:
            self.recommendation_fen = self.board.fen()

    def _destination(self, move):
        return (
            self.board.display_destination(move) if hasattr(self.board, "display_destination") else move.to_sq
        )

    def _smart_request(self, square, global_pos):
        root_fen = self.board.fen()
        revision = self._position_revision
        if not self.smart_move or self.recommendation_fen != self.board.fen():
            return False
        legal = list(self.board.legal_moves())
        if (
            self.game_move in legal
            and self._destination(self.game_move) == square
        ):
            move = self.game_move
            if self.interactive and self.preview_board is None:
                self.move_requested.emit(move)
            return True
        choices = [
            (m, r, t)
            for m, r, t in self.recommendations
            if m in legal and self._destination(m) == square
        ]
        if not choices:
            return False
        move = min(choices, key=lambda item: item[1])[0]
        if (
            self.board.fen() != root_fen
            or self._position_revision != revision
            or not self.interactive
            or self.preview_board is not None
            or move not in list(self.board.legal_moves())
        ):
            return True
        # A recommendation includes its promotion choice. Manual moves still
        # use the piece chooser in _request.
        self.move_requested.emit(move)
        return True

    @property
    def display_board(self):
        return self.preview_board if self.preview_board is not None else self.board

    def show_preview(self, board: Board, last_move: Move | None = None, caption="Preview"):
        self.preview_board = board
        self.preview_last_move = last_move
        self.preview_caption = caption
        self.update()

    def clear_preview(self):
        self.preview_board = None
        self.preview_last_move = None
        self.preview_caption = ""
        self.update()

    def _animate(self, value):
        self._anim_progress = float(value)
        self.update()

    def _animation_finished(self):
        self._anim_move = None
        self.update()

    def flip(self):
        self.flipped = not self.flipped
        self.update()

    def clear_annotations(self):
        self.arrows.clear()
        self.marks.clear()
        self.update()

    def _piece(self, painter: QPainter, piece: int, rect: QRectF):
        # Every set is vector art. QSvgRenderer follows the painter's device
        # pixel ratio; its asset viewBox alone controls piece size and spacing.
        self._renderers[piece].render(painter, rect)

    def _arrow(self, painter: QPainter, src: int, dst: int, color: QColor, unit: float, *, subtle=False):
        if src == dst:
            return
        a, b = self.square_rect(src).center(), self.square_rect(dst).center()
        dx, dy = b.x() - a.x(), b.y() - a.y()
        distance = math.hypot(dx, dy)
        dx, dy = dx / distance, dy / distance
        width = max(2.0, unit * 0.060) if subtle else unit * 0.115
        head_length = unit * (0.22 if subtle else 0.37)
        head_width = unit * (0.13 if subtle else 0.20)
        if subtle:
            a += QPointF(dx, dy) * (unit * 0.25)
        end = b - QPointF(dx, dy) * (head_length * 0.85 if subtle else unit * 0.20)
        painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(a, end)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        base = b - QPointF(dx, dy) * head_length
        normal = QPointF(-dy, dx) * head_width
        painter.drawPolygon(QPolygonF([b, base + normal, base - normal]))

    def _stockfish_arrow(self, painter, src, dst, unit, *, top=False):
        """Lichess pale brushes: round shafts, SVG marker proportions, 40% opacity."""
        if src == dst:
            return
        start = self.square_rect(src).center()
        target = self.square_rect(dst).center()
        delta = target - start
        length = math.hypot(delta.x(), delta.y())
        width = unit * (0.234375 if top else 0.15625)
        end = length - unit * 0.15625
        shaft = QPainterPath()
        shaft.moveTo(0, 0)
        shaft.lineTo(end, 0)
        stroker = QPainterPathStroker()
        stroker.setWidth(width)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        # SVG marker: M0,0 V4 L3,2 Z, refX=2.05, refY=2.
        head = QPainterPath()
        head.moveTo(end - 2.05 * width, -2 * width)
        head.lineTo(end - 2.05 * width, 2 * width)
        head.lineTo(end + 0.95 * width, 0)
        head.closeSubpath()
        painter.save()
        painter.translate(start)
        painter.rotate(math.degrees(math.atan2(delta.y(), delta.x())))
        # Fill one silhouette so shaft/head overlap cannot darken the arrow.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 48, 136, 102) if top else QColor(74, 74, 74, 102))
        painter.drawPath(stroker.createStroke(shaft).united(head))
        painter.restore()

    def _maia_rod_entries(self):
        colors = curve_colors(self.light)
        ranked = sorted(self.maia_recommendations, key=lambda entry: -entry[1])
        return [(move, index + 1, colors[index % len(colors)])
                for index, (move, probability, _) in enumerate(ranked) if probability > 0.10]

    def _draw_maia_rods(self, painter, unit):
        entries = self._maia_rod_entries()
        best_rank = {}
        for move, rank, _ in entries:
            destination = self._destination(move)
            best_rank[destination] = min(rank, best_rank.get(destination, rank))
        for move, rank, marker in reversed(entries):
            color = QColor(marker)
            color.setAlpha(225)
            start = self.square_rect(move.from_sq).center()
            end = self.square_rect(self._destination(move)).center()
            delta = end - start
            length = math.hypot(delta.x(), delta.y())
            if length:
                start += delta * (unit * 0.25 / length)
            painter.setPen(QPen(color, max(2.0, unit * 0.065), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(start, end)
        # Keep the most likely badge visible when two moves share a target.
        for move, rank, marker in reversed(entries):
            if best_rank[self._destination(move)] != rank:
                continue
            center = self.square_rect(self._destination(move)).center()
            diameter = max(13.0, unit * 0.245)
            badge = QRectF(center.x() - diameter / 2, center.y() - diameter / 2, diameter, diameter)
            color = QColor(marker)
            color.setAlpha(250)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(badge)
            painter.setPen(QColor("#17251d" if color.lightnessF() > .45 else "#ffffff"))
            font = QFont("Segoe UI")
            font.setPixelSize(max(9, int(diameter * 0.62)))
            painter.setFont(font)
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(rank))

    @staticmethod
    def last_move_color(base):
        # Keep the square's hue/saturation. Move HSV brightness by ten points,
        # darkening pale squares and lightening dark ones, independent of theme.
        color = QColor(base)
        hue, saturation, value, alpha = color.getHsvF()
        value = max(0.0, min(1.0, value + (-0.10 if value >= 0.5 else 0.10)))
        color.setHsvF(hue, saturation, value, alpha)
        return color

    def wheelEvent(self, event):
        if not self.wheel_navigation or self.square_at(event.position()) is None:
            return super().wheelEvent(event)
        steps = self._wheel_steps.consume(event)
        if steps is None:
            return super().wheelEvent(event)
        event.accept()
        if steps:
            self.wheel_navigated.emit(steps)

    def leaveEvent(self, event):
        self._wheel_steps.reset()
        super().leaveEvent(event)

    def paintEvent(self, event):
        board = self.display_board
        preview = self.preview_board is not None
        last_move = self.preview_last_move if preview else self.last_move
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect, unit = self._geometry()
        painter.setPen(Qt.PenStyle.NoPen)
        colors = palette(self.light)
        painter.setBrush(QColor(colors["border"]))
        painter.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), 10, 10)
        clip = QPainterPath()
        clip.addRoundedRect(rect, 8, 8)
        painter.save()
        painter.setClipPath(clip)
        light, dark = BOARD_THEMES.get(self.theme, BOARD_THEMES["Classic"])
        for square in SQUARES:
            square_rect = self.square_rect(square)
            base = QColor(dark if ((square >> 4) + (square & 7)) % 2 == 0 else light)
            if last_move and square in (last_move.from_sq, last_move.to_sq):
                base = self.last_move_color(base)
            painter.fillRect(square_rect, base)
            if not preview and square in self.marks:
                painter.fillRect(square_rect, QColor(114, 150, 180, 120))
            if not preview and square == self.selected:
                painter.fillRect(square_rect, QColor(232, 185, 72, 110))
                painter.setPen(QPen(QColor("#e2b75c"), 3))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(square_rect.adjusted(1.5, 1.5, -1.5, -1.5))
                painter.setPen(Qt.PenStyle.NoPen)
        if board.in_check():
            king = board.kings[0 if board.turn == 1 else 1]
            painter.fillRect(self.square_rect(king), QColor(207, 74, 68, 160))
        if not preview and self.selected is not None:
            for move in self.legal:
                if move.from_sq != self.selected:
                    continue
                target = self.square_rect(move.to_sq)
                if self.board.is_capture(move):
                    painter.setPen(QPen(QColor(30, 30, 30, 150), unit * 0.09))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(target.adjusted(unit * 0.06, unit * 0.06, -unit * 0.06, -unit * 0.06))
                else:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(30, 30, 30, 95))
                    painter.drawEllipse(target.center(), unit * 0.135, unit * 0.135)
        for square in SQUARES:
            piece = board.cells[square]
            if not piece or (not preview and self._drag_pos is not None and square == self._pressed):
                continue
            if not preview and self._anim_move and square == self._anim_move.to_sq:
                continue
            self._piece(painter, piece, self.square_rect(square))
        if not preview and self._anim_move:
            a = self.square_rect(self._anim_move.from_sq).topLeft()
            b = self.square_rect(self._anim_move.to_sq).topLeft()
            pos = a + (b - a) * self._anim_progress
            piece = self.board.cells[self._anim_move.to_sq]
            if piece:
                self._piece(painter, piece, QRectF(pos.x(), pos.y(), unit, unit))
        # Stockfish uses the familiar Lichess arrows; Maia's colored rods and
        # likelihood ranks sit above them when both models suggest a move.
        if not preview and self.overlays:
            entries = self.recommendations or ([(self.best_move, 1, "")] if self.best_move else [])
            for move, rank, _ in reversed(entries):
                self._stockfish_arrow(painter, move.from_sq, self._destination(move), unit, top=rank == 1)
        for src, dst in () if preview else self.arrows:
            self._arrow(painter, src, dst, QColor(232, 175, 79, 200), unit)
        if not preview and self.overlays:
            for move in self.branch_moves:
                self._arrow(painter, move.from_sq, self._destination(move), QColor(153, 137, 106, 65), unit, subtle=True)
            if self.maia_arrows_enabled:
                self._draw_maia_rods(painter, unit)
        if not preview and self._drag_pos is not None and self._pressed is not None:
            piece = self.board.cells[self._pressed]
            if piece:
                self._piece(
                    painter,
                    piece,
                    QRectF(self._drag_pos.x() - unit / 2, self._drag_pos.y() - unit / 2, unit, unit),
                )
        painter.restore()
        if preview:
            painter.setPen(QColor(colors["muted"]))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(
                QRectF(rect.x(), rect.y() - 22, rect.width(), 18),
                Qt.AlignmentFlag.AlignCenter,
                self.preview_caption,
            )
        if self.coordinates:
            font = QFont("Segoe UI")
            font.setPixelSize(max(9, int(unit * 0.14)))
            font.setBold(True)
            painter.setFont(font)
            for index in range(8):
                # Put file labels in the bottom row and rank labels on the
                # right edge, regardless of orientation, like Lichess.
                x = rect.x() + (index + 0.5) * unit
                bottom_y = rect.bottom() - unit / 2
                bottom_square = self.square_at(QPointF(x, bottom_y))
                if bottom_square is not None:
                    tile = BOARD_THEMES.get(self.theme, BOARD_THEMES["Classic"])
                    is_light = ((bottom_square >> 4) + (bottom_square & 7)) % 2 != 0
                    color = QColor(tile[1] if is_light else tile[0])
                    color.setAlpha(175)
                    painter.setPen(color)
                    painter.drawText(
                        QRectF(x - unit / 2 + 3, rect.bottom() - unit * 0.25, unit - 6, unit * 0.2),
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                        chr(97 + (bottom_square & 7)),
                    )

                y = rect.y() + (index + 0.5) * unit
                edge_x = rect.right() - unit / 2
                rank_square = self.square_at(QPointF(edge_x, y))
                if rank_square is not None:
                    tile = BOARD_THEMES.get(self.theme, BOARD_THEMES["Classic"])
                    is_light = ((rank_square >> 4) + (rank_square & 7)) % 2 != 0
                    color = QColor(tile[1] if is_light else tile[0])
                    color.setAlpha(175)
                    painter.setPen(color)
                    inset = 3
                    label_rect = QRectF(rect.right() - unit * 0.24, y - unit / 2 + inset, unit * 0.2, unit * 0.2)
                    painter.drawText(label_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                                     str((rank_square >> 4) + 1))

    def _request(self, src: int, dst: int, global_pos) -> bool:
        root_fen = self.board.fen()
        revision = self._position_revision
        candidates = [
            m for m in self.legal if m.from_sq == src and (m.to_sq == dst or self._destination(m) == dst)
        ]
        if not candidates:
            return False
        if len(candidates) > 1:
            menu = QMenu(self)
            chosen = {}
            for move in candidates:
                if move.promotion:
                    kind = PIECE_CHARS[move.promotion].lower()
                    name = {"q": "Queen", "r": "Rook", "b": "Bishop", "n": "Knight"}[kind]
                    action = menu.addAction(QIcon(str(self.piece_path(self.board.turn * move.promotion))), name)
                else:
                    from ..core.notation import san

                    action = menu.addAction(san(self.board, move))
                chosen[action] = move
            action = menu.exec(global_pos)
            if action is None:
                return False
            move = chosen[action]
        else:
            move = candidates[0]
        if (
            self.board.fen() != root_fen
            or self._position_revision != revision
            or not self.interactive
            or self.preview_board is not None
            or move not in list(self.board.legal_moves())
        ):
            return True
        self.move_requested.emit(move)
        return True

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.manual_input.emit()
        if self.preview_board is not None:
            return
        square = self.square_at(event.position())
        if event.button() == Qt.MouseButton.RightButton:
            self._right_from = square
            return
        if event.button() != Qt.MouseButton.LeftButton or not self.interactive or square is None:
            return
        self._animation.stop()
        self._anim_move = None
        self.clear_annotations()
        if self.selected is not None and square != self.selected:
            if self._request(self.selected, square, event.globalPosition().toPoint()):
                return
        if self.selected is None and self._smart_request(square, event.globalPosition().toPoint()):
            return
        if self.board.cells[square] * self.board.turn > 0:
            self.selected = self._pressed = square
            self._press_pos = event.position()
        else:
            self.selected = self._pressed = None
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.preview_board is not None:
            return
        if self._pressed is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if (event.position() - self._press_pos).manhattanLength() > 5:
                self._drag_pos = event.position()
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.preview_board is not None:
            return
        square = self.square_at(event.position())
        if event.button() == Qt.MouseButton.RightButton:
            if self._right_from is not None and square is not None:
                if self._right_from == square:
                    self.marks.symmetric_difference_update({square})
                else:
                    self.arrows.symmetric_difference_update({(self._right_from, square)})
            self._right_from = None
        elif event.button() == Qt.MouseButton.LeftButton:
            src, dragged = self._pressed, self._drag_pos is not None
            self._pressed, self._drag_pos = None, None
            if dragged and src is not None and square is not None and src != square:
                self._request(src, square, event.globalPosition().toPoint())
        self.update()
