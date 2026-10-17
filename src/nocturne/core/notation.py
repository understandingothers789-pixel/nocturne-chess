"""Legal SAN and single-game PGN interchange with recursive variations."""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from .board import Board, KING, PAWN, PIECE_CHARS, START_FEN, Move, square_name


def san(board: Board, move: Move, legal: list[Move] | None = None) -> str:
    if hasattr(board, "native"):
        from .rules import native

        return board.native.san(native(move))
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
            others = [
                m
                for m in legal
                if m != move and m.to_sq == move.to_sq and abs(board.cells[m.from_sq]) == piece
            ]
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
    if hasattr(board, "native"):
        from .rules import wrapped

        return wrapped(board.native.parse_san(text))
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
    annotations: dict[int, dict] = field(default_factory=dict)


def _validate_structure(text):
    text = re.sub(r"(?m)^%[^\n]*", "", text)
    depth, brace, quoted, line_comment, escaped = 0, False, False, False, False
    body = []
    for char in text:
        if line_comment:
            if char == "\n":
                line_comment = False
                body.append(" ")
        elif brace:
            if char == "}":
                brace = False
                body.append(" ")
        elif quoted:
            if char == '"' and not escaped:
                quoted = False
            escaped = char == "\\" and not escaped
        elif char == '"':
            quoted = True
        elif char == ";":
            line_comment = True
        elif char == "{":
            brace = True
        elif char == "}":
            raise ValueError("Unmatched PGN comment")
        else:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth < 0:
                    raise ValueError("Unmatched PGN variation")
            body.append(char)
    if depth or brace or quoted:
        raise ValueError("Unclosed PGN variation, comment or tag")
    return "".join(body)


def read_pgn(text: str) -> PgnGame:
    body = _validate_structure(text)
    if len(re.findall(r"(?<!\S)(?:1-0|0-1|1/2-1/2|\*)(?!\S)", body)) > 1:
        raise ValueError("Import one PGN game at a time")
    games = read_pgns(text)
    if len(games) != 1:
        raise ValueError("Import one PGN game at a time")
    return games[0]


def read_pgns(text):
    import io
    import chess.pgn
    from .rules import wrapped

    if len(text) > 4_000_000:
        raise ValueError("PGN exceeds the 4 MB import limit")
    _validate_structure(text)
    stream = io.StringIO(text.lstrip("\ufeff"))
    games = []
    while (source := chess.pgn.read_game(stream)) is not None:
        if source.errors:
            raise ValueError(str(source.errors[0]))
        if source.headers.get("Variant", "Standard").lower() not in (
            "standard",
            "chess",
            "chess960",
            "fischerandom",
        ):
            raise ValueError("Only standard chess and Chess960 are supported")
        board = source.board()
        result = PgnGame(
            {k: re.sub(r'\\([\\"])', r"\1", v) for k, v in source.headers.items()},
            board.fen(shredder=board.chess960, en_passant="fen"),
            result=source.headers.get("Result", "*"),
        )
        result.annotations[0] = {"comment": source.comment}
        stack = [(child, 0) for child in reversed(source.variations)]
        while stack:
            node, parent = stack.pop()
            result.edges.append((parent, wrapped(node.move)))
            index = len(result.edges)
            result.annotations[index] = {
                "comment": node.comment,
                "starting_comment": node.starting_comment,
                "nags": sorted(node.nags),
            }
            stack.extend((child, index) for child in reversed(node.variations))
            if len(result.edges) > 20_000:
                raise ValueError("PGN has too many moves")
        node = source
        while node.variations:
            node = node.variations[0]
            result.moves.append(wrapped(node.move))
        games.append(result)
        if len(games) > 1000:
            raise ValueError("PGN import is limited to 1000 games")
    if not games:
        raise ValueError("No PGN game found")
    return games


def write_pgn(game: PgnGame) -> str:
    import chess
    import chess.pgn
    import chess.engine
    from .rules import Board as RulesBoard, native

    source = chess.pgn.Game()
    board = RulesBoard(game.initial_fen).native
    source.setup(board)
    source.headers.update(game.headers)
    source.headers["Result"] = game.result
    nodes = [source]
    edges = game.edges or [(i, move) for i, move in enumerate(game.moves)]
    for parent, move in edges:
        if not 0 <= parent < len(nodes):
            raise ValueError("Invalid PGN variation parent")
        nodes.append(nodes[parent].add_variation(native(move)))
    for index, data in game.annotations.items():
        node = nodes[index]
        node.comment = data.get("comment", "")
        if index:
            node.starting_comment = data.get("starting_comment", "")
            node.nags.update(data.get("nags", []))
        analysis = data.get("analysis", {})
        value = data.get("evaluation")
        if value is not None and analysis.get("bound", "exact") == "exact":
            if analysis.get("score_type") == "mate":
                score = chess.engine.Mate(analysis["white_value"])
            else:
                score = chess.engine.Cp(value)
            node.set_eval(chess.engine.PovScore(score, chess.WHITE), analysis.get("depth"))

    class Exporter(chess.pgn.StringExporter):
        def visit_header(self, tagname, tagvalue):
            tagvalue = (
                tagvalue.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
            )
            super().visit_header(tagname, tagvalue)

    exporter = Exporter(headers=True, variations=True, comments=True, columns=100)
    return source.accept(exporter) + "\n"
