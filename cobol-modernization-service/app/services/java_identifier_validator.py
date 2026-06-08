"""Validate generated Java field/method references against parser canonical names."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from app.converters.cobol_name_converter import (
    canonical_field_names,
    canonical_record_class_names,
)
from app.converters.rewrite_record import LOAN_RECORD_FIELD_ALIASES
from app.services.java_name_reconciler import extract_class_declared_fields

_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_STRING_LITERAL_RE = re.compile(
    r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
    re.DOTALL,
)

_FIELD_DECL_RE = re.compile(
    r"^\s*(?:(?:public|private|protected)\s+)?"
    r"(?:(?:static|final)\s+)*"
    r"(?:static|final\s+)*"
    r"([\w.<>,\s\[\]]+?)\s+(\w+)\s*(?:=|;)",
    re.MULTILINE,
)

_LOCAL_DECL_RE = re.compile(
    r"(?:^|[;\{\(]\s*)(?:final\s+)?[\w.<>,\[\]]+\s+(\w+)\s*=",
    re.MULTILINE,
)

_FIELD_REF_RE = re.compile(r"\.(\w+)(?!\w|\s*[\.(])")

_BUILTIN_MEMBER_REFS = frozenset(
    {
        "length",
        "class",
        "values",
        "name",
        "size",
        "isEmpty",
        "getClass",
    }
)

_NON_CANONICAL_RECORD_CLASS_NAMES = frozenset(
    {"Loan", "LoanData", "LoanEntity", "LoanDto", "LoanCopy"},
)


def _strip_comments_and_strings(source: str) -> str:
    text = _BLOCK_COMMENT_RE.sub(" ", source)
    text = _LINE_COMMENT_RE.sub(" ", text)
    return _STRING_LITERAL_RE.sub('""', text)


def parse_declared_identifiers(java_source: str) -> tuple[Set[str], Set[str]]:
    """Return (field_names, method_names) declared in the compilation unit."""
    stripped = _strip_comments_and_strings(java_source)
    fields: Set[str] = set()
    for match in _FIELD_DECL_RE.finditer(stripped):
        type_part = match.group(1).strip()
        name = match.group(2)
        if "(" in type_part:
            continue
        fields.add(name)
    for match in _LOCAL_DECL_RE.finditer(stripped):
        fields.add(match.group(1))
    methods: Set[str] = set()
    for match in re.finditer(
        r"(?:public|protected|private)?\s*(?:static\s+)?[\w.<>,\[\]]+\s+(\w+)\s*\([^;]*\)\s*\{",
        stripped,
    ):
        methods.add(match.group(1))
    return fields, methods


def extract_field_member_references(java_source: str) -> Set[str]:
    """Member names used after '.' that are not followed by '(' (field access, not call)."""
    stripped = _strip_comments_and_strings(java_source)
    refs: Set[str] = set()
    for match in _FIELD_REF_RE.finditer(stripped):
        refs.add(match.group(1))
    return refs


def validate_identifier_references(
    java_source: str,
    parser_output: Dict[str, Any] | None = None,
) -> List[str]:
    """
    Reject generated Java when field references are dangling or non-canonical.

    When *parser_output* is provided, also flag legacy short names (e.g. ``status``)
    when the canonical name is ``loanStatus``.
    """
    if not (java_source or "").strip():
        return []

    declared_fields, declared_methods = parse_declared_identifiers(java_source)
    declared_fields |= extract_class_declared_fields(java_source, "LoanRecord")
    declared_all = declared_fields | declared_methods
    refs = extract_field_member_references(java_source)

    errors: List[str] = []
    canonical_fields = canonical_field_names(parser_output)
    record_classes = canonical_record_class_names(parser_output)

    for ref in sorted(refs):
        if ref in _BUILTIN_MEMBER_REFS:
            continue
        if ref in declared_all:
            continue
        legacy_canonical = LOAN_RECORD_FIELD_ALIASES.get(ref)
        if legacy_canonical and (
            not canonical_fields or legacy_canonical in canonical_fields
        ):
            errors.append(
                f"Non-canonical field reference '.{ref}' — use '.{legacy_canonical}' "
                f"(from parser symbol table)"
            )
            continue
        if canonical_fields and ref in canonical_fields and ref not in declared_fields:
            errors.append(
                f"Dangling field reference '.{ref}' — in symbol table but not declared "
                f"in generated Java"
            )

    if parser_output:
        for bad_class in _NON_CANONICAL_RECORD_CLASS_NAMES:
            if bad_class in record_classes:
                continue
            if re.search(rf"\bclass\s+{re.escape(bad_class)}\b", java_source):
                errors.append(
                    f"Non-canonical record class '{bad_class}' — use 'LoanRecord' "
                    f"(or parser 01-level java class name)"
                )
            if re.search(rf"\bnew\s+{re.escape(bad_class)}\s*\(", java_source):
                errors.append(
                    f"Non-canonical record type 'new {bad_class}(...)' — use 'LoanRecord'"
                )

    return errors
