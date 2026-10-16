"""Separate console executable for UCI managers."""

import multiprocessing

from nocturne.engine.uci import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
