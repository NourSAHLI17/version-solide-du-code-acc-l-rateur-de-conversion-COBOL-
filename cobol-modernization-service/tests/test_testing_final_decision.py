"""Tests for merged final trust decision."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.testing_final_decision_service import TestingFinalDecisionService

client = TestClient(app)
SVC = TestingFinalDecisionService()


class TestFinalDecisionService:
    def test_merged_validation_summary(self):
        result = SVC.build_final_decision(
            {
                "program_name": "Payroll",
                "behavioral_status": "passed",
                "failed_tests": [],
                "diff_summary": {"lines_compared": 5, "lines_matched": 5, "diff_percentage": 0},
                "unit_test_result": {"test_count": 3},
                "derive_retry_scope": False,
            }
        )
        assert "reliability_score" in result
        assert "test_summary" in result
        assert result["test_summary"]["behavioral_pass"] is True
        assert "save_gate" in result

    def test_save_eligibility_when_trustworthy(self):
        result = SVC.build_final_decision(
            {
                "program_name": "Payroll",
                "behavioral_status": "passed",
                "failed_tests": [],
                "diff_summary": {"lines_compared": 10, "lines_matched": 10, "diff_percentage": 0},
                "business_rules_test_result": {"test_count": 2},
                "edge_case_test_result": {"test_count": 2},
                "unit_test_result": {"test_count": 2},
                "derive_retry_scope": False,
            }
        )
        assert result["decision_state"] in {"ready_to_save", "needs_more_validation"}
        assert isinstance(result["blockers"], list)


    def test_layered_fields_pass_through_without_changing_reliability(self):
        baseline = SVC.build_final_decision(
            {
                "program_name": "Payroll",
                "behavioral_status": "partial",
                "failed_tests": [{"id": "BEH_1", "scenario_id": "s1", "description": "drift"}],
                "diff_summary": {
                    "lines_compared": 4,
                    "lines_matched": 2,
                    "lines_diverged": 2,
                    "diff_percentage": 50,
                },
                "derive_retry_scope": False,
            }
        )
        with_layered = SVC.build_final_decision(
            {
                "program_name": "Payroll",
                "behavioral_status": "partial",
                "failed_tests": [{"id": "BEH_1", "scenario_id": "s1", "description": "drift"}],
                "diff_summary": {
                    "lines_compared": 4,
                    "lines_matched": 2,
                    "lines_diverged": 2,
                    "diff_percentage": 50,
                },
                "derive_retry_scope": False,
                "qscore": 42,
                "layer_scores": {
                    "compile_health": 100,
                    "runtime_health": 100,
                    "behavioral_parity": 20,
                    "retry_stability": 30,
                    "attribution_confidence": 50,
                },
                "primary_failure_layer": "behavioral_parity",
                "run_diagnostics": {
                    "behavioral_status": "partial",
                    "lines_compared": 4,
                    "lines_matched": 2,
                    "lines_diverged": 2,
                },
            }
        )
        assert with_layered["reliability_score"] == baseline["reliability_score"]
        assert with_layered["decision_state"] == baseline["decision_state"]
        assert with_layered["save_eligible"] == baseline["save_eligible"]
        assert with_layered["qscore"] == 42
        assert with_layered["layer_scores"]["behavioral_parity"] == 20
        assert with_layered["primary_failure_layer"] == "behavioral_parity"
        assert with_layered["run_diagnostics"]["behavioral_status"] == "partial"

    def test_layered_fields_extracted_from_nested_test_result(self):
        result = SVC.build_final_decision(
            {
                "program_name": "TXNPOST",
                "behavioral_status": "failed",
                "failed_tests": [],
                "diff_summary": {"lines_compared": 0, "lines_matched": 0, "diff_percentage": None},
                "derive_retry_scope": False,
                "test_result": {
                    "status": "not_run",
                    "qscore": 5,
                    "layer_scores": {"compile_health": 0, "runtime_health": 0},
                    "primary_failure_layer": "compile_health",
                },
            }
        )
        assert result["qscore"] == 5
        assert result["primary_failure_layer"] == "compile_health"
        assert result["layer_scores"]["compile_health"] == 0

    def test_without_layered_fields_omits_attachment(self):
        result = SVC.build_final_decision(
            {
                "program_name": "Payroll",
                "behavioral_status": "passed",
                "failed_tests": [],
                "diff_summary": {"lines_compared": 5, "lines_matched": 5, "diff_percentage": 0},
                "derive_retry_scope": False,
            }
        )
        assert "qscore" not in result
        assert "layer_scores" not in result


class TestFinalDecisionApi:
    def test_final_decision_endpoint(self):
        resp = client.post(
            "/api/testing/final-decision",
            json={
                "program_name": "Payroll",
                "behavioral_status": "passed",
                "failed_tests": [],
                "diff_summary": {"lines_compared": 8, "lines_matched": 8, "diff_percentage": 0},
                "derive_retry_scope": False,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["reliability_score"] >= 0
        assert body["decision_state"] in {
            "ready_to_save",
            "needs_more_validation",
            "retry_recommended",
        }

    def test_final_decision_endpoint_returns_layered_fields_when_provided(self):
        resp = client.post(
            "/api/testing/final-decision",
            json={
                "program_name": "Payroll",
                "behavioral_status": "partial",
                "failed_tests": [{"id": "BEH_1", "scenario_id": "s1", "description": "drift"}],
                "diff_summary": {
                    "lines_compared": 4,
                    "lines_matched": 2,
                    "lines_diverged": 2,
                    "diff_percentage": 50,
                },
                "derive_retry_scope": False,
                "qscore": 55,
                "layer_scores": {
                    "compile_health": 100,
                    "runtime_health": 100,
                    "behavioral_parity": 25,
                    "retry_stability": 40,
                    "attribution_confidence": 60,
                },
                "primary_failure_layer": "behavioral_parity",
                "run_diagnostics": {"behavioral_status": "partial", "lines_compared": 4},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["reliability_score"] >= 0
        assert body["qscore"] == 55
        assert body["layer_scores"]["behavioral_parity"] == 25
        assert body["primary_failure_layer"] == "behavioral_parity"
        assert body["run_diagnostics"]["behavioral_status"] == "partial"
