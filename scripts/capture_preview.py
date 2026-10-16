"""Capture a real rendered Qt window with actual Nocturne search samples."""

import argparse
import os
from pathlib import Path
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from nocturne.core.game import Game
from nocturne.engine.search import SearchLimits, Searcher
from nocturne.gui.window import MainWindow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/preview.png"))
    parser.add_argument("--light", action="store_true")
    parser.add_argument("--pgn", action="store_true")
    parser.add_argument("--width", type=int, default=1340)
    parser.add_argument("--height", type=int, default=920)
    args = parser.parse_args()
    app = QApplication([])
    app.setStyle("Fusion")
    with tempfile.TemporaryDirectory() as tmp:
        window = MainWindow(Path(tmp))
        window.config.update({"mode": "analysis", "light": args.light, "analysis_seconds": 1.0,
                              "analysis_depth": 4})
        game = Game.from_pgn("1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Re1 b5 7.Bb3 d6 8.c3 O-O 9.h3 *")
        game.headers.update({"White": "You", "Black": "Nocturne"})
        cursor = game.cursor
        for ply in range(0, cursor + 1, 2):
            game.navigate(ply)
            result = Searcher(SearchLimits(depth=2, seconds=.08)).search(game.board)
            game.evaluations[ply] = result.info.score * game.board.turn
        game.navigate(cursor)
        window.game = game
        window._apply_settings()
        window._workspace(True)
        window.tabs.setCurrentIndex(2 if args.pgn else 1)
        window.resize(args.width, args.height)
        window.show()

        def capture():
            if window.engine.busy:
                QTimer.singleShot(100, capture)
                return
            args.output.parent.mkdir(parents=True, exist_ok=True)
            if not window.grab().save(str(args.output)):
                raise RuntimeError("Could not save Qt capture")
            print(f"Captured actual Qt window: {args.output}", flush=True)
            window.close()
            app.quit()

        QTimer.singleShot(1500, capture)
        QTimer.singleShot(10000, app.quit)
        app.exec()


if __name__ == "__main__":
    main()
