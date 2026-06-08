#!/usr/bin/env python3
"""
F33 verification: explicit pre-built symbol table naming end-to-end.

Usage (from cobol-modernization-service):
  python scripts/verify_f33_explicit_symbol_table.py

No LLM API required — inspects rendered conversion prompt, synthesizes
canonical vs drift Java from parser symbol table, and exercises
post-generation identifier validation.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ACME_COPY = ROOT.parent / "acme-bank-v3" / "copybooks"
sys.path.insert(0, str(ROOT))

from app.agents.conversion_agent import ConversionAgent
from app.converters.cobol_name_converter import (
    CobolNameConverter,
    build_explicit_symbol_table_rows,
    canonical_field_names,
    paragraph_table_for_prompt,
)
from app.services.java_pre_write_validator import validate_java_before_write
from app.services.pipeline_service import PipelineService

_F33_SOURCE = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. F33TEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY LOANCOPY.
       01 WS-CURRENT-LOAN-ID         PIC 9(10) VALUE ZEROS.
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM 2000-CLASSIFY-LOAN
           MOVE 'AC' TO LOAN-STATUS
           STOP RUN.
       2000-CLASSIFY-LOAN.
           EXIT.
"""

_PROMPT_MARKERS = (
    "Pre-built Symbol Table",
    "| COBOL Name | Java Name | Java Type | Source |",
    "Use EXACTLY these Java names",
    "LOAN-STATUS",
    "loanStatus",
    "LoanRecord",
    "not Loan, LoanData, LoanEntity",
    "2000-CLASSIFY-LOAN",
    "classifyLoan",
    "Do NOT introduce alternate field names",
)

_FORBIDDEN_NAMES = frozenset(
    {
        "status",
        "loan_status",
        "loanStat",
        "LoanData",
        "LoanEntity",
        "Loan",
        "custId",
        "outstanding",
    }
)

_KEY_FIELDS = (
    ("LOAN-STATUS", "loanStatus"),
    ("LOAN-ID", "loanId"),
    ("LOAN-OUTSTANDING", "loanOutstanding"),
    ("WS-CURRENT-LOAN-ID", "wsCurrentLoanId"),
)
_KEY_PARAGRAPH = ("2000-CLASSIFY-LOAN", "classifyLoan")


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def _ok(msg: str) -> None:
    print(f"OK  {msg}")


def parse_f33_sample() -> dict:
    svc = PipelineService()
    return svc.run_pipeline(
        _F33_SOURCE,
        {"copylib_paths": [str(ACME_COPY)]},
    )


def verify_prompt(parser_output: dict) -> int:
    print("\n--- 1. Rendered conversion prompt ---")
    agent = ConversionAgent()
    prompt, prompt_input = agent.build_conversion_prompt_input(
        _F33_SOURCE,
        parser_output,
        "{}",
        java_profile="plain_java",
    )
    rendered = agent._render_prompt_for_openrouter(prompt, prompt_input)
    md = prompt_input.get("explicit_symbol_table_markdown") or ""
    if not md.strip():
        return _fail("explicit_symbol_table_markdown is empty in prompt_input")
    _ok("prompt_input contains explicit_symbol_table_markdown")

    for marker in _PROMPT_MARKERS:
        if marker not in rendered:
            return _fail(f"rendered prompt missing marker: {marker!r}")
    _ok("rendered prompt contains all required F33 markers")

    for cobol, java in _KEY_FIELDS:
        row = f"| {cobol} | {java} |"
        if row not in md and f"| {cobol} | {java} |" not in rendered:
            return _fail(f"symbol table missing mapping row for {cobol} -> {java}")
    _ok("symbol table includes key LOANCOPY field mappings")

    cobol_para, java_method = _KEY_PARAGRAPH
    if f"| {cobol_para} | {java_method} |" not in md:
        return _fail(f"symbol table missing paragraph {cobol_para} -> {java_method}")
    _ok("symbol table includes paragraph method mapping")

    if "LoanRecord" not in md:
        return _fail("symbol table missing LoanRecord class row")
    _ok("symbol table mandates LoanRecord class name")
    return 0


