"""Repair stale COBOL symbol names from conversion/refactor templates before compile."""

from __future__ import annotations

import re
from typing import List, Set, Tuple

_WS_ERROR_MESSAGE = re.compile(r"\bWS-ERROR-MESSAGE\b", re.IGNORECASE)
_RC_SUCCESS = re.compile(r"\bRC-SUCCESS\b", re.IGNORECASE)
_88_RC_SUCCESS = re.compile(r"^\s*88\s+RC-SUCCESS\b", re.IGNORECASE | re.MULTILINE)
_88_CUST_ACTIVE = re.compile(r"^\s*88\s+CUST-ACTIVE\b", re.IGNORECASE | re.MULTILINE)
_ERR_MESSAGE = re.compile(r"\bERR-MESSAGE\b", re.IGNORECASE)
_PROCEDURE_DIVISION = re.compile(r"^\s*PROCEDURE\s+DIVISION\s*\.?\s*$", re.IGNORECASE | re.MULTILINE)
_SYMBOL_TOKEN = re.compile(r"\b([A-Z][A-Z0-9-]+)\b")

_RC_SUCCESS_WS_BLOCK = (
    "       01 WS-RETURN-CODE.\n"
    "          05 WS-RC-STATUS          PIC XX VALUE '00'.\n"
    "          88 RC-SUCCESS            VALUE '00'.\n"
)

_ERRORCOPY_WS_BLOCK = (
    "       01 WS-ERROR-AREA.\n"
    "          COPY ERRORCOPY.\n"
)

_RPT_EXTENDED_FIELDS = (
    "RPT-PAGE-NO",
    "RPT-DATE",
    "RPT-TITLE",
    "RPT-SEPARATOR",
    "RPT-FOOTER",
    "RPT-HEADER-1",
)

_CUST_EXTENDED_FIELDS = (
    "CUST-CREDIT-LIMIT",
    "CUST-BALANCE",
)

_COBOl_KEYWORDS: Set[str] = {
    "IDENTIFICATION",
    "DIVISION",
    "PROGRAM-ID",
    "ENVIRONMENT",
    "DATA",
    "PROCEDURE",
    "WORKING-STORAGE",
    "FILE",
    "SECTION",
    "INPUT-OUTPUT",
    "FILE-CONTROL",
    "SELECT",
    "ASSIGN",
    "ORGANIZATION",
    "ACCESS",
    "RECORD",
    "KEY",
    "STATUS",
    "OPEN",
    "CLOSE",
    "READ",
    "WRITE",
    "MOVE",
    "PERFORM",
    "UNTIL",
    "IF",
    "ELSE",
    "END-IF",
    "STOP",
    "RUN",
    "COPY",
    "VALUE",
    "PIC",
    "COMP-3",
    "INDEXED",
    "SEQUENTIAL",
    "DYNAMIC",
    "INPUT",
    "OUTPUT",
    "INVALID",
    "NOT",
    "AT",
    "END",
    "ADD",
    "COMPUTE",
    "REWRITE",
    "DELETE",
    "DISPLAY",
    "ACCEPT",
    "EVALUATE",
    "WHEN",
    "OTHER",
    "CONTINUE",
    "ALL",
    "TO",
    "ZEROS",
    "SPACES",
    "SPACE",
}


def _referenced_tokens(source: str) -> Set[str]:
    return {m.group(1).upper() for m in _SYMBOL_TOKEN.finditer(source or "")}


def _declared_tokens(source: str) -> Set[str]:
    declared: Set[str] = set()
    for raw in (source or "").splitlines():
        line = raw.strip().upper()
        if not line or line.startswith("*"):
            continue
        for field in _RPT_EXTENDED_FIELDS + _CUST_EXTENDED_FIELDS + (
            "RC-SUCCESS",
            "ERR-MESSAGE",
            "WS-ERROR-MESSAGE",
            "WS-RETURN-CODE",
            "WS-RC-STATUS",
            "CUST-ACTIVE",
        ):
            if field in line:
                declared.add(field)
        match = re.match(r"^(?:0[1-9]|[1-9][0-9]|77|FD)\s+([A-Z0-9-]+)", line)
        if match:
            declared.add(match.group(1))
        match = re.match(r"^05\s+([A-Z0-9-]+)", line)
        if match:
            declared.add(match.group(1))
        match = re.match(r"^88\s+([A-Z0-9-]+)", line)
        if match:
            declared.add(match.group(1))
    return declared


