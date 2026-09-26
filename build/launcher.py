"""Entry point for the frozen Sibit.exe (PyInstaller)."""
import multiprocessing
import sys

from sibit.__main__ import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
