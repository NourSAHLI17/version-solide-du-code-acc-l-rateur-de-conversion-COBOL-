"""COBOL DISPLAY record layout: PIC byte sizes and cumulative field offsets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

# Elementary PIC patterns (DISPLAY usage — byte = character position).
_PIC_CHAR = re.compile(r"([9XZA])\((\d+)\)|([9XZA])(?!\()")
_LITERAL_EDIT = re.compile(r"[.,+\-$*/]")


@dataclass(frozen=True)
class FieldLayout:
    """One elementary item in a COBOL record (DISPLAY storage)."""

    name: str
    offset: int
    length: int
    pic: str

    @property
    def end(self) -> int:
        return self.offset + self.length


def pic_display_byte_size(pic: str) -> int:
    """
    Return DISPLAY storage length for a PIC clause (one byte per character position).

    Rules:
    - ``PIC X(n)`` / ``9(n)`` / ``A(n)`` / ``Z(n)`` → n (or sum of repeats)
    - ``PIC 9(n)V9(m)`` → n + m (``V`` is implicit decimal, 0 bytes)
    - ``PIC S9(n)`` → n (``S`` is implicit sign in DISPLAY, 0 bytes)
    - Edited pictures ``ZZ,ZZ9`` → count each ``Z``, ``9``, and literal edit char (``,``)
    """

    if not pic or not str(pic).strip():
        return 0

    text = str(pic).upper().strip()

    # PIC V9(n) — decimal extension only
    if text.startswith("V"):
        dec = _count_nine_positions(text[1:])
        return dec if dec > 0 else max(1, len(text) - 1)

    total = 0
    idx = 0
    while idx < len(text):
        ch = text[idx]
        if ch == "S" and (idx == 0 or not text[idx - 1].isalnum()):
            idx += 1
            continue
        if ch == "V":
            idx += 1
            continue
        m = _PIC_CHAR.match(text, idx)
        if m:
            if m.group(2):
                total += int(m.group(2))
            else:
                total += 1
            idx = m.end()
            continue
        if _LITERAL_EDIT.match(text, idx):
            total += 1
            idx += 1
            continue
        idx += 1

    return total


def _count_nine_positions(segment: str) -> int:
    total = 0
    pos = 0
    while pos < len(segment):
        m = _PIC_CHAR.match(segment, pos)
        if not m:
            break
        total += int(m.group(2)) if m.group(2) else 1
        pos = m.end()
    return total


def build_record_layout(
    symbols: Sequence[Dict[str, object]],
    record_name: str = "LOAN-RECORD",
) -> List[FieldLayout]:
    """
    Walk elementary items under a 01-level record in declaration order.

    - Cumulative offsets (each field starts where the previous ended)
    - GROUP items (no PIC) occupy no storage
    - FILLER with PIC occupies space but is included in the layout list
    - Level-88 condition names are skipped
    """

    layouts: List[FieldLayout] = []
    offset = 0
    in_record = False

    for sym in symbols:
        name = str(sym.get("name", ""))
        level = int(sym.get("level", 0))

        if level == 1 and name == record_name:
            in_record = True
            continue

        if not in_record:
            continue

        if level == 1:
            break

        if level == 88:
            continue

        pic = sym.get("pic")
        if not pic:
            pic_decoded = sym.get("pic_decoded")
            if isinstance(pic_decoded, dict):
                pic = pic_decoded.get("raw")
        if not pic:
            continue

        size = pic_display_byte_size(str(pic))
        layouts.append(
            FieldLayout(name=name, offset=offset, length=size, pic=str(pic)),
        )
        offset += size

    return layouts


def layout_from_copybook_path(
    copybook_path: str | Path,
    record_name: str = "LOAN-RECORD",
) -> List[FieldLayout]:
    """Parse a ``.cpy`` file and return DISPLAY layouts for the named 01 record."""

    from app.parsers.cobol_parser import ParserLayer

    text = Path(copybook_path).read_text(encoding="utf-8", errors="replace")
    wrapped = (
        "IDENTIFICATION DIVISION.\n"
        "PROGRAM-ID. REC-LAYOUT.\n"
        "DATA DIVISION.\n"
        "WORKING-STORAGE SECTION.\n"
        f"{text}\n"
        "PROCEDURE DIVISION.\n"
        "STOP RUN.\n"
    )
    parser = ParserLayer()
    # Copybooks are column-aligned source without sequence numbers — use free-format
    # preprocessing so division/section lines are not truncated at column 72.
    lines = parser._preprocess(wrapped, "free")
    symbols = parser._extract_symbol_table(lines)
    return build_record_layout(symbols, record_name=record_name)


def layout_as_dict(layout: Sequence[FieldLayout]) -> Dict[str, FieldLayout]:
    return {field.name: field for field in layout}


def parse_display_field(line: str, field: FieldLayout) -> str:
    """Slice a fixed-format record line (0-based offsets)."""

    end = min(field.end, len(line))
    if field.offset >= len(line):
        return ""
    return line[field.offset:end]


def generate_parse_field_java(
    record_var: str,
    line_var: str,
    field: FieldLayout,
    *,
    java_name: Optional[str] = None,
) -> str:
    """Generate ``rec.field = parseString(line, start, end);`` for one elementary item."""

    prop = java_name or cobol_name_to_java(field.name)
    return (
        f"{record_var}.{prop} = parseString({line_var}, {field.offset}, {field.end});"
    )


def cobol_name_to_java(name: str) -> str:
    from app.converters.cobol_name_converter import CobolNameConverter

    return CobolNameConverter.to_java_field(name)


def _cobol_name_to_java(name: str) -> str:
    return cobol_name_to_java(name)