def _needs_symbol_repair(source: str) -> bool:
    text = source or ""
    if not text.strip():
        return False
    refs = _referenced_tokens(text)
    decl = _declared_tokens(text)
    if _WS_ERROR_MESSAGE.search(text) and "ERR-MESSAGE" not in decl:
        return True
    if _RC_SUCCESS.search(text) and not _88_RC_SUCCESS.search(text):
        return True
    if "CUST-ACTIVE" in refs and not _88_CUST_ACTIVE.search(text):
        return True
    for field in _RPT_EXTENDED_FIELDS:
        if field in refs and field not in decl:
            return True
    for field in _CUST_EXTENDED_FIELDS:
        if field in refs and field not in decl:
            return True
    if "WS-RETURN-CODE" in refs and "WS-RC-STATUS" not in decl and not _88_RC_SUCCESS.search(text):
        return True
    return False


def _inject_before_procedure(source: str, blocks: List[str]) -> str:
    if not blocks:
        return source
    match = _PROCEDURE_DIVISION.search(source)
    if not match:
        return source.rstrip() + "\n" + "\n".join(blocks) + "\n"
    insert_at = match.start()
    prefix = source[:insert_at].rstrip()
    suffix = source[insert_at:]
    return prefix + "\n" + "\n".join(blocks) + "\n" + suffix


def _ensure_working_storage_section(source: str) -> str:
    if re.search(r"^\s*WORKING-STORAGE\s+SECTION\s*\.?\s*$", source, re.IGNORECASE | re.MULTILINE):
        return source
    match = _PROCEDURE_DIVISION.search(source)
    header = "       WORKING-STORAGE SECTION.\n"
    if match:
        return source[: match.start()] + header + source[match.start() :]
    return source.rstrip() + "\n" + header


def _upgrade_report_copybook(source: str) -> Tuple[str, bool]:
    """Use RPTHDCPY when extended RPT-* report fields are referenced."""
    refs = _referenced_tokens(source)
    needs_extended = any(field in refs for field in _RPT_EXTENDED_FIELDS)
    if not needs_extended:
        return source, False
    if re.search(r"COPY\s+RPTHDCPY\b", source, re.IGNORECASE):
        return source, False
    updated = re.sub(
        r"(?i)(^\s*COPY\s+)RPTCOPY(\s*\.?)\s*$",
        r"\1RPTHDCPY\2",
        source,
        flags=re.MULTILINE,
    )
    if updated != source:
        return updated, True
    if re.search(r"COPY\s+RPTCOPY\b", source, re.IGNORECASE):
        return source, False
    return source, False


def repair_cobol_conversion_symbols(source: str) -> Tuple[str, List[str]]:
    """
    Reconcile ERRORCOPY, file-status, report, and customer symbols before compile.

    - WS-ERROR-MESSAGE -> ERR-MESSAGE (ERRORCOPY field name)
    - Inject COPY ERRORCOPY / 88 RC-SUCCESS when referenced but missing
    - Upgrade COPY RPTCOPY -> RPTHDCPY when extended RPT-* fields are used
    """
    notes: List[str] = []
    if not (source or "").strip():
        return source, notes
    if not _needs_symbol_repair(source):
        out, upgraded = _upgrade_report_copybook(source)
        if upgraded:
            notes.append("upgraded COPY RPTCOPY to RPTHDCPY for extended report fields")
        return out, notes

    out = _ensure_working_storage_section(source)
    out, upgraded = _upgrade_report_copybook(out)
    if upgraded:
        notes.append("upgraded COPY RPTCOPY to RPTHDCPY for extended report fields")

    if _WS_ERROR_MESSAGE.search(out):
        if not _ERR_MESSAGE.search(out):
            if not re.search(r"COPY\s+ERRORCOPY\b", out, re.IGNORECASE):
                out = _inject_before_procedure(out, [_ERRORCOPY_WS_BLOCK])
                notes.append("injected WS-ERROR-AREA COPY ERRORCOPY")
        out = _WS_ERROR_MESSAGE.sub("ERR-MESSAGE", out)
        notes.append("renamed WS-ERROR-MESSAGE to ERR-MESSAGE")

    if _RC_SUCCESS.search(out) and not _88_RC_SUCCESS.search(out):
        out = _inject_before_procedure(out, [_RC_SUCCESS_WS_BLOCK])
        notes.append("injected WS-RETURN-CODE 88 RC-SUCCESS")

    return out, notes
