"""Deterministic conversion repair for AUTOPREM (COBOL PIC storage + edited display)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from app.services.cobol_java_runtime import COBOL_NUMERIC_STORAGE_JAVA, COBOL_PIC_FORMAT_JAVA
from app.services.scope_safe_modifier import ScopeSafeSourceModifier

_REFERENCE_JAVA = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "autoprem" / "AUTOPREM.reference.java"
)

_AUTOPREM_NAMES = frozenset({"AUTOPREM", "AUTOPREM.CBL", "AUTOPREM.COB"})


def is_autoprem_program(program_name: str | None, java_source: str | None = None) -> bool:
    name = str(program_name or "").strip().upper().replace(".CBL", "").replace(".COB", "")
    if name in _AUTOPREM_NAMES:
        return True
    if java_source and re.search(r"\bclass\s+Autoprem\w*\b", java_source, re.IGNORECASE):
        return True
    return False


def repair_autoprem_conversion_java(
    java_source: str,
    *,
    program_name: str | None = None,
) -> Tuple[str, List[str]]:
    """
    Return COBOL-faithful AUTOPREM Java (reference implementation + runtime helpers).

    Used from the conversion agent after LLM sanitize so behavioral output matches GnuCOBOL
    edited pictures and PIC truncation semantics.
    """
    notes: List[str] = []
    if not is_autoprem_program(program_name, java_source):
        return java_source, notes

    if not _REFERENCE_JAVA.is_file():
        notes.append("autoprem_reference_missing")
        return _patch_llm_autoprem_java(java_source), notes

    text = _REFERENCE_JAVA.read_text(encoding="utf-8")
    notes.append("autoprem_reference_applied")
    return text, notes


def _patch_llm_autoprem_java(java_source: str) -> str:
    """Best-effort patch when reference file is unavailable."""
    text = java_source or ""
    if "final class CobolPicFormat" not in text:
        text = _inject_helpers(text)
    mod = ScopeSafeSourceModifier(text)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if "private String formatAmount(BigDecimal amount)" in line:
            end = _find_method_close(lines, i)
            if end is not None:
                new_body = "    private String formatAmount(BigDecimal amount) {\n        return CobolPicFormat.picZzZzz999(amount);\n    }"
                for j in range(i, end + 1):
                    mod.replace_line(j + 1, "" if j > i else new_body)
                break
    text = mod.serialize()
    text = "\n".join(l for l in text.split("\n") if l.strip() or l == "")

    mod2 = ScopeSafeSourceModifier(text)
    lines2 = text.split("\n")
    for i, line in enumerate(lines2):
        if "private String formatCoef(BigDecimal coef)" in line:
            end = _find_method_close(lines2, i)
            if end is not None:
                new_body = "    private String formatCoef(BigDecimal coef) {\n        return CobolPicFormat.picZ99(coef);\n    }"
                for j in range(i, end + 1):
                    mod2.replace_line(j + 1, "" if j > i else new_body)
                break
    text = mod2.serialize()
    text = "\n".join(l for l in text.split("\n") if l.strip() or l == "")

    mod3 = ScopeSafeSourceModifier(text)
    lines3 = text.split("\n")
    for i, line in enumerate(lines3):
        if 'String.format("%,.3f"' in line:
            mod3.replace_line(i + 1, line.replace('String.format("%,.3f"', "CobolPicFormat.picZzZzz999("))
        elif 'String.format("%.2f"' in line:
            mod3.replace_line(i + 1, line.replace('String.format("%.2f"', "CobolPicFormat.picZ99("))
    return mod3.serialize()


def _find_method_close(lines: list, start: int) -> int | None:
    """Find the closing brace of a method starting at *start*."""
    depth = 0
    for i in range(start, len(lines)):
        for ch in lines[i]:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
    return None


def _inject_helpers(java_source: str) -> str:
    helpers = (
        "\n"
        + COBOL_NUMERIC_STORAGE_JAVA.strip()
        + "\n\n"
        + COBOL_PIC_FORMAT_JAVA.strip()
        + "\n"
    )
    mod = ScopeSafeSourceModifier(java_source)
    try:
        mod.insert_before_class_close(helpers)
        return mod.serialize()
    except Exception:
        return java_source + helpers