def _build_canonical_java(parser_output: dict) -> str:
    """Synthesize Java that follows the pre-built symbol table exactly."""
    fields = sorted(
        name
        for name in canonical_field_names(parser_output)
        if name.startswith("loan") or name.startswith("ws")
    )
    # Ensure core LOANCOPY fields present even if parser subset differs.
    for _cobol, java in _KEY_FIELDS:
        if java not in fields:
            fields.append(java)
    for _cobol, java in _KEY_FIELDS:
        fields.append(java)
    fields = sorted(set(fields))

    def _decl_line(name: str) -> str:
        if name == "loanOutstanding":
            return "        private java.math.BigDecimal loanOutstanding;"
        if name.endswith("Status") or name.endswith("Class"):
            return f"        private String {name};"
        return f"        private int {name};"

    field_lines = "\n".join(_decl_line(f) for f in fields if f.startswith("loan") or f.startswith("ws"))
    return f"""\
package com.modernized.f33;

import java.math.BigDecimal;

public class F33test {{
    private int wsCurrentLoanId;

    private static class LoanRecord {{
{field_lines}
    }}

    private LoanRecord currentLoan = new LoanRecord();

    public static void main(String[] args) {{
        new F33test().classifyLoan();
    }}

    private void classifyLoan() {{
        currentLoan.loanStatus = "AC";
        currentLoan.loanId = 1;
        currentLoan.loanOutstanding = BigDecimal.ZERO;
        wsCurrentLoanId = 1;
    }}
}}
"""


def _build_drift_java() -> str:
    """Java that deliberately violates symbol-table naming."""
    return """\
package com.modernized.f33;

public class F33test {
    private static class LoanData {
        private String status;
        private int loan_id;
    }

    private LoanData rec = new LoanData();

    public void run() {
        rec.status = "AC";
        classify_loan();
    }

    private void classify_loan() {
    }
}
"""


def _audit_java_against_table(java: str, parser_output: dict) -> list[str]:
    issues: list[str] = []
    canonical = canonical_field_names(parser_output)
    rows = build_explicit_symbol_table_rows(parser_output)
    java_by_cobol = {cobol: java for cobol, java, _t, _s in rows}

    for bad in _FORBIDDEN_NAMES:
        if re.search(rf"\b{re.escape(bad)}\b", java):
            issues.append(f"forbidden alternate name appears: {bad}")

    if re.search(r"\bclass\s+Loan\b", java) and "LoanRecord" not in java:
        issues.append("used class Loan instead of LoanRecord")

    for cobol, expected in _KEY_FIELDS:
        if expected in canonical and expected not in java:
            issues.append(f"missing canonical field/method name: {expected} (from {cobol})")

    if "classifyLoan" in java_by_cobol.values() or any(
        e.get("java_method") == "classifyLoan" for e in paragraph_table_for_prompt(parser_output)
    ):
        if "classifyLoan(" not in java and "classifyLoan()" not in java:
            if "classify_loan" in java or "classify_loan()" in java:
                issues.append("paragraph drift: classify_loan instead of classifyLoan")

    return issues


def verify_generated_java(parser_output: dict) -> int:
    print("\n--- 2. Generated Java vs symbol table ---")
    canonical = _build_canonical_java(parser_output)
    issues = _audit_java_against_table(canonical, parser_output)
    if issues:
        return _fail(f"canonical sample failed audit: {issues}")
    _ok("canonical synthesized Java uses only symbol-table names")

    drift = _build_drift_java()
    drift_issues = _audit_java_against_table(drift, parser_output)
    if len(drift_issues) < 3:
        return _fail(f"drift sample should fail audit, got: {drift_issues}")
    _ok(f"drift sample correctly flagged {len(drift_issues)} naming issues")
    return 0


