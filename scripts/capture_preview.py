"""Render the real Qt app. --simulate uses explicitly labelled UCI test data."""

import argparse
import os
from pathlib import Path
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from nocturne.core.game import Game
from nocturne.gui.window import MainWindow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/preview.png"))
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--engine", type=Path)
    parser.add_argument("--light", action="store_true")
    parser.add_argument("--lines", action="store_true")
    parser.add_argument("--explorer-fixture", action="store_true", help="Clearly labelled cached test statistics; no network")
    parser.add_argument("--chessdb-fixture", action="store_true", help="Clearly labelled cached ChessDB test scores; no network")
    parser.add_argument("--pgn", action="store_true")
    parser.add_argument("--preview-ply", type=int)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=1040)
    parser.add_argument("--layout", choices=["classic", "analysis-left"], default="classic")
    args = parser.parse_args()
    app = QApplication([])
    app.setStyle("Fusion")
    with tempfile.TemporaryDirectory() as directory:
        window = MainWindow(Path(directory))
        window.timer.stop()
        window.autosave_timer.stop()
        window.config.update(
            mode="analysis",
            light=args.light,
            layout=args.layout,
            engine_id="capture",
            analysis_kind="explore",
            multipv=6,
            candidate_style="lines" if args.lines else "arrows",
        )
        window.game = Game.from_pgn(
            '[Event "Italian Game study"]\n\n1.e4 e5 2.Nf3 Nc6 3.Bc4 {Develop toward the center.} (3.Nc3 Nf6) Bc5 4.c3 *'
        )
        if args.explorer_fixture or args.chessdb_fixture:
            from nocturne.explorer import ExplorerQuery
            source = "chessdb" if args.chessdb_fixture else "lichess"
            window.config.update(explorer_enabled=True, explorer_source=source, explorer_speed="rapid", explorer_rating=1800)
            query = ExplorerQuery(window.game.board.fen(), source, "rapid", 1800)
            payload = {
                "white": 250, "draws": 150, "black": 100,
                "opening": {"eco": "TEST", "name": "Explorer fixture · not live statistics"},
                "moves": [{"uci": move.uci(), "white": 10 + i, "draws": 5, "black": 5}
                          for i, move in enumerate(list(window.game.board.legal_moves())[:8])],
            }
            if args.chessdb_fixture:
                payload = {"status": "ok", "moves": [
                    {"uci": move.uci(), "score": 20 - i * 10, "note": "Fixture · not live ChessDB data"}
                    for i, move in enumerate(list(window.game.board.legal_moves())[:8])]}
            window.explorer.client.cache.put(query.key, payload)
        if args.engine:
            window.profiles = [
                {
                    "id": "capture",
                    "path": str(args.engine.absolute()),
                    "name": "UCI engine",
                    "values": {},
                    "options": {},
                }
            ]
        elif args.simulate:
            fixture = Path(__file__).resolve().parents[1] / "tests/fixtures/uci_simulator.py"
            window.profiles = [
                {
                    "id": "capture",
                    "path": sys.executable,
                    "arguments": [str(fixture)],
                    "name": "UCI transport simulator · test data",
                    "label": "UCI simulator · test data",
                    "values": {},
                    "options": {},
                }
            ]
        window._apply_settings()
        window._workspace(True)
        window.tabs.setCurrentIndex(2 if args.pgn else 1)
        window.resize(args.width, args.height)
        window.show()
        deadline = time.monotonic() + 12

        def capture():
            if window.profiles and not window.candidates.lines and time.monotonic() < deadline:
                QTimer.singleShot(100, capture)
                return
            actual_fen = window.game.board.fen()
            if args.preview_ply is not None:
                window._preview_history(args.preview_ply)
            if args.explorer_fixture or args.chessdb_fixture:
                window.explorer.status_label.setText("Cached · test data (not live database results)")
            assert window.game.board.fen() == actual_fen
            args.output.parent.mkdir(parents=True, exist_ok=True)
            if not window.grab().save(str(args.output)):
                raise RuntimeError("Could not save Qt capture")
            window.board_view.clear_preview()
            assert window.board_view.display_board.fen() == actual_fen
            print("Captured real Qt window: " + str(args.output), flush=True)
            window.close()
            app.quit()

        QTimer.singleShot(500, capture)
        app.exec()


if __name__ == "__main__":
    main()
