"""Opt-in live database check of the Qt HTTPS client used by the application.

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
        sources = iter(("masters", "lichess", "chessdb"))
        current = [None]
        failures, protected = [], []

        def next_source():
            source = next(sources, None)
            if source is None:
                if protected:
                    print("Authenticated data not checked without a user token: " + ", ".join(protected), flush=True)
                app.exit(1 if failures else 0)
            else:
                current[0] = ExplorerQuery(board.fen(), source)
                client.load(current[0], force=True)

        def result(key, data, origin):
            detail = f"{data['total']:,} games" if "total" in data else "cloud analysis"
            print(f"{current[0].source}: {origin}; {detail}; {len(data['moves'])} legal moves", flush=True)
            if not data["moves"]:
                failures.append(current[0].source)
                QTimer.singleShot(1100, next_source)
            else:
                QTimer.singleShot(1100, next_source)

        def status(key, message):
            print(f"{current[0].source}: {message}", flush=True)
            if "access token required" in message:
                protected.append(current[0].source)
                QTimer.singleShot(1100, next_source)
            elif not (message.startswith("Loading") or message.startswith("Live")):
                failures.append(current[0].source)
                QTimer.singleShot(1100, next_source)

        client.result.connect(result)
        client.status.connect(status)
        guard = QTimer()
        guard.setSingleShot(True)
        guard.timeout.connect(lambda: app.exit(3))
        guard.start(50000)
        QTimer.singleShot(0, next_source)
        code = app.exec()
        client.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
