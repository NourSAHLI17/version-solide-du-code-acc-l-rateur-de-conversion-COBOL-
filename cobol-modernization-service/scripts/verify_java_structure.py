#!/usr/bin/env python3
"""Verify generated Java: balanced braces, no methods outside class body."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.converters.java_class_builder import GenerationError, validate_class_structure

DEFAULT_DIR = Path("/tmp/generated")


def verify_file(path: Path) -> None:
    source = path.read_text(encoding="utf-8", errors="replace")
    validate_class_structure(source)
    print(f"OK {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        default=DEFAULT_DIR,
        help=f"Directory of generated .java files (default: {DEFAULT_DIR})",
    )
    args = parser.parse_args()
    directory = args.directory.resolve()

    if not directory.is_dir():
        print(f"ERROR: directory not found: {directory}", file=sys.stderr)
        return 1

    java_files = sorted(directory.glob("*.java"))
    if not java_files:
        print(f"ERROR: no .java files in {directory}", file=sys.stderr)
        return 1

    for path in java_files:
        try:
            verify_file(path)
        except GenerationError as exc:
            print(f"FAIL {path}: {exc}", file=sys.stderr)
            return 1

    print(f"All {len(java_files)} file(s) passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
