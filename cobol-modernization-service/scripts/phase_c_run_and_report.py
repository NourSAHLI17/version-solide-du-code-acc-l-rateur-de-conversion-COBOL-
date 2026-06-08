#!/usr/bin/env python3
"""Run Phase C live-LLM F41 verification (all 6 programs) and emit consolidated report."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_parent = ROOT / "out" / "f41_runs"
    run_parent.mkdir(parents=True, exist_ok=True)
    log_path = run_parent / f"phase_c_{ts}.log"

    print(f"[phase-c] Starting verify_f41_e2e --live-llm --verbose --with-behavioral-diff")
    print(f"[phase-c] Log: {log_path}")

    with log_path.open("w", encoding="utf-8") as logf:
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "verify_f41_e2e.py"),
                "--live-llm",
                "--verbose",
                "--with-behavioral-diff",
            ],
            cwd=str(ROOT),
            stdout=logf,
            stderr=subprocess.STDOUT,
            text=True,
        )

    print(f"[phase-c] verify exit code: {proc.returncode}")

    # Copy log into run dir if summary exists
    from scripts.phase_c_consolidated_report import build_report, _latest_run_dir

    try:
        run_dir = _latest_run_dir()
        (run_dir / "run.log").write_text(log_path.read_text(encoding="utf-8"), encoding="utf-8")
    except FileNotFoundError:
        print("[phase-c] No summary.json yet — report may be incomplete")
        return proc.returncode

    report = build_report(run_dir)
    out = run_dir / "PHASE_C_CONSOLIDATED_REPORT.txt"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n[phase-c] Report saved: {out}")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
