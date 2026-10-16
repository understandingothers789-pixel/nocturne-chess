"""PyInstaller's windowed entry point, including Windows spawn support."""

from nocturne.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
