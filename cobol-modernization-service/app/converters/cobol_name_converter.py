"""Canonical COBOL → Java identifier conversion for the modernization pipeline."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import re

_EXPLICIT_TABLE_HEADER = (
    "| COBOL Name | Java Name | Java Type | Source |",
    "|---|---|---|---|",
)

PROGRAM_CLASS_MAP: Dict[str, str] = {
    "CALCFEE": "CalcFee",
    "CHKAML": "ChkAmlService",
    "LOANEVAL": "LoanevalApplication",
    "RECOVRY": "RecovryApplication",
    "RISKSCOR": "RiskscorApplication",
    "RPTMONTH": "RptmonthApplication",
}

SUB_PROGRAM_JAVA_CLASS_OVERRIDES: Dict[str, str] = {
    "CALCFEE": PROGRAM_CLASS_MAP["CALCFEE"],
    "CHKAML": PROGRAM_CLASS_MAP["CHKAML"],
}


def cobol_program_to_java_class(program_name: str) -> str:
    """Map COBOL PROGRAM-ID to the canonical Java public class name."""
    prog = str(program_name or "").strip().upper()
    if prog in PROGRAM_CLASS_MAP:
        return PROGRAM_CLASS_MAP[prog]
    return prog.capitalize() + "Application"


def fix_program_class_declaration(java_source: str, program_name: str) -> Tuple[str, bool]:
    """Rename ``public class`` to the canonical program class name when needed."""
    prog = str(program_name or "").strip().upper()
    if not prog:
        return java_source, False
    expected = cobol_program_to_java_class(prog)
    legacy = CobolNameConverter.to_java_class(prog)
    text = java_source or ""
    renamed = False
    match = re.search(
        r"^\s*public\s+(?:\w+\s+)*class\s+(\w+)\b",
        text,
        re.MULTILINE,
    )
    if match and match.group(1) != expected:
        from app.services.scope_safe_modifier import ScopeSafeSourceModifier

        old_name = match.group(1)
        mod = ScopeSafeSourceModifier(text)
        if mod.rename_class(old_name, expected) != 0:
            text = mod.serialize()
            renamed = True
            if old_name != expected:
                text = re.sub(
                    rf"\bnew\s+{re.escape(old_name)}\s*\(",
                    f"new {expected}(",
                    text,
                )
    if legacy and legacy != expected:
        new_text = re.sub(
            rf"\bnew\s+{re.escape(legacy)}\s*\(",
            f"new {expected}(",
            text,
        )
        if new_text != text:
            text = new_text
            renamed = True
    return text, renamed


class CobolNameConverter:
    """Single source of truth for COBOL name → Java identifier rules."""

    @staticmethod
    def to_java_field(cobol_name: str) -> str:
        """LOAN-STATUS → loanStatus, WS-CURRENT-IDX → wsCurrentIdx."""
        parts = cobol_name.lower().split("-")
        if not parts or not parts[0]:
            return ""
        return parts[0] + "".join(p.capitalize() for p in parts[1:])

    @staticmethod
    def to_java_class(cobol_name: str) -> str:
        """LOAN-RECORD → LoanRecord, CHKAML → Chkaml."""
        parts = cobol_name.lower().split("-")
        return "".join(p.capitalize() for p in parts if p)

    @staticmethod
    def to_java_method(cobol_paragraph: str) -> str:
        """1000-LOAD-CUSTOMER → loadCustomer, 0000-MAIN → main (strip leading digits)."""
        parts = [p for p in cobol_paragraph.split("-") if p]
        if parts and parts[0].isdigit():
            parts = parts[1:]
        if not parts:
            return ""
        return parts[0].lower() + "".join(p.capitalize() for p in parts[1:])

    @staticmethod
    def to_java_constant(cobol_value: str) -> str:
        """CLASS-1 → CLASS_1, AML-RESPONSE → AML_RESPONSE."""
        return cobol_value.upper().replace("-", "_")


def cobol_name_to_java(name: str) -> str:
    """Backward-compatible alias for :meth:`CobolNameConverter.to_java_field`."""
    return CobolNameConverter.to_java_field(name)


def paragraph_to_java_method(paragraph: str) -> str:
    """Backward-compatible alias for :meth:`CobolNameConverter.to_java_method`."""
    return CobolNameConverter.to_java_method(paragraph)


def to_java_class_name(cobol_name: str) -> str:
    """Backward-compatible alias for :meth:`CobolNameConverter.to_java_class`."""
    return CobolNameConverter.to_java_class(cobol_name)


def enrich_symbol_table_java_names(symbols: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach ``java_field``, ``java_name``, and 88-level ``java_constant`` to parser symbols."""
    for symbol in symbols:
        name = str(symbol.get("name") or "").strip()
        if not name:
            continue
        java_field = CobolNameConverter.to_java_field(name)
        symbol["java_field"] = java_field
        symbol["java_name"] = java_field
        for cond in symbol.get("condition_names") or []:
            if isinstance(cond, dict) and cond.get("name"):
                cond["java_constant"] = CobolNameConverter.to_java_constant(str(cond["name"]))
    return symbols


