"""Manual position editor backed by python-chess validation."""

import chess
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
from .board import BoardWidget
from ..core.rules import Board, square64


class SetupBoard(BoardWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.native = chess.Board()
        self.piece = chess.Piece(chess.QUEEN, True)

    def mousePressEvent(self, event):
        square = self.square_at(event.position())
        if square is None:
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.native.remove_piece_at(square64(square))
        else:
            self.native.set_piece_at(square64(square), self.piece)
        self._draw_setup()

    def mouseReleaseEvent(self, event):
        pass

    def _draw_setup(self):
        # Incomplete editor positions may temporarily have no kings.
        self.board.native = self.native.copy()
        self.board.cells = [0] * 128
        for square, piece in self.native.piece_map().items():
            self.board.cells[(square // 8) * 16 + square % 8] = piece.piece_type * (1 if piece.color else -1)
        self.board.in_check = lambda: False
        self.update()


class PositionDialog(QDialog):
    def __init__(self, fen, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set up a position")
        self.resize(650, 730)
        layout = QVBoxLayout(self)
        self.board = SetupBoard()
        self.board.native = Board(fen).native.copy()
        self.board._draw_setup()
        layout.addWidget(self.board, 1)
        row = QHBoxLayout()
        self.pieces = QComboBox()
        for color in (True, False):
            for kind in (chess.KING, chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN):
                self.pieces.addItem(
                    ("White " if color else "Black ") + chess.piece_name(kind), chess.Piece(kind, color)
                )
        self.pieces.currentIndexChanged.connect(lambda: self._piece())
        row.addWidget(self.pieces)
        for text, slot in [("Clear", self._clear), ("Starting board", self._reset)]:
            button = QPushButton(text)
            button.clicked.connect(slot)
            row.addWidget(button)
        layout.addLayout(row)
        self._piece()
        form = QFormLayout()
        self.turn = QComboBox()
        self.turn.addItems(["White", "Black"])
        self.turn.setCurrentIndex(0 if self.board.native.turn else 1)
        form.addRow("Side to move", self.turn)
        self.rights = QLineEdit(
            self.board.native.castling_shredder_fen()
            if self.board.native.chess960
            else self.board.native.castling_xfen()
        )
        form.addRow("Castling rights (KQkq / rook files)", self.rights)
        self.ep = QLineEdit(
            chess.square_name(self.board.native.ep_square) if self.board.native.ep_square is not None else "-"
        )
        form.addRow("En passant square", self.ep)
        layout.addLayout(form)
        layout.addWidget(
            QLabel(
                "Click to place the selected piece; right-click to erase. Imported positions are validated."
            )
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.result_fen = fen

    def _piece(self):
        self.board.piece = self.pieces.currentData()

    def _clear(self):
        self.board.native.clear()
        self.board._draw_setup()
        self.rights.setText("-") if hasattr(self, "rights") else None

    def _reset(self):
        self.board.native.reset()
        self.board._draw_setup()
        self.rights.setText("KQkq")

    def _accept(self):
        b = self.board.native.copy()
        b.turn = self.turn.currentIndex() == 0
        fen = (
            b.board_fen()
            + (" w " if b.turn else " b ")
            + (self.rights.text().strip() or "-")
            + " "
            + (self.ep.text().strip() or "-")
            + " 0 1"
        )
        try:
            self.result_fen = Board(fen).fen()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid position", str(exc))
            return
        self.accept()
