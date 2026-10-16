"""Windowed entry point; CLI subcommands do not require Qt."""

import multiprocessing
from pathlib import Path
import sys
import tempfile


def main():
    multiprocessing.freeze_support()
    if "--uci" in sys.argv:
        from .engine.uci import main as uci_main
        return uci_main()
    if "--bench" in sys.argv:
        from .engine.benchmark import main as bench_main
        return bench_main([a for a in sys.argv[1:] if a != "--bench"])
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
        window.config.update({"mode": "human_ai", "human_color": 1, "difficulty": "Casual"})
        window._refresh()
        pulse = QTimer()
        pulse.setInterval(25)

        def verify():
            if window.game.cursor >= 2:
                valid = window.game.board.key == window.game.board.compute_key()
                pulse.stop()
                window.close()
                app.exit(0 if valid else 2)

        def timeout():
            window.close()
            app.exit(3)

        pulse.timeout.connect(verify)
        pulse.start()
        QTimer.singleShot(0, lambda: window._human_move(window.game.board.parse_uci("e2e4")))
        QTimer.singleShot(8000, timeout)
    result = app.exec()
    if temporary:
        temporary.cleanup()
    return result


if __name__ == "__main__":
    sys.exit(main())
