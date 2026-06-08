"""Tests for deterministic edge-case JUnit test generation."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.edge_case_test_generator import EdgeCaseTestGenerator

client = TestClient(app)

JAVA_STUB = """
public class PayrollCalc {
    public void run() {}
}
"""


class TestEdgeCaseDerivation:
    def test_occurs_boundary_generates_three_values(self):
        gen = EdgeCaseTestGenerator()
        parser = {
            "symbol_table": [{"name": "EMP-TABLE", "occurs": 30}],
            "control_flow": {"loops": [], "branches": []},
            "operations": [],
        }
        cases = gen.derive_edge_cases(parser)
        occurs = next(c for c in cases if c["type"] == "OCCURS boundary")
        assert list(occurs["values"]) == [29, 30, 31]

    def test_loop_boundary_generates_empty_and_edge_cases(self):
        gen = EdgeCaseTestGenerator()
        parser = {
            "symbol_table": [],
            "control_flow": {
                "loops": [
                    {
                        "type": "PERFORM_VARYING",
                        "paragraph": "MAIN",
                        "until": "I > 10",
                        "start": "1",
                    }
                ],
                "branches": [],
            },
            "operations": [],
        }
        cases = gen.derive_edge_cases(parser)
        loop = next(c for c in cases if c["type"] == "loop boundary")
        assert loop["values"] == [9, 10, 11]

    def test_early_exit_generates_exit_condition_test(self):
        gen = EdgeCaseTestGenerator()
        parser = {
            "symbol_table": [],
            "control_flow": {"loops": [], "branches": []},
            "operations": [
                {"type": "EXIT_PARAGRAPH", "paragraph": "P1", "value": "EXIT"},
            ],
        }
        cases = gen.derive_edge_cases(parser)
        assert any(c["type"] == "early exit" for c in cases)

    def test_evaluate_threshold_generates_boundary_values(self):
        gen = EdgeCaseTestGenerator()
        parser = {
            "symbol_table": [],
            "control_flow": {
                "loops": [],
                "branches": [{"type": "EVALUATE", "condition": "WS-AMOUNT", "paragraph": "P2"}],
            },
            "operations": [
                {"type": "EVALUATE", "paragraph": "P2", "value": "AMOUNT < 500"},
            ],
        }
        cases = gen.derive_edge_cases(parser)
        eval_cases = [c for c in cases if c["type"] == "EVALUATE threshold"]
        assert eval_cases
        assert any(list(c["values"]) == [499, 500, 501] for c in eval_cases)


class TestEdgeCaseGeneratorOutput:
    def test_generates_valid_java_class(self):
        gen = EdgeCaseTestGenerator()
        source = gen.generate(
            "PayrollCalc",
            {"symbol_table": [{"name": "T", "occurs": 10}], "control_flow": {"loops": [], "branches": []}, "operations": []},
            JAVA_STUB,
        )
        assert "import org.junit.jupiter.api.Test" in source
        assert "class PayrollCalcEdgeCaseTest" in source

    def test_generates_at_least_one_test_per_structural_flag(self):
        gen = EdgeCaseTestGenerator()
        parser = {
            "symbol_table": [{"name": "ITEM", "occurs": 5}],
            "control_flow": {
                "loops": [{"type": "PERFORM_UNTIL", "paragraph": "READ-PARA", "until": "EOF = Y"}],
                "branches": [{"type": "EVALUATE", "condition": "TRUE", "paragraph": "MENU"}],
            },
            "operations": [
                {"type": "READ", "paragraph": "READ-PARA"},
                {"type": "EXIT_PERFORM", "paragraph": "MENU"},
            ],
        }
        result = gen.generate_with_metadata("PayrollCalc", parser, JAVA_STUB)
        types = {c["type"] for c in result["edge_cases"]}
        assert "OCCURS boundary" in types
        assert "loop boundary" in types
        assert "early exit" in types
        assert "EVALUATE threshold" in types
        assert result["test_count"] >= 4


class TestEdgeCaseGeneratorApi:
    def test_api_endpoint_returns_200(self):
        response = client.post(
            "/api/testing/generate-edge-case-tests",
            json={
                "program_name": "PayrollCalc",
                "parser_json": {
                    "symbol_table": [{"name": "ARR", "occurs": 30}],
                    "control_flow": {"loops": [], "branches": []},
                    "operations": [],
                },
                "java_source": JAVA_STUB,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["test_class_name"] == "PayrollCalcEdgeCaseTest"
        assert body["test_count"] >= 1
        assert "import org.junit.jupiter.api.Test" in body["test_source"]
        assert body["edge_cases"][0]["values"] == [29, 30, 31]
