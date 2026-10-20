"""Online chess databases: validated queries/results and a bounded local cache."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlencode

import chess

EXPLORER_URL = "https://explorer.lichess.org"
CHESSDB_URL = "https://www.chessdb.cn"
SPEEDS = ("ultraBullet", "bullet", "blitz", "rapid", "classical", "correspondence")
RATINGS = (0, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500)
MAX_RESPONSE = 512 * 1024
CACHE_AGE = 86400


@dataclass(frozen=True)
class ExplorerQuery:
    fen: str
    source: str = "masters"
    speed: str = "all"
    rating: int = 0

    def __post_init__(self):
        if self.source not in ("masters", "lichess", "chessdb") or self.speed not in ("all", *SPEEDS):
            raise ValueError("Unsupported explorer source or speed")
        if type(self.rating) is not int or self.rating not in RATINGS:
            raise ValueError("Unsupported rating group")
        board = chess.Board(self.fen)
        if not board.is_valid() or any(c not in "KQkq-" for c in self.fen.split()[2]):
            raise ValueError("Opening explorer supports standard chess positions")
        # Opening counts ignore counters; cloud analysis retains the fifty-move clock.
        fields = board.fen(en_passant="legal").split()
        canonical = fields[:5] + ["1"] if self.source == "chessdb" else fields[:4] + ["0", "1"]
        object.__setattr__(self, "fen", " ".join(canonical))

    @property
    def label(self):
        return {"masters": "Lichess Masters", "lichess": "Lichess players", "chessdb": "ChessDB"}[self.source]

    def url(self, base=None):
        base = base or (CHESSDB_URL if self.source == "chessdb" else EXPLORER_URL)
        if self.source == "chessdb":
            return base.rstrip("/") + "/cdb.php?" + urlencode({
                "action": "queryall", "board": self.fen, "json": 1, "learn": 0, "showall": 0,
            })
        params = {"fen": self.fen, "moves": 12, "topGames": 0}
        if self.source == "lichess":
            params.update(variant="standard", recentGames=0,
                          speeds=",".join(SPEEDS if self.speed == "all" else (self.speed,)),
                          ratings=",".join(str(r) for r in RATINGS if r >= self.rating))
        return base.rstrip("/") + "/" + self.source + "?" + urlencode(params)

    @property
    def key(self):
        return hashlib.sha256(self.url().encode()).hexdigest()


def parse_statistics(payload, query):
    """Never trust a remote SAN string or allow a database move to bypass rules."""
    if query.source == "chessdb":
        return parse_chessdb(payload, query)
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
        moves.append(dict(counts(row), uci=move.uci(), san=board.san(move)))
    result["moves"] = sorted(moves, key=lambda row: -row["total"])[:12]
    opening = payload.get("opening")
    result["opening"] = (
        {"eco": str(opening.get("eco", ""))[:8], "name": str(opening.get("name", ""))[:200]}
        if isinstance(opening, dict) else None
    )
    return result


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
