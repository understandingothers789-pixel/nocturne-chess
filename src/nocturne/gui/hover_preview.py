"""Mouse-transparent cursor preview; it never changes the study's board."""

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from .board import BoardWidget
from .theme import palette


class MiniBoard(BoardWidget):
    def _geometry(self):
        edge = max(8, min(self.width(), self.height()) - 12)
        return QRectF((self.width() - edge) / 2, (self.height() - edge) / 2, edge, edge), edge / 8


class HoverPreview(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("hoverPreview")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("Temporary move preview")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 5, 6, 5)
        layout.setSpacing(0)
        self.caption = QLabel()
        self.caption.setTextFormat(Qt.TextFormat.PlainText)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setFixedHeight(22)
        layout.addWidget(self.caption)
        self.board = MiniBoard(self)
        self.board.setMinimumSize(0, 0)
        self.board.setFixedSize(384, 384)
        self.board.coordinates = False
        self.board.interactive = self.board.animations = self.board.overlays = False
        self.board.wheel_navigation = False
        self.board.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.board)
        self.setFixedSize(396, 416)
        self.hide()

    def show_position(self, position, last_move, reference, caption):
        colors = palette(reference.light)
        self.setStyleSheet(f"QFrame#hoverPreview {{ background: {colors['panel']}; "
                          f"border: 1px solid {colors['accent']}; border-radius: 7px; }}")
        self.caption.setStyleSheet(f"color: {colors['metadata']}; font-size: 11px;")
        self.caption.setText(caption)
        self.board.theme, self.board.light = reference.theme, reference.light
        self.board.flipped = reference.flipped
        self.board.set_piece_set(reference.piece_set)
        self.board.set_position(position, last_move)
        self.move_near(QCursor.pos())
        self.show()
        self.raise_()

    def move_near(self, cursor):
        parent = self.parentWidget()
        bounds = QRect(parent.mapToGlobal(QPoint()), parent.size())
        screen = QGuiApplication.screenAt(cursor) or parent.screen()
        bounds = bounds.intersected(screen.availableGeometry()).adjusted(4, 4, -4, -4)
        edge = max(32, min(384, bounds.width() - 12, bounds.height() - 32))
        if self.board.width() != edge:
            self.board.setFixedSize(edge, edge)
            self.setFixedSize(edge + 12, edge + 32)
        # Place to the right/below first, then flip at the visible edges. The
        # cursor stays outside the board, so text hover/clicks keep reaching it.
        x, y = cursor.x() + 24, cursor.y() + 24
        if x + self.width() > bounds.right():
            x = cursor.x() - self.width() - 24
        if y + self.height() > bounds.bottom():
            y = cursor.y() - self.height() - 24
        x = max(bounds.left(), min(x, bounds.right() - self.width() + 1))
        y = max(bounds.top(), min(y, bounds.bottom() - self.height() + 1))
        self.move(parent.mapFromGlobal(QPoint(x, y)))
