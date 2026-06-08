"""Reliability score must be stable for identical AUTOPREM-style validation inputs."""

from __future__ import annotations

import copy

from app.services.reliability_score_service import ReliabilityScoreService
from app.services.reliability_scoring_stability import build_reliability_fingerprint

SVC = ReliabilityScoreService()

_PERFECT_DIFF = {
    "lines_compared": 42,
    "lines_matched": 42,
    "lines_diverged": 0,
    "diff_percentage": 0,
}

_BASE = {
    "program_name": "AUTOPREM",
    "behavioral_status": "passed",
    "failed_tests": [],
    "diff_summary": _PERFECT_DIFF,
    "derive_retry_scope": False,
    "validation_artifacts": {
        "business_rules_ready": True,
        "edge_cases_ready": True,
        "unit_tests_ready": True,
    },
    "business_rules_artifacts_ready": True,
    "edge_cases_artifacts_ready": True,
    "unit_tests_artifacts_ready": True,
}


class TestReliabilityScoreStability:
    def test_identical_payload_same_score(self):
        a = SVC.calculate_reliability_score(copy.deepcopy(_BASE))
        b = SVC.calculate_reliability_score(copy.deepcopy(_BASE))
        assert a["reliability_score"] == b["reliability_score"]
        assert a["score_breakdown"] == b["score_breakdown"]

    def test_artifacts_ready_beats_test_count_four(self):
        """Regression: test_count=4 used to score 18; artifacts_ready must stay at 20."""
        with_count = {
            **_BASE,
            "business_rules_test_result": {"test_count": 4},
            "edge_case_test_result": {"test_count": 4},
            "unit_test_result": {"test_count": 4},
        }
        without_count = copy.deepcopy(_BASE)
        a = SVC.calculate_reliability_score(with_count)
        b = SVC.calculate_reliability_score(without_count)
        assert a["reliability_score"] == b["reliability_score"] == 100
        assert a["score_breakdown"]["business_rules"] == 20

    def test_perfect_pass_ignores_advisory_retry_scope_penalty(self):
        scoped = {
            **_BASE,
            "retry_scope": {
                "scope_type": "paragraph",
                "scope_id": "4100-DISPLAY-QUOTE",
            },
        }
        out = SVC.calculate_reliability_score(scoped)
        assert out["reliability_score"] == 100
        assert out["score_breakdown"]["retry_stability"] == 10

    def test_fingerprint_ignores_retry_scope_on_clean_pass(self):
        a = build_reliability_fingerprint(_BASE)
        b = build_reliability_fingerprint(
            {
                **_BASE,
                "retry_scope": {"scope_type": "paragraph", "scope_id": "X"},
            }
        )
        assert a == b

    def test_score_drift_detected_when_breakdown_changes(self):
        from app.services.reliability_scoring_stability import _CANONICAL_SCORE_CACHE

        _CANONICAL_SCORE_CACHE.clear()
        fp = build_reliability_fingerprint(_BASE)
        first = SVC.calculate_reliability_score(copy.deepcopy(_BASE))
        # Simulate legacy 98 breakdown under same fingerprint (force cache entry).
        legacy_breakdown = dict(first["score_breakdown"])
        legacy_breakdown["business_rules"] = 18
        _CANONICAL_SCORE_CACHE[fp] = (98, legacy_breakdown)
        second = SVC.calculate_reliability_score(copy.deepcopy(_BASE))
        assert second["reliability_score"] == 100
        assert second.get("score_drift") is not None
        assert second["score_drift"]["canonical_reference_score"] == 98
