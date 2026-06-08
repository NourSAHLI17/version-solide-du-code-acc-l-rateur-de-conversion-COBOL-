"""Tests for save gate evaluation."""

from app.services.testing_save_gate_service import TestingSaveGateService

SVC = TestingSaveGateService()


class TestSaveGate:
    def test_ready_to_save(self):
        gate = SVC.evaluate_save_gate(
            {
                "reliability_score": 92,
                "behavioral_status": "passed",
                "failed_tests": [],
                "diff_summary": {"diff_percentage": 0, "lines_diverged": 0},
            }
        )
        assert gate["save_state"] == "ready_to_save"
        assert gate["save_eligible"] is True

    def test_blocked_when_diff_too_high(self):
        gate = SVC.evaluate_save_gate(
            {
                "reliability_score": 95,
                "behavioral_status": "passed",
                "failed_tests": [],
                "diff_summary": {"diff_percentage": 20},
            }
        )
        assert gate["save_eligible"] is False
        assert any("diff" in b.lower() for b in gate["blockers"])

    def test_blocked_when_tests_fail(self):
        gate = SVC.evaluate_save_gate(
            {
                "reliability_score": 95,
                "behavioral_status": "failed",
                "failed_tests": [{"id": "t1"}],
                "diff_summary": {"diff_percentage": 0},
            }
        )
        assert gate["save_eligible"] is False

    def test_borderline_state(self):
        gate = SVC.evaluate_save_gate(
            {
                "reliability_score": 75,
                "behavioral_status": "passed",
                "failed_tests": [],
                "diff_summary": {"diff_percentage": 2},
            }
        )
        assert gate["save_state"] == "needs_more_validation"
