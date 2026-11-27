"""Online chess databases: validated queries/results and a bounded local cache."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlencode

import chess

EXPLORER_URL = "https://explorer.lichess.org"
CHESSDB_URL = "https://www.chessdb.cn"
TABLEBASE_URL = "https://tablebase.lichess.ovh"
SPEEDS = ("ultraBullet", "bullet", "blitz", "rapid", "classical", "correspondence")
RATINGS = (0, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500)
MAX_RESPONSE = 512 * 1024
CACHE_AGE = 86400
GAME_ID = re.compile(r"[A-Za-z0-9]{8}")


def valid_explorer_month(month):
    return isinstance(month, str) and (not month or bool(re.fullmatch(r"[1-9][0-9]{3}-(0[1-9]|1[0-2])", month)))


def rating_groups(values):
    if not isinstance(values, (list, tuple)) or any(type(value) is not int or value not in RATINGS for value in values):
        raise ValueError("Unsupported rating band")
    return tuple(sorted(set(values)))


@dataclass(frozen=True)
class ExplorerQuery:
    fen: str
    source: str = "masters"
    speed: str = "all"
    rating: int = 0
    since: str = ""
    until: str = ""
    groups: tuple[int, ...] = ()
    include_games: bool = False

    def __post_init__(self):
        if self.source not in ("masters", "lichess", "chessdb", "tablebase") or self.speed not in ("all", *SPEEDS):
            raise ValueError("Unsupported explorer source or speed")
        if type(self.rating) is not int or self.rating not in RATINGS:
            raise ValueError("Unsupported rating group")
        if self.source in ("masters", "lichess"):
            if not valid_explorer_month(self.since) or not valid_explorer_month(self.until):
                raise ValueError("Enter months as YYYY-MM")
            if self.since and self.until and self.since > self.until:
                raise ValueError("The first month must be on or before the last month")
        else:
            object.__setattr__(self, "since", "")
            object.__setattr__(self, "until", "")
            object.__setattr__(self, "include_games", False)
        groups = rating_groups(self.groups) if self.source == "lichess" else ()
        object.__setattr__(self, "groups", groups)
        board = chess.Board(self.fen)
        if not board.is_valid() or any(c not in "KQkq-" for c in self.fen.split()[2]):
            raise ValueError("Opening explorer supports standard chess positions")
        # Opening counts ignore counters; cloud analysis retains the fifty-move clock.
        fields = board.fen(en_passant="legal").split()
        if self.source == "tablebase" and (fields[2] != "-" or board.occupied.bit_count() > 7):
            raise ValueError("Tablebase requires at most seven pieces and no castling rights")
        canonical = fields[:5] + ["1"] if self.source in ("chessdb", "tablebase") else fields[:4] + ["0", "1"]
        object.__setattr__(self, "fen", " ".join(canonical))

    @property
    def label(self):
        return {"masters": "Lichess Masters", "lichess": "Lichess players", "chessdb": "ChessDB",
                "tablebase": "Lichess Endgame Tablebase"}[self.source]

    @property
    def date_label(self):
        if self.since and self.until:
            return f"{self.since}–{self.until}"
        return f"From {self.since}" if self.since else f"Through {self.until}" if self.until else ""

    @property
    def rating_label(self):
        if self.groups and self.groups != RATINGS:
            return ", ".join(rating_band(value) for value in self.groups)
        return f"{self.rating}+" if self.rating and not self.groups else "all ratings"

    def url(self, base=None):
        if self.source == "tablebase":
            return (base or TABLEBASE_URL).rstrip("/") + "/standard?" + urlencode({"fen": self.fen})
        base = base or (CHESSDB_URL if self.source == "chessdb" else EXPLORER_URL)
        if self.source == "chessdb":
            return base.rstrip("/") + "/cdb.php?" + urlencode({
                "action": "queryall", "board": self.fen, "json": 1, "learn": 0, "showall": 0,
            })
        params = {"fen": self.fen, "moves": 12, "topGames": (15 if self.source == "masters" else 4)
                  if self.include_games else 0}
        if self.since:
            params["since"] = self.since
        if self.until:
            params["until"] = self.until
        if self.source == "lichess":
            params.update(variant="standard", recentGames=4 if self.include_games else 0,
                          speeds=",".join(SPEEDS if self.speed == "all" else (self.speed,)),
                          ratings=",".join(map(str, self.groups or tuple(r for r in RATINGS if r >= self.rating))))
        return base.rstrip("/") + "/" + self.source + "?" + urlencode(params)

    @property
    def key(self):
        return hashlib.sha256(self.url().encode()).hexdigest()


def rating_band(value):
    index = RATINGS.index(value)
    return f"{value}–{RATINGS[index + 1] - 1}" if index + 1 < len(RATINGS) else f"{value}+"


def _game_sample(row, board, uci=None):
    if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not GAME_ID.fullmatch(row["id"]):
        return None
    move_text = uci or row.get("uci")
    if not isinstance(move_text, str):
        return None
    try:
        move = board.parse_uci(move_text)
    except ValueError:
        return None
    if not move:
        return None
    game = {"id": row["id"], "uci": move.uci(), "san": board.san(move),
            "winner": row.get("winner") if row.get("winner") in ("white", "black") else None}
    month, year = row.get("month"), row.get("year")
    game["month"] = month if valid_explorer_month(month) else ""
    game["year"] = year if type(year) is int and 1000 <= year <= 9999 else None
    for color in ("white", "black"):
        player = row.get(color)
        if not isinstance(player, dict) or not isinstance(player.get("name"), str):
            return None
        rating = player.get("rating")
        game[color] = {"name": " ".join(player["name"].split())[:120],
                       "rating": rating if type(rating) is int and 0 < rating <= 5000 else None}
    return game


def parse_statistics(payload, query):
    """Never trust a remote SAN string or allow a database move to bypass rules."""
    if query.source == "chessdb":
        return parse_chessdb(payload, query)
    if query.source == "tablebase":
        return parse_tablebase(payload, query)
    if not isinstance(payload, dict) or not isinstance(payload.get("moves"), list):
        raise ValueError("Invalid opening statistics")

    def counts(data):
        values = [data.get(k) for k in ("white", "draws", "black")]
        if any(type(n) is not int or not 0 <= n <= 10**15 for n in values):
            raise ValueError("Invalid game counts")
        return dict(zip(("white", "draws", "black"), values), total=sum(values))

    result = counts(payload)
    board = chess.Board(query.fen)
    moves, seen = [], set()
    if len(payload["moves"]) > 128:
        raise ValueError("Too many database moves")
    for row in payload["moves"]:
        if not isinstance(row, dict) or not isinstance(row.get("uci"), str):
            raise ValueError("Invalid database move")
        move = board.parse_uci(row["uci"])
        if not move or move not in board.legal_moves or move in seen:
            raise ValueError("Illegal or duplicate database move")
        seen.add(move)
        move_row = dict(counts(row), uci=move.uci(), san=board.san(move))
        if query.include_games and (game := _game_sample(row.get("game"), board, move.uci())):
            move_row["game"] = game
        moves.append(move_row)
    result["moves"] = sorted(moves, key=lambda row: -row["total"])[:12]
    opening = payload.get("opening")
    result["opening"] = (
        {"eco": str(opening.get("eco", ""))[:8], "name": str(opening.get("name", ""))[:200]}
        if isinstance(opening, dict) else None
    )
    if query.include_games:
        for name, limit in (("topGames", 15 if query.source == "masters" else 4), ("recentGames", 4)):
            rows = payload.get(name)
            games = {}
            for row in rows[:64] if isinstance(rows, list) else ():
                if game := _game_sample(row, board):
                    games.setdefault(game["id"], game)
            result[name] = list(games.values())[:limit]
    return result


TABLEBASE_OUTCOMES = {
    "win": "Win", "syzygy-win": "Syzygy win", "maybe-win": "Possible win",
    "cursed-win": "Win without the 50-move rule", "draw": "Draw",
    "blessed-loss": "Loss without the 50-move rule", "maybe-loss": "Possible loss",
    "syzygy-loss": "Syzygy loss", "loss": "Loss", "unknown": "Unknown",
}


def tablebase_outcome(category, *, after_move=False):
    # The API reports moves from the opponent's perspective after the move.
    if after_move and category.endswith("win"):
        category = "blessed-loss" if category == "cursed-win" else category[:-3] + "loss"
    elif after_move and category.endswith("loss"):
        category = "cursed-win" if category == "blessed-loss" else category[:-4] + "win"
    return TABLEBASE_OUTCOMES[category]


def parse_tablebase(payload, query):
    if (not isinstance(payload, dict) or not isinstance(payload.get("category"), str)
            or payload["category"] not in TABLEBASE_OUTCOMES or payload["category"] == "unknown"):
        raise ValueError("No tablebase result for this position")
    rows = payload.get("moves")
    if not isinstance(rows, list) or len(rows) > 256:
        raise ValueError("Invalid tablebase moves")
    board = chess.Board(query.fen)
    legal = set(board.legal_moves)
    seen, moves = set(), []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("uci"), str):
            raise ValueError("Invalid tablebase move")
        category, dtz = row.get("category"), row.get("dtz")
        if not isinstance(category, str) or category not in TABLEBASE_OUTCOMES:
            raise ValueError("Invalid tablebase outcome")
        if dtz is not None and (type(dtz) is not int or abs(dtz) > 100_000):
            raise ValueError("Invalid tablebase distance")
        move = board.parse_uci(row["uci"])
        if move not in legal or move in seen:
            raise ValueError("Illegal or duplicate tablebase move")
        seen.add(move)
        moves.append(dict(uci=move.uci(), san=board.san(move), category=category, dtz=dtz))
    if seen != legal:
        raise ValueError("Incomplete tablebase result")
    return dict(category=payload["category"], moves=moves)


def parse_chessdb(payload, query):
    if not isinstance(payload, dict) or payload.get("status") not in ("ok", "unknown", "checkmate", "stalemate"):
        raise ValueError("Invalid ChessDB response")
    status = payload["status"]
    board = chess.Board(query.fen)
    if (status == "checkmate" and not board.is_checkmate()) or (status == "stalemate" and not board.is_stalemate()):
        raise ValueError("ChessDB terminal status disagrees with legal rules")
    if status != "ok":
        return {"status": status, "moves": []}
    rows = payload.get("moves")
    if not isinstance(rows, list) or len(rows) > 256:
        raise ValueError("Invalid ChessDB move list")
    moves, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("uci"), str):
            raise ValueError("Invalid ChessDB move")
        move = board.parse_uci(row["uci"])
        score = row.get("score")
        if not move or move not in board.legal_moves or move in seen:
            raise ValueError("Illegal or duplicate ChessDB move")
        if not ((type(score) is int and -40000 <= score <= 40000) or score == "??"):
            raise ValueError("Invalid ChessDB score")
        seen.add(move)
        moves.append({"uci": move.uci(), "san": board.san(move), "score": score,
                      "note": " ".join(str(row.get("note", "")).split())[:120]})
    # These are service scores for the side to move, independent of local MultiPV.
    moves.sort(key=lambda row: -(row["score"] if type(row["score"]) is int else -100000))
    return {"status": status, "moves": moves}


def chessdb_score(score, fen):
    if score == "??":
        return "Unscored"
    white = score * (1 if chess.Board(fen).turn else -1)
    # ChessDB encodes tablebase/mate values above the normal cp range. Preserve
    # those codes instead of inventing a mate distance or a giant pawn score.
    return f"{white / 100:+.2f}" if abs(white) < 10000 else f"DB {white:+}"


class ExplorerCache:
    """Cache failures leave the game library untouched and live requests usable."""

    def __init__(self, path: Path, limit=256):
        self.db = None
        self.limit = limit
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(path, timeout=0.1)
            self.db.execute("CREATE TABLE IF NOT EXISTS positions (key TEXT PRIMARY KEY, stamp REAL, payload TEXT)")
        except (OSError, sqlite3.Error):
            self.close()

    def get(self, key):
        try:
            row = self.db.execute("SELECT stamp, payload FROM positions WHERE key=?", (key,)).fetchone() if self.db else None
            if row and len(row[1]) <= MAX_RESPONSE:
                return float(row[0]), json.loads(row[1])
        except (sqlite3.Error, ValueError, TypeError):
            pass
        return None

    def put(self, key, payload, stamp=None):
        if not self.db:
            return
        try:
            text = json.dumps(payload, ensure_ascii=False, allow_nan=False)
            if len(text.encode()) > MAX_RESPONSE:
                return
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO positions VALUES (?, ?, ?)",
                                (key, time.time() if stamp is None else stamp, text))
                self.db.execute("DELETE FROM positions WHERE key NOT IN "
                                "(SELECT key FROM positions ORDER BY stamp DESC, key LIMIT ?)", (self.limit,))
        except (sqlite3.Error, ValueError, TypeError):
            pass

    def close(self):
        if self.db:
            self.db.close()
            self.db = None
