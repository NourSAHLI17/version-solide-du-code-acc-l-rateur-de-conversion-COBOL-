"""COBOL paragraph ↔ Java method name alignment for analysis and scoring."""

from __future__ import annotations

import re
from typing import List, Set, Tuple

from app.converters.cobol_name_converter import CobolNameConverter

_NUMERIC_PREFIX = re.compile(r"^\d+$")
_JAVA_METHOD_RE = re.compile(
    r"(?:public|private|protected|static|final|\s)+[\w<>,\[\]\s.]+\s+(\w+)\s*\(",
    re.MULTILINE,
)


def cobol_paragraph_semantic_parts(cobol_name: str) -> List[str]:
    """Split a paragraph name into tokens, dropping leading numeric section prefixes (e.g. 3000-)."""
    base = cobol_name.strip().upper().rstrip(".")
    if not base:
        return []
    parts = [x for x in base.split("-") if x]
    while parts and _NUMERIC_PREFIX.match(parts[0]):
        parts.pop(0)
    return parts


def cobol_paragraph_java_aliases(cobol_name: str) -> List[str]:
    """
    Possible Java-style identifiers for a COBOL paragraph.

    Strips numeric prefixes so ``3000-DISPLAY-SUMMARY`` matches ``displaySummary``.
    """
    base = cobol_name.strip()
    if not base:
        return []
    upper = base.upper().rstrip(".")
    parts = cobol_paragraph_semantic_parts(base)
    variants: List[str] = []

    canonical = CobolNameConverter.to_java_method(base)
    if canonical:
        variants.append(canonical)

    variants.append(upper.replace("-", "_").lower())
    if parts:
        variants.append("_".join(x.lower() for x in parts))
        camel = "".join(p.title() for p in parts)
        if camel:
            variants.append(camel)
            variants.append(camel[:1].lower() + camel[1:])
        variants.append("".join(parts).lower())

    # Legacy: full name including numeric prefix (some converters keep it)
    legacy_parts = [x for x in upper.split("-") if x]
    if legacy_parts:
        legacy_camel = "".join(p.title() for p in legacy_parts)
        variants.append(legacy_camel[:1].lower() + legacy_camel[1:] if legacy_camel else "")

    seen: Set[str] = set()
    out: List[str] = []
    for v in variants:
        v = v.strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def extract_java_method_names(java: str) -> List[str]:
    return [m.group(1) for m in _JAVA_METHOD_RE.finditer(java or "")]


def java_method_set_lookup(java: str) -> Tuple[Set[str], str]:
    methods = extract_java_method_names(java)
    lower = {m.lower() for m in methods}
    return lower, (java or "").lower()


def resolve_java_method_for_paragraph(cobol_name: str, java_methods: List[str]) -> str:
    """Return the best matching Java method name for a COBOL paragraph, or ``\"\"``."""
    by_lower = {m.lower(): m for m in java_methods}
    for alias in cobol_paragraph_java_aliases(cobol_name):
        hit = by_lower.get(alias.lower())
        if hit:
            return hit
    return ""


def paragraph_has_java_method(para: str, method_lower: Set[str], java_blob: str) -> bool:
    for alias in cobol_paragraph_java_aliases(para):
        al = alias.lower()
        if al in method_lower:
            return True
        if al and re.search(rf"\b{re.escape(al)}\s*\(", java_blob):
            return True
    return False
