"""Deterministic COBOL DISPLAY → System.out.println repair for converted Java."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from app.converters.cobol_name_converter import CobolNameConverter, paragraph_to_java_method
from app.converters.java_class_builder import JavaFileAssembler, _find_matching_brace
from app.converters.rewrite_record import _decode_pic
from app.services.cobol_java_runtime import COBOL_RECORD_REWRITE_JAVA
from app.services.symbol_table import SymbolTable, resolve_symbol_entries, resolve_symbol_table

_DISPLAY_TOKEN_RE = re.compile(
    r"'([^']*)'|\"([^\"]*)\"|([A-Z][A-Z0-9-]*(?:\([A-Z0-9-]+\))?)",
    re.IGNORECASE,
)
_WITH_NO_ADVANCING_RE = re.compile(r"\s+WITH\s+NO\s+ADVANCING\s*$", re.IGNORECASE)
_PRINTLN_RE = re.compile(r"System\.out\.println\s*\(")
_TODO_DISPLAY_RE = re.compile(
    r"//\s*(?:Original:\s*)?(?:.*)?DISPLAY\s+(.*?)(?:\s+WITH\s+NO\s+ADVANCING)?$",
    re.IGNORECASE,
)
_ABEND_MARKERS = ("ABEND", "FAILED", "FAIL ")


def _normalize_cobol(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (name or "").upper())


def _build_field_lookup(
    parser_output: Mapping[str, Any] | None,
    symbol_table: SymbolTable | None,
) -> Dict[str, Dict[str, str]]:
    """Map normalized COBOL field name → {java, pic, java_type}."""
    lookup: Dict[str, Dict[str, str]] = {}

    table = symbol_table or resolve_symbol_table(parser_output or {})
    for entry in table.fields.values():
        lookup[_normalize_cobol(entry.cobol_name)] = {
            "java": entry.java_name,
            "pic": entry.pic_clause or "",
            "java_type": entry.java_type or "String",
        }

    for sym in resolve_symbol_entries(parser_output or {}):
        if not isinstance(sym, dict):
            continue
        cobol = str(sym.get("name") or "").strip()
        if not cobol or cobol == "FILLER" or not sym.get("pic"):
            continue
        key = _normalize_cobol(cobol)
        lookup[key] = {
            "java": str(
                sym.get("java_field") or sym.get("java_name")
                or CobolNameConverter.to_java_field(cobol)
            ),
            "pic": str(sym.get("pic") or ""),
            "java_type": str(
                (sym.get("pic_decoded") or {}).get("java_type")
                or _java_type_from_pic(str(sym.get("pic") or ""))
            ),
        }
    return lookup


def _java_type_from_pic(pic: str) -> str:
    pic_u = pic.upper()
    if pic_u.startswith(("X", "A")):
        return "String"
    if "V" in pic_u or "." in pic_u:
        return "BigDecimal"
    if "9" in pic_u:
        return "int"
    return "String"


def _resolve_java_ref(cobol_ref: str, field_lookup: Mapping[str, Dict[str, str]]) -> Tuple[str, str, str]:
    """Return (java_expr, pic, java_type) for a COBOL identifier token."""
    base = cobol_ref.split("(", 1)[0].strip()
    key = _normalize_cobol(base)
    entry = field_lookup.get(key)
    if entry:
        return entry["java"], entry.get("pic", ""), entry.get("java_type", "String")

    java = CobolNameConverter.to_java_field(base)
    return java, "", "String"


def _format_java_display_expr(java_expr: str, pic: str, java_type: str) -> str:
    if java_type == "String":
        return java_expr
    if not pic:
        return java_expr

    decoded = _decode_pic(pic.upper())
    int_digits = int(decoded.get("int_digits") or 0)
    dec_digits = int(decoded.get("dec_digits") or 0)

    if java_type == "BigDecimal" or dec_digits > 0:
        if int_digits <= 0:
            int_digits = pic_display_digits(pic) - dec_digits
        return f"CobolRecordRewrite.formatDecimal({java_expr}, {int_digits}, {dec_digits})"

    if int_digits <= 0:
        int_digits = pic_display_digits(pic)
    if int_digits > 0:
        return f'String.format("%0{int_digits}d", {java_expr})'
    return java_expr


def pic_display_digits(pic: str) -> int:
    """Count 9 digit positions in a PIC clause (integer + decimal parts)."""
    pic_u = pic.upper()
    total = 0
    for m in re.finditer(r"9(?:\((\d+)\))?", pic_u):
        total += int(m.group(1) or 1)
    return total


def convert_display_to_println(
    display_content: str,
    field_lookup: Mapping[str, Dict[str, str]],
    *,
    indent: str = "        ",
    field_prefix: str = "",
) -> str:
    """Convert one COBOL DISPLAY operand list to System.out.println(...)."""
    content = _WITH_NO_ADVANCING_RE.sub("", (display_content or "").strip())
    parts: List[str] = []
    for m in _DISPLAY_TOKEN_RE.finditer(content):
        lit = m.group(1)
        if lit is not None:
            parts.append(f'"{lit}"')
            continue
        lit2 = m.group(2)
        if lit2 is not None:
            parts.append(f'"{lit2}"')
            continue
        ref = m.group(3)
        if not ref:
            continue
        java_expr, pic, java_type = _resolve_java_ref(ref, field_lookup)
        if field_prefix and not java_expr.startswith(field_prefix):
            java_expr = f"{field_prefix}{java_expr}"
        parts.append(_format_java_display_expr(java_expr, pic, java_type))

    if not parts:
        return f'{indent}// DISPLAY skipped (empty): {display_content!r}'
    if len(parts) == 1:
        return f"{indent}System.out.println({parts[0]});"
    expr = " + ".join(parts)
    return f"{indent}System.out.println({expr});"


def convert_display_statements(
    method_body: str,
    field_lookup: Mapping[str, Dict[str, str]],
    *,
    indent: str = "        ",
) -> str:
    """Convert remaining COBOL DISPLAY TODO comments to println."""
    lines = method_body.split("\n")
    result: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("// Original:") and "DISPLAY" in stripped.upper():
            display_match = re.search(
                r"DISPLAY\s+(.*?)(?:\s+WITH\s+NO\s+ADVANCING)?$",
                stripped,
                re.IGNORECASE,
            )
            if display_match:
                result.append(
                    convert_display_to_println(
                        display_match.group(1).strip(),
                        field_lookup,
                        indent=indent,
                    )
                )
                continue
        if "// TODO" in line and "DISPLAY" in line.upper():
            display_match = _TODO_DISPLAY_RE.search(line.strip())
            if display_match:
                java_print = convert_display_to_println(
                    display_match.group(1).strip(),
                    field_lookup,
                    indent=indent,
                )
                result.append(java_print)
                continue
        if line.strip().startswith("// Original:") and "System.out.println" in line:
            orig = line.split("System.out.println", 1)[-1].strip()
            if orig.startswith("("):
                restored = f"{indent}System.out.println{orig}"
                if not restored.rstrip().endswith(";"):
                    restored += ";"
                result.append(restored)
                continue
        result.append(line)
    return "\n".join(result)


def _collect_display_ops(parser_output: Mapping[str, Any] | None) -> List[Dict[str, Any]]:
    ops: List[Dict[str, Any]] = []
    for op in (parser_output or {}).get("operations") or []:
        if isinstance(op, dict) and op.get("type") == "DISPLAY":
            ops.append(op)
    return ops


def _display_category(display_value: str) -> str:
    upper = (display_value or "").upper()
    if " START " in f" {upper} " or upper.endswith(" START") or "START " in upper[:40]:
        return "start"
    if any(marker in upper for marker in _ABEND_MARKERS):
        return "abend"
    return "normal"


def _paragraph_to_method(paragraph: str, parser_output: Mapping[str, Any] | None) -> str:
    table = parser_output.get("paragraph_table") if parser_output else None
    if isinstance(table, list):
        for entry in table:
            if isinstance(entry, dict) and str(entry.get("cobol") or "").upper() == paragraph.upper():
                method = str(entry.get("java_method") or "").strip()
                if method:
                    return method
    return paragraph_to_java_method(paragraph)


def _method_body_without_comments(method_source: str) -> str:
    """Strip block and line comments before checking for existing DISPLAY output."""
    text = method_source or ""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//.*", "", text)
    return text


def _method_has_display_output(method_source: str, display_value: str) -> bool:
    body = _method_body_without_comments(method_source)
    if not _PRINTLN_RE.search(body):
        return False
    for lit in re.findall(r"'([^']*)'", display_value or ""):
        if lit and lit in body:
            return True
    return False


def _field_prefix_for_method(method_source: str) -> str:
    header = method_source.split("{", 1)[0]
    if "static" not in header:
        return ""
    match = re.search(r"(\w+)\s*=\s*new\s+\w+", method_source)
    if match:
        return f"{match.group(1)}."
    return ""


def _inject_after_anchor(
    method_source: str,
    anchor_pattern: str,
    insert_lines: Sequence[str],
) -> str:
    block = "\n".join(insert_lines)
    if not block.strip() or block.strip() in method_source:
        return method_source
    match = re.search(anchor_pattern, method_source)
    if not match:
        return method_source
    insert_at = match.end()
    return method_source[:insert_at] + "\n" + block + method_source[insert_at:]


def _inject_lines_after_open(method_source: str, insert_lines: Sequence[str]) -> str:
    open_brace = method_source.find("{")
    if open_brace < 0:
        return method_source
    close_brace = _find_matching_brace(method_source, open_brace)
    if close_brace < 0:
        return method_source
    body = method_source[open_brace + 1 : close_brace]
    block = "\n".join(insert_lines)
    if block.strip() and block.strip() in body:
        return method_source
    new_body = block + ("\n" if block else "") + body
    return method_source[: open_brace + 1] + new_body + method_source[close_brace:]


def _resolve_method_for_paragraph(
    assembler: JavaFileAssembler,
    paragraph: str,
    mapped_name: str,
) -> Any | None:
    """Pick the Java method that hosts a COBOL paragraph's DISPLAY output."""
    methods = assembler.primary.methods
    para = (paragraph or "").upper()

    if para in {"0000-MAIN", "MAIN"}:
        for preferred in ("run", "main"):
            target = next(
                (
                    m
                    for m in methods
                    if m.name == preferred and "static" not in m.source.split("(", 1)[0]
                ),
                None,
            )
            if target is not None:
                return target
        static_main = next(
            (m for m in methods if re.search(r"\bstatic\s+void\s+main\s*\(", m.source)),
            None,
        )
        if static_main is not None:
            return static_main

    target = next((m for m in methods if m.name == mapped_name), None)
    if target is None and mapped_name == "main":
        target = next((m for m in methods if m.name == "run"), None)
    if target is None and mapped_name == "run":
        target = next(
            (m for m in methods if m.name == "main" and "static" not in m.source.split("(", 1)[0]),
            None,
        )
    return target


