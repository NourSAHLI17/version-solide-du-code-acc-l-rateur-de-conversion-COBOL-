#!/usr/bin/env python3
"""
F29 verification: no Spring imports/annotations in plain_java profile output.

Regenerates ACME programs to /tmp/generated with java_profile=plain_java, then greps for leaks.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACME = ROOT.parent / "acme-bank-v3"
OUT_DIR = Path("/tmp/generated")
PROGRAMS = ("CALCFEE", "CHKAML", "RISKSCOR", "LOANEVAL", "RECOVRY", "RPTMONTH")

SPRING_PATTERNS = (
    re.compile(r"springframework", re.IGNORECASE),
    re.compile(r"@Service\b"),
    re.compile(r"@Autowired\b"),
)


def main() -> int:
    os.environ.setdefault("JAVA_PROJECT_PROFILE", "plain_java")
    sys.path.insert(0, str(ROOT))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    from app.services.java_pre_write_validator import write_java_file
    from app.services.pipeline_service import PipelineService

    svc = PipelineService()
    opts = {"copylib_paths": [str(ACME / "copybooks")], "java_profile": "plain_java"}
    generated = 0
    failures: list[str] = []

    print("F29 verification — no Spring in plain_java output")
    print("=" * 60)
    print(f"Output directory: {OUT_DIR.resolve()}")
    print(f"Profile: plain_java")
    print()

    for prog in PROGRAMS:
        cbl = ACME / "src" / f"{prog}.cbl"
        if not cbl.is_file():
            print(f"SKIP {prog}: missing {cbl.name}")
            continue
        src = cbl.read_text(encoding="utf-8")
        parsed = svc.run_pipeline(src, opts)
        analysis = "{}"
        try:
            analysis = json.dumps(svc.analyze(src, parsed), default=str)
        except Exception:
            pass
        conv = svc.convert_cobol(
            src,
            parsed,
            analysis,
            java_profile="plain_java",
        )
        if conv.get("conversion_failed"):
            failures.append(f"{prog}: {conv.get('error')}")
            print(f"FAIL convert {prog}: {conv.get('error')}")
            continue
        java = conv.get("java_code", "")
        if not java.strip():
            failures.append(f"{prog}: empty java_code")
            print(f"FAIL convert {prog}: empty output")
            continue
        out_file = OUT_DIR / f"{prog}App.java"
        try:
            write_java_file(out_file, java)
        except Exception as exc:
            failures.append(f"{prog}: write blocked — {exc}")
            print(f"FAIL write {prog}: {exc}")
            continue
        generated += 1
        print(f"OK  generated {out_file.name} ({len(java)} bytes)")

    print()
    java_files = sorted(OUT_DIR.glob("*.java"))
    if not java_files:
        print("FAIL: no .java files in /tmp/generated")
        if failures:
            print("Conversion failures:")
            for item in failures:
                print(f"  - {item}")
        return 1

    print(f"Scanning {len(java_files)} file(s) for Spring leaks...")
    leaks: list[str] = []
    for path in java_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_num, line in enumerate(text.splitlines(), 1):
            for pattern in SPRING_PATTERNS:
                if pattern.search(line):
                    leaks.append(f"{path.name}:{line_num}: {line.strip()[:100]}")

    if leaks:
        print("FAIL: Spring artifacts found:")
        for item in leaks:
            print(f"  {item}")
        return 1

    print("OK  grep-equivalent scan: no springframework, @Service, or @Autowired")
    print("=" * 60)
    print("F29 verification PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
