"""Deterministic REWRITE / record-layout repair for RISKSCOR (copy-then-modify)."""

from __future__ import annotations

import re
from typing import List, Tuple

from app.converters.rewrite_record import (
    collect_rewrite_targets,
    generate_format_loan_record_java,
    generate_loan_record_inner_class_java,
    generate_parse_loan_record_java,
    layout_for_loan_record,
    normalize_loan_record_field_refs,
    RISKSCOR_LOAN_WRITTEN_FIELDS,
)
from app.converters.java_class_builder import JavaFileAssembler
from app.services.cobol_java_runtime import COBOL_RECORD_REWRITE_JAVA
from app.services.java_output_sanitizer import _remove_dangling_field_duplicates

_RISKSCOR_NAMES = frozenset({"RISKSCOR", "RISKSCOR.CBL", "RISKSCOR.COB"})


def is_riskscor_program(program_name: str | None, java_source: str | None = None) -> bool:
    name = str(program_name or "").strip().upper().replace(".CBL", "").replace(".COB", "")
    if name in _RISKSCOR_NAMES:
        return True
    if java_source and re.search(r"\bclass\s+Riskscor\w*\b", java_source, re.IGNORECASE):
        return True
    return False


def repair_riskscor_rewrite_java(
    java_source: str,
    *,
    program_name: str | None = None,
    parser_output: dict | None = None,
    cobol_source: str | None = None,
) -> Tuple[str, List[str]]:
    """
    Apply copy-then-modify ``formatLoanRecord`` / ``parseLoanRecord`` for LOAN-RECORD REWRITE.

    Replaces rebuild-from-scratch formatters that drop unreferenced fields.
    """

    notes: List[str] = []
    if not is_riskscor_program(program_name, java_source):
        return java_source, notes

    layout = layout_for_loan_record()
    written = collect_rewrite_targets(
        parser_output or {},
        cobol_source or "",
        layout,
        explicit=set(RISKSCOR_LOAN_WRITTEN_FIELDS),
    )

    assembler = JavaFileAssembler.from_java_source(java_source or "")
    combined_preview = (java_source or "") + assembler.preamble
    if "final class CobolRecordRewrite" not in combined_preview:
        assembler.prepend_preamble(COBOL_RECORD_REWRITE_JAVA.strip())

    assembler.replace_inner_class(
        "LoanRecord",
        generate_loan_record_inner_class_java(layout, static_modifier="static "),
    )

    assembler.upsert_method("parseLoanRecord", generate_parse_loan_record_java(layout))
    assembler.upsert_method(
        "formatLoanRecord",
        generate_format_loan_record_java(layout, written),
    )

    notes.append("riskscor_rewrite_copy_then_modify_applied")
    notes.append(f"rewrite_fields={','.join(sorted(written))}")
    built = normalize_loan_record_field_refs(assembler.build(validate=False))
    # Reconcile may alias loan-file ``loanId`` → ``bctLoanId`` globally; LoanRecord
    # inner class keeps canonical ``loanId`` from LOAN-RECORD layout.
    built, alias_fixes = re.subn(r"\brec\.bctLoanId\b", "rec.loanId", built)
    if alias_fixes:
        notes.append(f"loan_record_parse_alias_fix={alias_fixes}")
    notes.append("loan_record_field_refs_normalized")
    built = _remove_dangling_field_duplicates(built)
    built, bct_fixes = _fix_bct_line_record_usage(built)
    if bct_fixes:
        notes.append(f"bctLine_record_usage_fix={bct_fixes}")
    return built, notes


def _fix_bct_line_record_usage(java_source: str) -> Tuple[str, int]:
    """
  Remove dead ``bctLine = new WsBctRecord()`` blocks — ``bctLine`` is a String
  buffer and top-level ``bct*`` fields are already populated above.
    """
    pattern = re.compile(
        r"(\s*)bctLine\s*=\s*new\s+WsBctRecord\s*\(\s*\)\s*;\s*\n"
        r"(?:\1\s*bctLine\.\w+\s*=\s*[^;]+;\s*\n)+",
        re.MULTILINE,
    )
    return pattern.subn(
        r"\1// bctLine: WsBctRecord copy removed (bctLine is String; fields set above)\n",
        java_source,
    )
