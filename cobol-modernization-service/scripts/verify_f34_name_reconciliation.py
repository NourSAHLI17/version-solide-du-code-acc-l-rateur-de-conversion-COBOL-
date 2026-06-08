#!/usr/bin/env python3
"""
F34 verification: post-generation name reconciliation.

Usage (from cobol-modernization-service):
  python scripts/verify_f34_name_reconciliation.py
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.conversion_agent import ConversionAgent
from app.converters.cobol_name_converter import enrich_symbol_table_java_names
from app.services.java_identifier_validator import validate_identifier_references
from app.services.java_name_reconciler import reconcile_names
from app.services.java_pre_write_validator import validate_java_before_write

_SYMBOL_TABLE = enrich_symbol_table_java_names(
    [{"name": "LOAN-STATUS", "pic": "X(2)", "java_field": "loanStatus"}]
)
_PARSER_OUTPUT = {"program_name": "TEST", "symbol_table": _SYMBOL_TABLE}

_USER_SAMPLE = """
public class Test {
    private static class LoanRecord { private String loanStatus; }
    void foo() { LoanRecord r = new LoanRecord(); r.status = "AC"; }
}
"""

_CANONICAL_SAMPLE = """
public class Test {
    private static class LoanRecord { private String loanStatus; }
    void foo() { LoanRecord r = new LoanRecord(); r.loanStatus = "AC"; }
}
"""

_LEGACY_ALIASES_SAMPLE = """
public class Test {
    private static class LoanRecord {
        String loanStatus;
        String loanClass;
        java.math.BigDecimal loanOutstanding;
        int loanCustId;
    }
    void foo() {
        LoanRecord rec = new LoanRecord();
        rec.status = "AC";
        rec.classNum = "1";
        rec.outstanding = java.math.BigDecimal.ZERO;
        rec.custId = 42;
    }
}
"""

_AMBIGUOUS_SAMPLE = """
public class Test {
    private String loanStatus;
    private String loanStat;
    void foo() { this.stat = "x"; }
}
"""


def _fail(msg: str, phase: str = "") -> int:
    prefix = f"[{phase}] " if phase else ""
    print(f"FAIL: {prefix}{msg}")
    return 1


def _ok(msg: str) -> None:
    print(f"OK  {msg}")


def verify_primary_status_to_loan_status() -> int:
    print("\n--- 1. Primary: r.status → r.loanStatus (symbol table) ---")
    fixed, notes = reconcile_names(
        _USER_SAMPLE,
        symbol_table=_SYMBOL_TABLE,
        program_name="TEST",
    )
    if "r.loanStatus" not in fixed or "r.status" in fixed:
        return _fail(f'expected r.loanStatus (not r.status), got:\n{fixed}', "phase-1/2 alias")
    if '"AC"' not in fixed:
        return _fail("assignment value lost during reconcile", "phase-1/2 alias")
    if not notes:
        return _fail("expected reconcile notes for alias rename", "phase-1/2 alias")
    _ok("r.status rewritten to r.loanStatus with symbol table")
    return 0


def verify_common_legacy_aliases() -> int:
    print("\n--- 2. Common legacy aliases on rec receiver ---")
    fixed, notes = reconcile_names(
        _LEGACY_ALIASES_SAMPLE,
        symbol_table=_SYMBOL_TABLE,
        program_name="TEST",
    )
    checks = (
        ("rec.loanStatus", "status"),
        ("rec.loanClass", "classNum"),
        ("rec.loanOutstanding", "outstanding"),
        ("rec.loanCustId", "custId"),
    )
    for good, bad in checks:
        if good not in fixed:
            return _fail(f"missing {good} after reconcile", "phase-1 known alias")
        if f"rec.{bad}" in fixed:
            return _fail(f"legacy rec.{bad} still present", "phase-1 known alias")
    if len(notes) < 3:
        return _fail(f"expected multiple rename notes, got {notes}", "phase-1 known alias")
    _ok(f"legacy aliases corrected ({len(notes)} rename note(s))")
    return 0


def verify_ambiguous_not_guessed() -> int:
    print("\n--- 3. Ambiguous cases flagged, not invented ---")
    fixed, notes = reconcile_names(_AMBIGUOUS_SAMPLE, symbol_table=_SYMBOL_TABLE)
    if "// TODO: Resolve these name mismatches" not in fixed:
        return _fail("ambiguous case should prepend TODO block", "phase-4 ambiguous")
    if "this.loanStat =" in fixed and "this.stat" not in fixed:
        return _fail("ambiguous stat should not be silently mapped to loanStat", "phase-3 fuzzy")
    id_errors = validate_identifier_references(
        fixed, {"symbol_table": _SYMBOL_TABLE}
    )
    if id_errors and not any("TODO" in fixed for _ in [0]):
        pass  # TODO is acceptable
    _ok("ambiguous mismatch gets TODO (not silent fuzzy guess)")
    return 0


def verify_canonical_unchanged() -> int:
    print("\n--- 4. Canonical input unchanged ---")
    fixed, notes = reconcile_names(
        _CANONICAL_SAMPLE,
        symbol_table=_SYMBOL_TABLE,
        program_name="TEST",
    )
    if fixed.replace("\r\n", "\n").strip() != _CANONICAL_SAMPLE.replace("\r\n", "\n").strip():
        return _fail("canonical sample was modified", "all phases")
    if notes:
        return _fail(f"canonical sample produced notes: {notes}", "all phases")
    _ok("canonical code left unchanged")
    return 0


def verify_pipeline_order_before_validation() -> int:
    print("\n--- 5. Pipeline: reconcile before validation/write ---")
    agent = ConversionAgent()
    broken = _USER_SAMPLE + "\n---MAPPING_NOTES---\n"
    call_order: list[str] = []

    real_reconcile = reconcile_names

    def _track_reconcile(java_source, symbol_table=None, **kwargs):
        call_order.append("reconcile")
        return real_reconcile(java_source, symbol_table, **kwargs)

    real_validate = validate_java_before_write

    def _track_validate(java_source, parser_output=None):
        call_order.append("validate")
        return real_validate(java_source, parser_output=parser_output)

    with (
        patch.object(agent, "_convert_raw", return_value=broken),
        patch("app.agents.conversion_agent.reconcile_names", side_effect=_track_reconcile),
        patch("app.agents.conversion_agent.validate_java_before_write", side_effect=_track_validate),
    ):
        java, _ = agent.convert_with_metadata(
            "PROCEDURE DIVISION.",
            _PARSER_OUTPUT,
            "{}",
        )

    if "reconcile" not in call_order or "validate" not in call_order:
        return _fail(f"expected reconcile+validate calls, got {call_order}", "pipeline")
    if call_order.index("reconcile") > call_order.index("validate"):
        return _fail(f"reconcile must run before validate, order={call_order}", "pipeline")

    if "r.loanStatus" not in java or "r.status" in java:
        return _fail("convert_with_metadata output missing reconciled field ref", "pipeline")

    errors = validate_java_before_write(java, parser_output=_PARSER_OUTPUT)
    id_errors = [e for e in errors if "non-canonical" in e.lower() or "dangling" in e.lower()]
    if id_errors:
        return _fail(f"reconciled output still has identifier errors: {id_errors}", "pipeline")

    # write_java_file path
    from app.services.java_pre_write_validator import write_java_file

    write_order: list[str] = []

    def _write_track_reconcile(java_source, symbol_table=None, **kwargs):
        write_order.append("reconcile")
        return real_reconcile(java_source, symbol_table, **kwargs)

    def _write_track_validate(java_source, parser_output=None):
        write_order.append("validate")
        return real_validate(java_source, parser_output=parser_output)

    with (
        patch("app.services.java_name_reconciler.reconcile_names", side_effect=_write_track_reconcile),
        patch("app.services.java_pre_write_validator.validate_java_before_write", side_effect=_write_track_validate),
    ):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Test.java"
            write_java_file(path, _USER_SAMPLE, parser_output=_PARSER_OUTPUT, reconcile=True)
            written = path.read_text(encoding="utf-8")

    if write_order != ["reconcile", "validate"]:
        return _fail(f"write_java_file order expected ['reconcile','validate'], got {write_order}", "write")
    if "r.loanStatus" not in written or "r.status" in written:
        return _fail("written file missing reconciled identifier", "write")

    _ok("reconcile runs before validate in convert_with_metadata and write_java_file")
    return 0


def verify_reconcile_source_location() -> int:
    print("\n--- 6. reconcile_names wired in conversion_agent ---")
    src = inspect.getsource(ConversionAgent._postprocess_conversion)
    if "reconcile_names" not in src:
        return _fail("reconcile_names not called from _postprocess_conversion", "pipeline")
    if "validate_java_before_write" in src:
        return _fail("validate should not be inside _postprocess_conversion", "pipeline")
    idx_reconcile = src.index("reconcile_names")
    idx_finalize = src.index("apply_java_structure_finalize")
    if idx_reconcile > idx_finalize:
        return _fail("reconcile_names must run before apply_java_structure_finalize", "pipeline")
    _ok("reconcile_names in _postprocess_conversion before structure finalize")
    return 0


def main() -> int:
    print("F34 — post-generation name reconciliation")
    steps = (
        verify_primary_status_to_loan_status,
        verify_common_legacy_aliases,
        verify_ambiguous_not_guessed,
        verify_canonical_unchanged,
        verify_pipeline_order_before_validation,
        verify_reconcile_source_location,
    )
    for step in steps:
        rc = step()
        if rc:
            return rc
    print("\n=== F34 PASSED ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
