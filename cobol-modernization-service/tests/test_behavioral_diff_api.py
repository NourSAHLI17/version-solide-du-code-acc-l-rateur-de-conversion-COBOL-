"""API route tests for POST /api/testing/behavioral-diff."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_LAYER_SCORE_KEYS = (
    "compile_health",
    "runtime_health",
    "behavioral_parity",
    "retry_stability",
    "attribution_confidence",
)


def _assert_layered_scoring_fields(body: dict) -> None:
    """Phase 3: layered scoring fields are present on behavioral-diff responses."""
    assert "qscore" in body
    qscore = body["qscore"]
    assert qscore is None or (isinstance(qscore, int) and 0 <= qscore <= 100)

    assert "layer_scores" in body
    layer_scores = body["layer_scores"]
    if layer_scores is not None:
        assert isinstance(layer_scores, dict)
        for key in _LAYER_SCORE_KEYS:
            assert key in layer_scores
            value = layer_scores[key]
            assert value is None or (isinstance(value, int) and 0 <= value <= 100)

    assert "primary_failure_layer" in body

    assert "run_diagnostics" in body
    run_diagnostics = body["run_diagnostics"]
    if run_diagnostics is not None:
        assert isinstance(run_diagnostics, dict)
        assert "behavioral_status" in run_diagnostics
        assert "program_name" in run_diagnostics


def test_behavioral_diff_endpoint_passes_with_snapshots():
    response = client.post(
        "/api/testing/behavioral-diff",
        json={
            "run_id": "api-run-1",
            "program_name": "HELLO",
            "scripted_input": "1\n",
            "fallback_mode": True,
            "cobol_snapshot_output": "HELLO WORLD\n",
            "java_snapshot_output": "HELLO WORLD\n",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "api-run-1"
    assert body["status"] == "passed"
    assert body["diff_summary"]["lines_diverged"] == 0
    _assert_layered_scoring_fields(body)
    assert body["qscore"] is not None
    assert body["layer_scores"]["compile_health"] is not None
    assert body["layer_scores"]["behavioral_parity"] is not None


def test_behavioral_diff_maps_paragraph_with_parser_output():
    response = client.post(
        "/api/testing/behavioral-diff",
        json={
            "run_id": "api-map-1",
            "program_name": "CUSTMGR",
            "fallback_mode": True,
            "cobol_snapshot_output": "Enter menu choice\nInvalid choice\n",
            "java_snapshot_output": "Enter menu choice\nInvalid option\n",
            "parser_output": {
                "paragraphs": ["1000-MAIN", "2000-VALIDATE"],
                "operations": [
                    {"type": "DISPLAY", "paragraph": "2000-VALIDATE", "value": "'Invalid choice'"},
                ],
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["retry_scope"] == "2000-VALIDATE"
    assert "2000-VALIDATE" in body["affected_paragraphs"]
    assert body["failure_reason"]
    assert body["failure_mapping"]["primary_retry_scope"] == "2000-VALIDATE"
    _assert_layered_scoring_fields(body)
    assert body["primary_failure_layer"] == "behavioral_parity"


def test_behavioral_diff_project_mode_aggregates_files():
    response = client.post(
        "/api/testing/behavioral-diff",
        json={
            "target_type": "project",
            "target_id": "proj-1",
            "project_id": "proj-1",
            "run_id": "api-proj-1",
            "program_name": "DEMO-PROJECT",
            "fallback_mode": True,
            "files": [
                {
                    "path": "src/HELLO.cbl",
                    "filename": "HELLO.cbl",
                    "program_name": "HELLO",
                    "cobol_source": "       IDENTIFICATION DIVISION.",
                    "cobol_snapshot_output": "HELLO WORLD\n",
                    "java_snapshot_output": "HELLO WORLD\n",
                },
                {
                    "path": "src/GOODBYE.cbl",
                    "filename": "GOODBYE.cbl",
                    "program_name": "GOODBYE",
                    "cobol_source": "       IDENTIFICATION DIVISION.",
                    "cobol_snapshot_output": "BYE\n",
                    "java_snapshot_output": "BYE\n",
                },
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["target_type"] == "project"
    assert body["project_id"] == "proj-1"
    assert body["status"] == "passed"
    assert body["project_summary"]["files_tested"] == 2
    assert body["project_summary"]["files_passed"] == 2
    assert isinstance(body["file_results"], list)
    assert len(body["file_results"]) == 2
    _assert_layered_scoring_fields(body)
    for file_row in body["file_results"]:
        _assert_layered_scoring_fields(file_row)


def test_legacy_test_endpoint_still_available():
    response = client.post(
        "/api/test",
        json={
            "parser_output": {"paragraphs": ["MAIN"], "symbol_table": [], "control_flow": {"calls": [], "loops": []}},
            "analysis_output": {},
            "java_source": "",
            "cobol_source": "",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "parser_tests" in body
    assert "behavioral_tests" in body
