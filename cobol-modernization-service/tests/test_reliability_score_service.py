"""Tests for reliability score calculation."""

from app.services.reliability_score_service import ReliabilityScoreService

SVC = ReliabilityScoreService()


class TestReliabilityScore:
    def test_high_score_ready_to_save(self):
        result = SVC.calculate_reliability_score(
            {
                "program_name": "Payroll",
                "behavioral_status": "passed",
                "failed_tests": [],
                "diff_summary": {
                    "lines_compared": 10,
                    "lines_matched": 10,
                    "diff_percentage": 0,
                },
                "business_rules_test_result": {"test_count": 5},
                "edge_case_test_result": {"test_count": 4},
                "unit_test_result": {"test_count": 6},
            }
        )
        assert result["reliability_score"] >= 85
        assert result["decision_state"] == "ready_to_save"
        assert result["save_eligible"] is True
        assert not result["blockers"]

    def test_borderline_needs_more_validation(self):
        result = SVC.calculate_reliability_score(
            {
                "program_name": "Payroll",
                "behavioral_status": "partial",
                "failed_tests": [],
                "diff_summary": {"diff_percentage": 3, "lines_compared": 10, "lines_matched": 9},
            }
        )
        assert 70 <= result["reliability_score"] < 90 or result["decision_state"] in {
            "needs_more_validation",
            "retry_recommended",
        }

    def test_artifact_ready_without_generated_tests_reaches_save_threshold(self):
        result = SVC.calculate_reliability_score(
            {
                "program_name": "Payroll",
                "behavioral_status": "passed",
                "failed_tests": [],
                "diff_summary": {
                    "lines_compared": 10,
                    "lines_matched": 10,
                    "diff_percentage": 0,
                },
                "validation_artifacts": {
                    "business_rules_ready": True,
                    "edge_cases_ready": True,
                    "unit_tests_ready": True,
                },
            }
        )
        assert result["reliability_score"] >= 85
        assert result["decision_state"] == "ready_to_save"

    def test_low_score_retry_recommended(self):
        result = SVC.calculate_reliability_score(
            {
                "program_name": "Payroll",
                "behavioral_status": "failed",
                "failed_tests": [{"id": "x"}],
                "diff_summary": {"diff_percentage": 25},
            }
        )
        assert result["reliability_score"] < 85
        assert result["decision_state"] == "retry_recommended"
        assert result["save_eligible"] is False
        assert result["blockers"]
