"""Single source of truth for whether a testing run can be saved to history."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.scoring_service import conversion_decision_from_total

SCORE_SAVE_THRESHOLD = 90
RELIABILITY_SAVE_THRESHOLD = 85
DIFF_SAVE_MAX_PERCENT = 5.0


def evaluate_save_candidate(
    *,
    score: Optional[int],
    diff_summary: Dict[str, Any],
    failed_tests: List[Dict[str, Any]],
    behavioral_status: str,
    retry_scope: Optional[Dict[str, Any]] = None,
    previous_score: Optional[int] = None,
) -> Dict[str, Any]:
    """Legacy helper — prefer TestingSaveGateService.evaluate_save_gate."""
    return TestingSaveGateService().evaluate_save_gate(
        {
            "conversion_score": score,
            "reliability_score": score,
            "diff_summary": diff_summary,
            "failed_tests": failed_tests,
            "behavioral_status": behavioral_status,
            "retry_scope": retry_scope,
            "previous_score": previous_score,
        }
    )


class TestingSaveGateService:
    """Evaluate save eligibility from reliability and validation signals."""

    def evaluate_save_gate(self, payload: dict) -> dict:
        reliability = payload.get("reliability_score")
        conversion = payload.get("conversion_score")
        if isinstance(conversion, dict):
            conversion = conversion.get("total") or conversion.get("total_score")

        primary: Optional[int] = None
        if reliability is not None:
            try:
                primary = int(reliability)
            except (TypeError, ValueError):
                primary = None
        if primary is None and conversion is not None:
            try:
                primary = int(conversion)
            except (TypeError, ValueError):
                primary = None

        diff_summary = dict(payload.get("diff_summary") or {})
        failed_tests = list(payload.get("failed_tests") or [])
        behavioral_status = str(payload.get("behavioral_status") or "failed").lower()
        previous_score = payload.get("previous_score")
        retry_scope = payload.get("retry_scope")
        test_summary = payload.get("test_summary") or {}

        diff_pct = float(diff_summary.get("diff_percentage") or 0)
        lines_diverged = int(
            diff_summary.get("lines_diverged") or diff_summary.get("differing_lines") or 0
        )
        failed_count = len(failed_tests)
        total = int(primary) if primary is not None else 0

        reasons: List[str] = []
        blockers: List[str] = []

        if behavioral_status == "passed" and failed_count == 0:
            reasons.append("Behavioral diff passed with no failed tests.")
        elif behavioral_status == "partial":
            blockers.append("Behavioral diff is partial — not fully equivalent.")
        else:
            blockers.append("Behavioral diff failed.")

        if failed_count > 0:
            blockers.append(f"{failed_count} failed test(s) remain.")

        if diff_pct > DIFF_SAVE_MAX_PERCENT:
            blockers.append(f"Diff {diff_pct:.1f}% exceeds {DIFF_SAVE_MAX_PERCENT}% threshold.")
        elif lines_diverged > 0 and behavioral_status != "passed":
            blockers.append(f"{lines_diverged} stdout line(s) still diverge.")

        threshold = RELIABILITY_SAVE_THRESHOLD if reliability is not None else SCORE_SAVE_THRESHOLD
        if total < threshold:
            blockers.append(f"Reliability score {total} is below save threshold {threshold}.")
        elif reliability is None and conversion_decision_from_total(total) != "auto_approve":
            blockers.append("Conversion score suggests manual review before save.")

        if previous_score is not None and total < int(previous_score):
            blockers.append(f"Score regressed ({previous_score} → {total}).")

        if retry_scope and blockers:
            scope_type = str(retry_scope.get("scope_type") or "")
            if scope_type and scope_type != "program":
                blockers.append(
                    f"Scoped issues may remain ({scope_type}: {retry_scope.get('scope_id')})."
                )

        optional_tests = ["business_rules_pass", "edge_cases_pass", "unit_tests_pass"]
        if test_summary and not any(test_summary.get(k) for k in optional_tests):
            if total < RELIABILITY_SAVE_THRESHOLD + 5:
                reasons.append(
                    "Optional generated test suites were not run; manual review recommended."
                )

        if not blockers and total >= RELIABILITY_SAVE_THRESHOLD:
            save_state = "ready_to_save"
            reason_summary = "All tests pass and diff is within threshold."
        elif total >= 70 and behavioral_status == "passed" and failed_count == 0:
            save_state = "needs_more_validation"
            reason_summary = "Passed behavioral diff but reliability is borderline."
        else:
            save_state = "retry_recommended"
            reason_summary = "Validation did not meet trust thresholds."

        return {
            "save_eligible": save_state == "ready_to_save",
            "save_state": save_state,
            "ready_to_save": save_state == "ready_to_save",
            "score_threshold": threshold,
            "diff_threshold_percent": DIFF_SAVE_MAX_PERCENT,
            "reasons": reasons,
            "blockers": blockers,
            "reason_summary": reason_summary,
            "conversion_decision": conversion_decision_from_total(total) if total else "reconversion_required",
        }
