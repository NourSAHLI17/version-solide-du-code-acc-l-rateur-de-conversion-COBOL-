"""Build user-facing summaries of compile-and-repair activity for the dashboard."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

_ITERATION_RE = re.compile(
    r"iteration\s+\d+:\s+repaired\s+(\w+)\s+at\s+[^:]+:(\d+)\s+\((.+)\)",
    re.IGNORECASE,
)
_RENAME_RE = re.compile(
    r"Auto-renamed reference\s+(\w+)\s*→\s*(\w+)(?:\s+\((\d+)\s+(?:on loan receiver|occurrence\(s\))\))?",
    re.IGNORECASE,
)
_COBOL_COMMENT_RE = re.compile(r"converted COBOL \* comment lines", re.IGNORECASE)
_ORPHAN_COMMENT_RE = re.compile(r"closed orphan block comment", re.IGNORECASE)
_REMOVED_IMPORT_RE = re.compile(r"^removed import:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_REMOVED_ANNOTATION_RE = re.compile(r"^removed annotation:\s*(.+)$", re.IGNORECASE | re.MULTILINE)

_TODO_LINE_RE = re.compile(
    r"^(\s*)//\s*TODO:\s*(.+)$",
    re.MULTILINE,
)

_FRAMEWORK_IMPORT_MARKERS = (
    "org.springframework",
    "jakarta.",
    "javax.annotation",
    "javax.inject",
    "lombok",
)


def _profile_label(profile: str) -> str:
    p = (profile or "plain_java").strip()
    if p == "plain_java":
        return "plain Java profile"
    return f"{p} profile"


def _format_iteration_repair(error_type: str, line: int, detail: str, profile: str) -> str:
    et = error_type.lower()
    if et == "semicolon_expected":
        return f"Added missing semicolon at line {line}"
    if et == "incompatible_types":
        short = detail.split("incompatible types:")[-1].strip() if "incompatible types" in detail.lower() else detail
        return f"Fixed type mismatch at line {line} ({short})"
    if et == "cannot_find_symbol":
        return f"Fixed missing symbol at line {line}"
    if et == "package_does_not_exist":
        return f"Removed unavailable import ({detail[:80]})"
    if et == "illegal_start":
        return f"Converted invalid COBOL-style syntax at line {line}"
    if et == "unclosed_comment":
        return "Closed unterminated block comment"
    if et == "class_interface_enum_expected":
        return f"Inserted missing closing brace near line {line}"
    if et == "missing_return":
        return f"Added default return statement near line {line}"
    if et == "unreachable_statement":
        return f"Commented out unreachable code at line {line}"
    if et == "duplicate_class":
        return f"Renamed duplicate class (see line {line})"
    if et == "public_class_wrong_file":
        return "Adjusted class visibility to match filename"
    return f"Repaired {error_type.replace('_', ' ')} at line {line}"


def _aggregate_package_repairs(messages: List[str], profile: str) -> List[str]:
    """Collapse repeated package-removal iteration notes into one summary line."""
    framework = [m for m in messages if "unavailable import" in m or "package" in m.lower()]
    other = [m for m in messages if m not in framework]
    if not framework:
        return other
    count = len(framework)
    label = _profile_label(profile)
    springish = sum(
        1
        for m in framework
        if any(marker in m for marker in _FRAMEWORK_IMPORT_MARKERS)
    )
    if springish >= count // 2 and count > 0:
        noun = "import" if count == 1 else "imports"
        return [
            f"Removed {count} Spring/framework {noun} ({label})",
            *other,
        ]
    noun = "import" if count == 1 else "imports"
    return [f"Removed {count} unavailable {noun} ({label})", *other]


def _parse_mapping_notes(mapping_notes: str, profile: str) -> List[str]:
    """Extract profile-sanitization lines from agent mapping notes."""
    if not mapping_notes:
        return []
    out: List[str] = []
    imports = _REMOVED_IMPORT_RE.findall(mapping_notes)
    annotations = _REMOVED_ANNOTATION_RE.findall(mapping_notes)
    if imports:
        spring = [i for i in imports if any(m in i for m in _FRAMEWORK_IMPORT_MARKERS)]
        if spring:
            n = len(spring)
            noun = "import" if n == 1 else "imports"
            out.append(
                f"Removed {n} Spring/framework {noun} ({_profile_label(profile)})"
            )
        other = [i for i in imports if i not in spring]
        for imp in other[:5]:
            out.append(f"Removed import {imp}")
        if len(other) > 5:
            out.append(f"Removed {len(other) - 5} more imports")
    for ann in annotations[:3]:
        short = ann.split(".")[-1] if "." in ann else ann
        out.append(f"Removed annotation @{short}")
    if len(annotations) > 3:
        out.append(f"Removed {len(annotations) - 3} more framework annotations")
    return out


def extract_manual_review_items(java_code: str) -> List[Dict[str, Any]]:
    """Find ``// TODO:`` comments that need human review."""
    items: List[Dict[str, Any]] = []
    if not java_code:
        return items

    lines = java_code.splitlines()
    for line_no, line in enumerate(lines, start=1):
        m = re.match(r"^\s*//\s*TODO:\s*(.+)$", line, re.IGNORECASE)
        if not m:
            continue
        message = m.group(1).strip()
        lower = message.lower()
        # Skip bulk mismatch headers — detail lines follow in source
        if lower.startswith("resolve these name mismatches"):
            continue
        if lower.startswith("auto-declared missing variable"):
            items.append({"line": line_no, "message": message})
            continue
        if lower.startswith("auto-generated") and "stub" in lower:
            items.append({"line": line_no, "message": message})
            continue
        if "type mismatch" in lower or "manual review" in lower:
            items.append({"line": line_no, "message": message})
            continue
        if "unreachable" in lower:
            items.append({"line": line_no, "message": message})
            continue
        if "unresolvable" in lower or "name mismatch" in lower:
            items.append({"line": line_no, "message": message})
            continue
        # Any other TODO in repaired output is worth surfacing
        if any(
            kw in lower
            for kw in (
                "call ",
                "sort ",
                "substituted",
                "restcontroller",
                "requestmapping",
            )
        ):
            items.append({"line": line_no, "message": message})

    # Deduplicate by line+message
    seen: set[tuple[int, str]] = set()
    unique: List[Dict[str, Any]] = []
    for item in items:
        key = (int(item["line"]), str(item["message"]))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def format_repair_notes_for_ui(
    repair_notes: Sequence[str],
    java_code: str = "",
    *,
    java_profile: str = "plain_java",
    mapping_notes: str = "",
) -> Dict[str, Any]:
    """
    Turn raw repair log lines into dashboard-friendly buckets.

    Returns::

        {
          "auto_repairs": ["Renamed status → loanStatus (name mismatch)", ...],
          "manual_review": [{"line": 312, "message": "Type mismatch (manual review)"}, ...],
        }
    """
    auto: List[str] = []
    package_pending: List[str] = []

    for raw in repair_notes or []:
        note = (raw or "").strip()
        if not note:
            continue

        m_iter = _ITERATION_RE.search(note)
        if m_iter:
            formatted = _format_iteration_repair(
                m_iter.group(1), int(m_iter.group(2)), m_iter.group(3), java_profile
            )
            if m_iter.group(1).lower() == "package_does_not_exist":
                package_pending.append(formatted)
            else:
                auto.append(formatted)
            continue

        m_rename = _RENAME_RE.search(note)
        if m_rename:
            old, new = m_rename.group(1), m_rename.group(2)
            auto.append(f"Renamed {old} → {new} (name mismatch)")
            continue

        if _COBOL_COMMENT_RE.search(note):
            auto.append("Converted COBOL-style * comment lines to Java // comments")
            continue
        if _ORPHAN_COMMENT_RE.search(note):
            auto.append("Closed unterminated block comment")
            continue

        if note.startswith("riskscor_") or note.startswith("autoprem_"):
            auto.append(note.replace("_", " ").capitalize())
            continue
        if note.startswith("sort_") or note.startswith("call_"):
            auto.append(f"Applied {note.replace('_', ' ')}")
            continue
        if note.lower().startswith("structure finalize skipped"):
            continue

        # Pass through short opaque notes unchanged
        if len(note) < 120 and "iteration" not in note.lower():
            auto.append(note)

    auto = _aggregate_package_repairs(package_pending + auto, java_profile)
    auto.extend(_parse_mapping_notes(mapping_notes, java_profile))

    # Deduplicate while preserving order
    seen_auto: set[str] = set()
    deduped_auto: List[str] = []
    for line in auto:
        if line in seen_auto:
            continue
        seen_auto.add(line)
        deduped_auto.append(line)

    manual = extract_manual_review_items(java_code)

    return {
        "auto_repairs": deduped_auto,
        "manual_review": manual,
    }


def build_repair_summary(
    repair_notes: Sequence[str],
    java_code: str,
    *,
    java_profile: str = "plain_java",
    mapping_notes: str = "",
) -> Dict[str, Any]:
    """Alias used by pipeline_service."""
    return format_repair_notes_for_ui(
        repair_notes,
        java_code,
        java_profile=java_profile,
        mapping_notes=mapping_notes,
    )
