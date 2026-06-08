"""Tests for deterministic business-rules JUnit test generation."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.business_rules_test_generator import (
    BusinessRulesTestGenerator,
    derive_boundary_inputs,
    generate_business_rules_tests,
)

client = TestClient(app)

JAVA_STUB = """
public class PayrollCalc {
    public void run() {}
}
"""


class TestBoundaryDerivation:
    def test_threshold_rule_generates_three_boundaries(self):
        match = derive_boundary_inputs("tax bracket < 500")
        assert match.pattern == "threshold_below"
        assert match.threshold == 500
        assert list(match.values) == [499, 500, 501]

    def test_capacity_rule_generates_boundary(self):
        match = derive_boundary_inputs("capacity limited to 30 employees")
        assert match.pattern == "capacity"
        assert match.threshold == 30
        assert list(match.values) == [29, 30, 31]

    def test_confirmation_rule_generates_yn(self):
        match = derive_boundary_inputs("confirmation Y required before delete")
        assert match.pattern == "confirmation"
        assert list(match.values) == ["Y", "N", "X"]

    def test_overtime_rule_generates_hours(self):
        match = derive_boundary_inputs("overtime paid at 1.5x rate")
        assert match.pattern == "overtime"
        assert list(match.values) == [40, 41]


class TestGeneratorOutput:
    def test_generates_valid_java_class(self):
        gen = BusinessRulesTestGenerator()
        source = gen.generate(
            "PayrollCalc",
            [{"text": "tax bracket < 500"}],
            JAVA_STUB,
        )
        assert "import org.junit.jupiter.api.Test" in source
        assert "import static org.junit.jupiter.api.Assertions" in source
        assert "class PayrollCalcBusinessRulesTest" in source

    def test_generates_correct_method_count(self):
        rules = [
            {"text": "tax bracket < 500"},
            {"text": "capacity limited to 30"},
            {"text": "confirmation Y required"},
        ]
        result = generate_business_rules_tests("PayrollCalc", rules, JAVA_STUB)
        assert result["rules_total"] == 3
        assert result["test_count"] >= 3
        assert result["test_source"].count("@Test") >= 3


class TestGeneratorApi:
    def test_api_endpoint_returns_200(self):
        response = client.post(
            "/api/testing/generate-business-rules-tests",
            json={
                "program_name": "PayrollCalc",
                "business_rules": [
                    "tax bracket < 500",
                    {"text": "capacity limited to 30"},
                ],
                "java_source": JAVA_STUB,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["test_class_name"] == "PayrollCalcBusinessRulesTest"
        assert body["test_count"] >= 2
        assert "import org.junit.jupiter.api.Test" in body["test_source"]
        assert len(body["boundary_inputs"]) == 2
