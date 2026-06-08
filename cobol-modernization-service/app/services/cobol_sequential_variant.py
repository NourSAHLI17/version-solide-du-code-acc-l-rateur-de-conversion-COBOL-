"""Create SEQUENTIAL-organized COBOL variants for GnuCOBOL baseline testing.

Production mainframe programs use ``ORGANIZATION IS INDEXED`` with flat
``.dat`` fixtures; GnuCOBOL treats INDEXED files as Berkeley DB (``.dat`` +
``.idx``). Generated Java reads the same flat fixed-width files directly.

Baseline testing uses a SEQUENTIAL variant so ``cobc`` can read the committed
``acme-bank-v3`` flat data files without building indexed file structures.

Key semantic distinction:
- ``AT END`` / ``NOT AT END`` → only valid on ``READ`` and ``RETURN``
- ``INVALID KEY`` / ``NOT INVALID KEY`` → only valid on ``READ``, ``WRITE``,
  ``REWRITE``, ``DELETE`` for indexed/relative files.
For sequential conversion we map ``INVALID KEY`` → ``AT END`` only on
``READ``/``RETURN`` statements; on ``WRITE``/``REWRITE``/``DELETE`` we strip
the clause entirely (sequential files never produce a key error).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

# FILE-CONTROL clauses only — does not match ``OCCURS ... INDEXED BY``.
_ORG_INDEXED_RE = re.compile(r"ORGANIZATION\s+IS\s+INDEXED", re.IGNORECASE)
_ACCESS_RANDOM_RE = re.compile(r"ACCESS\s+MODE\s+IS\s+RANDOM", re.IGNORECASE)
_ACCESS_DYNAMIC_RE = re.compile(r"ACCESS\s+MODE\s+IS\s+DYNAMIC", re.IGNORECASE)

_RECORD_KEY_LINE_RE = re.compile(r"^\s+RECORD\s+KEY\s+IS\s+[^\n]+\n", re.MULTILINE | re.IGNORECASE)
_ALT_KEY_BLOCK_RE = re.compile(
    r"^\s+ALTERNATE\s+RECORD\s+KEY\s+IS\s+[^\n]+\n(?:\s+WITH\s+DUPLICATES\s*\n)?",
    re.MULTILINE | re.IGNORECASE,
)

_START_LINE_RE = re.compile(r"^\s*START\s+\S+.*$", re.MULTILINE | re.IGNORECASE)

# KEY IS <field> on READ — only valid for indexed/relative random access.
_READ_KEY_IS_RE = re.compile(r"\s+KEY\s+IS\s+\S+", re.IGNORECASE)

_INVALID_KEY_RE = re.compile(r"\bINVALID\s+KEY\b", re.IGNORECASE)
_NOT_INVALID_KEY_RE = re.compile(r"\bNOT\s+INVALID\s+KEY\b", re.IGNORECASE)

# Verbs where INVALID KEY is valid but AT END is NOT — we must strip the clause.
_WRITE_VERB_RE = re.compile(r"^\s*(?:WRITE|REWRITE|DELETE)\b", re.IGNORECASE)
# Verbs where INVALID KEY → AT END is the correct sequential mapping.
_READ_VERB_RE = re.compile(r"^\s*(?:READ|RETURN)\b", re.IGNORECASE)

# Flat acme-bank-v3 LOANFILE.dat records are 239 bytes (238 logical + 1 pad).
_LOAN_FD_BLOCK_RE = re.compile(
    r"^\s*FD LOAN-FILE\s*\n"
    r"^\s+RECORD CONTAINS 238 CHARACTERS\.\s*\n"
    r"^\s*COPY LOANCOPY\.\s*(?:\n|$)",
    re.IGNORECASE | re.MULTILINE,
)
_LOAN_FD_REPLACEMENT = (
    "       FD LOAN-FILE\n"
    "           RECORD CONTAINS 239 CHARACTERS.\n"
    "       01 LOAN-RECORD.\n"
    "           COPY LOANCOPY REPLACING\n"
    "               ==01 LOAN-RECORD.==\n"
    "               BY ====\n"
    "               ==05 LOAN-FILLER          PIC X(8)==\n"
    "               BY ==05 LOAN-FILLER          PIC X(9)==.\n"
)


def _patch_flat_loan_fd_blocks(text: str) -> str:
    """Align LOAN-FILE FD with 239-byte flat LOANFILE.dat fixtures."""
    return _LOAN_FD_BLOCK_RE.sub(_LOAN_FD_REPLACEMENT, text)


def _find_governing_verb(lines: List[str], idx: int) -> str:
    """Walk backwards from *idx* to find the nearest COBOL I/O verb."""
    for i in range(idx, -1, -1):
        stripped = lines[i].lstrip()
        upper = stripped.upper()
        for verb in ("READ ", "RETURN ", "WRITE ", "REWRITE ", "DELETE "):
            if upper.startswith(verb):
                return verb.strip()
    return ""


def create_sequential_variant(indexed_cobol: str) -> str:
    """
    Create a SEQUENTIAL-organized variant of an INDEXED COBOL program.

    Transformations (GnuCOBOL baseline / Option A):

    1. ``ORGANIZATION IS INDEXED`` → ``ORGANIZATION IS SEQUENTIAL``
    2. ``ACCESS MODE IS RANDOM|DYNAMIC`` → ``ACCESS MODE IS SEQUENTIAL``
    3. Remove ``RECORD KEY`` / ``ALTERNATE RECORD KEY`` clauses
    4. ``INVALID KEY`` on ``READ``/``RETURN`` → ``AT END``
    5. ``INVALID KEY`` on ``WRITE``/``REWRITE``/``DELETE`` → stripped
    6. Remove ``START`` statements (indexed-only)
    """
    text = indexed_cobol or ""
    if not text.strip():
        return text

    text = _ORG_INDEXED_RE.sub("ORGANIZATION IS SEQUENTIAL", text)
    text = _ACCESS_RANDOM_RE.sub("ACCESS MODE IS SEQUENTIAL", text)
    text = _ACCESS_DYNAMIC_RE.sub("ACCESS MODE IS SEQUENTIAL", text)
    text = _ALT_KEY_BLOCK_RE.sub("\n", text)
    text = _RECORD_KEY_LINE_RE.sub("\n", text)

    # Pass 1: strip WRITE/REWRITE/DELETE INVALID KEY blocks and START blocks
    lines = text.splitlines()
    lines = _strip_write_and_start_blocks(lines)

    # Pass 2: remaining INVALID KEY should only be on READ/RETURN → AT END
    # Also strip KEY IS <field> from READ statements (invalid for sequential).
    final: List[str] = []
    for line in lines:
        if _NOT_INVALID_KEY_RE.search(line):
            line = _NOT_INVALID_KEY_RE.sub("NOT AT END", line)
        if _INVALID_KEY_RE.search(line):
            line = _INVALID_KEY_RE.sub("AT END", line)
        if re.match(r"^\s*READ\b", line, re.IGNORECASE):
            line = _READ_KEY_IS_RE.sub("", line)
        final.append(line)

    text = "\n".join(final)
    text = _patch_flat_loan_fd_blocks(text)
    if indexed_cobol.endswith("\n"):
        text += "\n"
    return text


_IO_VERB_RE = re.compile(r"^\s*(WRITE|REWRITE|DELETE|READ|RETURN|START)\b", re.IGNORECASE)
_END_ANY_RE = re.compile(r"^\s*END-(WRITE|REWRITE|DELETE|READ|RETURN|START)\b", re.IGNORECASE)


def _consume_scoped_block(lines: List[str], start: int, verb: str) -> Tuple[List[str], int]:
    """Collect lines from *start* through the matching ``END-{verb}``.

    Returns ``(block_lines, next_index)``.  Tracks nested I/O scope
    terminators so an inner ``END-WRITE`` doesn't close an outer ``WRITE``.
    """
    end_re = re.compile(rf"^\s*END-{verb}\b", re.IGNORECASE)
    collected = [lines[start]]
    # Single-line period-terminated statement (e.g. ``WRITE X FROM Y.``)
    if lines[start].rstrip().endswith("."):
        return collected, start + 1
    depth = 0
    i = start + 1
    while i < len(lines):
        line = lines[i]
        collected.append(line)
        if _IO_VERB_RE.match(line):
            depth += 1
        m = _END_ANY_RE.match(line)
        if m:
            if depth > 0:
                depth -= 1
            elif end_re.match(line):
                return collected, i + 1
        i += 1
    return collected, i


def _next_meaningful_line(lines: List[str], start: int) -> Tuple[int, str]:
    """Return index and uppercased content of the next non-blank non-comment line."""
    i = start
    while i < len(lines):
        stripped = lines[i].lstrip()
        if stripped and not stripped.startswith("*"):
            return i, stripped.upper()
        i += 1
    return i, ""


def _strip_write_and_start_blocks(lines: List[str]) -> List[str]:
    """Handle WRITE/REWRITE/DELETE with INVALID KEY and START blocks.

    - WRITE/REWRITE/DELETE + INVALID KEY: keep verb + END-xxx, strip body.
    - START: comment out entire block (indexed-only positioning verb).
    - Simple WRITE (no INVALID KEY): emit unchanged.
    """
    result: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^\s*(WRITE|REWRITE|DELETE)\b", line, re.IGNORECASE)
        if m:
            verb = m.group(1).upper()
            # Peek: does the next meaningful line start with INVALID KEY?
            ni, ntext = _next_meaningful_line(lines, i + 1)
            if ntext.startswith("INVALID KEY") or ntext.startswith("INVALID\tKEY"):
                block, end_idx = _consume_scoped_block(lines, i, verb)
                result.append(lines[i])  # verb line
                end_tag = f"END-{verb}"
                for bl in block:
                    if re.match(rf"^\s*{end_tag}\b", bl, re.IGNORECASE):
                        result.append(bl)
                        break
                i = end_idx
                continue

        if _START_LINE_RE.match(line):
            block, end_idx = _consume_scoped_block(lines, i, "START")
            # COBOL fixed-format: * must be in column 7 (6 leading spaces).
            for bl in block:
                result.append(f"      * BASELINE: {bl.lstrip()}")
            i = end_idx
            continue

        result.append(line)
        i += 1
    return result


def write_sequential_variant(
    indexed_path: Path,
    output_path: Path,
    *,
    header_comment: str | None = None,
) -> Tuple[str, List[str]]:
    """
    Read *indexed_path*, transform, write *output_path*.

    Returns ``(written_text, list_of_transform_notes)``.
    """
    source = indexed_path.read_text(encoding="utf-8")
    transformed = create_sequential_variant(source)
    notes: List[str] = []
    if "ORGANIZATION IS INDEXED" in source.upper():
        notes.append("ORGANIZATION IS INDEXED → SEQUENTIAL")
    if _START_LINE_RE.search(source):
        notes.append("START statements commented/removed")
    if "INVALID KEY" in source.upper():
        notes.append("INVALID KEY → AT END")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    banner = header_comment or (
        f"* SEQUENTIAL baseline variant of {indexed_path.name}\n"
        f"* For GnuCOBOL testing on flat .dat fixtures — not for production INDEXED deploy.\n"
    )
    if not transformed.lstrip().startswith("*"):
        transformed = banner + transformed
    output_path.write_text(transformed, encoding="utf-8")
    return transformed, notes


def generate_sequential_tree(
    src_dir: Path,
    out_dir: Path,
    *,
    pattern: str = "*.cbl",
) -> List[Tuple[Path, Path]]:
    """Generate ``out_dir/<NAME>.cbl`` for every ``src_dir`` program matching *pattern*."""
    written: List[Tuple[Path, Path]] = []
    for indexed in sorted(src_dir.glob(pattern)):
        if not indexed.is_file():
            continue
        dest = out_dir / indexed.name
        write_sequential_variant(indexed, dest)
        written.append((indexed, dest))
    return written
