#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROGRAMS = ("CALCFEE", "CHKAML", "RISKSCOR", "LOANEVAL", "RECOVRY", "RPTMONTH")


def _run_program(prog: str, timeout_s: int, merged_dir: Path, runlog) -> dict:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "verify_f41_e2e.py"),
        "--live-llm",
        "--verbose",
        "--with-behavioral-diff",
        "--program",
        prog,
    ]
    started = time.time()
    runlog.write(f"\n=== START {prog} timeout={timeout_s}s ===\n")
    runlog.flush()
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = ""
    timed_out = False
    try:
        output, _ = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, text=True)
        output += f"\n[phase-c] forced timeout for {prog} after {timeout_s}s\n"
    elapsed = round(time.time() - started, 2)
    runlog.write(output)
    runlog.flush()

    latest = None
    for p in sorted((ROOT / "out" / "f41_runs").iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if (p / "summary.json").is_file():
            try:
                data = json.loads((p / "summary.json").read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("programs") and data["programs"][0].get("program") == prog:
                latest = p
                break
    if latest:
        for f in latest.iterdir():
            if f.is_file():
                (merged_dir / f.name).write_bytes(f.read_bytes())
        data = json.loads((latest / "summary.json").read_text(encoding="utf-8"))
        entry = data.get("programs", [{}])[0]
        entry["runner_elapsed_s"] = elapsed
        entry["runner_timed_out"] = timed_out
        return entry
    return {
        "program": prog,
        "passed": False,
        "runner_elapsed_s": elapsed,
        "runner_timed_out": timed_out,
        "convert": {"ok": False, "detail": f"forced timeout after {timeout_s}s"},
        "compile": None,
        "execute": None,
        "baseline": None,
        "behavioral": None,
        "repair_count": 0,
        "compliance_pct": 0.0,
        "todo_count": 0,
    }


def main() -> int:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    merged_dir = ROOT / "out" / "f41_runs" / f"phase_c_merged_{ts}"
    merged_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    with (merged_dir / "run.log").open("w", encoding="utf-8") as runlog:
        for prog in PROGRAMS:
            timeout_s = 900 if prog in ("LOANEVAL", "RECOVRY", "RPTMONTH") else 600
            entries.append(_run_program(prog, timeout_s, merged_dir, runlog))

    combined = {
        "mode": "live-llm",
        "started": datetime.now().isoformat(),
        "total": 6,
        "programs": entries,
        "passed": sum(1 for e in entries if e.get("passed")),
        "failed": sum(1 for e in entries if not e.get("passed")),
        "total_repairs": sum(int(e.get("repair_count") or 0) for e in entries),
        "with_behavioral_diff": True,
    }
    (merged_dir / "summary.json").write_text(json.dumps(combined, indent=2), encoding="utf-8")

    sys.path.insert(0, str(ROOT / "scripts"))
    from phase_c_consolidated_report import build_report

    report = build_report(merged_dir)
    report_path = merged_dir / "PHASE_C_CONSOLIDATED_REPORT.txt"
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nMerged run: {merged_dir}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
