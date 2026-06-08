"""Phase 1 — isolated unit tests for behavioral layered scoring."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.behavioral_layer_scoring_service import (
    LAYER_ATTRIBUTION,
    LAYER_COMPILE,
    LAYER_PARITY,
    LAYER_RUNTIME,
    score_behavioral_run,
)


def _success_execution_details() -> list:
    ok = {"execution_status": "success", "mode": "executed"}
    return [{"scenario_id": "default", "cobol_execution": ok, "java_execution": ok}]


def _snapshot(*, cobol_status: str = "success", java_status: str = "success", **kwargs) -> dict:
    base = {
        "target_type": "single_file",
        "program_name": kwargs.get("program_name", "TXNPOST"),
        "run_id": "run-1",
        "created_at": "2026-05-20T12:00:00+00:00",
        "status": kwargs.get("status", "passed"),
        "execution_mode": "live",
        "execution_details": kwargs.get("execution_details") or _success_execution_details(),
        "diff_summary": kwargs.get(
            "diff_summary",
            {"lines_compared": 4, "lines_matched": 4, "diff_percentage": 0.0},
        ),
        "failed_tests": kwargs.get("failed_tests", []),
        "failure_reason": kwargs.get("failure_reason"),
        "affected_paragraphs": kwargs.get("affected_paragraphs", []),
        "retry_scope": kwargs.get("retry_scope", ""),
        "failure_mapping": kwargs.get("failure_mapping"),
    }
    if "execution_details" in kwargs:
        base["execution_details"] = kwargs["execution_details"]
    return base


class TestCompileHealth:
    def test_compile_failure_lowers_compile_health(self):
        details = [
            {
                "scenario_id": "default",
                "cobol_execution": {"execution_status": "compile_failure", "compile_stderr": "error"},
                "java_execution": {"execution_status": "success"},
            }
        ]
        result = score_behavioral_run(_snapshot(status="not_run", execution_details=details))
        assert result.layer_scores[LAYER_COMPILE] == 0
        assert result.primary_failure_layer == LAYER_COMPILE
        assert result.layer_scores[LAYER_PARITY] is None

    def test_unresolved_copybook_is_infrastructure_not_parity(self):
        result = score_behavioral_run(
            _snapshot(
                status="failed",
                failure_reason=(
                    "COBOL COPY book(s) not expanded before compile: ERRORCOPY. "
                    "Searched: /fixtures/copybooks."
                ),
                diff_summary={"lines_compared": 0, "diff_percentage": None},
            )
        )
        assert result.run_diagnostics["infrastructure_blocker"] is True
        assert result.layer_scores[LAYER_COMPILE] <= 10
        assert result.layer_scores[LAYER_PARITY] is None
        assert result.primary_failure_layer == LAYER_COMPILE

    def test_symbol_repair_message_classified_as_compile_blocker(self):
        result = score_behavioral_run(
            _snapshot(
                status="failed",
                failure_reason="cobol symbol repair injected WS-RETURN-CODE 88 RC-SUCCESS",
                execution_details=[
                    {
                        "scenario_id": "default",
                        "cobol_execution": {"execution_status": "compile_failure"},
                        "java_execution": {"execution_status": "success"},
                    }
                ],
            )
        )
        assert result.run_diagnostics["infrastructure_blocker"] is True
        assert result.primary_failure_layer == LAYER_COMPILE
        assert result.layer_scores[LAYER_PARITY] is None


class TestBehavioralParity:
    def test_stdout_mismatch_lowers_parity(self):
        result = score_behavioral_run(
            _snapshot(
                status="partial",
                diff_summary={
                    "lines_compared": 10,
                    "lines_matched": 2,
                    "lines_diverged": 8,
                    "diff_percentage": 80.0,
                    "first_mismatch_index": 0,
                },
                failed_tests=[{"id": "BEH_1", "severity": "high"}],
                failure_reason="Stdout drift at line 0",
                affected_paragraphs=["2100-POST-TRANSACTION"],
                retry_scope="2100-POST-TRANSACTION",
                failure_mapping={
                    "primary_retry_scope": "2100-POST-TRANSACTION",
                    "attribution_method": "display_literal",
                },
            )
        )
        assert result.layer_scores[LAYER_COMPILE] == 100
        assert result.layer_scores[LAYER_RUNTIME] == 100
        assert result.layer_scores[LAYER_PARITY] is not None
        assert result.layer_scores[LAYER_PARITY] <= 25
        assert result.primary_failure_layer == LAYER_PARITY

    def test_perfect_match_high_parity(self):
        result = score_behavioral_run(_snapshot(status="passed"))
        assert result.layer_scores[LAYER_PARITY] == 100
        assert result.qscore >= 90


class TestRuntimeHealth:
    def test_passed_with_lines_compared_scores_runtime_100_despite_unavailable_mode(self):
        result = score_behavioral_run(
            _snapshot(
                status="passed",
                execution_mode="unavailable",
                diff_summary={"lines_compared": 5, "lines_matched": 5, "diff_percentage": 0.0},
            )
        )
        assert result.layer_scores[LAYER_RUNTIME] == 100

    def test_passed_with_one_side_no_stdout_scores_runtime_100(self):
        details = [
            {
                "scenario_id": "default",
                "cobol_execution": {"execution_status": "success", "mode": "executed"},
                "java_execution": {"execution_status": "no_stdout", "mode": "executed"},
            }
        ]
        result = score_behavioral_run(
            _snapshot(
                status="passed",
                execution_mode="live",
                execution_details=details,
                diff_summary={"lines_compared": 2, "lines_matched": 2, "diff_percentage": 0.0},
            )
        )
        assert result.layer_scores[LAYER_RUNTIME] == 100

    def test_runtime_failure_primary_is_runtime(self):
        details = [
            {
                "scenario_id": "default",
                "cobol_execution": {"execution_status": "success"},
                "java_execution": {"execution_status": "timeout", "error": "timed out"},
            }
        ]
        result = score_behavioral_run(
            _snapshot(status="failed", execution_details=details, failure_reason="Java timed out")
        )
        assert result.layer_scores[LAYER_RUNTIME] == 0
        assert result.primary_failure_layer == LAYER_RUNTIME
        assert result.layer_scores[LAYER_PARITY] is None


class TestAttributionConfidence:
    def test_good_attribution_scores_higher_than_empty(self):
        rich = score_behavioral_run(
            _snapshot(
                status="partial",
                diff_summary={"lines_compared": 5, "lines_matched": 3, "diff_percentage": 40.0},
                failed_tests=[{"id": "BEH_x"}],
                failure_reason="Mismatch on line 2",
                affected_paragraphs=["2000-PROCESS"],
                retry_scope="2000-PROCESS",
                failure_mapping={
                    "primary_retry_scope": "2000-PROCESS",
                    "attribution_method": "display_literal",
                    "highlights": [{"likely_paragraph": "2000-PROCESS", "attribution_method": "display_literal"}],
                },
            )
        )
        empty = score_behavioral_run(
            _snapshot(
                status="partial",
                diff_summary={"lines_compared": 5, "lines_matched": 3, "diff_percentage": 40.0},
                failed_tests=[{"id": "BEH_x"}],
                failure_reason="Mismatch on line 2",
                affected_paragraphs=[],
                retry_scope="",
                failure_mapping=None,
            )
        )
        assert rich.layer_scores[LAYER_ATTRIBUTION] > empty.layer_scores[LAYER_ATTRIBUTION]
        assert empty.layer_scores[LAYER_ATTRIBUTION] <= 25
        assert rich.layer_scores[LAYER_ATTRIBUTION] >= 60


class TestQscoreAggregation:
    def test_qscore_within_bounds(self):
        result = score_behavioral_run(_snapshot(status="passed"))
        assert 0 <= result.qscore <= 100

    def test_project_run_exposes_ok_stage_labels_from_file_results(self):
        file_details = _success_execution_details()
        result = score_behavioral_run(
            {
                "target_type": "project",
                "program_name": "USECASE3",
                "status": "passed",
                "execution_mode": "live",
                "execution_details": None,
                "file_results": [
                    {
                        "path": "usecase3/TXNPOST.cbl",
                        "status": "passed",
                        "execution_details": file_details,
                        "diff_summary": {"lines_compared": 4, "lines_matched": 4},
                    }
                ],
                "diff_summary": {"lines_compared": 4, "lines_matched": 4, "diff_percentage": 0.0},
                "failed_tests": [],
            }
        )
        diag = result.run_diagnostics
        assert diag["cobol_compile_status"] == "ok"
        assert diag["java_compile_status"] == "ok"
        assert diag["cobol_runtime_status"] == "ok"
        assert diag["java_runtime_status"] == "ok"

    def test_executed_mode_without_execution_status_maps_to_ok_labels(self):
        details = [
            {
                "scenario_id": "default",
                "cobol_execution": {"mode": "executed", "exit_code": 0, "stdout": "LINE1"},
                "java_execution": {"mode": "executed", "exit_code": 0, "stdout": "LINE1"},
            }
        ]
        result = score_behavioral_run(
            _snapshot(
                status="passed",
                execution_mode="live",
                execution_details=details,
                diff_summary={"lines_compared": 1, "lines_matched": 1, "diff_percentage": 0.0},
            )
        )
        assert result.run_diagnostics["cobol_compile_status"] == "ok"
        assert result.run_diagnostics["java_runtime_status"] == "ok"

    def test_blocker_category_toolchain_for_missing_cobc(self):
        result = score_behavioral_run(
            _snapshot(
                status="not_run",
                execution_mode="unavailable",
                failure_reason="Behavioral comparison did not run: cobc not available (not found).",
                diff_summary={"lines_compared": 0, "diff_percentage": None},
            )
        )
        assert result.run_diagnostics["testing_blocker_category"] == "toolchain"

    def test_run_diagnostics_capture_core_fields(self):
        result = score_behavioral_run(
            _snapshot(
                program_name="STMTRPT",
                diff_summary={"lines_compared": 3, "lines_matched": 1, "diff_percentage": 66.7, "first_mismatch_index": 1},
            )
        )
        diag = result.run_diagnostics
        assert diag["program_name"] == "STMTRPT"
        assert diag["lines_compared"] == 3
        assert diag["first_mismatch_line"] == 1
        assert "compile_health" in diag.get("qscore_weights", {})
