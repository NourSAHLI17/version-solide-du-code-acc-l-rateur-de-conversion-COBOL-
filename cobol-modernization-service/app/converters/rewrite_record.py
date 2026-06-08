"""COBOL REWRITE: copy-then-modify record serialization (preserve unmodified bytes)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, List, Optional, Sequence, Set

from app.converters.cobol_name_converter import CobolNameConverter
from app.converters.record_layout import (
    FieldLayout,
    layout_as_dict,
    layout_from_copybook_path,
    parse_display_field,
    pic_display_byte_size,
    cobol_name_to_java,
)


def _decode_pic(pic_str: str) -> Dict[str, object]:
    """Delegate to ParserLayer._decode_pic via deferred import to avoid circular dependency."""
    from app.parsers.cobol_parser import ParserLayer

    return ParserLayer()._decode_pic(pic_str)


# File record fields RISKSCOR assigns before REWRITE LOAN-RECORD.
RISKSCOR_LOAN_WRITTEN_FIELDS = frozenset({
    "LOAN-CLASS",
    "LOAN-PROVISION-RATE",
    "LOAN-PROVISION-AMT",
})

# Legacy short names sometimes emitted by the LLM before canonical naming (F32).
LOAN_RECORD_FIELD_ALIASES: Dict[str, str] = {
    "custId": "loanCustId",
    "status": "loanStatus",
    "outstanding": "loanOutstanding",
    "daysPastDue": "loanDaysPastDue",
    "originalAmt": "loanOriginalAmt",
    "acctId": "loanAcctId",
    "provisionRate": "loanProvisionRate",
    "provisionAmt": "loanProvisionAmt",
    "classNum": "loanClass",
}


def detect_written_record_fields(
    operations: Sequence[Dict[str, object]],
    record_field_names: Iterable[str],
) -> Set[str]:
    """
    Detect elementary record fields written via MOVE (and similar) in procedure code.

    Only targets that match known layout names are returned.
    """

    names = {str(n).upper() for n in record_field_names}
    written: Set[str] = set()
    for op in operations:
        if str(op.get("type", "")).upper() != "MOVE":
            continue
        target = str(op.get("target", "")).upper()
        if target in names:
            written.add(target)
    return written


def detect_written_fields_from_source(
    source: str,
    record_field_names: Iterable[str],
) -> Set[str]:
    """Supplement parser operations with ``MOVE ... TO <field>`` lines in source."""

    names = {str(n).upper() for n in record_field_names}
    written: Set[str] = set()
    for match in re.finditer(
        r"\bMOVE\s+.+?\s+TO\s+([A-Z0-9-]+)\b",
        source.upper(),
    ):
        target = match.group(1)
        if target in names:
            written.add(target)
    return written


def collect_rewrite_targets(
    parser_output: Dict[str, object],
    source_code: str,
    layout: Sequence[FieldLayout],
    *,
    explicit: Optional[Set[str]] = None,
) -> Set[str]:
    """Union of parser MOVE targets, source MOVE scan, and optional explicit set."""

    field_names = {f.name for f in layout}
    ops = list(parser_output.get("operations") or [])
    written = detect_written_record_fields(ops, field_names)
    written |= detect_written_fields_from_source(source_code, field_names)
    if explicit:
        written |= {str(x).upper() for x in explicit}
    return written


def overwrite_chars(chars: List[str], start: int, end: int, value: str) -> None:
    """Overwrite ``chars[start:end]`` with ``value`` (truncate or right-pad with spaces)."""

    length = end - start
    if length <= 0:
        return
    text = value if len(value) >= length else value + (" " * (length - len(value)))
    text = text[:length]
    for idx, ch in enumerate(text):
        chars[start + idx] = ch


def format_display_value(value: object, pic: str) -> str:
    """Format a Java/COBOL value into DISPLAY characters for ``pic``."""

    size = pic_display_byte_size(pic)
    pic_u = pic.upper().strip()

    if pic_u.startswith("X") or pic_u.startswith("A"):
        return str(value)[:size].ljust(size)[:size]

    decoded = _decode_pic(pic_u)
    int_digits = int(decoded.get("int_digits") or 0)
    dec_digits = int(decoded.get("dec_digits") or 0)

    try:
        if isinstance(value, (int, float)):
            number = Decimal(str(value))
        else:
            number = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return "0" * size

    if dec_digits > 0:
        quant = Decimal(10) ** -dec_digits
        number = number.quantize(quant)
        sign = "-" if number < 0 else ""
        number = abs(number)
        digits = f"{number:f}".replace(".", "")
        digits = digits.zfill(int_digits + dec_digits)
        digits = digits[-(int_digits + dec_digits) :]
        return (sign + digits)[-size:].rjust(size, "0")[-size:]

    digits = str(int(number))
    if int_digits > 0:
        digits = digits.zfill(int_digits)[-int_digits:]
    return digits[-size:].rjust(size, "0")[-size:]


def format_record_rewrite(
    raw_line: str,
    layout: Sequence[FieldLayout],
    field_values: Dict[str, object],
    *,
    written_fields: Optional[Set[str]] = None,
) -> str:
    """
    Build REWRITE output from ``raw_line``, overwriting only ``written_fields``.

    Args:
        raw_line: Original record image (e.g. 238 bytes for LOAN-RECORD).
        layout: Elementary field layout for the record.
        field_values: COBOL field name → new value (only written keys are applied).
        written_fields: Subset to overwrite; defaults to all keys in ``field_values``.
    """

    total = sum(f.length for f in layout)
    chars = list(raw_line.ljust(total)[:total])
    by_name = layout_as_dict(layout)
    targets = {str(n).upper() for n in (written_fields or field_values.keys())}

    for name in targets:
        if name not in field_values or name not in by_name:
            continue
        field = by_name[name]
        formatted = format_display_value(field_values[name], field.pic)
        overwrite_chars(chars, field.offset, field.end, formatted)

    return "".join(chars)


def generate_parse_loan_record_java(
    layout: Sequence[FieldLayout],
    *,
    class_name: str = "LoanRecord",
    record_length: int = 238,
) -> str:
    """Generate ``parseLoanRecord`` with ``rawLine`` preservation."""

    lines: List[str] = [
        f"    private {class_name} parseLoanRecord(String line) {{",
        f"        {class_name} rec = new {class_name}();",
        f"        rec.rawLine = line.length() >= {record_length}",
        f"            ? line.substring(0, {record_length})",
        f"            : String.format(\"%-{record_length}s\", line);",
    ]
    for field in layout:
        if field.name == "FILLER":
            continue
        prop = cobol_name_to_java(field.name)
        if _is_numeric_pic(field.pic):
            lines.append(
                f"        rec.{prop} = CobolRecordRewrite.parseDisplayDecimal(line, "
                f"{field.offset}, {field.end}, \"{field.pic}\");"
            )
        else:
            lines.append(
                f"        rec.{prop} = CobolRecordRewrite.parseString(line, "
                f"{field.offset}, {field.end});"
            )
    lines.extend(["        return rec;", "    }"])
    return "\n".join(lines)


def generate_format_loan_record_java(
    layout: Sequence[FieldLayout],
    written_fields: Set[str],
    *,
    class_name: str = "LoanRecord",
) -> str:
    """Generate copy-then-modify ``formatLoanRecord`` for REWRITE."""

    by_name = layout_as_dict(layout)
    lines: List[str] = [
        f"    private String formatLoanRecord({class_name} rec) {{",
        "        char[] chars = rec.rawLine.toCharArray();",
    ]
    for name in sorted(written_fields):
        field = by_name.get(name)
        if not field:
            continue
        prop = cobol_name_to_java(field.name)
        if _is_numeric_pic(field.pic):
            decoded = _decode_pic(field.pic)
            int_d = int(decoded.get("int_digits") or 0)
            dec_d = int(decoded.get("dec_digits") or 0)
            lines.append(
                f"        CobolRecordRewrite.overwrite(chars, {field.offset}, {field.end}, "
                f"CobolRecordRewrite.formatDecimal(rec.{prop}, {int_d}, {dec_d}));"
            )
        else:
            lines.append(
                f"        CobolRecordRewrite.overwrite(chars, {field.offset}, {field.end}, "
                f"CobolRecordRewrite.formatDisplayString(rec.{prop}, {field.length}));"
            )
    lines.extend(["        return new String(chars);", "    }"])
    return "\n".join(lines)


def _is_numeric_pic(pic: str) -> bool:
    p = pic.upper()
    return "9" in p or p.startswith("S") or "V" in p


def _java_type_for_pic(pic: str) -> str:
    if _is_numeric_pic(pic):
        return "BigDecimal"
    return "String"


def generate_loan_record_inner_class_java(
    layout: Sequence[FieldLayout],
    *,
    class_name: str = "LoanRecord",
    static_modifier: str = "static ",
) -> str:
    """Emit inner ``LoanRecord`` fields aligned with ``parseLoanRecord`` / ``formatLoanRecord``."""
    lines: List[str] = [f"{static_modifier}class {class_name} {{"]
    lines.append("        String rawLine;")
    for field in layout:
        if field.name == "FILLER":
            continue
        prop = cobol_name_to_java(field.name)
        jtype = _java_type_for_pic(field.pic)
        lines.append(f"        {jtype} {prop};")
    lines.append("")
    lines.append("        boolean isActive() {")
    lines.append('            return "AC".equals(loanStatus);')
    lines.append("        }")
    lines.append("")
    lines.append("        boolean isRestructured() {")
    lines.append('            return "RS".equals(loanStatus);')
    lines.append("        }")
    lines.append("    }")
    return "\n".join(lines)


def normalize_loan_record_field_refs(java_source: str) -> str:
    """Rewrite legacy ``LoanRecord`` field spellings to canonical ``java_field`` names."""
    from app.services.java_name_reconciler import reconcile_names

    text, _notes = reconcile_names(java_source, symbol_table=None)
    return text


def canonical_loan_record_java_fields(layout: Sequence[FieldLayout]) -> Set[str]:
    """Java field names for LOAN-RECORD (excluding FILLER), plus ``rawLine``."""
    names = {"rawLine"}
    for field in layout:
        if field.name != "FILLER":
            names.add(CobolNameConverter.to_java_field(field.name))
    return names


def layout_for_loan_record(copybook_path: Optional[str] = None) -> List[FieldLayout]:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    path = Path(copybook_path) if copybook_path else root.parent / "acme-bank-v3" / "copybooks" / "LOANCOPY.cpy"
    return layout_from_copybook_path(path)