def _inject_lines_before_final_return(method_source: str, insert_lines: Sequence[str]) -> str:
    open_brace = method_source.find("{")
    if open_brace < 0:
        return method_source
    close_brace = _find_matching_brace(method_source, open_brace)
    if close_brace < 0:
        return method_source
    body = method_source[open_brace + 1 : close_brace]
    block = "\n".join(insert_lines)
    if block.strip() and block.strip() in body:
        return method_source

    lines = body.split("\n")
    insert_at = len(lines)
    depth = 0
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if depth == 1 and (stripped == "return;" or stripped.startswith("return ")):
            insert_at = idx
        for ch in line:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
    new_lines = lines[:insert_at] + list(insert_lines) + lines[insert_at:]
    new_body = "\n".join(new_lines)
    return method_source[: open_brace + 1] + new_body + method_source[close_brace:]


def _inject_abend_displays(method_source: str, abend_lines: Sequence[str]) -> str:
    if not abend_lines:
        return method_source
    block = "\n".join(abend_lines)
    if block.strip() in method_source:
        return method_source

    pattern = re.compile(
        r"(if\s*\(\s*wsReturnCode\s*!=\s*0\s*\)\s*\{)(.*?)(return\s*;)",
        re.DOTALL,
    )

    def _repl(match: re.Match[str]) -> str:
        inner = match.group(2)
        if any(line.strip() in inner for line in abend_lines):
            return match.group(0)
        return f"{match.group(1)}{inner}{block}\n{match.group(3)}"

    updated, n = pattern.subn(_repl, method_source, count=1)
    if n:
        return updated
    return method_source


