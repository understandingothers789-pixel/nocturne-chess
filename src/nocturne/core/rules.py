"""python-chess rules adapter for the desktop study model (0x88 drawing coordinates)."""

import hashlib

import chess

from .board import Move, Outcome, START_FEN


def square64(square):
    return (square >> 4) * 8 + (square & 7)


def square88(square):
    return chess.square_rank(square) * 16 + chess.square_file(square)


def native(move):
    return chess.Move(square64(move.from_sq), square64(move.to_sq), move.promotion or None)


def wrapped(move):
    return Move(square88(move.from_square), square88(move.to_square), move.promotion or 0)


class Board:
    def __init__(self, fen=START_FEN):
        fields = fen.split()
        is960 = len(fields) > 2 and any(c not in "KQkq-" for c in fields[2])
        self.native = chess.Board(fen, chess960=is960)
        if not self.native.is_valid():
            raise ValueError("Invalid chess position: kings, checks, pawns or castling rights")
        self._sync()
        self.key_history = [self.key]

    def _sync(self):
        b = self.native
        self.cells = [0] * 128
        for square, piece in b.piece_map().items():
            self.cells[square88(square)] = piece.piece_type * (1 if piece.color else -1)
        self.turn = 1 if b.turn else -1
        self.chess960 = b.chess960
        self.castling = b.castling_rights
        self.ep = square88(b.ep_square) if b.ep_square is not None else None
        self.halfmove, self.fullmove = b.halfmove_clock, b.fullmove_number
        self.kings = (square88(b.king(True)), square88(b.king(False)))
        key = " ".join(b.fen(shredder=b.chess960, en_passant="legal").split()[:4])
        self.key = int.from_bytes(hashlib.blake2b(key.encode(), digest_size=8).digest(), "little")

    def compute_key(self):
        key = " ".join(self.native.fen(shredder=self.chess960, en_passant="legal").split()[:4])
        return int.from_bytes(hashlib.blake2b(key.encode(), digest_size=8).digest(), "little")

    def fen(self):
        return self.native.fen(shredder=self.chess960, en_passant="fen")

    def copy(self, history=True):
        other = object.__new__(Board)
        other.native = self.native.copy(stack=history)
        # This is the same position: copy the synchronized drawing/rule state
        # instead of rebuilding piece maps, FEN and the position hash.
        other.cells = self.cells.copy()
        for name in ("turn", "chess960", "castling", "ep", "halfmove", "fullmove", "kings", "key"):
            setattr(other, name, getattr(self, name))
        other.key_history = self.key_history.copy() if history else [other.key]
        return other

    def legal_moves(self):
        return (wrapped(m) for m in self.native.legal_moves)

    def parse_uci(self, text):
        try:
            return wrapped(self.native.parse_uci(text))
        except ValueError as exc:
            raise ValueError(f"Illegal UCI move: {text}") from exc

    def push(self, move):
        m = native(move)
        if m not in self.native.legal_moves:
            raise ValueError("Illegal move: " + move.uci())
        self.native.push(m)
        self._sync()
        self.key_history.append(self.key)

    def pop(self):
        move = self.native.pop()
        self._sync()
        self.key_history.pop()
        return wrapped(move)

    def play_uci(self, text):
        self.push(self.parse_uci(text))

    def in_check(self, color=None):
        if color is None or color == self.turn:
            return self.native.is_check()
        return self.native.is_attacked_by(color == -1, self.native.king(color == 1))

    def display_destination(self, move):
        if self.native.is_castling(native(move)):
            file = 6 if move.to_sq > move.from_sq else 2
            return (move.from_sq & 0x70) + file
        return move.to_sq

    def is_capture(self, move):
        return self.native.is_capture(native(move))

    def insufficient_material(self):
        return self.native.is_insufficient_material()

    def outcome(self):
        result = self.native.outcome(claim_draw=False)
        if result is None:
            return None
        names = {
            "CHECKMATE": "Checkmate",
            "STALEMATE": "Stalemate",
            "INSUFFICIENT_MATERIAL": "Insufficient material",
            "SEVENTYFIVE_MOVES": "Seventy-five-move rule",
            "FIVEFOLD_REPETITION": "Fivefold repetition",
        }
        winner = None if result.winner is None else 1 if result.winner else -1
        return Outcome(result.result(), names.get(result.termination.name, result.termination.name), winner)

    def claimable_draws(self, intended=None):
        b = self.native.copy()
        if intended:
            m = native(intended)
            if m not in b.legal_moves:
                raise ValueError("Illegal intended draw-claim move")
            b.push(m)
        reasons = []
        if b.is_fifty_moves():
            reasons.append("Fifty-move rule")
        if b.is_repetition(3):
            reasons.append("Threefold repetition")
        return reasons
