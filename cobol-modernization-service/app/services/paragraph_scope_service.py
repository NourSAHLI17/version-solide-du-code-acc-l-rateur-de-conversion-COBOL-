"""Paragraph-level conversion context slicing for scoped testing retries."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.parsers.column_aware_paragraphs import extract_paragraph_bodies
from app.services.pipeline_segmenter import build_call_graph, build_reverse_graph

MAX_PARAGRAPH_SLICE = 4
SHARED_SYMBOL_PARAGRAPH_THRESHOLD = 3
SCOPE_WIDEN_ORDER: List[str] = ["method", "paragraph", "section", "file", "program"]


def _scope_is_wider(requested: str, actual: str) -> bool:
    order = {name: i for i, name in enumerate(SCOPE_WIDEN_ORDER)}
    return order.get(actual, 99) > order.get(requested, 99)


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


def _normalize_paragraph_id(paragraph_id: str, known: List[str]) -> Optional[str]:
    pid = (paragraph_id or "").strip().upper()
    if not pid:
        return None
    for name in known:
        if name.upper() == pid:
            return name
    return paragraph_id.strip() or None


def _calls_list(parser: Dict[str, Any]) -> List[Dict[str, Any]]:
    cf = parser.get("control_flow")
    if not isinstance(cf, dict):
        return []
    calls = cf.get("calls") or []
    return [c for c in calls if isinstance(c, dict)]


def _collect_dependency_paragraphs(
    target: str,
    parser: Dict[str, Any],
    all_paragraphs: List[str],
) -> Tuple[List[str], List[str]]:
    """Return (included, inclusion_reasons) with target + callers + callees (1 hop)."""
    calls = _calls_list(parser)
    forward = build_call_graph(calls)
    reverse = build_reverse_graph(calls)

    included: List[str] = []
    reasons: List[str] = []
    seen: Set[str] = set()

    def add(name: str, reason: str) -> None:
        if not name or name in seen:
            return
        if name not in all_paragraphs and name.upper() not in {p.upper() for p in all_paragraphs}:
            return
        canonical = next((p for p in all_paragraphs if p.upper() == name.upper()), name)
        seen.add(canonical)
        included.append(canonical)
        reasons.append(reason)

    add(target, f"Primary failing paragraph {target}.")
    for callee in forward.get(target, []):
        add(callee, f"PERFORM target from {target}.")
    for caller in reverse.get(target, []):
        add(caller, f"Caller paragraph {caller} dispatches to {target}.")

    if all_paragraphs and all_paragraphs[0] not in seen:
        entry = all_paragraphs[0]
        if target != entry and (forward.get(entry) or reverse.get(target)):
            add(entry, f"Program entry paragraph {entry} may initialize state for {target}.")

    return included, reasons


def _symbols_for_paragraphs(parser: Dict[str, Any], paragraphs: Set[str]) -> Tuple[Set[str], Set[str]]:
    reads: Set[str] = set()
    writes: Set[str] = set()
    for op in parser.get("operations") or []:
        if not isinstance(op, dict):
            continue
        if str(op.get("paragraph") or "") not in paragraphs:
            continue
        for key, bucket in (("target", writes), ("value", reads)):
            val = op.get(key)
            if isinstance(val, str) and val.strip():
                bucket.add(val.strip())
        for ref in op.get("references") or []:
            if isinstance(ref, str) and ref.strip():
                reads.add(ref.strip())
    return reads, writes


def _symbol_usage_by_paragraph(parser: Dict[str, Any]) -> Dict[str, Set[str]]:
    usage: Dict[str, Set[str]] = {}
    for op in parser.get("operations") or []:
        if not isinstance(op, dict):
            continue
        para = str(op.get("paragraph") or "")
        if not para:
            continue
        usage.setdefault(para, set())
        for field in ("target", "value"):
            v = op.get(field)
            if isinstance(v, str) and v.strip():
                usage[para].add(v.strip())
        for ref in op.get("references") or []:
            if isinstance(ref, str) and ref.strip():
                usage[para].add(ref.strip())
    return usage


def _assess_widen(
    target: str,
    included: List[str],
    parser: Dict[str, Any],
    all_paragraphs: List[str],
    cobol_source: str,
) -> Tuple[bool, str, str]:
    """
    Return (safe_for_paragraph_retry, widen_reason, effective_scope_if_not_safe).
    """
    if len(included) > MAX_PARAGRAPH_SLICE:
        return (
            False,
            f"Paragraph {target} depends on {len(included)} related paragraphs; "
            "widening to section-level context.",
            "section",
        )

    if not cobol_source.strip():
        return (
            False,
            "COBOL source unavailable for paragraph body extraction; using narrowed analysis only.",
            "section",
        )

    usage = _symbol_usage_by_paragraph(parser)
    included_set = set(included)
    shared_reads, shared_writes = _symbols_for_paragraphs(parser, included_set)
    cross_paragraph_symbols: Set[str] = set()
    for sym in shared_reads | shared_writes:
        users = [p for p, syms in usage.items() if sym in syms]
        if len(users) > SHARED_SYMBOL_PARAGRAPH_THRESHOLD:
            cross_paragraph_symbols.add(sym)

    if cross_paragraph_symbols:
        return (
            False,
            "Paragraph depends on working-storage symbols used across multiple sections "
            f"({', '.join(sorted(cross_paragraph_symbols)[:3])}).",
            "section",
        )

    if all_paragraphs and target == all_paragraphs[0]:
        others_with_io = [
            p
            for p in all_paragraphs[1:]
            if any(
                isinstance(op, dict)
                and op.get("paragraph") == p
                and str(op.get("type") or "").upper() in {"READ", "WRITE", "OPEN", "CLOSE"}
                for op in (parser.get("operations") or [])
            )
        ]
        if others_with_io:
            return (
                False,
                "Entry paragraph retry would omit file I/O in downstream paragraphs.",
                "file",
            )

    return True, "", "paragraph"


def _parser_subset(parser: Dict[str, Any], paragraphs: List[str]) -> Dict[str, Any]:
    ps = {p for p in paragraphs}
    subset = dict(parser)
    subset["paragraphs"] = [p for p in (parser.get("paragraphs") or []) if str(p) in ps or p in ps]
    ops = [
        o
        for o in (parser.get("operations") or [])
        if isinstance(o, dict) and str(o.get("paragraph") or "") in ps
    ]
    subset["operations"] = ops
    cf = parser.get("control_flow")
    if isinstance(cf, dict):
        subset["control_flow"] = {
            "branches": [
                b
                for b in (cf.get("branches") or [])
                if isinstance(b, dict) and str(b.get("paragraph") or "") in ps
            ],
            "loops": [
                l
                for l in (cf.get("loops") or [])
                if isinstance(l, dict) and str(l.get("paragraph") or "") in ps
            ],
            "calls": [
                c
                for c in (cf.get("calls") or [])
                if isinstance(c, dict)
                and (
                    str(c.get("from") or "") in ps
                    or str(c.get("to") or "") in ps
                )
            ],
            "gotos": [
                g
                for g in (cf.get("gotos") or [])
                if isinstance(g, dict)
                and (
                    str(g.get("from_paragraph") or "") in ps
                    or str(g.get("to_paragraph") or "") in ps
                )
            ],
        }
    return subset


def _analysis_subset(analysis: Dict[str, Any], paragraphs: List[str]) -> Dict[str, Any]:
    from app.services.analysis_prompt_utils import prepare_analysis_for_conversion_prompt

    ps = {p for p in paragraphs}
    sections = [
        s
        for s in (analysis.get("sections") or [])
        if isinstance(s, dict) and str(s.get("name") or "") in ps
    ]
    if not sections:
        sections = [
            s
            for s in (analysis.get("sections") or [])[:MAX_PARAGRAPH_SLICE]
            if isinstance(s, dict)
        ]
    base = dict(analysis)
    base["sections"] = sections
    return prepare_analysis_for_conversion_prompt(base, chunk_sections=sections)


def _cobol_excerpt(cobol_source: str, paragraphs: List[str]) -> str:
    if not cobol_source.strip() or not paragraphs:
        return ""
    bodies = extract_paragraph_bodies(cobol_source, paragraphs)
    parts: List[str] = []
    for para in paragraphs:
        lines = bodies.get(para) or bodies.get(para.upper()) or []
        if not lines:
            continue
        parts.append(f"{para}.")
        parts.extend(lines)
        parts.append("")
    return "\n".join(parts).strip()


class ParagraphScopeService:
    """Build minimal paragraph-level payloads for scoped re-conversion."""

    def build_paragraph_slice(
        self,
        parser_json: dict,
        analysis_json: dict,
        java_source: str,
        paragraph_id: str,
        *,
        cobol_source: str = "",
    ) -> dict:
        parser = _unwrap_parser(parser_json)
        analysis = _unwrap_analysis(analysis_json)
        all_paragraphs = _paragraph_names(parser)
        target = _normalize_paragraph_id(paragraph_id, all_paragraphs)
        if not target:
            return {
                "paragraph_id": paragraph_id,
                "included_paragraphs": [],
                "excluded_paragraphs": all_paragraphs,
                "inclusion_reasons": ["Paragraph not found in parser output."],
                "safe_for_paragraph_retry": False,
                "effective_scope": "program",
                "widen_reason": "Unknown paragraph; full program context required.",
                "parser_subset": parser,
                "analysis_subset": analysis,
                "cobol_excerpt": "",
                "java_method_hints": [],
            }

        included, reasons = _collect_dependency_paragraphs(target, parser, all_paragraphs)
        excluded = [p for p in all_paragraphs if p not in included]
        safe, widen_reason, effective = _assess_widen(
            target, included, parser, all_paragraphs, cobol_source
        )

        from app.services.failure_mapping_service import _java_method_hints_for_paragraph

        java_hints = _java_method_hints_for_paragraph(target, java_source)

        excerpt = _cobol_excerpt(cobol_source, included) if safe else _cobol_excerpt(
            cobol_source, included[:MAX_PARAGRAPH_SLICE]
        )

        return {
            "paragraph_id": target,
            "included_paragraphs": included,
            "excluded_paragraphs": excluded,
            "inclusion_reasons": reasons,
            "safe_for_paragraph_retry": safe,
            "effective_scope": effective if not safe else "paragraph",
            "widen_reason": widen_reason,
            "parser_subset": _parser_subset(parser, included if safe else included[:MAX_PARAGRAPH_SLICE]),
            "analysis_subset": _analysis_subset(analysis, included),
            "cobol_excerpt": excerpt,
            "java_method_hints": java_hints,
        }

    def prepare_conversion_payload(
        self,
        parser_json: dict,
        analysis_json: dict,
        java_source: str,
        cobol_source: str,
        retry_scope: dict,
    ) -> dict:
        """
        Build narrowed parser/analysis for retry and report requested vs actual scope.
        """
        original_requested_type = str(retry_scope.get("scope_type") or "program")
        requested_type = original_requested_type
        requested_id = str(retry_scope.get("scope_id") or "")
        all_paragraphs = _paragraph_names(_unwrap_parser(parser_json))
        analysis = _unwrap_analysis(analysis_json)
        parser = _unwrap_parser(parser_json)

        actual_type = requested_type
        widen_reason: Optional[str] = None
        included: List[str] = list(retry_scope.get("affected_paragraphs") or [])
        excluded: List[str] = []
        inclusion_reasons: List[str] = []
        slice_meta: Optional[dict] = None

        if requested_type == "method":
            paras = retry_scope.get("affected_paragraphs") or []
            paragraph_id = paras[0] if paras else requested_id
            requested_type = "paragraph"
            requested_id = paragraph_id

        if requested_type == "paragraph" and requested_id:
            slice_meta = self.build_paragraph_slice(
                parser_json,
                analysis_json,
                java_source,
                requested_id,
                cobol_source=cobol_source,
            )
            included = list(slice_meta.get("included_paragraphs") or [])
            excluded = list(slice_meta.get("excluded_paragraphs") or [])
            inclusion_reasons = list(slice_meta.get("inclusion_reasons") or [])

            if slice_meta.get("safe_for_paragraph_retry"):
                actual_type = "paragraph"
            else:
                actual_type = str(slice_meta.get("effective_scope") or "section")
                widen_reason = str(slice_meta.get("widen_reason") or "")
                if actual_type == "section" and not included:
                    included = retry_scope.get("affected_paragraphs") or [requested_id]
                elif actual_type == "file":
                    included = all_paragraphs
                    excluded = []

        elif requested_type == "section" and requested_id:
            included = [
                p
                for p in all_paragraphs
                if p == requested_id or requested_id.upper() in p.upper()
            ] or list(retry_scope.get("affected_paragraphs") or [])
            excluded = [p for p in all_paragraphs if p not in included]
            inclusion_reasons = [f"Section scope: {requested_id}."]
            actual_type = "section"

        elif requested_type == "file":
            included = all_paragraphs
            excluded = []
            inclusion_reasons = ["File-level procedure division retry."]
            actual_type = "file"

        else:
            included = all_paragraphs
            excluded = []
            inclusion_reasons = ["Full program retry."]
            actual_type = "program"

        parser_subset = _parser_subset(parser, included) if included else parser
        analysis_subset = _analysis_subset(analysis, included)

        analysis_subset["_paragraph_conversion_slice"] = {
            "requested_scope": str(retry_scope.get("scope_type") or requested_type),
            "actual_scope": actual_type,
            "primary_paragraph": requested_id,
            "included_paragraphs": included,
            "excluded_paragraphs": excluded,
            "inclusion_reasons": inclusion_reasons,
            "cobol_excerpt": (slice_meta or {}).get("cobol_excerpt", ""),
            "java_method_hints": (slice_meta or {}).get("java_method_hints", []),
            "scope_widened": _scope_is_wider(original_requested_type, actual_type),
            "widen_reason": widen_reason,
        }
        analysis_subset["_retry_focus"] = {
            **retry_scope,
            "scope_type": actual_type,
            "scope_id": requested_id if actual_type == "paragraph" else retry_scope.get("scope_id"),
            "affected_paragraphs": included,
        }

        summary_parts = [
            f"Requested {retry_scope.get('scope_type')} retry on {retry_scope.get('scope_id')}.",
            f"Used {actual_type}-level context with {len(included)} paragraph(s).",
        ]
        if widen_reason:
            summary_parts.append(f"Scope widened: {widen_reason}")
        retry_summary = " ".join(summary_parts)

        return {
            "requested_scope": original_requested_type,
            "actual_scope": actual_type,
            "scope_widened": _scope_is_wider(original_requested_type, actual_type),
            "widen_reason": widen_reason,
            "included_paragraphs": included,
            "excluded_paragraphs": excluded,
            "inclusion_reasons": inclusion_reasons,
            "parser_json": parser_subset,
            "analysis_json": analysis_subset,
            "paragraph_slice": slice_meta,
            "retry_summary": retry_summary,
            "retry_scope_actual": {
                **retry_scope,
                "scope_type": actual_type,
                "scope_id": requested_id if actual_type == "paragraph" else retry_scope.get("scope_id", actual_type),
                "affected_paragraphs": included,
                "reason": retry_summary,
            },
        }
