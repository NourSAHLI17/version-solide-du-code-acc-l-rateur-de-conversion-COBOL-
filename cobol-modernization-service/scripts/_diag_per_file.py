#!/usr/bin/env python3
import zipfile
from pathlib import Path

from app.services.behavioral_diff_runner import run_project_behavioral_diff

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "cobol-modernization-service" / "tests" / "fixtures" / "acme_e2e"
files = {}
with zipfile.ZipFile(ROOT / "acme-bank-v3.zip") as z:
    for i in z.infolist():
        if not i.is_dir() and i.filename.startswith("src/") and i.filename.endswith(".cbl"):
            files[i.filename] = z.read(i.filename).decode("utf-8")
arts = []
for p in sorted(files):
    prog = Path(p).stem.upper()
    jp = FIX / f"{prog}.raw.java"
    if not jp.is_file():
        continue
    arts.append(
        {
            "path": p,
            "filename": Path(p).name,
            "program_name": prog,
            "cobol_source": files[p],
            "java_source": jp.read_text(encoding="utf-8"),
            "parser_output": {},
            "analysis_output": {},
        }
    )
result = run_project_behavioral_diff(
    {
        "target_type": "project",
        "run_id": "diag-run",
        "program_name": "acme-bank-v3",
        "files": arts,
        "timeout_seconds": 120,
        "fallback_mode": False,
    }
)
print("PROJECT qscore:", result.get("qscore"), "status:", result.get("status"))
print()
for row in result.get("file_results") or []:
    prog = row.get("program_name") or row.get("path")
    diag = row.get("run_diagnostics") or {}
    diff = row.get("diff_summary") or {}
    print(f"=== {prog} ===")
    print("  status:", row.get("status"))
    print("  behavioral_status:", diag.get("behavioral_status"))
    print("  cobol_compile:", diag.get("cobol_compile_status"))
    print("  java_compile:", diag.get("java_compile_status"))
    print("  diff_pct:", diff.get("diff_percentage"))
    fr = row.get("failure_reason") or diag.get("failure_reason") or ""
    print("  failure_reason:", fr[:200] if fr else "")
    cob = (row.get("cobol_output") or "").splitlines()
    jav = (row.get("java_output") or "").splitlines()
    print("  COBOL stdout (first 10):")
    for ln in cob[:10]:
        print("   ", repr(ln))
    print("  Java stdout (first 10):")
    for ln in jav[:10]:
        print("   ", repr(ln))
    fts = row.get("failed_tests") or []
    if fts:
        print(f"  failed_tests ({len(fts)}):")
        for ft in fts[:5]:
            print("   -", ft.get("id"), ":", (ft.get("description") or "")[:120])
    for e in (row.get("execution_details") or [])[:1]:
        ce = e.get("cobol_execution") or {}
        je = e.get("java_execution") or {}
        if ce.get("stderr") or ce.get("error"):
            print("  COBOL runtime err:", (ce.get("error") or ce.get("stderr") or "")[:400])
        if je.get("stderr") or je.get("error"):
            print("  Java runtime err:", (je.get("error") or je.get("stderr") or "")[:400])
    print()
