"""Tests for deterministic unit-test JUnit generation."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.unit_test_generator import UnitTestGenerator, generate_unit_tests

client = TestClient(app)

JAVA_SAMPLE = """
public class PayrollCalc {
    public PayrollCalc() {}

    public void run() {
        calculateNetPay(40, 25.0);
    }

    public double calculateNetPay(int hours, double rate) {
        return hours * rate;
    }

    public void processWithDependency() {
        new java.io.File("tmp.dat");
    }
}
"""

PARSER_STUB = {
    "paragraphs": ["RUN-PARA", "CALCULATE-NET-PAY"],
    "control_flow": {"loops": [], "branches": [{"type": "IF", "condition": "X > 0"}]},
    "operations": [],
}

ANALYSIS_STUB = {
    "sections": [
        {"name": "CALCULATE-NET-PAY", "role": "compute pay amount"},
        {"name": "RUN-PARA", "role": "file io handler"},
    ],
    "business_rules": [],
}


class TestMethodExtraction:
    def test_extract_public_methods(self):
        gen = UnitTestGenerator()
        methods = gen.extract_public_methods(JAVA_SAMPLE)
        names = {m["name"] for m in methods}
        assert "PayrollCalc" in names
        assert "run" in names
        assert "calculateNetPay" in names
        assert "processWithDependency" in names

        calc = next(m for m in methods if m["name"] == "calculateNetPay")
        assert len(calc["params"]) == 2
        assert calc["is_void"] is False


class TestUnitTestGeneration:
    def test_generates_test_for_no_arg_method(self):
        gen = UnitTestGenerator()
        java = "public class Demo { public void run() {} }"
        cases = gen.derive_test_cases(java, PARSER_STUB, ANALYSIS_STUB)
        assert any(c["method_name"] == "run" for c in cases)
        source = gen.generate("Demo", PARSER_STUB, ANALYSIS_STUB, java)
        assert "test_run_" in source
        assert "assertDoesNotThrow" in source or "assertNotNull" in source

    def test_generates_test_for_method_with_arguments(self):
        gen = UnitTestGenerator()
        cases = gen.derive_test_cases(JAVA_SAMPLE, PARSER_STUB, ANALYSIS_STUB)
        calc_cases = [c for c in cases if c["method_name"] == "calculateNetPay"]
        assert len(calc_cases) >= 2
        assert any(len(c.get("fixtures") or []) == 2 for c in calc_cases)

    def test_generates_assertions_for_returning_method(self):
        gen = UnitTestGenerator()
        source = gen.generate("PayrollCalc", PARSER_STUB, ANALYSIS_STUB, JAVA_SAMPLE)
        assert "calculateNetPay" in source
        assert "assertEquals(" in source and "calculateNetPay" in source

    def test_generates_mock_or_stub_for_dependency_method(self):
        gen = UnitTestGenerator()
        cases = gen.derive_test_cases(JAVA_SAMPLE, PARSER_STUB, ANALYSIS_STUB)
        dep = [c for c in cases if c["method_name"] == "processWithDependency"]
        assert dep
        assert any(c.get("needs_mock") for c in dep)
        source = gen.generate("PayrollCalc", PARSER_STUB, ANALYSIS_STUB, JAVA_SAMPLE)
        assert "dependency stubs" in source or "Stub File" in source

    def test_generates_valid_java_class(self):
        result = generate_unit_tests("PayrollCalc", PARSER_STUB, ANALYSIS_STUB, JAVA_SAMPLE)
        assert "import org.junit.jupiter.api.Test" in result["test_source"]
        assert result["test_class_name"] == "PayrollCalcUnitTest"
        assert result["test_count"] >= len(result["methods_covered"])
        assert result["test_count"] >= 1

    def test_test_count_matches_methods_covered(self):
        result = generate_unit_tests("PayrollCalc", PARSER_STUB, ANALYSIS_STUB, JAVA_SAMPLE)
        covered_total = sum(m["test_count"] for m in result["methods_covered"])
        assert result["test_count"] == covered_total
        assert result["test_source"].count("@Test") == result["test_count"]

    def test_class_name_is_deterministic(self):
        a = generate_unit_tests("PayrollCalc", PARSER_STUB, ANALYSIS_STUB, JAVA_SAMPLE)
        b = generate_unit_tests("PayrollCalc", PARSER_STUB, ANALYSIS_STUB, JAVA_SAMPLE)
        assert a["test_class_name"] == b["test_class_name"]
        assert a["test_source"] == b["test_source"]

    def test_uses_junit5(self):
        source = UnitTestGenerator().generate("Demo", {}, {}, "public class Demo { public int x() { return 1; } }")
        assert "@Test" in source
        assert "org.junit.jupiter.api.Test" in source
        assert "Assertions" in source or "assertNotNull" in source


class TestUnitTestApi:
    def test_api_endpoint_returns_200(self):
        response = client.post(
            "/api/testing/generate-unit-tests",
            json={
                "program_name": "PayrollCalc",
                "parser_json": PARSER_STUB,
                "analysis_json": ANALYSIS_STUB,
                "java_source": JAVA_SAMPLE,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["test_class_name"] == "PayrollCalcUnitTest"
        assert body["test_count"] >= 1
        assert len(body["methods_covered"]) >= 1
        assert "import org.junit.jupiter.api.Test" in body["test_source"]
