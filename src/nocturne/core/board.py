"""Auditable 0x88 chess rules with reversible moves and incremental hashing.

There is deliberately no dependency on a chess library. ``push`` is a fast
internal primitive; callers at a trust boundary must use ``parse_uci`` or
check membership in ``legal_moves`` first.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Iterator

WHITE, BLACK = 1, -1
PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING = range(1, 7)
WK, WQ, BK, BQ = 1, 2, 4, 8
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
SQUARES = tuple(r * 16 + f for r in range(8) for f in range(8))
PIECE_CHARS = " PNBRQK"
KNIGHT_STEPS = (33, 31, 18, 14, -14, -18, -31, -33)
BISHOP_STEPS = (17, 15, -15, -17)
ROOK_STEPS = (16, 1, -1, -16)
KING_STEPS = BISHOP_STEPS + ROOK_STEPS
_rng = random.Random(0x4E4F435455524E45)
_Z_PIECES = tuple(tuple(_rng.getrandbits(64) for _ in range(128)) for _ in range(12))
_Z_CASTLE = tuple(_rng.getrandbits(64) for _ in range(16))
_Z_EP = tuple(_rng.getrandbits(64) for _ in range(8))
_Z_TURN = _rng.getrandbits(64)
_RIGHTS_MASK = {0: 13, 7: 14, 4: 12, 112: 7, 119: 11, 116: 3}


def square_name(square: int) -> str:
    if square < 0 or square & 0x88:
        raise ValueError(f"Invalid square: {square}")
    return chr(97 + (square & 7)) + str((square >> 4) + 1)


def parse_square(name: str) -> int:
    if len(name) != 2 or name[0] not in "abcdefgh" or name[1] not in "12345678":
        raise ValueError(f"Invalid square: {name!r}")
    return (int(name[1]) - 1) * 16 + ord(name[0]) - 97


def piece_index(piece: int) -> int:
    return piece - 1 if piece > 0 else 5 - piece


@dataclass(frozen=True, slots=True)
class Move:
    from_sq: int
    to_sq: int
    promotion: int = 0

    def uci(self) -> str:
        return square_name(self.from_sq) + square_name(self.to_sq) + (
            PIECE_CHARS[self.promotion].lower() if self.promotion else ""
        )

    @classmethod
    def from_uci(cls, text: str) -> Move:
        if len(text) not in (4, 5):
            raise ValueError(f"Invalid UCI move: {text!r}")
        promotion = 0
        if len(text) == 5:
            if text[4] not in "qrbn":
                raise ValueError("Promotion must be q, r, b or n")
            promotion = PIECE_CHARS.index(text[4].upper())
        return cls(parse_square(text[:2]), parse_square(text[2:4]), promotion)


@dataclass(frozen=True, slots=True)
class Outcome:
    result: str
    reason: str
    winner: int | None = None


@dataclass(frozen=True, slots=True)
class Undo:
    move: Move
    moved: int
    captured: int
    capture_sq: int
    castling: int
    ep: int | None
    halfmove: int
    fullmove: int
    key: int
    kings: tuple[int, int]


class Board:
    def __init__(self, fen: str = START_FEN):
        self.cells = [0] * 128
        self.turn = WHITE
        self.castling = 0
        self.ep: int | None = None
        self.halfmove = 0
        self.fullmove = 1
        self.kings = [4, 116]  # white, black
        self.key = 0
        self._undo: list[Undo] = []
        self.key_history: list[int] = []
        self.set_fen(fen)

    def copy(self, history: bool = True) -> Board:
        other = object.__new__(Board)
        other.cells = self.cells.copy()
        other.turn, other.castling, other.ep = self.turn, self.castling, self.ep
        other.halfmove, other.fullmove = self.halfmove, self.fullmove
        other.kings = self.kings.copy()
        other.key = self.key
        other._undo = self._undo.copy() if history else []
        other.key_history = self.key_history.copy() if history else [self.key]
        return other

    def set_fen(self, fen: str) -> None:
        """Validate into a temporary board, so failed imports are atomic."""
        fields = fen.split()
        if len(fields) != 6:
            raise ValueError("FEN requires six fields")
        placement, side, rights, ep_text, half, full = fields
        cells = [0] * 128
        ranks = placement.split("/")
        if len(ranks) != 8:
            raise ValueError("FEN must contain eight ranks")
        for r, row in enumerate(reversed(ranks)):
            file = 0
            for char in row:
                if char in "12345678":
                    file += int(char)
                elif char.upper() in PIECE_CHARS[1:] and file < 8:
                    cells[r * 16 + file] = PIECE_CHARS.index(char.upper()) * (1 if char.isupper() else -1)
                    file += 1
                else:
                    raise ValueError("Invalid FEN placement")
                if file > 8:
                    raise ValueError("FEN rank is too wide")
            if file != 8:
                raise ValueError("Each FEN rank must contain eight squares")
        if side not in ("w", "b"):
            raise ValueError("FEN side must be w or b")
        turn = WHITE if side == "w" else BLACK
        if rights != "-" and (not rights or any(c not in "KQkq" for c in rights)
                              or len(set(rights)) != len(rights)):
            raise ValueError("Invalid castling rights")
        castling = sum(bit for char, bit in zip("KQkq", (WK, WQ, BK, BQ)) if char in rights)
        try:
            halfmove, fullmove = int(half), int(full)
        except ValueError as exc:
            raise ValueError("Invalid FEN counters") from exc
        if halfmove < 0 or fullmove < 1:
            raise ValueError("FEN counters are out of range")
        kings = []
        for color in (WHITE, BLACK):
            found = [s for s in SQUARES if cells[s] == color * KING]
            if len(found) != 1:
                raise ValueError("A position needs exactly one king of each color")
            kings.append(found[0])
            if sum(cells[s] * color > 0 for s in SQUARES) > 16:
                raise ValueError("A color cannot have more than sixteen pieces")
            if sum(cells[s] == color * PAWN for s in SQUARES) > 8:
                raise ValueError("A color cannot have more than eight pawns")
        if any(abs(cells[s]) == PAWN for s in (*range(8), *range(112, 120))):
            raise ValueError("Unpromoted pawns cannot occupy the first or eighth rank")
        for bit, king_sq, rook_sq, color in ((WK, 4, 7, 1), (WQ, 4, 0, 1),
                                               (BK, 116, 119, -1), (BQ, 116, 112, -1)):
            if castling & bit and (cells[king_sq] != color * KING or cells[rook_sq] != color * ROOK):
                raise ValueError("Castling rights require a king and rook on their home squares")
        ep = None if ep_text == "-" else parse_square(ep_text)
        if ep is not None:
            if ep >> 4 != (5 if turn == WHITE else 2) or cells[ep] or cells[ep - 16 * turn] != -turn:
                raise ValueError("Invalid en passant target")
            if cells[ep + 16 * turn]:
                raise ValueError("The double-pushed pawn's origin must be empty")
        candidate = object.__new__(Board)
        candidate.cells, candidate.turn, candidate.kings = cells, turn, kings
        if candidate.is_attacked(kings[1 if turn == WHITE else 0], turn):
            raise ValueError("The side that just moved cannot have left its king in check")
        self.cells, self.turn, self.kings = cells, turn, kings
        self.castling, self.ep = castling, ep
        self.halfmove, self.fullmove = halfmove, fullmove
        self._undo = []
        self.key = self.compute_key()
        self.key_history = [self.key]

    def fen(self) -> str:
        rows = []
        for rank in range(7, -1, -1):
            row, empty = "", 0
            for file in range(8):
                piece = self.cells[rank * 16 + file]
                if not piece:
                    empty += 1
                else:
                    if empty:
                        row += str(empty)
                        empty = 0
                    char = PIECE_CHARS[abs(piece)]
                    row += char if piece > 0 else char.lower()
            rows.append(row + (str(empty) if empty else ""))
        rights = "".join(c for c, bit in zip("KQkq", (WK, WQ, BK, BQ)) if self.castling & bit) or "-"
        return f"{'/'.join(rows)} {'w' if self.turn == WHITE else 'b'} {rights} " + (
            square_name(self.ep) if self.ep is not None else "-"
        ) + f" {self.halfmove} {self.fullmove}"

    def is_attacked(self, square: int, by: int) -> bool:
        cells = self.cells
        for offset in (-1, 1):
            src = square - by * 16 + offset
            if not src & 0x88 and cells[src] == by * PAWN:
                return True
        for step in KNIGHT_STEPS:
            src = square + step
            if not src & 0x88 and cells[src] == by * KNIGHT:
                return True
        for step in KING_STEPS:
            src = square + step
            if not src & 0x88 and cells[src] == by * KING:
                return True
        for directions, kinds in ((BISHOP_STEPS, (BISHOP, QUEEN)), (ROOK_STEPS, (ROOK, QUEEN))):
            for step in directions:
                src = square + step
                while not src & 0x88:
                    piece = cells[src]
                    if piece:
                        if piece * by > 0 and abs(piece) in kinds:
                            return True
                        break
                    src += step
        return False

    def in_check(self, color: int | None = None) -> bool:
        color = self.turn if color is None else color
        return self.is_attacked(self.kings[0 if color == WHITE else 1], -color)

    def _legal_ep_file(self) -> int | None:
        """FIDE repetition identity ignores EP if *no legal* EP capture exists."""
        if self.ep is None:
            return None
        target, turn = self.ep, self.turn
        victim = target - turn * 16
        king = self.kings[0 if turn == WHITE else 1]
        for offset in (-1, 1):
            src = victim + offset
            if not src & 0x88 and self.cells[src] == turn * PAWN:
                captured = self.cells[victim]
                self.cells[src] = self.cells[victim] = 0
                self.cells[target] = turn * PAWN
                legal = not self.is_attacked(king, -turn)
                self.cells[target] = 0
                self.cells[src], self.cells[victim] = turn * PAWN, captured
                if legal:
                    return target & 7
        return None

    def compute_key(self) -> int:
        key = _Z_CASTLE[self.castling] ^ (_Z_TURN if self.turn == BLACK else 0)
        for square in SQUARES:
            piece = self.cells[square]
            if piece:
                key ^= _Z_PIECES[piece_index(piece)][square]
        ep_file = self._legal_ep_file()
        if ep_file is not None:
            key ^= _Z_EP[ep_file]
        return key

    def _set_piece(self, square: int, piece: int) -> None:
        old = self.cells[square]
        if old:
            self.key ^= _Z_PIECES[piece_index(old)][square]
        self.cells[square] = piece
        if piece:
            self.key ^= _Z_PIECES[piece_index(piece)][square]

    def push(self, move: Move) -> None:
        src, dst = move.from_sq, move.to_sq
        piece, target = self.cells[src], self.cells[dst]
        color = self.turn
        capture_sq = dst
        if abs(piece) == PAWN and dst == self.ep and not target:
            capture_sq = dst - color * 16
            target = self.cells[capture_sq]
        self._undo.append(Undo(move, piece, target, capture_sq, self.castling, self.ep,
                               self.halfmove, self.fullmove, self.key, tuple(self.kings)))
        ep_file = self._legal_ep_file()
        if ep_file is not None:
            self.key ^= _Z_EP[ep_file]
        self.key ^= _Z_CASTLE[self.castling]
        self._set_piece(src, 0)
        if capture_sq != dst:
            self._set_piece(capture_sq, 0)
        self._set_piece(dst, color * move.promotion if move.promotion else piece)
        if abs(piece) == KING:
            self.kings[0 if color == WHITE else 1] = dst
            if abs(dst - src) == 2:
                rook_src, rook_dst = (src + 3, src + 1) if dst > src else (src - 4, src - 1)
                self._set_piece(rook_src, 0)
                self._set_piece(rook_dst, color * ROOK)
        self.castling &= _RIGHTS_MASK.get(src, 15) & _RIGHTS_MASK.get(dst, 15)
        self.ep = (src + dst) // 2 if abs(piece) == PAWN and abs(dst - src) == 32 else None
        self.halfmove = 0 if abs(piece) == PAWN or target else self.halfmove + 1
        self.fullmove += color == BLACK
        self.turn = -color
        self.key ^= _Z_TURN ^ _Z_CASTLE[self.castling]
        ep_file = self._legal_ep_file()
        if ep_file is not None:
            self.key ^= _Z_EP[ep_file]
        self.key_history.append(self.key)

    def pop(self) -> Move:
        if not self._undo:
            raise IndexError("No move to undo")
        undo = self._undo.pop()
        src, dst = undo.move.from_sq, undo.move.to_sq
        self.turn = -self.turn
        self.cells[src], self.cells[dst] = undo.moved, 0
        self.cells[undo.capture_sq] = undo.captured
        if abs(undo.moved) == KING and abs(dst - src) == 2:
            rook_src, rook_dst = (src + 3, src + 1) if dst > src else (src - 4, src - 1)
            self.cells[rook_src], self.cells[rook_dst] = self.turn * ROOK, 0
        self.castling, self.ep = undo.castling, undo.ep
        self.halfmove, self.fullmove, self.key = undo.halfmove, undo.fullmove, undo.key
        self.kings[:] = undo.kings
        self.key_history.pop()
        return undo.move

    def is_capture(self, move: Move) -> bool:
        return bool(self.cells[move.to_sq]) or (abs(self.cells[move.from_sq]) == PAWN and move.to_sq == self.ep)

    def pseudo_legal_moves(self, captures_only: bool = False) -> Iterator[Move]:
        cells, color = self.cells, self.turn
        for src in SQUARES:
            piece = cells[src]
            if piece * color <= 0:
                continue
            kind = abs(piece)
            if kind == PAWN:
                forward = src + color * 16
                promotion_rank = 7 if color == WHITE else 0
                if not forward & 0x88 and not cells[forward]:
                    if forward >> 4 == promotion_rank:
                        for promo in (QUEEN, ROOK, BISHOP, KNIGHT):
                            yield Move(src, forward, promo)
                    elif not captures_only:
                        yield Move(src, forward)
                        double = forward + color * 16
                        if src >> 4 == (1 if color == WHITE else 6) and not cells[double]:
                            yield Move(src, double)
                for offset in (-1, 1):
                    dst = forward + offset
                    if dst & 0x88:
                        continue
                    if (cells[dst] * color < 0 and abs(cells[dst]) != KING) or dst == self.ep:
                        if dst >> 4 == promotion_rank:
                            for promo in (QUEEN, ROOK, BISHOP, KNIGHT):
                                yield Move(src, dst, promo)
                        else:
                            yield Move(src, dst)
                continue
            if kind in (KNIGHT, KING):
                for step in KNIGHT_STEPS if kind == KNIGHT else KING_STEPS:
                    dst = src + step
                    if dst & 0x88 or cells[dst] * color > 0 or abs(cells[dst]) == KING:
                        continue
                    if not captures_only or cells[dst]:
                        yield Move(src, dst)
                if kind == KING and not captures_only:
                    home = 4 if color == WHITE else 116
                    if src == home and not self.is_attacked(src, -color):
                        if self.castling & (WK if color == WHITE else BK):
                            if not cells[src + 1] and not cells[src + 2] and (
                                not self.is_attacked(src + 1, -color) and not self.is_attacked(src + 2, -color)
                            ):
                                yield Move(src, src + 2)
                        if self.castling & (WQ if color == WHITE else BQ):
                            if not any(cells[src - n] for n in (1, 2, 3)) and (
                                not self.is_attacked(src - 1, -color) and not self.is_attacked(src - 2, -color)
                            ):
                                yield Move(src, src - 2)
                continue
            directions = BISHOP_STEPS if kind == BISHOP else ROOK_STEPS if kind == ROOK else KING_STEPS
            for step in directions:
                dst = src + step
                while not dst & 0x88:
                    target = cells[dst]
                    if target * color > 0 or abs(target) == KING:
                        break
                    if not captures_only or target:
                        yield Move(src, dst)
                    if target:
                        break
                    dst += step

    def legal_moves(self, captures_only: bool = False) -> Iterator[Move]:
        color = self.turn
        for move in self.pseudo_legal_moves(captures_only):
            self.push(move)
            legal = not self.in_check(color)
            self.pop()
            if legal:
                yield move

    def parse_uci(self, text: str) -> Move:
        move = Move.from_uci(text.strip())
        if move not in self.legal_moves():
            raise ValueError(f"Illegal move: {text}")
        return move

    def play_uci(self, text: str) -> Move:
        move = self.parse_uci(text)
        self.push(move)
        return move

    def repetition_count(self) -> int:
        return self.key_history.count(self.key)

    def insufficient_material(self) -> bool:
        pieces = [(s, abs(self.cells[s])) for s in SQUARES if self.cells[s] and abs(self.cells[s]) != KING]
        if not pieces:
            return True
        if len(pieces) == 1 and pieces[0][1] in (KNIGHT, BISHOP):
            return True
        if all(kind == BISHOP for _, kind in pieces):
            return len({((s >> 4) + (s & 7)) % 2 for s, _ in pieces}) == 1
        return False

    def outcome(self, legal: list[Move] | None = None) -> Outcome | None:
        moves = list(self.legal_moves()) if legal is None else legal
        if not moves:
            if self.in_check():
                winner = -self.turn
                return Outcome("1-0" if winner == WHITE else "0-1", "Checkmate", winner)
            return Outcome("1/2-1/2", "Stalemate")
        if self.insufficient_material():
            return Outcome("1/2-1/2", "Insufficient material")
        if self.halfmove >= 150:
            return Outcome("1/2-1/2", "Seventy-five-move rule")
        if self.repetition_count() >= 5:
            return Outcome("1/2-1/2", "Fivefold repetition")
        return None

    def claimable_draws(self, intended: Move | None = None) -> tuple[str, ...]:
        """Current-position or declared-next-move claims, distinct from automatic draws."""
        if intended is not None:
            if intended not in self.legal_moves():
                raise ValueError("An intended claim move must be legal")
            self.push(intended)
        try:
            reasons = []
            if self.repetition_count() >= 3:
                reasons.append("Threefold repetition")
            if self.halfmove >= 100 and any(self.legal_moves()):
                reasons.append("Fifty-move rule")
            return tuple(reasons)
        finally:
            if intended is not None:
                self.pop()


def perft(board: Board, depth: int) -> int:
    if depth < 0:
        raise ValueError("Depth cannot be negative")
    if depth == 0:
        return 1
    if depth == 1:
        return sum(1 for _ in board.legal_moves())
    total = 0
    for move in board.legal_moves():
        board.push(move)
        total += perft(board, depth - 1)
        board.pop()
    return total


def divide(board: Board, depth: int) -> dict[str, int]:
    if depth < 1:
        raise ValueError("Divide depth must be at least one")
    counts = {}
    for move in board.legal_moves():
        board.push(move)
        counts[move.uci()] = perft(board, depth - 1)
        board.pop()
    return counts
