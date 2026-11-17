"""Compatibility entry point. Full verification: python3 tests/check.py."""

from pathlib import Path
import runpy
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent / "tests"))
    runpy.run_path(
        str(Path(__file__).resolve().parent / "tests/verify_examples.py"),
        run_name="__main__",
    )
