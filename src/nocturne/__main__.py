"""Windowed entry point; CLI subcommands do not require Qt."""

import multiprocessing
from pathlib import Path
import sys
import tempfile


def main():
    multiprocessing.freeze_support()
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        raise SystemExit("PySide6 is required for the desktop app. Install with: python -m pip install -e .")
    from .gui.window import MainWindow
    from .gui.theme import install_menu_stripes

    app = QApplication(sys.argv)
    app.setApplicationName("Nocturne Chess")
    app.setOrganizationName("Nocturne")
    app.setStyle("Fusion")
    install_menu_stripes(app)
    smoke = "--smoke-test" in sys.argv
    temporary = tempfile.TemporaryDirectory() if smoke else None
    window = MainWindow(Path(temporary.name) if temporary else None)
    window.show()
    if smoke:
        from PySide6.QtCore import QTimer
        from .core.game import Game

        window.config.update({"mode": "analysis", "analysis_kind": "bounded", "engine_id": "smoke"})
        window.analysis_mode = True
        window._analysis_enabled = True
        window.game = Game.from_pgn("1.e4 {Smoke annotation} (1.d4 d5) e5 *")
        from .explorer import ExplorerQuery
        move = next(window.game.board.legal_moves())
        # Exercise the public ChessDB default, with deterministic local data
        # for every fixture position so coverage never depends on the network.
        for node in range(len(window.game.nodes)):
            position = window.game.position_at_node(node)
            query = ExplorerQuery(position.fen(), "chessdb")
            fixture_move = next(position.legal_moves())
            window.explorer.client.cache.put(query.key, {
                "status": "ok", "moves": [{"uci": fixture_move.uci(), "score": 25, "note": "Smoke fixture"}],
            })
        window.config["explorer_enabled"] = True
        window.config["explorer_statistics"] = True
        if "--smoke-engine" in sys.argv:
            index = sys.argv.index("--smoke-engine")
            executable = sys.argv[index + 1]
            script = sys.argv[index + 2]
            window.profiles = [
                {
                    "id": "smoke",
                    "path": executable,
                    "arguments": [script],
                    "name": "Protocol fixture",
                    "values": {},
                    "options": {},
                }
            ]
        window._apply_settings()
        window._refresh()
        window._set_explorer_option("explorer_enabled", False)
        pulse = QTimer()
        pulse.setInterval(25)
        review_started = False
        explorer_valid = False

        def verify():
            nonlocal review_started, explorer_valid
            if not window.profiles or window._last_info:
                if window.profiles and not review_started:
                    explorer_valid = len(window.explorer.rows) == 1 and window.explorer.rows[0]["uci"] == move.uci()
                    review_started = True
                    window._show_review()
                    window._begin_review(0.05)
                    return
                if review_started and window._review is not None:
                    return
                from .review import rows, summarize

                reviewed = summarize(rows(window.game))
                restored = Game.from_dict(window.game.to_dict())
                valid = (
                    restored.board.fen() == window.game.board.fen()
                    and "Smoke annotation" in restored.pgn()
                    and "(" in restored.pgn()
                    and (explorer_valid if review_started else
                         len(window.explorer.rows) == 1 and window.explorer.rows[0]["uci"] == move.uci())
                    and (not review_started or reviewed["reviewed"] == reviewed["total"] == 2
                         and reviewed["accuracy"] is not None)
                )
                # Exercise collected vector assets and the cursor-board path
                # in the frozen executable, not just from the source checkout.
                valid = valid and len(window.board_view._renderers) == 12 and all(
                    renderer.isValid() for renderer in window.board_view._renderers.values())
                actual_fen = window.game.board.fen()
                window._set_cursor_preview(True)
                window._preview_history(1)
                valid = (valid and window.hover_preview.isVisible()
                         and window.board_view.display_board.fen() == actual_fen
                         and window.hover_preview.board.display_board.fen() == window.game.position_at_node(1).fen())
                window._end_preview("history")
                valid = valid and not window.hover_preview.isVisible()
                pulse.stop()
                window.close()
                app.exit(0 if valid else 2)

        def timeout():
            window.close()
            app.exit(3)

        pulse.timeout.connect(verify)
        pulse.start()
        QTimer.singleShot(50, window._schedule_engine)
        QTimer.singleShot(12000, timeout)
    result = app.exec()
    if temporary:
        temporary.cleanup()
    return result


if __name__ == "__main__":
    sys.exit(main())
