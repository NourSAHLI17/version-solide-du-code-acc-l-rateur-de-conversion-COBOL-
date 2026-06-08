"""Tests for testing retry scope derivation and retry API."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.testing_retry_scope_service import TestingRetryScopeService
from app.services.testing_save_gate_service import evaluate_save_candidate

client = TestClient(app)

JAVA = """
public class PayrollCalc {
    public double determineTaxRate(int income) { return income * 0.1; }
    public void run() { determineTaxRate(100); }
}
"""

PARSER = {
    "paragraphs": ["8300-DETERMINE-TAX-RATE", "RUN-PARA"],
    "control_flow": {"branches": [{"type": "IF"}]},
}

ANALYSIS = {
    "sections": [
        {"name": "8300-DETERMINE-TAX-RATE", "role": "compute tax rate"},
        {"name": "RUN-PARA", "role": "orchestration"},
    ],
}


class TestRetryScopeDerivation:
    def test_maps_failure_to_paragraph_scope(self):
        svc = TestingRetryScopeService()
        scope = svc.derive_retry_scope(
            PARSER,
            ANALYSIS,
            JAVA,
            [
                {
                    "id": "BEH_default",
                    "likely_paragraph": "8300-DETERMINE-TAX-RATE",
                    "description": "stdout mismatch",
                }
            ],
            {"diff_percentage": 12, "highlights": [{"likely_paragraph": "8300-DETERMINE-TAX-RATE"}]},
        )
        assert scope["scope_type"] in {"method", "paragraph"}
        assert "8300-DETERMINE-TAX-RATE" in scope["affected_paragraphs"] or scope["scope_id"]

    def test_fallback_scope_widens(self):
        svc = TestingRetryScopeService()
        scope = svc.derive_retry_scope(PARSER, ANALYSIS, JAVA, [], {})
        assert scope["scope_type"] == "program"
        assert scope["fallback_scope"] == "program"

    def test_user_selected_scope(self):
        svc = TestingRetryScopeService()
        scope = svc.derive_retry_scope(
            PARSER,
            ANALYSIS,
            JAVA,
            [],
            {},
            scope_type="paragraph",
            scope_id="8300-DETERMINE-TAX-RATE",
        )
        assert scope["scope_type"] == "paragraph"
        assert scope["scope_id"] == "8300-DETERMINE-TAX-RATE"


class TestSaveGate:
    def test_ready_to_save_when_passed(self):
        gate = evaluate_save_candidate(
            score=92,
            diff_summary={"diff_percentage": 0, "lines_diverged": 0},
            failed_tests=[],
            behavioral_status="passed",
        )
        assert gate["save_state"] == "ready_to_save"
        assert gate["ready_to_save"] is True

    def test_retry_recommended_when_failed(self):
        gate = evaluate_save_candidate(
            score=95,
            diff_summary={"diff_percentage": 20},
            failed_tests=[{"id": "x"}],
            behavioral_status="failed",
        )
        assert gate["save_state"] == "retry_recommended"
        assert gate["ready_to_save"] is False


class TestRetryApi:
    def test_derive_retry_scope_endpoint(self):
        resp = client.post(
            "/api/testing/derive-retry-scope",
            json={
                "program_name": "PayrollCalc",
                "parser_json": PARSER,
                "analysis_json": ANALYSIS,
                "java_source": JAVA,
                "failed_tests": [{"likely_paragraph": "8300-DETERMINE-TAX-RATE"}],
                "diff_summary": {},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "retry_scope" in body
        assert body["retry_scope"]["scope_type"]

    def test_retry_conversion_scope_endpoint(self):
        cobol = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYROLLCALC.
       PROCEDURE DIVISION.
       8300-DETERMINE-TAX-RATE.
           DISPLAY "TAX".
           STOP RUN.
        """
        resp = client.post(
            "/api/testing/retry-conversion-scope",
            json={
                "program_name": "PayrollCalc",
                "cobol_source": cobol,
                "parser_json": PARSER,
                "analysis_json": ANALYSIS,
                "java_source": JAVA,
                "failed_tests": [{"likely_paragraph": "8300-DETERMINE-TAX-RATE"}],
                "diff_summary": {"diff_percentage": 10},
                "fallback_mode": True,
                "cobol_snapshot_output": "TAX\\n",
                "java_snapshot_output": "TAX\\n",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "retry_scope" in body
        assert "save_state" in body
        assert "test_result" in body
