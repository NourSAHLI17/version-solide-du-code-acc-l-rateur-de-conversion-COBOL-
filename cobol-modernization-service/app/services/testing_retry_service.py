"""Orchestrate scoped conversion retry and re-validation for the testing agent."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.behavioral_diff_runner import run_behavioral_diff
from app.services.business_rules_test_generator import generate_business_rules_tests
from app.services.edge_case_test_generator import generate_edge_case_tests
from app.services.paragraph_scope_service import ParagraphScopeService
from app.services.pipeline_service import PipelineService
from app.services.testing_retry_scope_service import TestingRetryScopeService
from app.services.testing_final_decision_service import TestingFinalDecisionService
from app.services.testing_save_gate_service import evaluate_save_candidate
from app.services.unit_test_generator import generate_unit_tests

_pipeline = PipelineService()
_scope_service = TestingRetryScopeService()
_paragraph_service = ParagraphScopeService()
_final_decision = TestingFinalDecisionService()


def _analysis_to_json_str(analysis: Any) -> str:
    if isinstance(analysis, str):
        return analysis
    return json.dumps(analysis, ensure_ascii=False)


def _extract_score(conversion_result: Dict[str, Any]) -> Optional[int]:
    raw = conversion_result.get("conversion_score")
    if isinstance(raw, dict):
        for key in ("total", "total_score", "score"):
            if key in raw and raw[key] is not None:
                try:
                    return int(raw[key])
                except (TypeError, ValueError):
                    pass
    if isinstance(raw, (int, float)):
        return int(raw)
    return None


def _collect_business_rules(analysis_json: dict) -> List[Any]:
    rules: List[Any] = []
    analysis = analysis_json if isinstance(analysis_json, dict) else {}
    for item in analysis.get("business_rules") or []:
        rules.append(item)
    for sec in analysis.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        for rule in sec.get("business_rules") or []:
            rules.append(rule)
    return rules


def retry_conversion_scope(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Re-run conversion for a narrowed scope (paragraph-aware when safe), re-validate,
    and return save gating metadata.
    """
    program_name = str(payload.get("program_name") or "Program")
    cobol_source = str(payload.get("cobol_source") or "")
    parser_json = payload.get("parser_json") or {}
    analysis_json = payload.get("analysis_json") or {}
    java_source = str(payload.get("java_source") or "")
    failed_tests = list(payload.get("failed_tests") or [])
    diff_summary = dict(payload.get("diff_summary") or {})
    previous_score = payload.get("previous_score")
    scripted_input = str(payload.get("scripted_input") or "")
    run_validation_loop = bool(payload.get("run_validation_loop"))

    requested_scope = _scope_service.derive_retry_scope(
        parser_json,
        analysis_json,
        java_source,
        failed_tests,
        diff_summary,
        scope_type=payload.get("scope_type"),
        scope_id=payload.get("scope_id"),
    )

    conversion_ctx = _paragraph_service.prepare_conversion_payload(
        parser_json if isinstance(parser_json, dict) else {},
        analysis_json if isinstance(analysis_json, dict) else {},
        java_source,
        cobol_source,
        requested_scope,
    )

    actual_scope = conversion_ctx["retry_scope_actual"]
    narrowed_parser = conversion_ctx["parser_json"]
    narrowed_analysis = conversion_ctx["analysis_json"]
    analysis_str = _analysis_to_json_str(narrowed_analysis)

    conversion_result: Dict[str, Any] = {}
    conversion_error: Optional[str] = None
    if cobol_source.strip():
        try:
            conversion_result = _pipeline.convert_cobol(
                cobol_source,
                narrowed_parser if isinstance(narrowed_parser, dict) else {},
                analysis_str,
            )
        except Exception as exc:
            conversion_error = str(exc)
            conversion_result = {"java_code": java_source, "conversion_score": None}
    else:
        conversion_result = {"java_code": java_source, "conversion_score": None}
        conversion_error = "cobol_source missing — returned existing Java without re-conversion."

    new_java = str(conversion_result.get("java_code") or java_source)
    score = _extract_score(conversion_result)

    run_id = str(payload.get("run_id") or uuid.uuid4())
    diff_request = {
        "target_type": "single_file",
        "run_id": run_id,
        "program_name": program_name,
        "cobol_source": cobol_source or None,
        "java_source": new_java,
        "parser_output": narrowed_parser if isinstance(narrowed_parser, dict) else {},
        "analysis_output": narrowed_analysis,
        "scripted_input": scripted_input,
        "scenarios": payload.get("scenarios") or [],
        "fallback_mode": bool(payload.get("fallback_mode")),
        "cobol_snapshot_output": payload.get("cobol_snapshot_output"),
        "java_snapshot_output": payload.get("java_snapshot_output"),
    }
    test_result = run_behavioral_diff(diff_request)
    new_diff = dict(test_result.get("diff_summary") or {})
    new_failed = list(test_result.get("failed_tests") or [])
    behavioral_status = str(test_result.get("status") or "failed")

    unit_test_result: Optional[Dict[str, Any]] = None
    edge_test_result: Optional[Dict[str, Any]] = None
    br_test_result: Optional[Dict[str, Any]] = None

    if run_validation_loop and new_java.strip():
        unit_test_result = generate_unit_tests(
            program_name, narrowed_parser, narrowed_analysis, new_java
        )
        edge_test_result = generate_edge_case_tests(program_name, narrowed_parser, new_java)
        rules = _collect_business_rules(narrowed_analysis)
        if rules:
            br_test_result = generate_business_rules_tests(program_name, rules, new_java)

    decision_payload = {
        "program_name": program_name,
        "diff_summary": new_diff,
        "failed_tests": new_failed,
        "behavioral_status": behavioral_status,
        "conversion_score": conversion_result.get("conversion_score") or score,
        "retry_scope": actual_scope,
        "business_rules_test_result": br_test_result,
        "edge_case_test_result": edge_test_result,
        "unit_test_result": unit_test_result,
        "test_result": test_result,
    }
    final_decision = _final_decision.build_final_decision(decision_payload)
    save_gate = final_decision.get("save_gate") or evaluate_save_candidate(
        score=final_decision.get("reliability_score") or score,
        diff_summary=new_diff,
        failed_tests=new_failed,
        behavioral_status=behavioral_status,
        retry_scope=actual_scope,
        previous_score=int(previous_score) if previous_score is not None else None,
    )

    reliability_score = int(final_decision.get("reliability_score") or 0)
    score_before = int(previous_score) if previous_score is not None else None
    score_delta = (
        (reliability_score - score_before) if score_before is not None else None
    )

    return {
        "program_name": program_name,
        "retry_scope": actual_scope,
        "requested_scope": conversion_ctx["requested_scope"],
        "actual_scope": conversion_ctx["actual_scope"],
        "scope_widened": conversion_ctx["scope_widened"],
        "widen_reason": conversion_ctx.get("widen_reason"),
        "included_paragraphs": conversion_ctx["included_paragraphs"],
        "excluded_paragraphs": conversion_ctx["excluded_paragraphs"],
        "retry_summary": conversion_ctx["retry_summary"],
        "paragraph_slice": conversion_ctx.get("paragraph_slice"),
        "conversion_result": {
            "java_code": new_java,
            "conversion_score": conversion_result.get("conversion_score"),
            "error": conversion_error,
        },
        "test_result": test_result,
        "diff_summary": new_diff,
        "failed_tests": new_failed,
        "score": score,
        "reliability_score": reliability_score,
        "decision_state": final_decision.get("decision_state"),
        "save_eligible": final_decision.get("save_eligible", save_gate.get("save_eligible")),
        "score_breakdown": final_decision.get("score_breakdown"),
        "reason_summary": final_decision.get("reason_summary"),
        "blockers": final_decision.get("blockers", []),
        "final_decision": final_decision,
        "score_before": score_before,
        "score_delta": score_delta,
        "ready_to_save": save_gate.get("ready_to_save", False),
        "save_state": save_gate.get("save_state", "retry_recommended"),
        "save_gate": save_gate,
        "unit_test_result": unit_test_result,
        "edge_test_result": edge_test_result,
        "business_rules_test_result": br_test_result,
        "retried_at": datetime.now(timezone.utc).isoformat(),
    }


def build_final_decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Compute reliability score and trust decision from validation artifacts."""
    return _final_decision.build_final_decision(payload)


def derive_scope_only(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return retry scope without executing conversion."""
    scope = _scope_service.derive_retry_scope(
        payload.get("parser_json") or {},
        payload.get("analysis_json") or {},
        str(payload.get("java_source") or ""),
        list(payload.get("failed_tests") or []),
        dict(payload.get("diff_summary") or {}),
        scope_type=payload.get("scope_type"),
        scope_id=payload.get("scope_id"),
    )
    return {"retry_scope": scope}
