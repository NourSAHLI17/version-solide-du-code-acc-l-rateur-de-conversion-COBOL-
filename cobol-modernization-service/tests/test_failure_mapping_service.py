"""Tests for deterministic failure mapping on behavioral diff results."""

import pytest

from app.services.behavioral_diff_runner import compare_normalized_outputs, run_behavioral_diff
from app.services.failure_mapping_service import (
    build_display_literals_by_paragraph,
    classify_failure_kind,
    enrich_behavioral_result,
    map_scenario_failure,
)


PARSER_WITH_DISPLAY = {
    "paragraphs": ["1000-MAIN", "2000-VALIDATE", "3000-REPORT"],
    "operations": [
        {"type": "DISPLAY", "paragraph": "1000-MAIN", "value": "'Enter menu choice'"},
        {"type": "DISPLAY", "paragraph": "2000-VALIDATE", "value": "'Invalid choice'"},
        {"type": "DISPLAY", "paragraph": "3000-REPORT", "value": "'End of Report'"},
    ],
}

ANALYSIS_WITH_SECTIONS = {
    "sections": [
        {"paragraph": "2000-VALIDATE", "role": "Validate user menu selection"},
        {"paragraph": "3000-REPORT", "role": "Print summary report"},
    ],
}


class TestClassifyFailureKind:
    def test_content_mismatch(self):
        kind = classify_failure_kind(["a", "COBOL"], ["a", "JAVA"], 1)
        assert kind == "content_mismatch"

    def test_missing_java_line(self):
        kind = classify_failure_kind(["expected line", "tail"], ["", "tail"], 0)
        assert kind in ("missing_java_line", "content_mismatch")

    def test_order_mismatch(self):
        kind = classify_failure_kind(["b", "a"], ["a", "b"], 0)
        assert kind == "order_mismatch"

    def test_menu_branch_mismatch(self):
        kind = classify_failure_kind(["Invalid choice"], ["Invalid option"], 0)
        assert kind == "menu_branch_mismatch"


class TestDisplayLiteralMapping:
    def test_parser_display_literals(self):
        m = build_display_literals_by_paragraph(PARSER_WITH_DISPLAY)
        assert "Invalid choice" in m["2000-VALIDATE"]

    def test_map_with_parser_data(self):
        diff = compare_normalized_outputs(
            "Enter menu choice\nInvalid choice\n",
            "Enter menu choice\nInvalid option\n",
        )
        mapping = map_scenario_failure(
            scenario_id="scn-menu",
            scenario_label="Menu test",
            diff=diff,
            scenario_inputs={"MENU-CHOICE": "9"},
            parser_output=PARSER_WITH_DISPLAY,
            analysis_output=ANALYSIS_WITH_SECTIONS,
            cobol_source=None,
            java_source=None,
        )
        assert mapping is not None
        assert mapping["failure_kind"] == "menu_branch_mismatch"
        assert "2000-VALIDATE" in mapping["affected_paragraphs"]
        assert mapping["retry_scope"] == "2000-VALIDATE"
        assert "2000-VALIDATE" in mapping["explanation"]
        assert mapping["likely_paragraph"] == "2000-VALIDATE"
        assert mapping["highlights"][0].get("likely_paragraph") == "2000-VALIDATE"

    def test_map_without_parser_uses_line_proportion(self):
        diff = compare_normalized_outputs("line0\nline1\nline2\n", "line0\nWRONG\nline2\n")
        mapping = map_scenario_failure(
            scenario_id="scn-1",
            scenario_label="No parser",
            diff=diff,
            scenario_inputs={},
            parser_output=None,
            analysis_output=None,
            cobol_source=None,
            java_source=None,
        )
        assert mapping is not None
        assert mapping["attribution_method"] in ("line_proportion", "none")
        assert mapping["failure_kind"] == "content_mismatch"
        assert "line 2" in mapping["where_failed"].lower()


class TestEnrichBehavioralResult:
    def test_identical_outputs_no_mapping(self):
        result = run_behavioral_diff(
            {
                "run_id": "pass-1",
                "program_name": "DEMO",
                "fallback_mode": True,
                "cobol_snapshot_output": "ok\n",
                "java_snapshot_output": "ok\n",
                "parser_output": PARSER_WITH_DISPLAY,
            }
        )
        assert result["status"] == "passed"
        assert result["affected_paragraphs"] == []
        assert result["retry_scope"] == ""
        assert result["failure_reason"] is None

    def test_one_wrong_line_maps_retry_scope(self):
        result = run_behavioral_diff(
            {
                "run_id": "fail-1",
                "program_name": "CUSTMGR",
                "fallback_mode": True,
                "cobol_snapshot_output": "Enter menu choice\nInvalid choice\n",
                "java_snapshot_output": "Enter menu choice\nInvalid option\n",
                "parser_output": PARSER_WITH_DISPLAY,
            }
        )
        assert result["status"] in ("failed", "partial")
        assert result["retry_scope"]
        assert result["affected_paragraphs"]
        assert result["failure_reason"]
        assert "2000-VALIDATE" in result["affected_paragraphs"]
        assert result["failed_tests"][0].get("likely_paragraph") == "2000-VALIDATE"
        assert result["diff_summary"]["highlights"][0].get("failure_kind")

    def test_missing_line_classification_via_enrich(self):
        diff = compare_normalized_outputs("only cobol\n", "")
        enriched = enrich_behavioral_result(
            {
                "status": "failed",
                "failed_tests": [],
                "diff_summary": diff,
                "execution_details": [
                    {
                        "scenario_id": "default",
                        "diff": diff,
                        "cobol_execution": {"mode": "fallback", "exit_code": 0},
                        "java_execution": {"mode": "fallback", "exit_code": 0},
                    }
                ],
                "input_set": {"scenarios": [{"id": "default", "label": "x", "inputs": {}}]},
            },
            parser_output={"paragraphs": ["P1", "P2"]},
        )
        assert enriched["retry_scope"]
        assert enriched["failure_reason"]

    def test_order_mismatch_maps_as_ordering_issue(self):
        result = run_behavioral_diff(
            {
                "run_id": "order-1",
                "program_name": "DEMO",
                "fallback_mode": True,
                "cobol_snapshot_output": "alpha\nbeta\n",
                "java_snapshot_output": "beta\nalpha\n",
            }
        )
        assert result["status"] != "passed"
        assert "order" in (result["failure_reason"] or "").lower() or any(
            t.get("failure_kind") == "order_mismatch" for t in result["failed_tests"]
        )
