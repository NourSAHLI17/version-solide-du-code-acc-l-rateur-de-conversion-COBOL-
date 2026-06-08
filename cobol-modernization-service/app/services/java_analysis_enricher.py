"""Enrich generated Java with metadata from the COBOL analyzer output.

This post-processing step injects:
  - Per-method JavaDoc from ``business_rules`` (tagged ``[pattern]`` or LLM-derived)
  - Class-level ``@implNote`` tags from ``risk_points``
  - Import statements and field declarations from ``dependencies.external_calls``
  - Architectural hints from ``complexity_drivers``
"""

from __future__ import annotations

import json
import re
import textwrap
from typing import Any, Dict, List, Optional, Tuple

from app.converters.cobol_name_converter import (
    CobolNameConverter,
    paragraph_to_java_method,
    to_java_class_name,
)


_METHOD_SIG_RE = re.compile(
    r"^(\s*)"
    r"((?:public|private|protected)\s+)?"
    r"((?:static\s+)?[\w<>\[\],\s.?]+\s+)"
    r"(\w+)\s*\(",
    re.MULTILINE,
)

_CLASS_OPEN_RE = re.compile(
    r"^(\s*public\s+class\s+\w+[^{]*\{)",
    re.MULTILINE,
)

_PACKAGE_RE = re.compile(r"^package\s+[\w.]+;\s*$", re.MULTILINE)
_IMPORT_RE = re.compile(r"^import\s+[\w.]+;\s*$", re.MULTILINE)


def enrich_java_with_analysis(
    java_source: str,
    analysis_output: dict | str | None,
) -> Tuple[str, List[str]]:
    """Inject analysis metadata into *java_source* and return ``(enriched, notes)``.

    The function is intentionally lenient: if *analysis_output* is missing or
    unparseable the original source is returned unchanged.
    """
    notes: List[str] = []
    analysis = _normalize(analysis_output)
    if not analysis:
        return java_source, notes

    sections = analysis.get("sections") or []
    risk_points = analysis.get("risk_points") or []
    complexity_drivers = analysis.get("complexity_drivers") or []
    deps = analysis.get("dependencies") or {}
    external_calls = deps.get("external_calls") or []

    section_map = _build_section_map(sections)

    java_source, method_notes = _inject_method_javadoc(java_source, section_map)
    notes.extend(method_notes)

    java_source, risk_notes = _inject_class_risk_javadoc(java_source, risk_points, complexity_drivers)
    notes.extend(risk_notes)

    java_source, dep_notes = _inject_dependency_declarations(java_source, external_calls)
    notes.extend(dep_notes)

    java_source, driver_notes = _inject_complexity_hints(java_source, complexity_drivers)
    notes.extend(driver_notes)

    return java_source, notes


# ──────────────────────────────────────────────────────────────────────
# 1. Business rules → per-method JavaDoc
# ──────────────────────────────────────────────────────────────────────

