"""High-DPI vector chessboard with drag, click, animation and annotations."""

from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QMouseEvent, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QMenu, QWidget

from ..core.board import Board, Move, PIECE_CHARS, SQUARES
from .theme import ASSETS, BOARD_THEMES


class BoardWidget(QWidget):
    move_requested = Signal(object)

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
        self.theme = "Forest"
        self.interactive = True
        self.animations = True
        self.overlays = True
        self.last_move: Move | None = None
        self.best_move: Move | None = None
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
        for color in (1, -1):
            for kind in range(1, 7):
                file = ("w" if color == 1 else "b") + PIECE_CHARS[kind].lower() + ".svg"
                self._renderers[color * kind] = QSvgRenderer(str(ASSETS / "pieces" / file), self)
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(170)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.valueChanged.connect(self._animate)
        self._animation.finished.connect(self._animation_finished)
        self.setAccessibleName("Chessboard")

    def sizeHint(self):
        return QSize(690, 690)

    def _geometry(self) -> tuple[QRectF, float]:
        edge = min(self.width(), self.height()) - 48
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
        self.clear_preview()
        self._animation.stop()
        self._anim_move = None
        self.board, self.last_move = board, last_move
        self.selected = self._pressed = None
        self._drag_pos = None
        self.legal = list(board.legal_moves())
        self.best_move = None
        if animate and last_move and self.animations:
            self._anim_move = last_move
            self._animation.start()
        self.update()

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
        inset = rect.width() * .045
        self._renderers[piece].render(painter, rect.adjusted(inset, inset, -inset, -inset))

    def _arrow(self, painter: QPainter, src: int, dst: int, color: QColor, unit: float):
        if src == dst:
            return
        a, b = self.square_rect(src).center(), self.square_rect(dst).center()
        dx, dy = b.x() - a.x(), b.y() - a.y()
        distance = math.hypot(dx, dy)
        dx, dy = dx / distance, dy / distance
        end = b - QPointF(dx, dy) * (unit * .20)
        painter.setPen(QPen(color, unit * .115, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(a, end)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        base = b - QPointF(dx, dy) * (unit * .37)
        normal = QPointF(-dy, dx) * (unit * .20)
        painter.drawPolygon(QPolygonF([b, base + normal, base - normal]))

    def paintEvent(self, event):
        board = self.display_board
        preview = self.preview_board is not None
        last_move = self.preview_last_move if preview else self.last_move
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect, unit = self._geometry()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#25352b"))
        painter.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), 10, 10)
        clip = QPainterPath()
        clip.addRoundedRect(rect, 8, 8)
        painter.save()
        painter.setClipPath(clip)
        light, dark = BOARD_THEMES.get(self.theme, BOARD_THEMES["Forest"])
        for square in SQUARES:
            square_rect = self.square_rect(square)
            painter.fillRect(square_rect, QColor(dark if ((square >> 4) + (square & 7)) % 2 == 0 else light))
            if last_move and square in (last_move.from_sq, last_move.to_sq):
                painter.fillRect(square_rect, QColor(220, 215, 105, 105))
            if not preview and square in self.marks:
                painter.fillRect(square_rect, QColor(76, 170, 159, 135))
            if not preview and square == self.selected:
                painter.fillRect(square_rect, QColor(217, 236, 131, 130))
                painter.setPen(QPen(QColor("#d8ecb2"), 3))
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
                    painter.setPen(QPen(QColor(20, 49, 32, 150), unit * .09))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(target.adjusted(unit * .06, unit * .06, -unit * .06, -unit * .06))
                else:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(20, 49, 32, 95))
                    painter.drawEllipse(target.center(), unit * .135, unit * .135)
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
        for src, dst in (() if preview else self.arrows):
            self._arrow(painter, src, dst, QColor(232, 175, 79, 200), unit)
        if not preview and self.overlays and self.best_move:
            self._arrow(painter, self.best_move.from_sq, self.best_move.to_sq, QColor(94, 192, 181, 195), unit)
        if not preview and self._drag_pos is not None and self._pressed is not None:
            piece = self.board.cells[self._pressed]
            if piece:
                self._piece(painter, piece, QRectF(self._drag_pos.x() - unit / 2,
                                                  self._drag_pos.y() - unit / 2, unit, unit))
        painter.restore()
        if preview:
            painter.setPen(QColor("#82998a"))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(QRectF(rect.x(), rect.y() - 22, rect.width(), 18),
                             Qt.AlignmentFlag.AlignCenter, self.preview_caption)
        if self.coordinates:
            painter.setFont(QFont("Segoe UI", 10))
            painter.setPen(QColor("#82998a"))
            for index in range(8):
                square = index if not self.flipped else 119 - index
                center = self.square_rect(square).center()
                file_label = chr(97 + ((7 - index) if self.flipped else index))
                painter.drawText(QRectF(center.x() - unit / 2, rect.bottom() + 6, unit, 18),
                                 Qt.AlignmentFlag.AlignCenter, file_label)
                rank = index if self.flipped else 7 - index
                painter.drawText(QRectF(rect.x() - 23, rect.y() + index * unit, 18, unit),
                                 Qt.AlignmentFlag.AlignCenter, str(rank + 1))

    def _request(self, src: int, dst: int, global_pos) -> bool:
        candidates = [m for m in self.legal if m.from_sq == src and m.to_sq == dst]
        if not candidates:
            return False
        if len(candidates) > 1:
            menu = QMenu(self)
            chosen = {}
            color = "w" if self.board.turn == 1 else "b"
            for move in candidates:
                kind = PIECE_CHARS[move.promotion].lower()
                name = {"q": "Queen", "r": "Rook", "b": "Bishop", "n": "Knight"}[kind]
                action = menu.addAction(QIcon(str(ASSETS / "pieces" / f"{color}{kind}.svg")), name)
                chosen[action] = move
            action = menu.exec(global_pos)
            if action is None:
                return False
            move = chosen[action]
        else:
            move = candidates[0]
        self.move_requested.emit(move)
        return True

    def mousePressEvent(self, event: QMouseEvent):
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
