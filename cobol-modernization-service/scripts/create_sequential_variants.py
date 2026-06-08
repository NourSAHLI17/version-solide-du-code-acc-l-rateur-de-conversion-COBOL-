#!/usr/bin/env python3
"""
Generate SEQUENTIAL baseline variants for acme-bank-v3 COBOL programs.

Writes ``acme-bank-v3/src/sequential/<PROGRAM>.cbl`` from indexed sources in
``acme-bank-v3/src/*.cbl`` for GnuCOBOL behavioral baseline testing.

Usage (from cobol-modernization-service):
  python scripts/create_sequential_variants.py
  python scripts/create_sequential_variants.py --acme-root ../acme-bank-v3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ACME = ROOT.parent / "acme-bank-v3"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create SEQUENTIAL COBOL variants for ACME baseline.")
    parser.add_argument(
        "--acme-root",
        type=Path,
        default=DEFAULT_ACME,
        help="Path to acme-bank-v3 (default: sibling of cobol-modernization-service)",
    )
    parser.add_argument(
        "--src",
        type=Path,
        default=None,
        help="Indexed COBOL source dir (default: <acme-root>/src)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output dir (default: <acme-root>/src/sequential)",
    )
    args = parser.parse_args()

    acme = args.acme_root.resolve()
    src_dir = (args.src or acme / "src").resolve()
    out_dir = (args.out or acme / "src" / "sequential").resolve()

    if not src_dir.is_dir():
        print(f"FAIL: source directory not found: {src_dir}", file=sys.stderr)
        return 1

    sys.path.insert(0, str(ROOT))
    from app.services.cobol_sequential_variant import generate_sequential_tree

    written = generate_sequential_tree(src_dir, out_dir, pattern="*.cbl")
    if not written:
        print(f"No .cbl files under {src_dir}", file=sys.stderr)
        return 1

    print(f"Wrote {len(written)} SEQUENTIAL variant(s) to {out_dir}")
    for src, dest in written:
        print(f"  {src.name} -> {dest.relative_to(acme)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
