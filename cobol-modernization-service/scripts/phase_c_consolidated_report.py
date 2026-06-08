#!/usr/bin/env python3
"""Build Phase C Rounds 1-5 consolidated report from an F41 live-LLM run directory."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
ACME = ROOT.parent / "acme-bank-v3"
PROGRAMS = ("CALCFEE", "CHKAML", "RISKSCOR", "LOANEVAL", "RECOVRY", "RPTMONTH")
SUB_PROGRAMS = {"CALCFEE", "CHKAML"}


@dataclass
class ProgMetrics:
    program: str
    convert_ok: bool = False
    compile_ok: bool = False
    execute_ok: bool = False
    baseline_ok: bool = False
    behavioral_ok: bool = False
    structural_ok: bool = False
    illegal_start: int = 0
    cannot_find_symbol: int = 0
    semicolon_expected: int = 0
    javac_error_lines: int = 0
    todo_count: int = 0
    compliance_pct: float = 0.0
    compliance_retries: int = 0
    repair_count: int = 0
    analysis_engine: str = "unknown"
    business_rules: int = 0
    fallback_reason: Optional[str] = None
    conversion_seconds: float = 0.0
    behavioral_detail: str = ""
    behavioral_cases: str = ""
    stream_seconds: float = 0.0


def _latest_run_dir() -> Path:
    base = ROOT / "out" / "f41_runs"
    if not base.is_dir():
        raise FileNotFoundError(f"No runs under {base}")
    runs = sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in runs:
        if (p / "summary.json").is_file():
            return p
    raise FileNotFoundError("No F41 run with summary.json found")


def _structural_check(java_path: Path) -> Tuple[bool, int, int, int]:
    """Return (ok, illegal_start, cannot_find_symbol, semicolon_expected) via javac + javalang."""
    illegal = cannot = semi = 0
    if not java_path.is_file():
        return False, 0, 0, 0
    text = java_path.read_text(encoding="utf-8", errors="replace")
    # javalang brace / class structure
    try:
        import javalang

        tree = javalang.parse.parse(text)
        if not tree.types:
            return False, 0, 0, 0
    except Exception:
        pass
    work = java_path.parent / "_struct_check"
    work.mkdir(exist_ok=True)
    tmp = work / java_path.name
    tmp.write_text(text, encoding="utf-8")
    proc = subprocess.run(
        ["javac", "-encoding", "UTF-8", str(tmp.name)],
        cwd=work,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    err = (proc.stderr or "") + (proc.stdout or "")
    illegal = len(re.findall(r"illegal start of expression", err, re.I))
    cannot = len(re.findall(r"cannot find symbol", err, re.I))
    semi = len(re.findall(r"';' expected", err, re.I))
    ok = proc.returncode == 0 and illegal == 0
    return ok, illegal, cannot, semi


def _load_analyzed(run_dir: Path, program: str) -> Optional[Dict[str, Any]]:
    p = run_dir / f"{program}.analyzed.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def _parse_run_log(run_dir: Path) -> Dict[str, float]:
    """Extract per-program stream conversion seconds from run.log."""
    log_path = run_dir / "run.log"
    if not log_path.is_file():
        alt = ROOT / "out" / "phase_c_live_run.log"
        log_path = alt if alt.is_file() else log_path
    if not log_path.is_file():
        return {}
    text = log_path.read_text(encoding="utf-8", errors="replace")
    out: Dict[str, float] = {}
    for m in re.finditer(
        r"\[STREAM\] (\w+): completed in ([\d.]+)s", text
    ):
        out[m.group(1)] = float(m.group(2))
    return out


def _analyze_program(program: str) -> Tuple[str, int, Optional[str]]:
    sys.path.insert(0, str(ROOT))
    from app.services.pipeline_service import PipelineService

    cbl = ACME / "src" / f"{program}.cbl"
    if not cbl.is_file():
        return "missing_source", 0, "source not found"
    src = cbl.read_text(encoding="utf-8")
    svc = PipelineService()
    opts = {"copylib_paths": [str(ACME / "copybooks")]}
    parsed = svc.run_pipeline(src, opts)
    try:
        analysis = svc.analyze_cobol(src, parsed)
    except Exception as exc:
        return "error", 0, str(exc)
    engine = str(analysis.get("analysis_engine") or analysis.get("engine") or "unknown")
    rules = analysis.get("business_rules") or []
    fb = analysis.get("fallback_reason")
    return engine, len(rules) if isinstance(rules, list) else 0, fb


def _load_behavioral(run_dir: Path, program: str) -> Dict[str, Any]:
    p = run_dir / f"{program}.behavioral.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def build_report(run_dir: Path) -> str:
    summary_path = run_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    started = summary.get("started", "")
    duration_s = float(summary.get("duration_s", 0))
    h, rem = divmod(int(duration_s), 3600)
    m, s = divmod(rem, 60)
    duration_str = f"{h:02d}:{m:02d}:{s:02d}"

    import os
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    model = os.getenv("OPENAI_MODEL", "unknown")

    metrics: Dict[str, ProgMetrics] = {}
    for prog in PROGRAMS:
        pm = ProgMetrics(program=prog)
        entry = next((p for p in summary.get("programs", []) if p.get("program") == prog), {})
        for phase in ("convert", "compile", "execute", "baseline", "behavioral"):
            ph = entry.get(phase)
            ok = bool(ph and ph.get("ok"))
            if phase == "convert":
                pm.convert_ok = ok
            elif phase == "compile":
                pm.compile_ok = ok
            elif phase == "execute":
                pm.execute_ok = ok or prog in SUB_PROGRAMS
            elif phase == "baseline":
                pm.baseline_ok = ok or prog in SUB_PROGRAMS
            elif phase == "behavioral":
                pm.behavioral_ok = ok
        pm.compliance_pct = float(entry.get("compliance_pct") or 0)
        pm.compliance_retries = int(entry.get("compliance_retries") or 0)
        pm.repair_count = int(entry.get("repair_count") or 0)
        final_java = run_dir / f"{prog}.final.java"
        if final_java.is_file():
            pm.todo_count = final_java.read_text(encoding="utf-8", errors="replace").count(
                "// TODO: invented references need manual review"
            )
        ok_struct, ill, cfs, semi = _structural_check(final_java)
        pm.structural_ok = ok_struct and pm.compile_ok
        pm.illegal_start = ill
        pm.cannot_find_symbol = cfs
        pm.semicolon_expected = semi
        pm.javac_error_lines = ill + cfs + semi
        beh = _load_behavioral(run_dir, prog)
        pm.behavioral_detail = str(beh.get("stdout_detail") or beh.get("verdict_reason") or "")
        km = beh.get("key_metrics_match") or {}
        if prog in SUB_PROGRAMS:
            tc = beh.get("test_cases") or beh.get("key_metrics_match") or {}
            if isinstance(tc, dict) and tc:
                passed = sum(1 for v in tc.values() if v)
                pm.behavioral_cases = f"{passed}/{len(tc)} cases"
            else:
                pm.behavioral_cases = pm.behavioral_detail[:20]
        elif km:
            passed_km = sum(1 for v in km.values() if v)
            pm.behavioral_cases = f"{passed_km}/{len(km)} metrics"
        analyzed = _load_analyzed(run_dir, prog)
        if analyzed:
            pm.analysis_engine = str(
                analyzed.get("analysis_engine") or analyzed.get("engine") or "unknown"
            )
            rules = analyzed.get("business_rules") or []
            pm.business_rules = len(rules) if isinstance(rules, list) else 0
            pm.fallback_reason = analyzed.get("fallback_reason")
        else:
            try:
                eng, rules, fb = _analyze_program(prog)
                pm.analysis_engine = eng
                pm.business_rules = rules
                pm.fallback_reason = fb
            except Exception as exc:
                pm.analysis_engine = "error"
                pm.fallback_reason = str(exc)
        metrics[prog] = pm

    stream_times = _parse_run_log(run_dir)
    for prog, secs in stream_times.items():
        if prog in metrics:
            metrics[prog].stream_seconds = secs

    # Round verdicts
    r1_pass = sum(1 for p in metrics.values() if p.structural_ok and p.illegal_start == 0)
    lint_proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "lint_scope_safe.py")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    lint_ok = lint_proc.returncode == 0

    r2_todo_zero = sum(1 for p in metrics.values() if p.todo_count == 0)
    r2_javac_ok = sum(1 for p in metrics.values() if p.javac_error_lines <= 10)
    r2_compliance_ok = sum(1 for p in metrics.values() if p.compliance_pct >= 95.0)

    r3_llm = sum(
        1
        for p in metrics.values()
        if p.analysis_engine == "llm" and p.business_rules >= 3 and not p.fallback_reason
    )

    r4_complete = sum(1 for p in metrics.values() if p.convert_ok)
    r5_beh = sum(1 for p in metrics.values() if p.behavioral_ok)

    lines: List[str] = []
    lines.append("=" * 64)
    lines.append("PHASE C — Combined Rounds 1-5 Verification Report (All 6 Programs)")
    lines.append("=" * 64)
    lines.append(f"Timestamp:        {started or datetime.now().isoformat()}")
    lines.append(f"Run directory:    {run_dir}")
    lines.append(f"Total duration:   {duration_str}")
    lines.append(f"LLM model used:   {model}")
    lines.append("")
    lines.append("ROUND 1 — Structural integrity")
    lines.append(f"  Programs with 0 structural errors:  {r1_pass}/6")
    for prog in PROGRAMS:
        p = metrics[prog]
        lines.append(
            f"  {prog} structural:                "
            f"{'PASS' if p.structural_ok and p.illegal_start == 0 else 'FAIL'} "
            f"(illegal_start={p.illegal_start})"
        )
    lines.append(f"  Regex-on-Java lint:                 {'PASS' if lint_ok else 'FAIL'}")
    lines.append(
        f"  Verdict:                            {'PASS' if r1_pass == 6 and lint_ok else 'FAIL'}"
    )
    lines.append("")
    lines.append("ROUND 2 — Naming consistency")
    lines.append(f"  Programs with 0 TODOs:              {r2_todo_zero}/6")
    lines.append(f"  Programs with javac errors ≤10:     {r2_javac_ok}/6")
    for prog in PROGRAMS:
        p = metrics[prog]
        lines.append(
            f"  {prog} compliance:                 "
            f"{p.compliance_pct:.0f}% (TODOs: {p.todo_count}, javac err cats: {p.javac_error_lines})"
        )
    lines.append("  Top invented categories:            (see run logs)")
    lines.append(
        f"  Verdict:                            "
        f"{'PASS' if r2_todo_zero == 6 and r2_javac_ok == 6 else 'FAIL'}"
    )
    lines.append("")
    lines.append("ROUND 3 — Analyzer activation")
    lines.append(f"  Programs using LLM analyzer:        {r3_llm}/6")
    for prog in PROGRAMS:
        p = metrics[prog]
        lines.append(
            f"  {prog} engine:                     {p.analysis_engine} (rules: {p.business_rules})"
        )
    fbs = [f"{p.program}={p.fallback_reason}" for p in metrics.values() if p.fallback_reason]
    lines.append(f"  Fallback reasons (if any):          {', '.join(fbs) or 'none'}")
    lines.append(f"  Verdict:                            {'PASS' if r3_llm == 6 else 'FAIL'}")
    lines.append("")
    log_text = ""
    log_path = run_dir / "run.log"
    if log_path.is_file():
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
    timeout_hits = len(re.findall(r"timeout|TimeoutExpired|LLMStallError", log_text, re.I))
    stall_hits = len(re.findall(r"LLMStallError|No chunks for", log_text))
    crash_hits = len(re.findall(r"Traceback \(most recent|FATAL", log_text))
    max_stream_prog = max(stream_times, key=stream_times.get) if stream_times else "n/a"
    max_stream_sec = max(stream_times.values()) if stream_times else 0.0

    lines.append("ROUND 4 — Timeout & resilience")
    lines.append(f"  Programs completing convert:        {r4_complete}/6")
    lines.append(f"  Timeouts hit:                       {timeout_hits}")
    lines.append(f"  Stream stalls:                      {stall_hits}")
    lines.append(f"  Crashes:                            {crash_hits}")
    lines.append(
        f"  Max conversion time:                {max_stream_sec:.1f}s (for {max_stream_prog})"
    )
    lines.append("  Per-program conversion time (stream):")
    for prog in PROGRAMS:
        lines.append(
            f"    {prog}:                          {metrics[prog].stream_seconds:.1f}s"
        )
    lines.append("  Per-program repair count:")
    for prog in PROGRAMS:
        lines.append(f"    {prog}:                          {metrics[prog].repair_count}")
    lines.append(
        f"  Verdict:                            {'PASS' if r4_complete == 6 else 'FAIL'}"
    )
    lines.append("")
    lines.append("ROUND 5 — Behavioral parity")
    lines.append(f"  Programs PASS behavioral:           {r5_beh}/6")
    for prog in PROGRAMS:
        p = metrics[prog]
        tag = "sub-program" if prog in SUB_PROGRAMS else "main"
        detail = p.behavioral_cases or p.behavioral_detail[:40]
        lines.append(
            f"  {prog} ({tag}):              "
            f"{'PASS' if p.behavioral_ok else 'FAIL'} ({detail})"
        )
    rs = metrics["RISKSCOR"]
    risk_target = "MATCH" if rs.behavioral_ok and "726" in rs.behavioral_detail else "MISMATCH"
    lines.append(f"  RISKSCOR target 726/0/0/0:          {risk_target}")
    lines.append(
        f"  Verdict:                            {'PASS' if r5_beh == 6 else 'FAIL'}"
    )
    lines.append("")
    rounds_passed = sum(
        [
            r1_pass == 6 and lint_ok,
            r2_todo_zero == 6 and r2_javac_ok == 6,
            r3_llm == 6,
            r4_complete == 6,
            r5_beh == 6,
        ]
    )
    all_pass = all(
        p.convert_ok and p.compile_ok and p.behavioral_ok for p in metrics.values()
    )
    lines.append("=" * 64)
    lines.append("OVERALL PHASE C STATUS:")
    lines.append(f"  Rounds passed:                {rounds_passed}/5")
    lines.append(f"  Programs at 6/6 PASS:         {'YES' if all_pass else 'NO'}")
    lines.append(f"  Ready for Phase D:            {'YES' if rounds_passed == 5 and all_pass else 'NO'}")
    lines.append("=" * 64)
    lines.append("")
    lines.append(
        "PROGRAM    CONVERT  COMPILE  EXECUTE  BASELINE  BEHAVIORAL  ENGINE       REPAIRS  RETRIES  TODOS  RESULT"
    )
    for prog in PROGRAMS:
        p = metrics[prog]
        def sym(ok: bool) -> str:
            return "✓" if ok else "✗"

        exe = "n/a*" if prog in SUB_PROGRAMS else sym(p.execute_ok)
        base = "n/a*" if prog in SUB_PROGRAMS else sym(p.baseline_ok)
        result = (
            "PASS"
            if p.convert_ok and p.compile_ok and p.behavioral_ok
            else "FAIL"
        )
        lines.append(
            f"{prog:<10} {sym(p.convert_ok):<8} {sym(p.compile_ok):<8} {exe:<8} {base:<9} "
            f"{sym(p.behavioral_ok):<11} {p.analysis_engine:<12} {p.repair_count:<8} "
            f"{p.compliance_retries:<8} {p.todo_count:<6} {result}"
        )
    lines.append("")
    lines.append("* Sub-programs are not run standalone; tested via test harness in BEHAVIORAL column.")
    lines.append("=" * 64)

    failures = [p for p in metrics.values() if not (p.convert_ok and p.compile_ok and p.behavioral_ok)]
    if failures:
        lines.append("")
        lines.append("STEP 7 — Failure analysis")
        for p in failures:
            lines.append(f"\n--- {p.program} ---")
            if not p.convert_ok:
                lines.append("  CONVERT: failed (see run.log / convert phase detail)")
            if not p.compile_ok:
                lines.append(f"  COMPILE: failed (javac categories: illegal={p.illegal_start} symbol={p.cannot_find_symbol})")
                ej = run_dir / f"{p.program}.final.java"
                if ej.is_file():
                    lines.append(f"  final.java: {ej}")
            if not p.behavioral_ok:
                lines.append(f"  BEHAVIORAL: {p.behavioral_detail}")
                bj = run_dir / f"{p.program}.behavioral.json"
                if bj.is_file():
                    lines.append(f"  behavioral.json: {bj}")
            if p.fallback_reason:
                lines.append(f"  ANALYZER fallback: {p.fallback_reason}")

    lines.append("")
    lines.append("STEP 8 — Honest assessment")
    if all_pass and rounds_passed == 5:
        lines.append(
            "All six programs achieved CONVERT, COMPILE, and BEHAVIORAL PASS with five round "
            "verdicts passing. Phase C verification is complete and the stack is ready for Phase D."
        )
    else:
        failed_names = [p.program for p in failures]
        weakest = min(
            metrics.values(),
            key=lambda p: (
                int(p.behavioral_ok) + int(p.compile_ok) + int(p.convert_ok),
                p.compliance_pct,
            ),
        )
        lines.append(
            f"Full PASS was not achieved for all programs. Failures or partial passes: "
            f"{', '.join(failed_names) or 'see round verdicts'}. "
            f"Weakest link: {weakest.program} "
            f"(convert={weakest.convert_ok}, compile={weakest.compile_ok}, "
            f"behavior={weakest.behavioral_ok}, engine={weakest.analysis_engine}). "
            f"Rounds passed: {rounds_passed}/5. More work is needed before Phase D — "
            f"prioritize failed stages above and re-run verify_f41_e2e --live-llm --with-behavioral-diff."
        )

    return "\n".join(lines)


def main() -> int:
    run_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _latest_run_dir()
    report = build_report(run_dir)
    out = run_dir / "PHASE_C_CONSOLIDATED_REPORT.txt"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
