"""Deterministic failure attribution for behavioral diff results.

Maps stdout mismatches to likely COBOL paragraphs / Java conversion slices using
parser DISPLAY literals, analysis section metadata, and output-line heuristics.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

# Menu / branching phrases commonly seen in interactive COBOL programs
_MENU_MARKERS = (
    "menu",
    "choice",
    "invalid",
    "option",
    "select",
    "enter",
    "prompt",
)

_FAILURE_LABELS = {
    "content_mismatch": "Output text differs",
    "missing_java_line": "Expected COBOL output line missing in Java",
    "missing_cobol_line": "Extra Java output line not produced by COBOL",
    "extra_java_line": "Java produced additional output",
    "extra_cobol_line": "COBOL produced additional output",
    "order_mismatch": "Output lines match but appear in a different order",
    "menu_branch_mismatch": "Menu or branch response text differs",
    "execution_error": "Program execution failed before stdout could be compared",
}


def _paragraph_names(parser_output: Optional[Mapping[str, Any]]) -> List[str]:
    if not parser_output:
        return []
    raw = parser_output.get("paragraphs") or []
    if not isinstance(raw, list):
        return []
    return [str(p) for p in raw if p]


def _analysis_sections(analysis_output: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    if not analysis_output:
        return []
    sections = analysis_output.get("sections")
    if isinstance(sections, list):
        return [s for s in sections if isinstance(s, dict)]
    return []


def _extract_quoted_literals(display_value: str) -> List[str]:
    literals: List[str] = []
    for m in re.finditer(r"'([^']*)'|\"([^\"]*)\"", display_value or ""):
        text = (m.group(1) or m.group(2) or "").strip()
        if text:
            literals.append(text)
    return literals


def build_display_literals_by_paragraph(
    parser_output: Optional[Mapping[str, Any]],
    cobol_source: Optional[str] = None,
) -> Dict[str, List[str]]:
    """Map paragraph name → DISPLAY literal snippets from parser operations."""
    by_para: Dict[str, List[str]] = {}
    if parser_output:
        for op in parser_output.get("operations") or []:
            if not isinstance(op, dict) or op.get("type") != "DISPLAY":
                continue
            para = str(op.get("paragraph") or "PROCEDURE")
            for lit in _extract_quoted_literals(str(op.get("value") or "")):
                by_para.setdefault(para, []).append(lit)
    if cobol_source and not by_para:
        current: Optional[str] = None
        for line in cobol_source.splitlines():
            upper = line.strip().upper()
            m = re.match(r"^([A-Z0-9][A-Z0-9-]*)\.\s*$", upper)
            if m and m.group(1) not in {"IF", "ELSE", "END-IF", "PERFORM", "DISPLAY"}:
                current = m.group(1)
                by_para.setdefault(current, [])
                continue
            dm = re.search(r"DISPLAY\s+(.+)", upper)
            if dm and current:
                for lit in _extract_quoted_literals(dm.group(1)):
                    by_para.setdefault(current, []).append(lit)
    return by_para


def _paragraph_by_proportional_index(paragraphs: Sequence[str], line_idx: int, total_lines: int) -> Optional[str]:
    if not paragraphs or total_lines <= 0 or line_idx < 0:
        return None
    if total_lines == 1:
        return paragraphs[0]
    ratio = line_idx / max(total_lines - 1, 1)
    idx = min(int(ratio * len(paragraphs)), len(paragraphs) - 1)
    return paragraphs[idx]


def _score_paragraph_for_text(
    text: str,
    display_map: Mapping[str, List[str]],
    analysis_sections: Sequence[Mapping[str, Any]],
) -> Tuple[Optional[str], str]:
    """Return (paragraph, attribution_method)."""
    lowered = text.lower()
    if not lowered.strip():
        return None, "none"

    best_para: Optional[str] = None
    best_len = 0
    for para, literals in display_map.items():
        for lit in literals:
            lit_l = lit.lower()
            if lit_l and lit_l in lowered and len(lit) > best_len:
                best_para = para
                best_len = len(lit)
    if best_para:
        return best_para, "display_literal"

    for section in analysis_sections:
        para = str(section.get("paragraph") or section.get("name") or "")
        role = str(section.get("role") or section.get("description") or "")
        if para and role.lower() in lowered:
            return para, "analysis_role"
        for lit in _extract_quoted_literals(role):
            if lit.lower() in lowered:
                return para or None, "analysis_role"

    return None, "none"


def _java_method_hints_for_paragraph(paragraph: str, java_source: Optional[str]) -> List[str]:
    if not java_source or not paragraph:
        return []
    base = paragraph.replace("-", "_")
    candidates = {paragraph, base, base.lower(), base.title().replace("_", "")}
    found: List[str] = []
    for cand in candidates:
        if cand and re.search(rf"\b{re.escape(cand)}\b", java_source, re.IGNORECASE):
            found.append(cand)
    return found


def classify_failure_kind(
    cobol_lines: List[str],
    java_lines: List[str],
    first_idx: Optional[int],
) -> str:
    if first_idx is None:
        return "content_mismatch"

    cl = cobol_lines[first_idx] if first_idx < len(cobol_lines) else ""
    jl = java_lines[first_idx] if first_idx < len(java_lines) else ""

    c_nonempty = [ln for ln in cobol_lines if ln.strip()]
    j_nonempty = [ln for ln in java_lines if ln.strip()]
    if c_nonempty and j_nonempty and sorted(c_nonempty) == sorted(j_nonempty) and c_nonempty != j_nonempty:
        return "order_mismatch"

    if cl.strip() and not jl.strip():
        if len(java_lines) < len(cobol_lines):
            return "missing_java_line"
        return "content_mismatch"
    if jl.strip() and not cl.strip():
        if len(cobol_lines) < len(java_lines):
            return "extra_java_line"
        return "missing_cobol_line"
    if len(cobol_lines) != len(java_lines):
        if len(java_lines) > len(cobol_lines):
            return "extra_java_line"
        return "extra_cobol_line"

    combined = f"{cl} {jl}".lower()
    if any(marker in combined for marker in _MENU_MARKERS):
        return "menu_branch_mismatch"

    return "content_mismatch"


def _enrich_highlights(
    highlights: List[Dict[str, Any]],
    display_map: Mapping[str, List[str]],
    paragraphs: Sequence[str],
    analysis_sections: Sequence[Mapping[str, Any]],
    failure_kind: str,
) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for row in highlights:
        cobol_text = str(row.get("cobol") or "")
        java_text = str(row.get("java") or "")
        probe = cobol_text if cobol_text.strip() else java_text
        para, method = _score_paragraph_for_text(probe, display_map, analysis_sections)
        if para is None and paragraphs:
            line_no = int(row.get("line") or 1) - 1
            para = _paragraph_by_proportional_index(paragraphs, line_no, max(len(paragraphs), 1))
            method = "line_proportion"
        enriched.append(
            {
                **row,
                "failure_kind": failure_kind,
                "likely_paragraph": para,
                "attribution_method": method,
            }
        )
    return enriched


def _build_paragraph_breakdown(
    paragraphs: Sequence[str],
    affected: Sequence[str],
    display_map: Mapping[str, List[str]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for para in paragraphs:
        status = "affected" if para in affected else "ok"
        rows.append(
            {
                "paragraph": para,
                "status": status,
                "display_literals": display_map.get(para, [])[:5],
            }
        )
    for para in affected:
        if para not in paragraphs:
            rows.append({"paragraph": para, "status": "affected", "display_literals": display_map.get(para, [])[:5]})
    return rows


_BLOCKING_EXEC_STATUSES = frozenset({"compile_failure", "runtime_failure", "timeout", "no_stdout"})


def _execution_blocked_mapping(
    *,
    scenario_id: str,
    scenario_label: str,
    cobol_execution: Optional[Mapping[str, Any]],
    java_execution: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    cob_st = str((cobol_execution or {}).get("execution_status") or "")
    jav_st = str((java_execution or {}).get("execution_status") or "")
    parts: List[str] = []
    if cob_st == "compile_failure":
        parts.append("COBOL compile failed")
    elif cob_st == "runtime_failure":
        parts.append("COBOL runtime failed")
    elif cob_st in ("timeout", "no_stdout"):
        parts.append(f"COBOL {cob_st.replace('_', ' ')}")
    if jav_st == "compile_failure":
        parts.append("Java compile failed")
    elif jav_st == "runtime_failure":
        parts.append("Java runtime failed")
    elif jav_st in ("timeout", "no_stdout"):
        parts.append(f"Java {jav_st.replace('_', ' ')}")
    what_failed = (
        "Behavioral comparison blocked because " + " and ".join(parts) + "."
        if parts
        else "Behavioral comparison blocked because execution did not produce comparable stdout."
    )
    return {
        "scenario_id": scenario_id,
        "scenario_label": scenario_label,
        "failure_kind": "execution_error",
        "what_failed": what_failed,
        "where_failed": "compile/runtime execution",
        "why_likely": (
            "Stdout parity is not valid until both COBOL and Java compile and run successfully. "
            "Fix compile/runtime errors or provide scripted stdin for interactive programs."
        ),
        "retry_hint": "Fix conversion compile/runtime issues, then re-run behavioral testing.",
        "likely_paragraph": None,
        "attribution_method": "execution_status",
        "affected_paragraphs": [],
        "retry_scope": "",
        "highlights": [],
        "failed_test": {
            "id": f"BEH_{scenario_id}",
            "scenario_id": scenario_id,
            "description": what_failed,
            "severity": "critical",
            "failure_kind": "execution_error",
            "likely_paragraph": None,
        },
        "explanation": what_failed,
        "paragraph_breakdown": [],
    }


def map_scenario_failure(
    *,
    scenario_id: str,
    scenario_label: str,
    diff: Mapping[str, Any],
    scenario_inputs: Mapping[str, str],
    parser_output: Optional[Mapping[str, Any]],
    analysis_output: Optional[Mapping[str, Any]],
    cobol_source: Optional[str],
    java_source: Optional[str],
    cobol_execution: Optional[Mapping[str, Any]] = None,
    java_execution: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Produce mapping for one scenario when diff shows divergence or execution failed."""
    if diff.get("parity_blocked"):
        return _execution_blocked_mapping(
            scenario_id=scenario_id,
            scenario_label=scenario_label,
            cobol_execution=cobol_execution,
            java_execution=java_execution,
        )

    cob_st = str((cobol_execution or {}).get("execution_status") or "")
    jav_st = str((java_execution or {}).get("execution_status") or "")
    if cob_st in _BLOCKING_EXEC_STATUSES or jav_st in _BLOCKING_EXEC_STATUSES:
        return _execution_blocked_mapping(
            scenario_id=scenario_id,
            scenario_label=scenario_label,
            cobol_execution=cobol_execution,
            java_execution=java_execution,
        )

    diverging = int(diff.get("differing_lines") or 0)
    exec_failed = False
    if cobol_execution and cobol_execution.get("exit_code") not in (0, None):
        if cobol_execution.get("mode") == "executed" and cobol_execution.get("exit_code") != 0:
            exec_failed = True
    if java_execution and java_execution.get("exit_code") not in (0, None):
        if java_execution.get("mode") == "executed" and java_execution.get("exit_code") != 0:
            exec_failed = True

    if diverging == 0 and not exec_failed:
        return None

    paragraphs = _paragraph_names(parser_output)
    analysis_sections = _analysis_sections(analysis_output)
    display_map = build_display_literals_by_paragraph(parser_output, cobol_source)

    cobol_norm = str(diff.get("cobol_normalized") or "")
    java_norm = str(diff.get("java_normalized") or "")
    cobol_lines = cobol_norm.split("\n") if cobol_norm else []
    java_lines = java_norm.split("\n") if java_norm else []
    first_idx = diff.get("first_mismatch_index")

    failure_kind = "execution_error" if exec_failed and diverging == 0 else classify_failure_kind(
        cobol_lines, java_lines, first_idx if isinstance(first_idx, int) else None
    )

    probe_line = ""
    if isinstance(first_idx, int):
        probe_line = cobol_lines[first_idx] if first_idx < len(cobol_lines) else ""
        if not probe_line.strip() and first_idx < len(java_lines):
            probe_line = java_lines[first_idx]

    likely_para, method = _score_paragraph_for_text(probe_line, display_map, analysis_sections)
    if likely_para is None and paragraphs and isinstance(first_idx, int):
        likely_para = _paragraph_by_proportional_index(paragraphs, first_idx, max(len(cobol_lines), len(java_lines), 1))
        method = "line_proportion"

    affected: List[str] = []
    if likely_para:
        affected.append(likely_para)

    highlights = list(diff.get("highlights") or [])
    enriched_highlights = _enrich_highlights(
        highlights, display_map, paragraphs, analysis_sections, failure_kind
    )
    for row in enriched_highlights:
        lp = row.get("likely_paragraph")
        if lp and lp not in affected:
            affected.append(str(lp))

    retry_scope = affected[0] if affected else ""
    java_hints = _java_method_hints_for_paragraph(retry_scope, java_source) if retry_scope else []

    what_failed = _FAILURE_LABELS.get(failure_kind, "Behavioral output mismatch")
    where_failed = (
        f"stdout line {int(first_idx) + 1}" if isinstance(first_idx, int) else "stdout comparison"
    )
    if likely_para:
        where_failed += f" (likely paragraph {likely_para})"

    why_parts: List[str] = []
    if failure_kind == "order_mismatch":
        why_parts.append(
            "The same messages appear in COBOL and Java output but in a different sequence, "
            "which often indicates branch or menu handling was converted in the wrong order."
        )
    elif failure_kind == "menu_branch_mismatch":
        why_parts.append(
            "Menu, prompt, or validation text differs, suggesting the Java path for user input "
            "or EVALUATE/IF dispatch does not match the COBOL program."
        )
    elif failure_kind in ("missing_java_line", "extra_java_line", "missing_cobol_line", "extra_cobol_line"):
        why_parts.append(
            "Line count or blank-line structure differs between COBOL and Java stdout, "
            "so a DISPLAY or STOP/RUN path may be missing or duplicated in the conversion."
        )
    else:
        why_parts.append(
            "Normalized stdout text differs at the first mismatch; the Java conversion likely "
            "altered literals, formatting, or business wording for this path."
        )
    if method == "display_literal":
        why_parts.append("Attribution matched a DISPLAY literal in parser output to this stdout line.")
    elif method == "line_proportion":
        why_parts.append(
            "Parser DISPLAY mapping was unavailable; paragraph estimated from output line position."
        )

    retry_hint = (
        f"Re-convert and re-test paragraph {retry_scope} and its DISPLAY/ACCEPT paths."
        if retry_scope
        else "Re-run conversion for the procedure section that owns the mismatched stdout."
    )
    if java_hints:
        retry_hint += f" Check Java methods: {', '.join(java_hints[:3])}."

    if scenario_inputs:
        inputs_desc = ", ".join(f"{k}={v}" for k, v in list(scenario_inputs.items())[:4])
        why_parts.append(f"Scenario inputs: {inputs_desc}.")

    explanation = (
        f"{what_failed} at {where_failed}. "
        + " ".join(why_parts)
        + f" Recommended retry: {retry_hint}"
    )

    severity = "critical" if failure_kind in ("execution_error", "missing_java_line") else "high"
    if failure_kind == "order_mismatch":
        severity = "high"

    return {
        "scenario_id": scenario_id,
        "scenario_label": scenario_label,
        "failure_kind": failure_kind,
        "what_failed": what_failed,
        "where_failed": where_failed,
        "why_likely": " ".join(why_parts),
        "retry_hint": retry_hint,
        "likely_paragraph": likely_para,
        "attribution_method": method,
        "affected_paragraphs": affected,
        "retry_scope": retry_scope,
        "highlights": enriched_highlights,
        "failed_test": {
            "id": f"BEH_{scenario_id}",
            "scenario_id": scenario_id,
            "description": f"{what_failed} — {where_failed}",
            "severity": severity,
            "failure_kind": failure_kind,
            "likely_paragraph": likely_para,
        },
        "explanation": explanation,
        "paragraph_breakdown": _build_paragraph_breakdown(paragraphs, affected, display_map),
    }


