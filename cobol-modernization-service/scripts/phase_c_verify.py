#!/usr/bin/env python3
"""Phase C completion check: compile generated Java and run RISKSCOR on ACME data."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACME = ROOT.parent / "acme-bank-v3"
JAVA_TEST = ROOT / "java_test"
PROGRAMS = ("CALCFEE", "CHKAML", "RISKSCOR", "LOANEVAL", "RECOVRY", "RPTMONTH")


def main() -> int:
    JAVA_TEST.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))

    from app.parsers.cobol_parser import ParserLayer
    from app.services.pipeline_service import PipelineService
    from app.converters.record_layout import layout_from_copybook_path, parse_display_field

    svc = PipelineService()
    opts = {"copylib_paths": [str(ACME / "copybooks")]}
    compile_results: dict[str, str] = {}

    for prog in PROGRAMS:
        cbl = ACME / "src" / f"{prog}.cbl"
        if not cbl.is_file():
            compile_results[prog] = "missing source"
            continue
        src = cbl.read_text(encoding="utf-8")
        parsed = svc.run_pipeline(src, opts)
        analysis = "{}"
        try:
            analysis = json.dumps(svc.analyze(src, parsed), default=str)
        except Exception:
            pass
        conv = svc.convert_cobol(src, parsed, analysis)
        java = conv.get("java_code", "")
        pkg = f"com.modernized.{prog.lower()}"
        out_dir = JAVA_TEST / "com" / "modernized" / prog.lower()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{prog.title().replace('_', '')}App.java"
        from app.services.java_pre_write_validator import write_java_file

        if conv.get("conversion_failed"):
            compile_results[prog] = conv.get("error", "conversion failed")
            continue
        try:
            write_java_file(out_file, java)
        except Exception as exc:
            compile_results[prog] = f"validation failed: {exc}"[:500]
            continue
        r = subprocess.run(
            ["javac", str(out_file.relative_to(JAVA_TEST))],
            cwd=JAVA_TEST,
            capture_output=True,
            text=True,
        )
        compile_results[prog] = "ok" if r.returncode == 0 else (r.stderr or r.stdout)[:500]

    # Expected class counts from LOANFILE + RISKSCOR rules
    layout = layout_from_copybook_path(ACME / "copybooks" / "LOANCOPY.cpy")
    by_name = {f.name: f for f in layout}
    counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for line in (ACME / "data" / "LOANFILE.dat").read_text(encoding="latin-1").splitlines():
        if not line.strip():
            continue
        st = parse_display_field(line, by_name["LOAN-STATUS"]).strip()
        if st not in ("AC", "RS"):
            continue
        dpd = int(parse_display_field(line, by_name["LOAN-DAYS-PAST-DUE"]).strip() or "0")
        if dpd <= 30:
            bucket = 1
        elif dpd <= 90:
            bucket = 2
        elif dpd <= 180:
            bucket = 3
        else:
            bucket = 4
        counts[bucket] += 1

    # Run RISKSCOR Java if compiled
    risk_java = JAVA_TEST / "com" / "modernized" / "riskscor" / "RiskscorApp.java"
    run_out = ""
    java_counts = None
    if compile_results.get("RISKSCOR") == "ok":
        work = JAVA_TEST / "run"
        work.mkdir(exist_ok=True)
        for dat in (ACME / "data").glob("*.dat"):
            shutil.copy2(dat, work / dat.name)
        for name in ("SCORFILE.dat", "RECVNEW.dat", "RISKRPT.dat", "BCTSUBM.dat"):
            (work / name).touch(exist_ok=True)
        launcher = work / "RunRiskscor.java"
        launcher.write_text(
            """
import com.modernized.riskscor.RiskscorApp;

public class RunRiskscor {
    public static void main(String[] args) throws Exception {
        Object svc = Class.forName("com.modernized.riskscor.RiskscorApp").getDeclaredConstructor().newInstance();
        for (var m : svc.getClass().getMethods()) {
            if ("execute".equals(m.getName()) && m.getParameterCount() == 0) {
                m.invoke(svc);
                return;
            }
        }
        throw new IllegalStateException("no execute() on RiskscorApp");
    }
}
""".strip()
            + "\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["javac", "-cp", str(JAVA_TEST), "RunRiskscor.java"],
            cwd=work,
            check=False,
        )
        proc = subprocess.run(
            ["java", "-cp", f"{JAVA_TEST}{Path.pathsep}{work}", "RunRiskscor"],
            cwd=work,
            capture_output=True,
            text=True,
        )
        run_out = (proc.stdout or "") + (proc.stderr or "")
        java_counts = {}
        for i in range(1, 5):
            m = re.search(rf"CLASS {i}:\s*(\d+)", run_out)
            if m:
                java_counts[i] = int(m.group(1))

    print("=== Phase C compile results ===")
    for prog, status in compile_results.items():
        print(f"{prog}: {status}")

    print("\n=== Expected RISKSCOR class counts (from LOANFILE.dat) ===")
    print(counts)

    print("\n=== RISKSCOR Java run output ===")
    print(run_out or "(not run)")
    if java_counts:
        print("parsed java counts:", java_counts)
        print("match:", java_counts == counts)

    return 0 if compile_results.get("RISKSCOR") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
