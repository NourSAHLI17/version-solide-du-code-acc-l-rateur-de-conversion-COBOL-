"""Fixed-format COBOL paragraph body extraction (Area A / column 7 rules).

Skips sequence area (1–6), honors indicator in column 7 (* / comment),
and treats paragraph headers as Area A tokens ending with `.`
"""

from __future__ import annotations

import re
from typing import Dict, List, Set


def extract_paragraph_bodies(source_code: str, paragraph_names: List[str]) -> Dict[str, List[str]]:
    """
    Map each paragraph name to its body lines (logical lines after Area B join of continuations).

    Rules:
    - Skip line if fixed-format col 7 is ``*`` or ``/`` (comment or page eject).
    - Strip cols 1–6 when detecting fixed format (6-digit sequence optional).
    - Paragraph header: token in ``paragraph_names`` ending with ``.`` in Area A.
    - Continuation: col 7 ``-`` joins to previous line (Area B text).
    """
    names_upper: Set[str] = {p.upper() for p in paragraph_names}
    para_map: Dict[str, List[str]] = {p: [] for p in paragraph_names}
    current: str | None = None
    buffer: List[str] = []
    current_line: str | None = None

    def flush_buffer() -> None:
        nonlocal buffer, current_line
        if current and buffer:
            para_map.setdefault(current, []).extend(buffer)
        buffer = []
        current_line = None

    lines = source_code.splitlines()
    fixed_like = sum(1 for ln in lines if len(ln) >= 7 and re.fullmatch(r"[ 0-9]{6}", ln[:6])) >= max(1, len(lines) // 4)

    for raw in lines:
        line = raw.rstrip("\n\r")
        if not line.strip():
            continue

        if fixed_like and len(line) >= 7:
            indicator = line[6]
            # Columns 8-72 only; 73-80 identification area is ignored.
            body = line[7:72]
        else:
            stripped = line.lstrip()
            if stripped.startswith("*") or stripped.startswith("*>"):
                continue
            indicator = ""
            body = re.sub(r"\s+", " ", line.replace("\t", " ")).strip()
            if not body:
                continue

        if indicator in {"*", "/"}:
            continue

        normalized = re.sub(r"\s+", " ", body.replace("\t", " ")).strip()
        if not normalized:
            continue

        if fixed_like and indicator == "-" and current_line is not None:
            current_line = f"{current_line} {normalized}".strip()
            if buffer:
                buffer[-1] = current_line
            continue

        # Paragraph header: AREA A — first word + optional rest, ends with .
        para_token = normalized[:-1].strip() if normalized.endswith(".") else None
        if (
            para_token
            and para_token.upper() in names_upper
            and (
                not fixed_like
                or (len(line) >= 8 and len(line) - len(line.lstrip()) <= 10)
            )
        ):
            flush_buffer()
            current = para_token.upper()
            current_line = None
            buffer = []
            continue

        if current:
            current_line = normalized
            buffer.append(normalized)

    flush_buffer()
    return para_map
