"""Legal SAN and single-game PGN interchange with recursive variations."""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from .board import Board, KING, PAWN, PIECE_CHARS, START_FEN, Move, square_name


def san(board: Board, move: Move, legal: list[Move] | None = None) -> str:
    legal = list(board.legal_moves()) if legal is None else legal
    if move not in legal:
        raise ValueError(f"Cannot format illegal move {move.uci()}")
    piece = abs(board.cells[move.from_sq])
    capture = board.is_capture(move)
    if piece == KING and abs(move.to_sq - move.from_sq) == 2:
        text = "O-O" if move.to_sq > move.from_sq else "O-O-O"
    else:
        text = "" if piece == PAWN else PIECE_CHARS[piece]
        if piece != PAWN:
            others = [m for m in legal if m != move and m.to_sq == move.to_sq
                      and abs(board.cells[m.from_sq]) == piece]
            if others:
                if all((m.from_sq & 7) != (move.from_sq & 7) for m in others):
                    text += square_name(move.from_sq)[0]
                elif all((m.from_sq >> 4) != (move.from_sq >> 4) for m in others):
                    text += square_name(move.from_sq)[1]
                else:
                    text += square_name(move.from_sq)
        elif capture:
            text += square_name(move.from_sq)[0]
        text += ("x" if capture else "") + square_name(move.to_sq)
        if move.promotion:
            text += "=" + PIECE_CHARS[move.promotion]
    board.push(move)
    try:
        if board.in_check():
            text += "+" if any(board.legal_moves()) else "#"
    finally:
        board.pop()
    return text


def _normalized_san(text: str) -> str:
    return re.sub(r"[+#?!]+$", "", text.strip().replace("0", "O"))


def parse_san(board: Board, text: str) -> Move:
    normalized = _normalized_san(text)
    legal = list(board.legal_moves())
    found = [m for m in legal if _normalized_san(san(board, m, legal)) == normalized]
    if len(found) != 1:
        raise ValueError(f"Illegal or ambiguous SAN: {text!r}")
    return found[0]


@dataclass(slots=True)
class PgnGame:
    headers: dict[str, str] = field(default_factory=dict)
    initial_fen: str = START_FEN
    moves: list[Move] = field(default_factory=list)
    result: str = "*"
    edges: list[tuple[int, Move]] = field(default_factory=list)


_TAG = re.compile(r'^\s*\[([A-Za-z0-9_]+)\s+"((?:\\.|[^"\\])*)"\]\s*', re.MULTILINE)
_RESULTS = {"1-0", "0-1", "1/2-1/2", "*"}


def read_pgn(text: str) -> PgnGame:
    """Read one game with ordered recursive variations; skip comments and NAGs."""
    if len(text) > 4_000_000:
        raise ValueError("PGN exceeds the 4 MB single-game import limit")
    headers: dict[str, str] = {}
    pos = 0
    text = text.lstrip("\ufeff")
    while match := _TAG.match(text, pos):
        headers[match[1]] = re.sub(r'\\([\\"])', r'\1', match[2])
        pos = match.end()
    if headers.get("Variant", "Standard").lower() not in ("standard", "chess"):
        raise ValueError("Only standard chess PGNs are supported")
    initial = headers.get("FEN", START_FEN)
    board = Board(initial)
    game = PgnGame(headers, initial)
    # Strip comments/NAGs while retaining RAV parentheses.
    body = re.sub(r";[^\n]*|\{[^}]*\}", " ", text[pos:])
    if "{" in body or "}" in body:
        raise ValueError("Unclosed or unmatched PGN comment")
    body = re.sub(r"\$\d+", " ", body)
    body = re.sub(r"\d+\.(?:\.\.)?", " ", body)
    tokens = re.findall(r"[()]|[^\s()]+", body)
    current, stack, ended, root_result = 0, [], False, None
    lookup, children = {}, {0: []}
    for token in tokens:
        if token == "(":
            if ended or current == 0:
                raise ValueError("Variation has no preceding move")
            stack.append((board.copy(), current, ended))
            current = game.edges[current - 1][0]
            board.pop()
            ended = False
        elif token == ")":
            if not stack:
                raise ValueError("Unmatched PGN variation terminator")
            board, current, ended = stack.pop()
        elif token in ("...", "e.p.", "ep") or re.fullmatch(r"[!?]+", token):
            continue
        elif token in _RESULTS:
            if ended:
                raise ValueError("Import one PGN game at a time")
            ended = True
            if not stack:
                root_result = token
        else:
            if ended:
                raise ValueError("Import one PGN game at a time")
            move = parse_san(board, token)
            key = (current, move)
            if key not in lookup:
                if len(game.edges) >= 20_000:
                    raise ValueError("PGN has too many moves")
                game.edges.append((current, move))
                lookup[key] = len(game.edges)
                children.setdefault(current, []).append(len(game.edges))
            current = lookup[key]
            board.push(move)
    if stack:
        raise ValueError("Unclosed PGN variation")
    index = 0
    while children.get(index):
        index = children[index][0]
        game.moves.append(game.edges[index - 1][1])
    game.result = root_result or headers.get("Result", "*")
    if game.result not in _RESULTS:
        raise ValueError("Invalid PGN result")
    if "Result" in headers and headers["Result"] != game.result:
        raise ValueError("PGN header and movetext results disagree")
    return game


def write_pgn(game: PgnGame) -> str:
    defaults = {"Event": "Nocturne game", "Site": "Local", "Date": "????.??.??",
                "Round": "-", "White": "White", "Black": "Black", "Result": game.result}
    headers = defaults | game.headers | {"Result": game.result}
    if game.initial_fen != START_FEN:
        headers.update({"SetUp": "1", "FEN": game.initial_fen})
    else:
        headers.pop("SetUp", None)
        headers.pop("FEN", None)
    lines = []
    for name, value in headers.items():
        if not re.fullmatch(r"[A-Za-z0-9_]+", name):
            continue
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
        lines.append(f'[{name} "{escaped}"]')
    tokens = []
    if game.edges:
        from .variation import build_nodes, tree_tokens
        nodes = build_nodes(game.initial_fen, game.edges)
        tokens = [text for text, _ in tree_tokens(nodes, game.initial_fen)]
    else:
        board = Board(game.initial_fen)
        for i, move in enumerate(game.moves):
            if board.turn == 1:
                tokens.append(f"{board.fullmove}.")
            elif i == 0:
                tokens.append(f"{board.fullmove}...")
            tokens.append(san(board, move))
            board.push(move)
    tokens.append(game.result)
    wrapped, current = [], ""
    for token in tokens:
        if current and len(current) + len(token) + 1 > 88:
            wrapped.append(current)
            current = ""
        current += (" " if current else "") + token
    if current:
        wrapped.append(current)
    return "\n".join(lines) + "\n\n" + "\n".join(wrapped) + "\n"
