"""Packaged Maia worker entry point; deliberately separate from the GUI."""
from nocturne.maia.worker import main

if __name__ == "__main__":
    raise SystemExit(main())