def verify_post_generation_validation(parser_output: dict) -> int:
    print("\n--- 3. Post-generation identifier validation ---")
    canonical = _build_canonical_java(parser_output)
    drift = _build_drift_java()

    canon_errors = validate_java_before_write(canonical, parser_output=parser_output)
    if canon_errors:
        id_errors = [e for e in canon_errors if "canonical" in e.lower() or "dangling" in e.lower()]
        if id_errors:
            return _fail(f"canonical Java rejected (identifier): {id_errors}")
        # structural-only failures on minimal stub are acceptable if any
        print(f"  note: canonical had non-identifier warnings: {canon_errors[:3]}")

    drift_errors = validate_java_before_write(drift, parser_output=parser_output)
    naming_errors = [
        e
        for e in drift_errors
        if "non-canonical" in e.lower()
        or "dangling" in e.lower()
        or "LoanRecord" in e
    ]
    if not naming_errors:
        return _fail(f"drift Java should fail identifier validation; all errors: {drift_errors}")
    _ok(f"drift Java rejected ({len(naming_errors)} identifier error(s))")
    for err in naming_errors[:5]:
        print(f"      {err}")

    # Targeted unit checks
    bad_status = """\
public class X {
    private static class LoanRecord { private String loanStatus; }
    private void m(LoanRecord r) { r.status = "A"; }
}
"""
    if not any("non-canonical" in e.lower() for e in validate_java_before_write(bad_status, parser_output)):
        return _fail("expected non-canonical rejection for .status")

    bad_dangling = """\
public class X {
    private void m() { int x = this.loanStatus; }
}
"""
    if not any("dangling" in e.lower() for e in validate_java_before_write(bad_dangling, parser_output)):
        return _fail("expected dangling rejection for undeclared loanStatus")

    _ok("validator accepts canonical output and rejects naming drift")
    return 0


def _postprocess_passthrough(raw: str, **kwargs: object) -> tuple[str, str]:
    """Skip repair/finalize so F33 tests isolate identifier validation."""
    from app.agents.conversion_agent import sanitize_java_conversion_output

    java_code, notes = sanitize_java_conversion_output(raw)
    return java_code, notes


def verify_convert_pipeline_mock(parser_output: dict) -> int:
    print("\n--- 4. convert_with_metadata + mocked LLM ---")
    agent = ConversionAgent()
    canonical = _build_canonical_java(parser_output)
    drift = _build_drift_java() + "\n---MAPPING_NOTES---\ndrift test\n"

    with (
        patch.object(agent, "_convert_raw", return_value=canonical),
        patch.object(agent, "_postprocess_conversion", _postprocess_passthrough),
    ):
        java, _ = agent.convert_with_metadata(_F33_SOURCE, parser_output, "{}")
    if _audit_java_against_table(java, parser_output):
        return _fail("mocked canonical convert_with_metadata produced naming drift")
    _ok("convert_with_metadata preserves canonical names (mocked LLM)")

    from app.services.java_pre_write_validator import JavaPreWriteValidationError

    with (
        patch.object(agent, "_convert_raw", return_value=drift),
        patch.object(agent, "_postprocess_conversion", _postprocess_passthrough),
    ):
        try:
            agent.convert_with_metadata(_F33_SOURCE, parser_output, "{}")
        except JavaPreWriteValidationError as exc:
            if any(
                "non-canonical" in e.lower() or "LoanRecord" in e for e in exc.errors
            ):
                _ok("convert_with_metadata rejects drift Java after validation/regen")
                return 0
            return _fail(f"drift validation errors unexpected: {exc.errors}")
        except Exception as exc:
            return _fail(f"drift raised unexpected error: {exc}")
        return _fail("convert_with_metadata should reject drift Java")
    return 0


def main() -> int:
    print("F33 — explicit symbol table naming (end-to-end)")
    if not ACME_COPY.is_dir():
        return _fail(f"copybooks not found: {ACME_COPY}")

    parser_output = parse_f33_sample()
    if not parser_output.get("symbol_table_entries"):
        return _fail("parser returned empty symbol_table")

    program = parser_output.get("program_name")
    _ok(f"parsed F33TEST ({len(parser_output.get('symbol_table_entries') or [])} symbols)")

    rc = verify_prompt(parser_output)
    if rc:
        return rc
    rc = verify_generated_java(parser_output)
    if rc:
        return rc
    rc = verify_post_generation_validation(parser_output)
    if rc:
        return rc
    rc = verify_convert_pipeline_mock(parser_output)
    if rc:
        return rc

    print("\n=== F33 PASSED ===")
    print("Layers verified: prompt generation -> symbol table -> validation -> convert pipeline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
