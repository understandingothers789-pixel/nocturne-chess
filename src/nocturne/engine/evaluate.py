"""Handcrafted tapered evaluation. Values are centipawns, never Elo estimates."""

from __future__ import annotations

from ..core.board import (
    Board, PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING, SQUARES,
    KNIGHT_STEPS, KING_STEPS, BISHOP_STEPS, ROOK_STEPS,
)

MG_VALUE = (0, 100, 320, 335, 500, 950, 0)
EG_VALUE = (0, 125, 305, 325, 525, 950, 0)
PHASE = (0, 0, 1, 1, 2, 4, 0)
_MOBILITY = (0, 0, 4, 4, 2, 1, 0)


def _pst(kind: int, rank: int, file: int) -> tuple[int, int]:
    center = 7 - abs(2 * file - 7) - abs(2 * rank - 7)
    if kind == PAWN:
        return rank * 7 + max(0, center) * 3, rank * rank * 3 + max(0, center)
    if kind == KNIGHT:
        return center * 7 - (12 if rank == 0 else 0), center * 5
    if kind == BISHOP:
        return center * 4 + (8 if rank > 0 else -8), center * 3
    if kind == ROOK:
        return (22 if rank == 6 else 0) + rank * 2, rank * 3 + center
    if kind == QUEEN:
        return center * 2 - (10 if rank > 2 else 0), center * 4
    return (-rank * 13 + (22 if file in (1, 2, 6) and rank < 2 else 0), center * 8)


PST = {kind: tuple(_pst(kind, s >> 4, s & 7) if not s & 0x88 else (0, 0)
                   for s in range(128)) for kind in range(1, 7)}


def evaluate(board: Board) -> int:
    """Return a score for the side to move; positive favors that side.

    Material + piece-square values are interpolated across 24 phase units.
    Pseudo-mobility, pawn structure, bishop pair, rook files, king shelter,
    king-ring pressure and central control supply explicit positional terms.
    Evaluation never changes board state or generates legal moves.
    """
    cells = board.cells
    mg, eg = [0, 0], [0, 0]
    pawns: list[list[int]] = [[], []]
    files = [[0] * 8, [0] * 8]
    attacks = [[0] * 128, [0] * 128]
    bishops = [0, 0]
    rooks: list[list[int]] = [[], []]
    phase = 0
    for square in SQUARES:
        piece = cells[square]
        if not piece:
            continue
        color = 1 if piece > 0 else -1
        index = 0 if color == 1 else 1
        kind = abs(piece)
        relative = square if color == 1 else square ^ 112
        pmg, peg = PST[kind][relative]
        mg[index] += MG_VALUE[kind] + pmg
        eg[index] += EG_VALUE[kind] + peg
        phase += PHASE[kind]
        if kind == PAWN:
            pawns[index].append(square)
            files[index][square & 7] += 1
            for step in (color * 16 - 1, color * 16 + 1):
                dst = square + step
                if not dst & 0x88:
                    attacks[index][dst] += 1
        elif kind in (KNIGHT, KING):
            mobility = 0
            for step in KNIGHT_STEPS if kind == KNIGHT else KING_STEPS:
                dst = square + step
                if not dst & 0x88:
                    attacks[index][dst] += 1
                    mobility += cells[dst] * color <= 0
            mg[index] += mobility * _MOBILITY[kind]
            eg[index] += mobility * _MOBILITY[kind]
        else:
            if kind == BISHOP:
                bishops[index] += 1
            if kind == ROOK:
                rooks[index].append(square)
            directions = BISHOP_STEPS if kind == BISHOP else ROOK_STEPS if kind == ROOK else KING_STEPS
            mobility = 0
            for step in directions:
                dst = square + step
                while not dst & 0x88:
                    attacks[index][dst] += 1
                    target = cells[dst]
                    mobility += target * color <= 0
                    if target:
                        break
                    dst += step
            mg[index] += mobility * _MOBILITY[kind]
            eg[index] += mobility * (_MOBILITY[kind] + (1 if kind == ROOK else 0))
    for index, color in enumerate((1, -1)):
        enemy = 1 - index
        if bishops[index] >= 2:
            mg[index] += 28
            eg[index] += 42
        for file in range(8):
            doubled = max(0, files[index][file] - 1)
            mg[index] -= doubled * 13
            eg[index] -= doubled * 20
        for square in pawns[index]:
            file, rank = square & 7, (square >> 4 if color == 1 else 7 - (square >> 4))
            adjacent = [f for f in (file - 1, file + 1) if 0 <= f < 8]
            isolated = not any(files[index][f] for f in adjacent)
            if isolated:
                mg[index] -= 15
                eg[index] -= 12
            enemy_ahead = [s for s in pawns[enemy] if abs((s & 7) - file) <= 1
                           and ((s >> 4) - (square >> 4)) * color > 0]
            if not enemy_ahead:
                mg[index] += (0, 0, 6, 15, 30, 55, 90, 0)[rank]
                eg[index] += (0, 0, 12, 28, 55, 100, 170, 0)[rank]
            forward = square + color * 16
            support_behind = any((s & 7) in adjacent and ((s >> 4) - (square >> 4)) * color <= 0
                                 for s in pawns[index])
            if not isolated and not support_behind and not forward & 0x88 and attacks[enemy][forward]:
                mg[index] -= 10
                eg[index] -= 7
            if attacks[index][square]:
                mg[index] += 6
                eg[index] += 8
        for square in rooks[index]:
            file = square & 7
            if not files[index][file]:
                mg[index] += 12 if files[enemy][file] else 24
                eg[index] += 8 if files[enemy][file] else 14
        king = board.kings[index]
        pressure = 0
        for step in KING_STEPS:
            dst = king + step
            if not dst & 0x88:
                pressure += min(3, attacks[enemy][dst])
        mg[index] -= pressure * 9
        shield_rank = (king >> 4) + color
        if 0 <= shield_rank < 8:
            for file in ((king & 7) - 1, king & 7, (king & 7) + 1):
                if 0 <= file < 8 and cells[shield_rank * 16 + file] == color * PAWN:
                    mg[index] += 12
        for center in (51, 52, 67, 68):
            mg[index] += min(3, attacks[index][center]) * 5
            eg[index] += min(3, attacks[index][center]) * 2
    phase = min(24, phase)
    white_score = int(((mg[0] - mg[1]) * phase + (eg[0] - eg[1]) * (24 - phase)) / 24)
    return white_score * board.turn + 10
