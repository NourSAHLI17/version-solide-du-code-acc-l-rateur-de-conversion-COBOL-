"""Build committed TXNPOST behavioral data fixtures (indexed + sequential)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
SEED_COB = SERVICE_ROOT / "tests" / "fixtures" / "usecase3" / "behavioral_data" / "SEEDTXNPOST.cbl"
OUT_DIR = SERVICE_ROOT / "tests" / "fixtures" / "usecase3" / "behavioral_data"
ASSIGN_FILES = ("ACME.CUSTOMER.MASTER", "ACME.TRANSACTIONS")


def main() -> int:
    if not SEED_COB.is_file():
        print(f"Missing seed program: {SEED_COB}", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in ASSIGN_FILES:
        path = OUT_DIR / name
        if path.exists():
            path.unlink()
    work = OUT_DIR / "_build"
    work.mkdir(parents=True, exist_ok=True)
    seed_copy = work / "SEEDTXNPOST.cbl"
    seed_copy.write_text(SEED_COB.read_text(encoding="utf-8"), encoding="utf-8")
    out_bin = work / "seed"
    proc = subprocess.run(
        ["cobc", "-x", "-o", str(out_bin), str(seed_copy)],
        capture_output=True,
        text=True,
        cwd=str(work),
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return proc.returncode
    exe = out_bin.with_suffix(".exe") if sys.platform == "win32" else out_bin
    run = subprocess.run([str(exe)], capture_output=True, text=True, cwd=str(work), timeout=30)
    if run.returncode != 0:
        print(run.stderr or run.stdout, file=sys.stderr)
        return run.returncode
    for name in ASSIGN_FILES:
        src = work / name
        dest = OUT_DIR / name
        if not src.is_file():
            print(f"Seed did not create {src}", file=sys.stderr)
            return 1
        dest.write_bytes(src.read_bytes())
        print(f"Wrote {dest} ({dest.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