def _build_section_map(sections: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Map Java method names to their analysis section data."""
    result: Dict[str, Dict[str, Any]] = {}
    for section in sections:
        para_name = str(section.get("name") or "")
        if not para_name:
            continue
        method_name = paragraph_to_java_method(para_name)
        result[method_name] = section
    return result


def _inject_method_javadoc(
    java_source: str,
    section_map: Dict[str, Dict[str, Any]],
) -> Tuple[str, List[str]]:
    """Insert JavaDoc above methods that have matching analysis sections."""
    if not section_map:
        return java_source, []
    notes: List[str] = []
    insertions: List[Tuple[int, str]] = []

    for m in _METHOD_SIG_RE.finditer(java_source):
        method_name = m.group(4)
        section = section_map.get(method_name)
        if not section:
            continue

        rules = section.get("business_rules") or []
        role = section.get("role") or ""
        if not rules and not role:
            continue

        preceding = java_source[:m.start()]
        if preceding.rstrip().endswith("*/"):
            continue

        raw_indent = m.group(1)
        indent = raw_indent.lstrip("\r\n")
        javadoc = _format_method_javadoc(role, rules, indent)
        insert_pos = m.start() + len(raw_indent) - len(indent)
        insertions.append((insert_pos, javadoc))
        notes.append(f"analysis_javadoc:{method_name}:{len(rules)}_rules")

    if not insertions:
        return java_source, notes

    # Apply insertions in reverse order to preserve offsets
    parts = list(java_source)
    for offset, text in sorted(insertions, key=lambda x: x[0], reverse=True):
        java_source = java_source[:offset] + text + java_source[offset:]

    return java_source, notes


def _format_method_javadoc(role: str, rules: List[str], indent: str) -> str:
    lines = [f"{indent}/**"]
    if role:
        lines.append(f"{indent} * {role}")
        if rules:
            lines.append(f"{indent} *")
    if rules:
        lines.append(f"{indent} * <p><b>Business rules (analysis-extracted):</b></p>")
        lines.append(f"{indent} * <ul>")
        for rule in rules:
            escaped = rule.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f"{indent} *   <li>{escaped}</li>")
        lines.append(f"{indent} * </ul>")
    lines.append(f"{indent} */")
    return "\n".join(lines) + "\n"


# ──────────────────────────────────────────────────────────────────────
# 2. Risk points → class-level @implNote JavaDoc
# ──────────────────────────────────────────────────────────────────────

def _inject_class_risk_javadoc(
    java_source: str,
    risk_points: List[str],
    complexity_drivers: List[str],
) -> Tuple[str, List[str]]:
    """Add class-level JavaDoc with risk points and complexity info."""
    if not risk_points and not complexity_drivers:
        return java_source, []
    notes: List[str] = []

    m = _CLASS_OPEN_RE.search(java_source)
    if not m:
        return java_source, []

    preceding = java_source[:m.start()].rstrip()
    if preceding.endswith("*/"):
        return java_source, []

    lines = ["/**"]
    if complexity_drivers:
        lines.append(" * @implNote <b>Complexity drivers:</b>")
        for d in complexity_drivers:
            escaped = d.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f" *   {escaped}")
        notes.append(f"analysis_class_drivers:{len(complexity_drivers)}")
    if risk_points:
        if complexity_drivers:
            lines.append(" *")
        lines.append(" * @implNote <b>Risk points (review during migration):</b>")
        for r in risk_points:
            escaped = r.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f" *   {escaped}")
        notes.append(f"analysis_class_risks:{len(risk_points)}")
    lines.append(" */")
    javadoc = "\n".join(lines) + "\n"
    java_source = java_source[:m.start()] + javadoc + java_source[m.start():]
    return java_source, notes


# ──────────────────────────────────────────────────────────────────────
# 3. External calls → import and field declarations
# ──────────────────────────────────────────────────────────────────────

def _inject_dependency_declarations(
    java_source: str,
    external_calls: List[Dict[str, Any]],
) -> Tuple[str, List[str]]:
    """Add import and field for each external call target not already present."""
    if not external_calls:
        return java_source, []
    notes: List[str] = []

    from app.converters.call_codegen import KNOWN_SUBPROGRAMS, subprogram_names_from_meta

    for call in external_calls:
        program = str(call.get("program_name") or "").upper()
        if not program:
            continue
        class_name, field_name, _ = subprogram_names_from_meta(call)
        known = KNOWN_SUBPROGRAMS.get(program, {})
        pkg = str(known.get("java_package") or f"com.modernized.{program.lower()}")

        import_line = f"import {pkg}.{class_name};"
        if import_line not in java_source:
            java_source = _insert_import(java_source, import_line)
            notes.append(f"analysis_import:{class_name}")

        if re.search(rf"\b{re.escape(field_name)}\b", java_source):
            continue
        if class_name in _find_existing_fields(java_source):
            continue

        field_decl = f"    private final {class_name} {field_name} = new {class_name}();"
        java_source = _insert_field_after_class_open(java_source, field_decl)
        notes.append(f"analysis_field:{field_name}")

    return java_source, notes


def _insert_import(java_source: str, import_line: str) -> str:
    """Insert an import statement after existing imports, or after package."""
    all_imports = list(_IMPORT_RE.finditer(java_source))
    if all_imports:
        last = all_imports[-1]
        pos = last.end()
        return java_source[:pos] + "\n" + import_line + java_source[pos:]

    pkg = _PACKAGE_RE.search(java_source)
    if pkg:
        pos = pkg.end()
        return java_source[:pos] + "\n\n" + import_line + java_source[pos:]

    return import_line + "\n" + java_source


def _insert_field_after_class_open(java_source: str, field_line: str) -> str:
    """Insert a field declaration right after the primary class opening brace."""
    m = _CLASS_OPEN_RE.search(java_source)
    if not m:
        return java_source
    pos = m.end()
    return java_source[:pos] + "\n" + field_line + java_source[pos:]


def _find_existing_fields(java_source: str) -> set:
    """Return set of class names already declared as fields."""
    return set(re.findall(r"private\s+(?:final\s+)?(\w+)\s+\w+", java_source))


# ──────────────────────────────────────────────────────────────────────
# 4. Complexity drivers → architectural TODO hints
# ──────────────────────────────────────────────────────────────────────

def _inject_complexity_hints(
    java_source: str,
    complexity_drivers: List[str],
) -> Tuple[str, List[str]]:
    """Add targeted architectural TODO comments based on complexity drivers."""
    if not complexity_drivers:
        return java_source, []
    notes: List[str] = []
    driver_set = {d.lower() for d in complexity_drivers}
    driver_text = " ".join(complexity_drivers).lower()

    if "embedded sql" in driver_set or "exec sql" in driver_text:
        stub = (
            "\n    // TODO: [analysis-hint] Embedded SQL detected — "
            "implement JDBC calls or use a repository pattern.\n"
        )
        if "TODO: [analysis-hint] Embedded SQL" not in java_source:
            java_source = _append_after_class_fields(java_source, stub)
            notes.append("analysis_hint:jdbc_stub")

    if "internal sort" in driver_text:
        stub = (
            "\n    // TODO: [analysis-hint] Internal SORT detected — "
            "use java.util.List + Comparator for sort operations.\n"
        )
        if "TODO: [analysis-hint] Internal SORT" not in java_source:
            java_source = _append_after_class_fields(java_source, stub)
            notes.append("analysis_hint:sort_pattern")

    high_io = any("high" in d.lower() and "file" in d.lower() for d in complexity_drivers)
    if high_io:
        stub = (
            "\n    // TODO: [analysis-hint] High file I/O count — "
            "use try-with-resources for all file handles.\n"
        )
        if "TODO: [analysis-hint] High file I/O" not in java_source:
            java_source = _append_after_class_fields(java_source, stub)
            notes.append("analysis_hint:try_with_resources")

    return java_source, notes


def _append_after_class_fields(java_source: str, snippet: str) -> str:
    """Insert snippet after the first block of field declarations inside the class."""
    m = _CLASS_OPEN_RE.search(java_source)
    if not m:
        return java_source
    pos = m.end()
    next_method = _METHOD_SIG_RE.search(java_source, pos)
    if next_method:
        pos = next_method.start()
    return java_source[:pos] + snippet + java_source[pos:]


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _normalize(analysis_output: dict | str | None) -> dict:
    """Parse analysis_output into a dict, tolerating various input forms."""
    if not analysis_output:
        return {}
    if isinstance(analysis_output, dict):
        return analysis_output
    try:
        text = str(analysis_output).strip()
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}
