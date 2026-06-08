"""Merge all validation signals into one trust decision for the testing agent."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.reliability_score_service import ReliabilityScoreService
from app.services.testing_retry_scope_service import TestingRetryScopeService
from app.services.testing_save_gate_service import TestingSaveGateService

_reliability = ReliabilityScoreService()
_save_gate = TestingSaveGateService()
_scope = TestingRetryScopeService()

_LAYERED_BEHAVIORAL_KEYS = (
    "qscore",
    "layer_scores",
    "primary_failure_layer",
    "run_diagnostics",
)


def extract_layered_behavioral_fields(payload: dict) -> Dict[str, Any]:
    """
    Passthrough layered diagnostic fields when present on the request or nested behavioral run.

    Does not compute scores; only surfaces data already produced by the behavioral diff runner.
    """
    attachment: Dict[str, Any] = {}
    sources: List[dict] = [payload]
    for nest_key in ("behavioral_result", "test_result", "behavioral_run"):
        nested = payload.get(nest_key)
        if isinstance(nested, dict):
            sources.append(nested)
    for src in sources:
        for field in _LAYERED_BEHAVIORAL_KEYS:
            if field in src and field not in attachment:
                attachment[field] = src[field]
    return attachment


def _bucket_status(result: Optional[Dict[str, Any]], artifacts_ready: bool) -> str:
    if result and int(result.get("test_count") or 0) > 0:
        return "pass"
    if artifacts_ready:
        return "ready"
    return "unavailable"


def _test_summary(
    behavioral_status: str,
    failed_tests: List[Dict[str, Any]],
    diff_summary: Dict[str, Any],
    br_result: Optional[Dict[str, Any]],
    ec_result: Optional[Dict[str, Any]],
    unit_result: Optional[Dict[str, Any]],
    *,
    br_ready: bool = False,
    ec_ready: bool = False,
    unit_ready: bool = False,
) -> Dict[str, Any]:
    compared = int(diff_summary.get("lines_compared") or 0)
    behavioral_pass = (
        behavioral_status == "passed"
        and behavioral_status != "not_run"
        and len(failed_tests) == 0
        and compared > 0
    )
    br_status = _bucket_status(br_result, br_ready)
    ec_status = _bucket_status(ec_result, ec_ready)
    unit_status = _bucket_status(unit_result, unit_ready)
    return {
        "behavioral_pass": behavioral_pass,
        "business_rules_pass": br_status == "pass",
        "edge_cases_pass": ec_status == "pass",
        "unit_tests_pass": unit_status == "pass",
        "business_rules_status": br_status,
        "edge_cases_status": ec_status,
        "unit_tests_status": unit_status,
    }


def _artifact_flags(payload: dict) -> tuple[bool, bool, bool]:
    artifacts = payload.get("validation_artifacts") or {}
    return (
        bool(payload.get("business_rules_artifacts_ready") or artifacts.get("business_rules_ready")),
        bool(payload.get("edge_cases_artifacts_ready") or artifacts.get("edge_cases_ready")),
        bool(payload.get("unit_tests_artifacts_ready") or artifacts.get("unit_tests_ready")),
    )


def _diff_summary_view(diff_summary: Dict[str, Any]) -> Dict[str, Any]:
    compared = int(diff_summary.get("lines_compared") or 0)
    matched = int(diff_summary.get("lines_matched") or 0)
    match_rate = round(_diff_match_rate(diff_summary), 1) if compared > 0 else 0.0
    diverged = int(
        diff_summary.get("lines_diverged")
        or diff_summary.get("differing_lines")
        or max(0, compared - matched)
    )
    return {
        "match_rate": match_rate,
        "mismatch_count": diverged,
        "diff_percentage": float(diff_summary.get("diff_percentage") or 0),
    }


def _diff_match_rate(diff_summary: Dict[str, Any]) -> float:
    compared = int(diff_summary.get("lines_compared") or 0)
    matched = int(diff_summary.get("lines_matched") or 0)
    if compared > 0:
        return (matched / compared) * 100.0
    diff_pct = float(diff_summary.get("diff_percentage") or 0)
    return max(0.0, 100.0 - diff_pct) if diff_pct > 0 else 0.0


class TestingFinalDecisionService:
    """Produce the final 'Can I trust this conversion?' answer."""

    def build_final_decision(self, payload: dict) -> dict:
        program_name = str(payload.get("program_name") or "Program")
        diff_summary = dict(payload.get("diff_summary") or {})
        failed_tests = list(payload.get("failed_tests") or [])
        behavioral_status = str(payload.get("behavioral_status") or payload.get("status") or "failed").lower()
        compared_lines = int(diff_summary.get("lines_compared") or 0)
        if behavioral_status == "not_run" and compared_lines > 0:
            diverged = int(
                diff_summary.get("lines_diverged")
                or diff_summary.get("differing_lines")
                or 0
            )
            if failed_tests:
                behavioral_status = "failed"
            elif diverged > 0:
                behavioral_status = "partial"
            else:
                behavioral_status = "passed"

        retry_scope = payload.get("retry_scope")
        if not retry_scope and payload.get("derive_retry_scope"):
            retry_scope = _scope.derive_retry_scope(
                payload.get("parser_json") or {},
                payload.get("analysis_json") or {},
                str(payload.get("java_source") or ""),
                failed_tests,
                diff_summary,
            )

        br_ready, ec_ready, unit_ready = _artifact_flags(payload)
        reliability_payload = {
            "program_name": program_name,
            "diff_summary": diff_summary,
            "failed_tests": failed_tests,
            "behavioral_status": behavioral_status,
            "business_rules_test_result": payload.get("business_rules_test_result"),
            "edge_case_test_result": payload.get("edge_case_test_result"),
            "unit_test_result": payload.get("unit_test_result"),
            "validation_artifacts": payload.get("validation_artifacts"),
            "business_rules_artifacts_ready": br_ready,
            "edge_cases_artifacts_ready": ec_ready,
            "unit_tests_artifacts_ready": unit_ready,
            "conversion_score": payload.get("conversion_score"),
            "retry_scope": retry_scope,
        }
        reliability = _reliability.calculate_reliability_score(reliability_payload)

        save_gate = _save_gate.evaluate_save_gate(
            {
                "reliability_score": reliability["reliability_score"],
                "conversion_score": payload.get("conversion_score"),
                "diff_summary": diff_summary,
                "failed_tests": failed_tests,
                "behavioral_status": behavioral_status,
                "retry_scope": retry_scope,
                "test_summary": _test_summary(
                    behavioral_status,
                    failed_tests,
                    diff_summary,
                    payload.get("business_rules_test_result"),
                    payload.get("edge_case_test_result"),
                    payload.get("unit_test_result"),
                    br_ready=br_ready,
                    ec_ready=ec_ready,
                    unit_ready=unit_ready,
                ),
            }
        )

        decision_state = save_gate["save_state"]
        save_eligible = save_gate["save_eligible"]
        blockers = list(dict.fromkeys(reliability.get("blockers", []) + save_gate.get("blockers", [])))

        retry_scope_out: Optional[Dict[str, Any]] = None
        if retry_scope and isinstance(retry_scope, dict):
            retry_scope_out = {
                "scope_type": retry_scope.get("scope_type"),
                "scope_id": retry_scope.get("scope_id"),
                "scope_name": retry_scope.get("scope_name"),
                "confidence": retry_scope.get("confidence"),
                "reason": retry_scope.get("reason"),
                "affected_paragraphs": retry_scope.get("affected_paragraphs") or [],
            }

        result: Dict[str, Any] = {
            "program_name": program_name,
            "reliability_score": reliability["reliability_score"],
            "decision_state": decision_state,
            "save_eligible": save_eligible,
            "score_breakdown": reliability.get("score_breakdown"),
            "reason_summary": reliability.get("reason_summary") or save_gate.get("reason_summary"),
            "blockers": blockers,
            "diff_summary": _diff_summary_view(diff_summary),
            "test_summary": _test_summary(
                behavioral_status,
                failed_tests,
                diff_summary,
                payload.get("business_rules_test_result"),
                payload.get("edge_case_test_result"),
                payload.get("unit_test_result"),
                br_ready=br_ready,
                ec_ready=ec_ready,
                unit_ready=unit_ready,
            ),
            "retry_scope": retry_scope_out,
            "save_gate": save_gate,
        }
        result.update(extract_layered_behavioral_fields(payload))
        for meta_key in ("score_fingerprint", "perfect_behavioral_pass", "score_drift"):
            if meta_key in reliability:
                result[meta_key] = reliability[meta_key]
        return result
