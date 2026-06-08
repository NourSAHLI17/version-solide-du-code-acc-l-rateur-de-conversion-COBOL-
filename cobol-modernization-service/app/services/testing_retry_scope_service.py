"""Derive the smallest safe retry scope from behavioral diff failures."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Set

from app.services.failure_mapping_service import _java_method_hints_for_paragraph

SCOPE_PRIORITY: List[str] = ["method", "paragraph", "section", "file", "program"]


def _unwrap_parser(parser_json: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(parser_json, dict):
        return {}
    ast = parser_json.get("ast")
    if isinstance(ast, dict) and ast:
        return dict(ast)
    return dict(parser_json)


def _unwrap_analysis(analysis_json: Any) -> Dict[str, Any]:
    if isinstance(analysis_json, dict):
        return dict(analysis_json)
    return {}


def _paragraph_names(parser: Dict[str, Any]) -> List[str]:
    raw = parser.get("paragraphs") or []
    out: List[str] = []
    if isinstance(raw, list):
        for p in raw:
            if isinstance(p, str) and p.strip():
                out.append(p.strip())
            elif isinstance(p, dict) and p.get("name"):
                out.append(str(p["name"]).strip())
    return out


def _sections(analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = analysis.get("sections") or []
    return [s for s in rows if isinstance(s, dict)]


def _collect_paragraphs_from_failures(
    failed_tests: Sequence[Dict[str, Any]],
    diff_summary: Dict[str, Any],
) -> List[str]:
    found: List[str] = []
    seen: Set[str] = set()

    def add(p: Optional[str]) -> None:
        if not p:
            return
        p = str(p).strip()
        if p and p not in seen:
            seen.add(p)
            found.append(p)

    for ft in failed_tests or []:
        if not isinstance(ft, dict):
            continue
        add(ft.get("likely_paragraph"))
        desc = str(ft.get("description") or "")
        for m in re.finditer(r"paragraph\s+([A-Z0-9][A-Z0-9-]*)", desc, re.IGNORECASE):
            add(m.group(1).upper())

    for row in (diff_summary or {}).get("highlights") or []:
        if isinstance(row, dict):
            add(row.get("likely_paragraph"))

    for row in (diff_summary or {}).get("paragraph_breakdown") or []:
        if isinstance(row, dict) and row.get("status") == "affected":
            add(row.get("paragraph"))

    return found


def _resolve_java_methods(
    paragraphs: Sequence[str],
    java_source: str,
) -> List[str]:
    methods: List[str] = []
    seen: Set[str] = set()
    for para in paragraphs:
        for hint in _java_method_hints_for_paragraph(para, java_source):
            if hint not in seen:
                seen.add(hint)
                methods.append(hint)
    if not methods and java_source:
        for m in re.finditer(
            r"public\s+(?:static\s+)?(?:final\s+)?[\w<>,\[\]\s.]+\s+(\w+)\s*\([^)]*\)",
            java_source,
        ):
            name = m.group(1)
            if name not in seen and name[0].islower():
                seen.add(name)
                methods.append(name)
    return methods


def _section_for_paragraph(paragraph: str, sections: Sequence[Dict[str, Any]]) -> Optional[str]:
    for sec in sections:
        name = str(sec.get("name") or sec.get("paragraph") or "").strip()
        if name == paragraph:
            return name
    return None


def _confidence_for_attribution(
    failed_tests: Sequence[Dict[str, Any]],
    paragraphs: Sequence[str],
) -> str:
    if not paragraphs:
        return "low"
    kinds = {str(ft.get("failure_kind") or "") for ft in failed_tests if isinstance(ft, dict)}
    if any(ft.get("likely_paragraph") for ft in failed_tests if isinstance(ft, dict)):
        return "high"
    if kinds & {"menu_branch_mismatch", "content_mismatch", "order_mismatch"}:
        return "medium"
    return "low"


def _fallback_scope(scope_type: str) -> str:
    try:
        idx = SCOPE_PRIORITY.index(scope_type)
    except ValueError:
        return "program"
    if idx + 1 < len(SCOPE_PRIORITY):
        return SCOPE_PRIORITY[idx + 1]
    return "program"


class TestingRetryScopeService:
    """Pick the narrowest safe conversion retry target from test/diff failures."""

    def derive_retry_scope(
        self,
        parser_json: dict,
        analysis_json: dict,
        java_source: str,
        failed_tests: list[dict],
        diff_summary: dict,
        *,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
    ) -> dict:
        parser = _unwrap_parser(parser_json)
        analysis = _unwrap_analysis(analysis_json)
        sections = _sections(analysis)
        paragraphs = _collect_paragraphs_from_failures(failed_tests, diff_summary)

        if scope_type and scope_id:
            return self._build_scope(
                scope_type=str(scope_type),
                scope_id=str(scope_id),
                scope_name=str(scope_id),
                reason=f"User-selected retry scope: {scope_type} {scope_id}.",
                affected_methods=_resolve_java_methods([scope_id], java_source)
                if scope_type == "method"
                else _resolve_java_methods(paragraphs, java_source),
                affected_paragraphs=[scope_id] if scope_type != "method" else paragraphs,
                confidence="high",
            )

        methods = _resolve_java_methods(paragraphs, java_source)
        confidence = _confidence_for_attribution(failed_tests, paragraphs)

        if len(methods) == 1 and paragraphs:
            para = paragraphs[0]
            return self._build_scope(
                scope_type="method",
                scope_id=methods[0],
                scope_name=methods[0],
                reason=(
                    f"Failure maps to Java method `{methods[0]}` linked to paragraph {para}."
                ),
                affected_methods=methods,
                affected_paragraphs=paragraphs,
                confidence=confidence,
            )

        if len(paragraphs) == 1:
            para = paragraphs[0]
            return self._build_scope(
                scope_type="paragraph",
                scope_id=para,
                scope_name=para,
                reason=f"Failure maps to COBOL paragraph {para}.",
                affected_methods=methods,
                affected_paragraphs=paragraphs,
                confidence=confidence,
            )

        if len(paragraphs) > 1 and sections:
            section_names = {
                _section_for_paragraph(p, sections) or p for p in paragraphs
            }
            if len(section_names) == 1:
                sec = next(iter(section_names))
                return self._build_scope(
                    scope_type="section",
                    scope_id=sec,
                    scope_name=sec,
                    reason=f"Failures cluster in section {sec} ({len(paragraphs)} paragraphs).",
                    affected_methods=methods,
                    affected_paragraphs=paragraphs,
                    confidence="medium" if confidence == "high" else confidence,
                )

        if paragraphs:
            return self._build_scope(
                scope_type="file",
                scope_id="main",
                scope_name="procedure division",
                reason=(
                    f"Multiple paragraphs affected ({', '.join(paragraphs[:3])}); "
                    "retry the file-level conversion slice."
                ),
                affected_methods=methods,
                affected_paragraphs=paragraphs,
                confidence="medium",
            )

        program_paras = _paragraph_names(parser)
        return self._build_scope(
            scope_type="program",
            scope_id="program",
            scope_name="full program",
            reason="No paragraph attribution available; retry full program conversion.",
            affected_methods=methods,
            affected_paragraphs=program_paras[:5],
            confidence="low",
        )

    def _build_scope(
        self,
        *,
        scope_type: str,
        scope_id: str,
        scope_name: str,
        reason: str,
        affected_methods: List[str],
        affected_paragraphs: List[str],
        confidence: str,
    ) -> dict:
        return {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "scope_name": scope_name,
            "reason": reason,
            "affected_methods": affected_methods,
            "affected_paragraphs": affected_paragraphs,
            "confidence": confidence,
            "fallback_scope": _fallback_scope(scope_type),
        }


def narrow_analysis_for_scope(
    analysis_json: dict,
    retry_scope: dict,
) -> dict:
    """Return analysis JSON focused on the retry scope (reuses full program structure)."""
    analysis = _unwrap_analysis(analysis_json)
    if not analysis:
        return {"_retry_focus": retry_scope}

    scope_type = str(retry_scope.get("scope_type") or "program")
    affected = set(retry_scope.get("affected_paragraphs") or [])
    scope_id = str(retry_scope.get("scope_id") or "")

    sections = _sections(analysis)
    if scope_type == "method" and scope_id:
        focused = [
            s
            for s in sections
            if scope_id.lower() in str(s.get("name") or "").lower()
            or scope_id.lower() in str(s.get("role") or "").lower()
        ]
    elif scope_type in {"paragraph", "section"} and affected:
        focused = [s for s in sections if str(s.get("name") or "") in affected]
        if scope_type == "section" and scope_id:
            focused = [s for s in sections if str(s.get("name") or "") == scope_id] or focused
    else:
        focused = sections

    if not focused and sections:
        focused = sections[: min(5, len(sections))]

    narrowed = dict(analysis)
    narrowed["sections"] = focused
    narrowed["_retry_focus"] = retry_scope
    return narrowed