def build_paragraph_table(paragraphs: List[str]) -> List[Dict[str, str]]:
    """Build ``paragraph_table`` entries with COBOL and Java method names."""
    table: List[Dict[str, str]] = []
    seen: set[str] = set()
    for para in paragraphs:
        cobol = str(para or "").strip()
        if not cobol or cobol in seen:
            continue
        seen.add(cobol)
        table.append(
            {
                "cobol": cobol,
                "java_method": CobolNameConverter.to_java_method(cobol),
            }
        )
    return table


def java_symbol_table_for_prompt(parser_output: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compact symbol rows for the conversion LLM prompt (canonical Java names)."""
    from app.services.symbol_table import resolve_symbol_entries

    rows: List[Dict[str, Any]] = []
    for sym in resolve_symbol_entries(parser_output):
        if not isinstance(sym, dict):
            continue
        cobol = str(sym.get("name") or "").strip()
        if not cobol:
            continue
        row: Dict[str, Any] = {
            "cobol": cobol,
            "java": sym.get("java_field") or CobolNameConverter.to_java_field(cobol),
        }
        if sym.get("kind"):
            row["kind"] = sym["kind"]
        if sym.get("pic"):
            row["pic"] = sym["pic"]
        if sym.get("parent"):
            row["parent"] = sym["parent"]
        rows.append(row)
    return rows


def paragraph_table_for_prompt(parser_output: Dict[str, Any]) -> List[Dict[str, str]]:
    """Paragraph name map for the conversion LLM prompt."""
    table = parser_output.get("paragraph_table")
    if isinstance(table, list) and table:
        return [dict(entry) for entry in table if isinstance(entry, dict)]
    return build_paragraph_table(list(parser_output.get("paragraphs") or []))


def _escape_markdown_cell(text: str) -> str:
    return str(text or "").replace("|", "\\|")


def _symbol_source_label(sym: Dict[str, Any]) -> str:
    section = str(sym.get("section") or "").strip()
    if section:
        return section.replace(" SECTION", "").replace(" SECTION.", "").lower()
    parent = str(sym.get("parent") or "").strip()
    if parent:
        return f"under {parent}"
    return "data division"


def _symbol_java_type(sym: Dict[str, Any]) -> str:
    kind = str(sym.get("kind") or "").lower()
    if kind in {"condition_88", "condition"}:
        return "boolean (computed)"
    if kind == "index":
        return "int"
    decoded = sym.get("pic_decoded")
    if isinstance(decoded, dict):
        java_type = decoded.get("java_type")
        if java_type == "BigDecimal":
            return "BigDecimal"
        if java_type == "String":
            return "String"
        if java_type in ("int", "long", "Integer", "Long"):
            return "int" if java_type in ("int", "Integer") else "long"
    pic = str(sym.get("pic") or "").upper()
    if not pic:
        if kind == "group":
            return "class"
        return "Object"
    if pic.startswith(("X", "A")):
        return "String"
    if "V" in pic or "." in pic:
        return "BigDecimal"
    if "9" in pic:
        return "int"
    return "String"


def build_explicit_symbol_table_rows(
    parser_output: Dict[str, Any],
) -> List[Tuple[str, str, str, str]]:
    """
    Rows for the LLM symbol table: (cobol_name, java_name, java_type, source).
    """
    rows: List[Tuple[str, str, str, str]] = []
    seen: set[Tuple[str, str]] = set()

    def _add(cobol: str, java: str, java_type: str, source: str) -> None:
        key = (cobol.upper(), java)
        if not cobol or not java or key in seen:
            return
        seen.add(key)
        rows.append((cobol, java, java_type, source))

    from app.services.symbol_table import resolve_symbol_entries, resolve_symbol_table

    table = resolve_symbol_table(parser_output) if parser_output else None
    for sym in resolve_symbol_entries(parser_output or {}):
        if not isinstance(sym, dict):
            continue
        cobol = str(sym.get("name") or "").strip()
        if not cobol:
            continue
        level = int(sym.get("level") or 0)
        pic = sym.get("pic")

        if level == 1 and not pic:
            _add(
                cobol,
                CobolNameConverter.to_java_class(cobol),
                "class",
                "01-level record (use this type name)",
            )
            continue

        if pic and cobol != "FILLER":
            java = str(sym.get("java_field") or sym.get("java_name") or "")
            if not java:
                java = CobolNameConverter.to_java_field(cobol)
            _add(cobol, java, _symbol_java_type(sym), _symbol_source_label(sym))

        parent = cobol
        for cond in sym.get("condition_names") or []:
            if not isinstance(cond, dict):
                continue
            cond_name = str(cond.get("name") or "").strip()
            if not cond_name:
                continue
            java_const = str(cond.get("java_constant") or "")
            if not java_const:
                java_const = CobolNameConverter.to_java_constant(cond_name)
            _add(
                cond_name,
                java_const,
                "boolean (computed)",
                f"88-level on {parent}",
            )

    for entry in paragraph_table_for_prompt(parser_output):
        cobol_para = str(entry.get("cobol") or "").strip()
        java_method = str(entry.get("java_method") or "").strip()
        if cobol_para and java_method:
            _add(cobol_para, java_method, "private void method", "paragraph")

    program = str(parser_output.get("program_name") or "").strip()
    if program:
        _add(
            program,
            cobol_program_to_java_class(program),
            "class",
            "PROGRAM-ID (main class)",
        )
    _add(
        "LOAN-RECORD",
        "LoanRecord",
        "class",
        "LOANCOPY file record — use type name LoanRecord only",
    )

    if table is not None:
        for prog, sub in table.sub_programs.items():
            _add(prog, sub.java_field_name, sub.java_class, "CALL sub-program service field")
        for sel, fh in table.file_handles.items():
            _add(sel, fh.java_handle_name, fh.java_handle_type, "file I/O handle")

    rows.sort(key=lambda item: (item[3] != "paragraph", item[0]))
    return rows


def format_explicit_symbol_table_markdown(
    parser_output: Dict[str, Any],
    *,
    max_rows: int | None = 400,
) -> str:
    """Markdown table of COBOL symbols with explicit Java names for the conversion LLM."""
    rows = build_explicit_symbol_table_rows(parser_output)
    lines = list(_EXPLICIT_TABLE_HEADER)
    truncated = False
    if max_rows is not None and len(rows) > max_rows:
        rows = rows[:max_rows]
        truncated = True
    for cobol, java, java_type, source in rows:
        lines.append(
            f"| {_escape_markdown_cell(cobol)} | {_escape_markdown_cell(java)} | "
            f"{_escape_markdown_cell(java_type)} | {_escape_markdown_cell(source)} |"
        )
    if truncated:
        lines.append("")
        lines.append(
            f"(Table truncated to {max_rows} rows; use parser symbol_table for remaining names.)"
        )
    return "\n".join(lines)


def canonical_field_names(parser_output: Dict[str, Any] | None) -> set[str]:
    """All canonical Java field/constant identifiers from parser output."""
    from app.services.symbol_table import resolve_symbol_entries, resolve_symbol_table

    names: set[str] = set()
    if not parser_output:
        return names
    table = resolve_symbol_table(parser_output)
    if table.fields:
        names |= {f.java_name for f in table.fields.values()}
    for sym in resolve_symbol_entries(parser_output):
        if not isinstance(sym, dict):
            continue
        cobol = str(sym.get("name") or "").strip()
        if not cobol:
            continue
        if sym.get("pic") and cobol != "FILLER":
            names.add(str(sym.get("java_field") or CobolNameConverter.to_java_field(cobol)))
        for cond in sym.get("condition_names") or []:
            if isinstance(cond, dict) and cond.get("name"):
                names.add(
                    str(cond.get("java_constant"))
                    or CobolNameConverter.to_java_constant(str(cond["name"]))
                )
    return names


def canonical_method_names(parser_output: Dict[str, Any] | None) -> set[str]:
    names: set[str] = set()
    if not parser_output:
        return names
    for entry in paragraph_table_for_prompt(parser_output):
        method = str(entry.get("java_method") or "").strip()
        if method:
            names.add(method)
    return names


def canonical_record_class_names(parser_output: Dict[str, Any] | None) -> set[str]:
    """Preferred Java type names for COBOL 01-level records."""
    from app.services.symbol_table import resolve_symbol_entries, resolve_symbol_table

    names: set[str] = set()
    names.add("LoanRecord")
    if not parser_output:
        return names
    table = resolve_symbol_table(parser_output)
    if table.classes:
        names |= {c.java_name for c in table.classes.values()}
    for sym in resolve_symbol_entries(parser_output):
        if int(sym.get("level") or 0) == 1 and not sym.get("pic"):
            cobol = str(sym.get("name") or "").strip()
            if cobol:
                names.add(CobolNameConverter.to_java_class(cobol))
    return names
