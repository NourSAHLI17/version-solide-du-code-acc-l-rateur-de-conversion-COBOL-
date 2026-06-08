"""Tests for paragraph-level scoped re-conversion slicing."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.paragraph_scope_service import ParagraphScopeService

client = TestClient(app)

PARSER = {
    "paragraphs": ["INIT-PARA", "8300-DETERMINE-TAX-RATE", "RUN-PARA"],
    "operations": [
        {"type": "MOVE", "paragraph": "INIT-PARA", "target": "WS-RATE", "value": "0"},
        {"type": "COMPUTE", "paragraph": "8300-DETERMINE-TAX-RATE", "target": "WS-TAX", "value": "WS-RATE"},
        {"type": "DISPLAY", "paragraph": "8300-DETERMINE-TAX-RATE", "value": "'TAX'"},
    ],
    "control_flow": {
        "calls": [
            {"from": "RUN-PARA", "to": "8300-DETERMINE-TAX-RATE"},
            {"from": "INIT-PARA", "to": "RUN-PARA"},
        ],
        "branches": [{"type": "IF", "paragraph": "8300-DETERMINE-TAX-RATE"}],
        "loops": [],
    },
}

ANALYSIS = {
    "sections": [
        {"name": "INIT-PARA", "role": "initialize working storage"},
        {"name": "8300-DETERMINE-TAX-RATE", "role": "compute tax rate"},
        {"name": "RUN-PARA", "role": "orchestration"},
    ],
}

COBOL = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYROLL.
       PROCEDURE DIVISION.
       INIT-PARA.
           MOVE 0 TO WS-RATE.
       8300-DETERMINE-TAX-RATE.
           COMPUTE WS-TAX = WS-RATE * 10.
           DISPLAY "TAX".
       RUN-PARA.
           PERFORM 8300-DETERMINE-TAX-RATE.
           STOP RUN.
"""

JAVA = "public class Payroll { public void determineTaxRate() {} }"


class TestParagraphSlice:
    def test_build_paragraph_slice_includes_dependencies(self):
        svc = ParagraphScopeService()
        result = svc.build_paragraph_slice(
            PARSER, ANALYSIS, JAVA, "8300-DETERMINE-TAX-RATE", cobol_source=COBOL
        )
        assert "8300-DETERMINE-TAX-RATE" in result["included_paragraphs"]
        assert len(result["inclusion_reasons"]) >= 1
        assert result["parser_subset"]["paragraphs"]
        assert result["cobol_excerpt"]

    def test_prepare_conversion_payload_reports_actual_scope(self):
        svc = ParagraphScopeService()
        retry_scope = {
            "scope_type": "paragraph",
            "scope_id": "8300-DETERMINE-TAX-RATE",
            "affected_paragraphs": ["8300-DETERMINE-TAX-RATE"],
        }
        ctx = svc.prepare_conversion_payload(PARSER, ANALYSIS, JAVA, COBOL, retry_scope)
        assert ctx["requested_scope"] == "paragraph"
        assert ctx["actual_scope"] in {"paragraph", "section", "file"}
        assert "included_paragraphs" in ctx
        assert ctx["retry_summary"]

    def test_widen_when_too_many_dependencies(self):
        parser = dict(PARSER)
        parser["paragraphs"] = [
            "8300-DETERMINE-TAX-RATE",
            "P2",
            "P3",
            "P4",
            "P5",
            "P6",
        ]
        parser["control_flow"] = {
            "calls": [
                {"from": "P2", "to": "8300-DETERMINE-TAX-RATE"},
                {"from": "P3", "to": "P2"},
                {"from": "P4", "to": "P3"},
                {"from": "P5", "to": "P4"},
                {"from": "P6", "to": "P5"},
            ],
            "branches": [],
            "loops": [],
        }
        svc = ParagraphScopeService()
        result = svc.build_paragraph_slice(parser, ANALYSIS, JAVA, "8300-DETERMINE-TAX-RATE", cobol_source=COBOL)
        if len(result["included_paragraphs"]) > 4:
            assert result["safe_for_paragraph_retry"] is False
            assert result["effective_scope"] in {"section", "file"}


class TestRetryScopeReporting:
    def test_retry_endpoint_reports_scope_metadata(self):
        resp = client.post(
            "/api/testing/retry-conversion-scope",
            json={
                "program_name": "Payroll",
                "cobol_source": COBOL,
                "parser_json": PARSER,
                "analysis_json": ANALYSIS,
                "java_source": JAVA,
                "failed_tests": [{"likely_paragraph": "8300-DETERMINE-TAX-RATE"}],
                "diff_summary": {"diff_percentage": 5},
                "fallback_mode": True,
                "cobol_snapshot_output": "TAX\n",
                "java_snapshot_output": "TAX\n",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "requested_scope" in body
        assert "actual_scope" in body
        assert "retry_summary" in body
        assert isinstance(body.get("included_paragraphs"), list)
