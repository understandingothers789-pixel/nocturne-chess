"""Find stable, instructive material balances in a saved continuation."""

from dataclasses import dataclass
from itertools import groupby

import chess


# Cancel bishops and knights as a group so ordinary minor-piece exchanges
# don't create a material-imbalance lesson by themselves.
KINDS = (
    ("pawn", "pawns", 1, (chess.PAWN,)),
    ("minor piece", "minor pieces", 3, (chess.KNIGHT, chess.BISHOP)),
    ("rook", "rooks", 5, (chess.ROOK,)),
    ("queen", "queens", 9, (chess.QUEEN,)),
)


@dataclass(frozen=True)
class MaterialStudy:
    signature: tuple[int, ...]
    ply: int
    setup: int
    title: str
    description: str
    verified_eval: bool


def _material_delta(board):
    return tuple(sum(board.pieces_mask(piece, chess.WHITE).bit_count() - board.pieces_mask(piece, chess.BLACK).bit_count()
                     for piece in pieces) for _, _, _, pieces in KINDS)


def _describe(counts, *, compact=False):
    terms = []
    for count, (singular, plural, _, _) in reversed(list(zip(counts, KINDS))):
        if count:
            terms.append(singular if count == 1 and compact else f"{count} {singular if count == 1 else plural}")
    return " + ".join(terms) or "no extra material"


def material_studies(fen, pv, white_line_score, position_scores, *, first_ply, last_ply):
    """Use cached position evaluations first and the root line score as a clue."""
    board = chess.Board(fen)
    balances = [_material_delta(board)]
    for uci in pv[:last_ply + 2]:
        board.push_uci(uci)
        balances.append(_material_delta(board))

    seen = set()
    for delta, run in groupby(enumerate(balances), key=lambda sample: sample[1]):
        samples = list(run)
        start, end = samples[0][0], samples[-1][0]
        # A recapture can briefly create a material deficit. Require a full
        # move of unchanged balance after a new imbalance has materialized.
        if end - start < (min(2, len(pv)) if start == 0 else 2) or delta in seen:
            continue
        ply = 0 if start == 0 else max(start, first_ply)
        if ply > min(end, last_ply):
            continue

        white = tuple(max(0, count) for count in delta)
        black = tuple(max(0, -count) for count in delta)
        balance = sum(count * kind[2] for count, kind in zip(delta, KINDS))
        deficit = abs(balance)
        side = "Black" if balance > 0 else "White"
        cached_score = position_scores.get(ply)
        score = cached_score if cached_score is not None else white_line_score
        side_score = None if score is None else (score if side == "White" else -score)
        compensated = deficit >= 2 and side_score is not None and side_score > -100
        unusual_exchange = (sum(white) and sum(black) and max(sum(white), sum(black)) >= 2
                            and (any(white[1:]) or any(black[1:])))

        if unusual_exchange and (deficit <= 1 or compensated):
            # Put the more valuable piece first so familiar pairings scan well.
            first, second = sorted((white, black), key=lambda counts: counts[::-1], reverse=True)
            title = f"{_describe(first, compact=True)} for {_describe(second, compact=True)}"
        elif compensated:
            title = f"{side} down {deficit} points"
        else:
            continue

        parts = [f"Extra material after matching pieces cancel: White has {_describe(white)}; Black has {_describe(black)}."]
        if compensated:
            parts.append(f"{side} is down {deficit} points in material.")
        if score is not None:
            source = "Cached position eval" if cached_score is not None else "Root line eval"
            perspective, shown_score = (side, side_score) if compensated else ("White", score)
            parts.append(f"{source} for {perspective}: {shown_score / 100:+.2f}.")
            if cached_score is None and ply:
                parts.append("The resulting position was not separately evaluated.")
        seen.add(delta)
        yield MaterialStudy(delta, ply, max(0, start - 1), title, " ".join(parts), cached_score is not None)