def repair_display_java(
    java_source: str,
    *,
    parser_output: dict | None = None,
    symbol_table: SymbolTable | None = None,
    cobol_source: str | None = None,
) -> Tuple[str, List[str]]:
    """
    Inject System.out.println for COBOL DISPLAY operations missing from converted Java.
    """
    del cobol_source  # reserved for future paragraph-body ordering
    notes: List[str] = []
    display_ops = _collect_display_ops(parser_output)
    if not display_ops:
        return java_source, notes

    field_lookup = _build_field_lookup(parser_output, symbol_table)
    assembler = JavaFileAssembler.from_java_source(java_source or "")

    by_paragraph: Dict[str, List[Dict[str, Any]]] = {}
    for op in display_ops:
        para = str(op.get("paragraph") or "0000-MAIN").strip()
        by_paragraph.setdefault(para.upper(), []).append(op)

    injected_methods = 0
    injected_lines = 0

    result = java_source or ""
    replacements: List[Tuple[str, str]] = []

    for para, ops in by_paragraph.items():
        method_name = _paragraph_to_method(para, parser_output)
        target = _resolve_method_for_paragraph(assembler, para, method_name)
        if target is None:
            continue

        missing_ops = [
            op for op in ops
            if not _method_has_display_output(target.source, str(op.get("value") or ""))
        ]
        if not missing_ops:
            continue

        start_lines: List[str] = []
        abend_lines: List[str] = []
        normal_lines: List[str] = []
        prefix = _field_prefix_for_method(target.source)
        for op in missing_ops:
            line = convert_display_to_println(
                str(op.get("value") or ""), field_lookup, field_prefix=prefix,
            )
            cat = _display_category(str(op.get("value") or ""))
            if cat == "start":
                start_lines.append(line)
            elif cat == "abend":
                abend_lines.append(line)
            else:
                normal_lines.append(line)

        updated = target.source
        if start_lines:
            updated = _inject_lines_after_open(updated, start_lines)
            injected_lines += len(start_lines)
        if abend_lines:
            updated = _inject_abend_displays(updated, abend_lines)
            injected_lines += len(abend_lines)
        if normal_lines:
            anchored = _inject_after_anchor(
                updated,
                r"(?:\.\s*)?closeFiles\s*\(\s*\)\s*;",
                normal_lines,
            )
            if anchored != updated:
                updated = anchored
            else:
                updated = _inject_lines_before_final_return(updated, normal_lines)
            injected_lines += len(normal_lines)

        if updated != target.source:
            replacements.append((target.source, updated))
            injected_methods += 1

    for old_source, new_source in replacements:
        if old_source in result:
            result = result.replace(old_source, new_source, 1)
    if injected_methods:
        notes.append(f"display_injected:{injected_methods} methods/{injected_lines} lines")

    if (
        "CobolRecordRewrite." in result
        and "final class CobolRecordRewrite" not in result
    ):
        runtime = COBOL_RECORD_REWRITE_JAVA.strip()
        class_match = re.search(r"\bpublic\s+(?:final\s+)?class\s+", result)
        if class_match:
            insert_at = class_match.start()
            result = result[:insert_at] + runtime + "\n\n" + result[insert_at:]
        else:
            result = runtime + "\n\n" + result
        notes.append("display_runtime:CobolRecordRewrite")

    return result, notes
