"""Transactional local SQLite persistence, with validated, versioned payloads."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
from uuid import UUID

from .core.game import Game


class StorageError(RuntimeError):
    pass


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.db = sqlite3.connect(self.path, timeout=5)
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                self.db.close()
                raise StorageError(f"Library schema {version} requires a newer Nocturne version")
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS games (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, updated TEXT NOT NULL,
                    result TEXT NOT NULL, plies INTEGER NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                PRAGMA user_version=1;
            """)
        except sqlite3.Error as exc:
            raise StorageError(f"Cannot open game library: {exc}") from exc

    def save(self, game: Game, autosave: bool = True) -> None:
        try:
            payload = json.dumps(game.to_dict(), ensure_ascii=False, allow_nan=False)
            title = f"{game.headers.get('White', 'White')} · {game.headers.get('Black', 'Black')}"
            event = game.headers.get("Event", "").strip()
            if event and event != "?":
                title = event + " · " + title
            result = game.outcome.result if game.outcome else "*"
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with self.db:
                self.db.execute("INSERT INTO games VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                                "title=excluded.title, updated=excluded.updated, result=excluded.result, "
                                "plies=excluded.plies, payload=excluded.payload",
                                (game.id, title, now, result, game.cursor, payload))
                if autosave:
                    self.db.execute("INSERT OR REPLACE INTO preferences VALUES ('resume_id', ?)",
                                    (json.dumps(game.id),))
        except (sqlite3.Error, ValueError, TypeError) as exc:
            raise StorageError(f"Cannot save game: {exc}") from exc
        self.archive_pgn(game)

    @property
    def pgn_directory(self) -> Path:
        return self.path.parent / "PGNs"

    def pgn_path(self, game_id: str) -> Path:
        # Imported save IDs are untrusted; never use them directly as file paths.
        try:
            name = str(UUID(game_id))
        except (ValueError, AttributeError):
            name = hashlib.sha256(str(game_id).encode("utf-8", errors="surrogatepass")).hexdigest()
        return self.pgn_directory / f"game-{name}.pgn"

    def archive_pgn(self, game: Game) -> Path:
        """One atomic, readable PGN per study; the SQLite copy remains authoritative."""
        temporary = None
        try:
            destination = self.pgn_path(game.id)
            text = game.pgn()
            self.pgn_directory.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                try:
                    if destination.read_text(encoding="utf-8") == text:
                        return destination
                except UnicodeError:
                    pass  # Repair an incomplete/non-UTF-8 copy from the validated library.
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n", dir=self.pgn_directory,
                prefix=".nocturne-", suffix=".tmp", delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            return destination
        except (OSError, ValueError, TypeError) as exc:
            raise StorageError(f"Game retained in the library; cannot write its PGN backup: {exc}") from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def game_ids(self) -> list[str]:
        try:
            return [row[0] for row in self.db.execute("SELECT id FROM games ORDER BY updated DESC")]
        except sqlite3.Error as exc:
            raise StorageError(f"Cannot read saved games: {exc}") from exc

    def load(self, game_id: str) -> Game:
        try:
            row = self.db.execute("SELECT payload FROM games WHERE id=?", (game_id,)).fetchone()
            if row is None:
                raise StorageError("That saved game no longer exists")
            if len(row[0]) > 8_000_000:
                raise StorageError("Saved game is too large")
            return Game.from_dict(json.loads(row[0]))
        except (sqlite3.Error, ValueError, TypeError) as exc:
            raise StorageError(f"Cannot restore game: {exc}") from exc

    def resume(self) -> Game | None:
        game_id = self.get("resume_id")
        return self.load(game_id) if game_id else None

    def list_games(self) -> list[dict]:
        try:
            return [dict(zip(("id", "title", "updated", "result", "plies"), row)) for row in
                    self.db.execute("SELECT id,title,updated,result,plies FROM games ORDER BY updated DESC LIMIT 1000")]
        except sqlite3.Error as exc:
            raise StorageError(f"Cannot list saved games: {exc}") from exc

    def delete(self, game_id: str) -> None:
        try:
            with self.db:
                self.db.execute("DELETE FROM games WHERE id=?", (game_id,))
                if self.get("resume_id") == game_id:
                    self.db.execute("DELETE FROM preferences WHERE key='resume_id'")
        except sqlite3.Error as exc:
            raise StorageError(f"Cannot delete saved game: {exc}") from exc

    def match_stats(self) -> dict[str, int]:
        stats = {"white_wins": 0, "black_wins": 0, "draws": 0, "unfinished": 0}
        try:
            for result, payload in self.db.execute("SELECT result,payload FROM games"):
                try:
                    data = json.loads(payload)
                    if data.get("metadata", {}).get("mode") != "ai_ai":
                        continue
                except (ValueError, TypeError, AttributeError):
                    continue
                key = {"1-0": "white_wins", "0-1": "black_wins", "1/2-1/2": "draws"}.get(result, "unfinished")
                stats[key] += 1
            return stats
        except sqlite3.Error as exc:
            raise StorageError(f"Cannot read match statistics: {exc}") from exc

    def get(self, key: str, default=None):
        try:
            row = self.db.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default
        except (sqlite3.Error, ValueError, TypeError):
            return default

    def set(self, key: str, value) -> None:
        try:
            encoded = json.dumps(value, allow_nan=False)
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO preferences VALUES (?, ?)", (key, encoded))
        except (sqlite3.Error, ValueError, TypeError) as exc:
            raise StorageError(f"Cannot save preference: {exc}") from exc

    def close(self) -> None:
        self.db.close()