def enrich_behavioral_result(
    result: MutableMapping[str, Any],
    *,
    parser_output: Optional[Mapping[str, Any]] = None,
    analysis_output: Optional[Mapping[str, Any]] = None,
    cobol_source: Optional[str] = None,
    java_source: Optional[str] = None,
) -> MutableMapping[str, Any]:
    """
    Enrich a behavioral diff result with failure_reason, affected_paragraphs,
    retry_scope, failed_tests, and annotated highlights.
    """
    status = str(result.get("status") or "")
    diff_summary = result.get("diff_summary") if isinstance(result.get("diff_summary"), dict) else {}
    if result.get("parity_blocked") or diff_summary.get("parity_blocked"):
        if status != "failed":
            result["failed_tests"] = []
        result["affected_paragraphs"] = []
        result["retry_scope"] = ""
        if not result.get("failure_reason"):
            result["failure_reason"] = (
                "Behavioral comparison blocked because COBOL/Java execution did not produce "
                "comparable stdout."
            )
        return result

    if status == "not_run":
        result["affected_paragraphs"] = []
        result["retry_scope"] = ""
        if not result.get("failure_reason"):
            result["failure_reason"] = (
                "Behavioral comparison did not run — no stdout lines were captured."
            )
        return result

    if status == "passed" and not result.get("failed_tests"):
        result["affected_paragraphs"] = []
        result["retry_scope"] = ""
        result["failure_reason"] = None
        if isinstance(result.get("diff_summary"), dict):
            result["diff_summary"]["paragraph_breakdown"] = _build_paragraph_breakdown(
                _paragraph_names(parser_output),
                [],
                build_display_literals_by_paragraph(parser_output, cobol_source),
            )
        return result

    scenarios = (result.get("input_set") or {}).get("scenarios") or []
    scenario_by_id = {str(s.get("id")): s for s in scenarios if isinstance(s, dict)}
    exec_details = result.get("execution_details") or []

    all_failed_tests: List[Dict[str, Any]] = []
    all_affected: List[str] = []
    all_highlights: List[Dict[str, Any]] = []
    explanations: List[str] = []
    breakdown_accum: List[Dict[str, Any]] = []

    for detail in exec_details:
        if not isinstance(detail, dict):
            continue
        sid = str(detail.get("scenario_id") or "default")
        sc_meta = scenario_by_id.get(sid) or {}
        label = str(sc_meta.get("label") or sid)
        inputs = sc_meta.get("inputs") if isinstance(sc_meta.get("inputs"), dict) else {}
        mapping = map_scenario_failure(
            scenario_id=sid,
            scenario_label=label,
            diff=detail.get("diff") or {},
            scenario_inputs=inputs,
            parser_output=parser_output,
            analysis_output=analysis_output,
            cobol_source=cobol_source,
            java_source=java_source,
            cobol_execution=detail.get("cobol_execution"),
            java_execution=detail.get("java_execution"),
        )
        if not mapping:
            continue
        all_failed_tests.append(mapping["failed_test"])
        for para in mapping["affected_paragraphs"]:
            if para not in all_affected:
                all_affected.append(para)
        all_highlights.extend(mapping["highlights"])
        explanations.append(mapping["explanation"])
        breakdown_accum.extend(mapping["paragraph_breakdown"])

    if not all_failed_tests and result.get("failed_tests"):
        diff_summary = result.get("diff_summary") or {}
        aggregate_mapping = map_scenario_failure(
            scenario_id="aggregate",
            scenario_label="Combined output",
            diff=diff_summary,
            scenario_inputs={},
            parser_output=parser_output,
            analysis_output=analysis_output,
            cobol_source=cobol_source,
            java_source=java_source,
        )
        if aggregate_mapping:
            all_failed_tests = [aggregate_mapping["failed_test"]]
            all_affected = list(aggregate_mapping["affected_paragraphs"])
            all_highlights = aggregate_mapping["highlights"]
            explanations = [aggregate_mapping["explanation"]]
            breakdown_accum = aggregate_mapping["paragraph_breakdown"]

    result["failed_tests"] = all_failed_tests
    result["affected_paragraphs"] = all_affected
    result["retry_scope"] = all_affected[0] if all_affected else ""

    if explanations:
        result["failure_reason"] = explanations[0]
        if len(explanations) > 1:
            result["failure_reason"] += f" (+{len(explanations) - 1} more scenario(s) with drift.)"
    elif result.get("status") != "passed":
        result["failure_reason"] = "Behavioral equivalence check failed; see diff highlights."

    if isinstance(result.get("diff_summary"), dict):
        ds = result["diff_summary"]
        if all_highlights:
            ds["highlights"] = all_highlights[:50]
        if breakdown_accum:
            seen = set()
            unique_breakdown: List[Dict[str, Any]] = []
            for row in breakdown_accum:
                key = row.get("paragraph")
                if key in seen:
                    continue
                seen.add(key)
                unique_breakdown.append(row)
            ds["paragraph_breakdown"] = unique_breakdown
        else:
            ds["paragraph_breakdown"] = _build_paragraph_breakdown(
                _paragraph_names(parser_output),
                all_affected,
                build_display_literals_by_paragraph(parser_output, cobol_source),
            )

    result["failure_mapping"] = {
        "scenarios_mapped": len(all_failed_tests),
        "primary_retry_scope": result["retry_scope"],
        "attribution": "deterministic_heuristics",
    }
    return result
