#!/usr/bin/env python3
"""Run live-LLM F41 verify per program (avoids one hung run blocking all) and merge report."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROGRAMS = ("CALCFEE", "CHKAML", "RISKSCOR", "LOANEVAL", "RECOVRY", "RPTMONTH")


def main() -> int:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    merged_dir = ROOT / "out" / "f41_runs" / f"phase_c_merged_{ts}"
    merged_dir.mkdir(parents=True, exist_ok=True)
    log_path = merged_dir / "run.log"
    combined: dict = {
        "mode": "live-llm",
        "started": datetime.now().isoformat(),
        "programs": [],
        "total": 6,
        "passed": 0,
        "failed": 0,
        "duration_s": 0.0,
        "total_repairs": 0,
        "with_behavioral_diff": True,
    }
    exit_codes: list[int] = []

    with log_path.open("w", encoding="utf-8") as logf:
        for prog in PROGRAMS:
            logf.write(f"\n{'='*60}\n=== LIVE VERIFY {prog} ===\n")
            logf.flush()
            print(f"[phase-c] Running {prog}...")
            timeout_s = 900 if prog in ("LOANEVAL", "RECOVRY", "RPTMONTH") else 600
            try:
                proc = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "verify_f41_e2e.py"),
                        "--live-llm",
                        "--verbose",
                        "--with-behavioral-diff",
                        "--program",
                        prog,
                    ],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_s,
                )
            except subprocess.TimeoutExpired:
                logf.write(f"\n[phase-c] TIMEOUT after {timeout_s}s for {prog}\n")
                logf.flush()
                exit_codes.append(124)
                combined["programs"].append(
                    {
                        "program": prog,
                        "passed": False,
                        "convert_ok": False,
                        "error": f"subprocess timeout after {timeout_s}s",
                    }
                )
                continue
            logf.write(proc.stdout or "")
            logf.write(proc.stderr or "")
            logf.flush()
            exit_codes.append(proc.returncode)

            runs = sorted((ROOT / "out" / "f41_runs").iterdir(), key=lambda p: p.stat().st_mtime)
            src_run = None
            for p in reversed(runs):
                if (p / "summary.json").is_file():
                    data = json.loads((p / "summary.json").read_text(encoding="utf-8"))
                    if data.get("programs") and data["programs"][0].get("program") == prog:
                        src_run = p
                        break
            if not src_run:
                print(f"[phase-c] WARN: no run dir for {prog}")
                continue

            for artifact in src_run.iterdir():
                if artifact.is_file():
                    dest = merged_dir / artifact.name
                    if dest.exists() and prog not in artifact.name:
                        continue
                    dest.write_bytes(artifact.read_bytes())
                elif artifact.name == "work":
                    dest_work = merged_dir / "work"
                    dest_work.mkdir(exist_ok=True)
                    for f in artifact.rglob("*"):
                        if f.is_file():
                            rel = f.relative_to(artifact)
                            out = dest_work / rel
                            out.parent.mkdir(parents=True, exist_ok=True)
                            out.write_bytes(f.read_bytes())

            for entry in json.loads((src_run / "summary.json").read_text(encoding="utf-8")).get(
                "programs", []
            ):
                combined["programs"].append(entry)

    combined["passed"] = sum(1 for e in combined["programs"] if e.get("passed"))
    combined["failed"] = combined["total"] - combined["passed"]
    combined["total_repairs"] = sum(int(e.get("repair_count") or 0) for e in combined["programs"])
    (merged_dir / "summary.json").write_text(json.dumps(combined, indent=2), encoding="utf-8")

    sys.path.insert(0, str(ROOT / "scripts"))
    from phase_c_consolidated_report import build_report

    report = build_report(merged_dir)
    (merged_dir / "PHASE_C_CONSOLIDATED_REPORT.txt").write_text(report, encoding="utf-8")
    print(report)
    print(f"\nMerged run: {merged_dir}")
    print(f"Report: {merged_dir / 'PHASE_C_CONSOLIDATED_REPORT.txt'}")
    return 0 if all(c == 0 for c in exit_codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
