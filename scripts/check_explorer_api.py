"""Opt-in live smoke check of the same Qt HTTPS client used by the application.

This is separate from deterministic tests; public service availability is not a
build prerequisite. It sends only a standard opening position, with no user data.
"""

from pathlib import Path
import tempfile

from PySide6.QtCore import QCoreApplication, QTimer
import chess

from nocturne.explorer import ExplorerCache, ExplorerQuery
from nocturne.gui.explorer_client import ExplorerClient


def main():
    app = QCoreApplication([])
    with tempfile.TemporaryDirectory() as directory:
        client = ExplorerClient(ExplorerCache(Path(directory) / "cache.db"))
        board = chess.Board()
        board.push_uci("e2e4")
        board.push_uci("e7e5")
        sources = iter(("masters", "lichess"))
        current = [None]

        def next_source():
            source = next(sources, None)
            if source is None:
                app.exit(0)
            else:
                current[0] = ExplorerQuery(board.fen(), source)
                client.load(current[0], force=True)

        def result(key, data, origin):
            print(f"{current[0].source}: {origin}; {data['total']:,} games; {len(data['moves'])} legal moves", flush=True)
            if not data["total"] or not data["moves"]:
                app.exit(2)
            else:
                QTimer.singleShot(1100, next_source)

        def status(key, message):
            print(f"{current[0].source}: {message}", flush=True)
            if not (message.startswith("Loading") or message.startswith("Live")):
                app.exit(1)

        client.result.connect(result)
        client.status.connect(status)
        guard = QTimer()
        guard.setSingleShot(True)
        guard.timeout.connect(lambda: app.exit(3))
        guard.start(30000)
        QTimer.singleShot(0, next_source)
        code = app.exec()
        client.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
