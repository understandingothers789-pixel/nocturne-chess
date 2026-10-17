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

    app = QApplication(sys.argv)
    app.setApplicationName("Nocturne Chess")
    app.setOrganizationName("Nocturne")
    app.setStyle("Fusion")
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
        pulse = QTimer()
        pulse.setInterval(25)

        def verify():
            if not window.profiles or window._last_info:
                restored = Game.from_dict(window.game.to_dict())
                valid = (
                    restored.board.fen() == window.game.board.fen()
                    and "Smoke annotation" in restored.pgn()
                    and "(" in restored.pgn()
                )
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
