"""Final reliability score from behavioral diff and generated test artifacts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.reliability_scoring_stability import (
    build_reliability_fingerprint,
    canonical_conversion_points,
    canonical_diff_summary,
    detect_score_drift,
    is_perfect_behavioral_pass,
    register_canonical_score,
)

MAX_BEHAVIORAL = 40
MAX_BUSINESS_RULES = 20
MAX_EDGE_CASES = 15
MAX_UNIT_TESTS = 15
MAX_RETRY_STABILITY = 10

RELIABILITY_READY = 85
RELIABILITY_BORDERLINE = 70


def _clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, value))


def _diff_match_rate(diff_summary: Dict[str, Any]) -> float:
    canon = canonical_diff_summary(diff_summary)
    compared = canon["lines_compared"]
    matched = canon["lines_matched"]
    if compared > 0:
        return (matched / compared) * 100.0
    diff_pct = canon["diff_percentage_milli"] / 1000.0
    if diff_pct > 0:
        return max(0.0, 100.0 - diff_pct)
    return 0.0


def _score_behavioral(
    diff_summary: Dict[str, Any],
    behavioral_status: str,
    failed_tests: List[Dict[str, Any]],
) -> int:
    status = str(behavioral_status or "failed").lower()
    match_rate = _diff_match_rate(diff_summary)
    failed_count = len(failed_tests or [])

    canon = canonical_diff_summary(diff_summary)
    compared = canon["lines_compared"]
    matched = canon["lines_matched"]
    if status == "not_run" or compared <= 0:
        return 0
    if status == "passed" and failed_count == 0:
        if matched >= compared and canon["lines_diverged"] == 0:
            return MAX_BEHAVIORAL
        if match_rate >= 98:
            return MAX_BEHAVIORAL
        if match_rate >= 90:
            return 36
        return 32
    if status == "partial":
        return _clamp(int(match_rate * 0.35))
    if failed_count > 0:
        return _clamp(int(match_rate * 0.25))
    return _clamp(int(match_rate * 0.3))


def _score_generated_tests(
    result: Optional[Dict[str, Any]],
    max_points: int,
    *,
    artifacts_ready: bool = False,
    perfect_pass: bool = False,
) -> int:
    """
  Award generated-test layer points from stable tiers (not raw count alone).

  ``artifacts_ready`` means the workspace can run that layer; it must not score
  lower than a partial ``test_count`` (e.g. 4 tests → 18) on a later rerun.
    """
    if artifacts_ready or perfect_pass:
        return max_points
    count = 0
    if result and isinstance(result, dict):
        count = int(result.get("test_count") or 0)
    if count <= 0:
        return 0
    if count >= 5:
        return max_points
    # Stable tier table (order-independent, no float scaling).
    tier_by_count = {1: 10, 2: 14, 3: 17, 4: 19}
    return _clamp(tier_by_count.get(count, max_points - 1))


def _score_retry_stability(
    behavioral_status: str,
    failed_tests: List[Dict[str, Any]],
    retry_scope: Optional[Dict[str, Any]],
    *,
    perfect_pass: bool = False,
) -> int:
    status = str(behavioral_status or "failed").lower()
    failed_count = len(failed_tests or [])
    if status == "passed" and failed_count == 0:
        # Advisory retry_scope must not reduce a clean passed run.
        if perfect_pass:
            return MAX_RETRY_STABILITY
        pts = MAX_RETRY_STABILITY
        if retry_scope and str(retry_scope.get("scope_type") or "") not in ("", "program"):
            pts = max(pts - 2, 6)
        return pts
    if status == "partial":
        return 5
    return 0


class ReliabilityScoreService:
    """Compute trustworthiness score from validation outputs."""

    def calculate_reliability_score(self, payload: dict) -> dict:
        program_name = str(payload.get("program_name") or "Program")
        diff_summary = canonical_diff_summary(dict(payload.get("diff_summary") or {}))
        failed_tests = list(payload.get("failed_tests") or [])
        behavioral_status = str(
            payload.get("behavioral_status")
            or payload.get("status")
            or (payload.get("behavioral_result") or {}).get("status")
            or "failed"
        ).lower()
        compared_lines = diff_summary["lines_compared"]
        if behavioral_status == "not_run" and compared_lines > 0:
            diverged = int(
                diff_summary.get("lines_diverged")
                or diff_summary.get("differing_lines")
                or 0
            )
            failed_count = len(failed_tests or [])
            if failed_count > 0:
                behavioral_status = "failed"
            elif diverged > 0:
                behavioral_status = "partial"
            else:
                behavioral_status = "passed"

        artifacts = payload.get("validation_artifacts") or {}
        br_ready = bool(
            payload.get("business_rules_artifacts_ready")
            or artifacts.get("business_rules_ready")
        )
        ec_ready = bool(
            payload.get("edge_cases_artifacts_ready") or artifacts.get("edge_cases_ready")
        )
        unit_ready = bool(
            payload.get("unit_tests_artifacts_ready") or artifacts.get("unit_tests_ready")
        )

        perfect_pass = is_perfect_behavioral_pass(
            behavioral_status, failed_tests, diff_summary
        )

        breakdown = {
            "behavioral_diff": _score_behavioral(diff_summary, behavioral_status, failed_tests),
            "business_rules": _score_generated_tests(
                payload.get("business_rules_test_result"),
                MAX_BUSINESS_RULES,
                artifacts_ready=br_ready,
                perfect_pass=perfect_pass,
            ),
            "edge_cases": _score_generated_tests(
                payload.get("edge_case_test_result"),
                MAX_EDGE_CASES,
                artifacts_ready=ec_ready,
                perfect_pass=perfect_pass,
            ),
            "unit_tests": _score_generated_tests(
                payload.get("unit_test_result"),
                MAX_UNIT_TESTS,
                artifacts_ready=unit_ready,
                perfect_pass=perfect_pass,
            ),
            "retry_stability": _score_retry_stability(
                behavioral_status,
                failed_tests,
                payload.get("retry_scope"),
                perfect_pass=perfect_pass,
            ),
        }

        conv_pts = canonical_conversion_points(payload.get("conversion_score"))
        if conv_pts is not None:
            breakdown["conversion_layer"] = conv_pts

        reliability_score = _clamp(sum(breakdown.values()))

        fingerprint = build_reliability_fingerprint(payload)
        drift = detect_score_drift(fingerprint, reliability_score, breakdown)
        if drift is None:
            register_canonical_score(fingerprint, reliability_score, breakdown)

        blockers: List[str] = []
        if behavioral_status == "not_run":
            blockers.append(
                "Behavioral diff did not run (no stdout captured — install cobc/javac or enable fallback snapshots)."
            )
        elif behavioral_status != "passed":
            blockers.append(f"Behavioral diff status is {behavioral_status}.")
        compared_lines = diff_summary["lines_compared"]
        if compared_lines <= 0 and behavioral_status != "not_run":
            blockers.append("Behavioral diff compared 0 stdout lines.")
        if failed_tests:
            blockers.append(f"{len(failed_tests)} behavioral test(s) failed.")
        diff_pct = diff_summary["diff_percentage_milli"] / 1000.0
        if diff_pct > 5:
            blockers.append(f"Stdout diff {diff_pct:.1f}% exceeds 5% threshold.")

        if reliability_score >= RELIABILITY_READY and not blockers:
            decision_state = "ready_to_save"
            reason_summary = "High match rate and validation signals support trusting this conversion."
        elif reliability_score >= RELIABILITY_BORDERLINE:
            decision_state = "needs_more_validation"
            reason_summary = (
                "Conversion is promising but confidence is not yet strong enough to save without review."
            )
        else:
            decision_state = "retry_recommended"
            reason_summary = "Validation signals indicate the conversion needs scoped retry or inspection."

        result: Dict[str, Any] = {
            "program_name": program_name,
            "reliability_score": reliability_score,
            "decision_state": decision_state,
            "save_eligible": decision_state == "ready_to_save",
            "score_breakdown": breakdown,
            "reason_summary": reason_summary,
            "blockers": blockers,
            "score_fingerprint": fingerprint,
            "perfect_behavioral_pass": perfect_pass,
        }
        if drift:
            result["score_drift"] = drift
        return result
