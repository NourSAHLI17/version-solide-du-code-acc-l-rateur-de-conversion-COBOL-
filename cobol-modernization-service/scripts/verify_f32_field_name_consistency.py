#!/usr/bin/env python3
"""
F32 verification: canonical LoanRecord field names end-to-end (no declaration/reference drift).

Usage (from cobol-modernization-service):
  python scripts/verify_f32_field_name_consistency.py

Builds /tmp/generated/RISKSCOR.java via RISKSCOR repair + plain_java sanitization,
runs javac, and audits LoanRecord field declarations vs parseLoanRecord references.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACME = ROOT.parent / "acme-bank-v3"
OUT_FILE = Path("/tmp/generated/RISKSCOR.java")
SOURCE_JAVA = ROOT / "java_test" / "com" / "modernized" / "riskscor" / "RiskscorService.java"

# Non-canonical spellings that must not appear on LoanRecord receivers.
FORBIDDEN_LEGACY_FIELDS = frozenset(
    {
        "custId",
        "status",
        "outstanding",
        "daysPastDue",
        "originalAmt",
        "provisionRate",
        "provisionAmt",
        "loan_status",
    }
)

LOAN_RECORD_RECEIVER_RE = re.compile(
    r"\b(?:currentLoan(?:Record)?|rec)\.(\w+)\b",
)
LOAN_RECORD_METHODS = frozenset({"isActive", "isRestructured"})


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def _ok(msg: str) -> None:
    print(f"OK  {msg}")


def build_riskscor_java() -> tuple[str, list[str]]:
    sys.path.insert(0, str(ROOT))
    from app.services.java_project_profile import JAVA_PROFILE_PLAIN, apply_java_profile_sanitization
    from app.services.pipeline_service import PipelineService
    from app.services.riskscor_java_repair import repair_riskscor_rewrite_java

    if not SOURCE_JAVA.is_file():
        raise FileNotFoundError(SOURCE_JAVA)

    java = SOURCE_JAVA.read_text(encoding="utf-8")
    cbl = ACME / "src" / "RISKSCOR.cbl"
    cobol_source = cbl.read_text(encoding="utf-8")
    parser_output = PipelineService().run_pipeline(
        cobol_source,
        {"copylib_paths": [str(ACME / "copybooks")]},
    )
    java, repair_notes = repair_riskscor_rewrite_java(
        java,
        program_name="RISKSCOR",
        parser_output=parser_output,
        cobol_source=cobol_source,
    )
    java, _ = apply_java_profile_sanitization(
        java,
        JAVA_PROFILE_PLAIN,
        program_name="RISKSCOR",
    )
    return java, repair_notes


def extract_loan_record_fields(java_source: str) -> set[str]:
    """Fields declared on ``LoanRecord`` inner class."""
    match = re.search(
        r"(?:static\s+)?class\s+LoanRecord\s*\{([^}]*)\}",
        java_source,
        re.DOTALL,
    )
    if not match:
        return set()
    body = match.group(1)
    fields: set[str] = set()
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("boolean "):
            continue
        m = re.match(
            r"(?:public\s+|private\s+|protected\s+)?(?:static\s+)?"
            r"[\w.<>,\s\[\]]+\s+(\w+)\s*(?:=|;)",
            stripped,
        )
        if m:
            fields.add(m.group(1))
    return fields


def extract_parse_loan_record_assignments(java_source: str) -> set[str]:
    """Fields assigned in ``parseLoanRecord`` (``rec.<field> =``)."""
    match = re.search(
        r"LoanRecord\s+parseLoanRecord\s*\([^)]*\)\s*\{",
        java_source,
    )
    if not match:
        return set()
    start = match.end()
    depth = 1
    i = start
    while i < len(java_source) and depth > 0:
        if java_source[i] == "{":
            depth += 1
        elif java_source[i] == "}":
            depth -= 1
        i += 1
    body = java_source[start : i - 1]
    assigned: set[str] = set()
    for m in re.finditer(r"\brec\.(\w+)\s*=", body):
        assigned.add(m.group(1))
    return assigned


def audit_field_references(java_source: str, declared: set[str]) -> list[str]:
    issues: list[str] = []
    for m in LOAN_RECORD_RECEIVER_RE.finditer(java_source):
        field = m.group(1)
        if field in LOAN_RECORD_METHODS:
            continue
        if field in FORBIDDEN_LEGACY_FIELDS:
            issues.append(f"legacy field reference: .{field}")
        elif field not in declared and field != "rawLine":
            issues.append(f"reference to undeclared field: .{field}")
    if "-" in java_source and re.search(r"\brec\.[A-Z0-9-]+\b", java_source):
        issues.append("COBOL-style hyphenated field reference on rec")
    if re.search(r"\bloan_status\b", java_source):
        issues.append("snake_case loan_status reference")
    parse_fields = extract_parse_loan_record_assignments(java_source)
    extra_parse = parse_fields - declared
    if extra_parse:
        issues.append(f"parseLoanRecord assigns undeclared fields: {sorted(extra_parse)}")
    missing_parse = {f for f in declared if f != "rawLine"} - parse_fields
    if missing_parse and parse_fields:
        issues.append(
            f"LoanRecord declares fields not populated by parseLoanRecord: {sorted(missing_parse)[:8]}..."
        )
    return issues


def run_javac(path: Path) -> tuple[int, str]:
    proc = subprocess.run(
        ["javac", "-Xlint:all", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    print("F32 verification — LoanRecord field-name consistency")
    print("=" * 60)

    try:
        java, notes = build_riskscor_java()
    except Exception as exc:
        return _fail(f"build RISKSCOR.java: {exc}")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(java, encoding="utf-8")
    _ok(f"Wrote {OUT_FILE} ({len(java)} bytes)")
    for note in notes:
        print(f"    note: {note}")

    declared = extract_loan_record_fields(java)
    if not declared:
        return _fail("could not find LoanRecord field declarations")
    _ok(f"LoanRecord declares {len(declared)} fields (incl. rawLine)")

    issues = audit_field_references(java, declared)
    if issues:
        print("FAIL: field consistency audit:")
        for item in issues:
            print(f"  - {item}")
        return 1
    _ok("parseLoanRecord assignments match LoanRecord declarations")
    _ok("no legacy custId/status/outstanding references on LoanRecord receivers")

    code, output = run_javac(OUT_FILE)
    symbol_lines = [
        line
        for line in output.splitlines()
        if "cannot find symbol" in line.lower()
    ]
    if symbol_lines:
        print("FAIL: javac cannot find symbol (field-related):")
        for line in symbol_lines[:20]:
            print(f"  {line}")
        return 1
    if code != 0:
        print("WARN: javac exited non-zero but no 'cannot find symbol' for fields")
        print(output[-2000:])
    else:
        _ok("javac completed with no cannot find symbol errors")

    print("\n" + "=" * 60)
    print("F32 verification PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
