"""GnuCOBOL GMP runtime detection for COMP-3 / PACKED-DECIMAL behavioral compiles."""

from __future__ import annotations

import os
from pathlib import Path


def gnucobol_root() -> Path | None:
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if not local:
        return None
    root = Path(local) / "GnuCOBOL"
    return root if root.is_dir() else None


def gmp_runtime_ready(root: Path | None = None) -> tuple[bool, str]:
    """
    Return whether gmp.h and libgmp link artifacts are present for cobc -x.

    GnuCOBOL maps mathematical library to GMP; COMP-3 in copybooks needs it at compile time.
    """
    base = root or gnucobol_root()
    if base is None:
        return False, "GnuCOBOL not found under %LOCALAPPDATA%\\GnuCOBOL"
    gmp_h = base / "include" / "gmp.h"
    if not gmp_h.is_file():
        return (
            False,
            "gmp.h missing (COMP-3 requires GMP dev headers; run scripts/ensure-gnucobol-gmp.ps1)",
        )
    if gmp_h.stat().st_size < 50_000:
        return (
            False,
            "gmp.h incomplete (run scripts/ensure-gnucobol-gmp.ps1 to reinstall from MSYS2)",
        )
    if not (base / "lib" / "libgmp.dll.a").is_file():
        return (
            False,
            "libgmp.dll.a missing under GnuCOBOL\\lib (run scripts/ensure-gnucobol-gmp.ps1)",
        )
    return True, ""
