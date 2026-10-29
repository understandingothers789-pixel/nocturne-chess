"""Measure local GUI paths with synthetic Stockfish data; no engine or model required."""

import json
import os
from pathlib import Path
import statistics
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from nocturne.core.rules import Board
from nocturne.core.notation import san
from nocturne.gui.window import MainWindow


def measure(operation, count):
    """Median milliseconds per operation across five batches."""
    samples = []
    for _ in range(5):
        start = time.perf_counter()
        for _ in range(count):
            operation()
        samples.append((time.perf_counter() - start) * 1000 / count)
    return round(statistics.median(samples), 5)


def main():
    app = QApplication.instance() or QApplication([])
    board = Board()
    for text in ("e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6"):
        board.play_uci(text)
    results = {"board_copy_ms": measure(board.copy, 2000)}
    with tempfile.TemporaryDirectory() as directory:
        window = MainWindow(Path(directory))
        try:
            window.timer.stop()
            window.autosave_timer.stop()
            window._analysis_enabled = False
            window.config.update(maia_enabled=False, explorer_statistics=False, multipv=3)
            window.maia.stop()
            window.resize(1500, 900)
            window.show()
            app.processEvents()
            variations = [
                "e2e4 e7e5 g1f3 b8c6 f1b5 a7a6 b5a4 g8f6 e1g1 f8e7 f1e1 b7b5",
                "d2d4 d7d5 c2c4 e7e6 b1c3 g8f6 c1g5 f8e7 e2e3 e8g8 g1f3 h7h6",
                "c2c4 e7e5 b1c3 g8f6 g2g3 d7d5 c4d5 f6d5 f1g2 d5b6 g1f3 b8c6",
            ]
            infos = []
            for rank, variation in enumerate(variations, 1):
                pv = variation.split()
                position, names = Board(), []
                for text in pv:
                    move = position.parse_uci(text)
                    names.append(san(position, move))
                    position.push(move)
                infos.append(dict(depth=25, seldepth=30, nodes=100000, score=30, score_type="cp",
                                  score_value=30, multipv=rank, pv=pv, san=names))
            job = {"turn": 1, "multipv": 3}
            sequence = 0

            def update():
                nonlocal sequence
                sequence += 1
                info = infos[sequence % 3].copy()
                info["nodes"] += sequence
                info["score"] = info["score_value"] = sequence % 50
                window._show_info(info, job)

            for _ in range(10):
                update()
            app.processEvents()
            results["stockfish_update_ms"] = measure(update, 100)
            view = window.candidates.rows[1][2]
            cursor = view.document().find("Nf3")
            cursor.setPosition(cursor.selectionStart() + 1)
            point = view.cursorRect(cursor).center()
            results["pv_hit_test_ms"] = measure(lambda: view._move_at(point), 1000)
            results["paused_tick_ms"] = measure(window._tick, 1000)
        finally:
            window.close()
            window.deleteLater()
            app.processEvents()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
