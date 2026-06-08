"""Tests for the Stage 9 Testing Agent — real logic, no mocks."""

import pytest
from app.services.testing_agent import (
    run_parser_tests,
    run_conversion_tests,
    run_testing_agent,
)


class TestParserTests:
    def test_symbol_completeness(self):
        parser_output = {
            "symbol_table": [
                {"name": "VAR-A", "pic": "X(10)", "kind": "string"},
                {"name": "VAR-B", "kind": "numeric"},
            ],
            "paragraphs": ["MAIN-PARA"],
            "control_flow": {"calls": [], "loops": [], "branches": []},
            "operations": [],
        }
        tests = run_parser_tests(parser_output)
        sym_tests = [t for t in tests if t["id"].startswith("SYM_")]
        assert len(sym_tests) == 2
        assert all(t["passed"] for t in sym_tests)

    def test_symbol_missing_pic_and_kind(self):
        parser_output = {
            "symbol_table": [{"name": "BAD-VAR"}],
            "paragraphs": [],
            "control_flow": {"calls": [], "loops": [], "branches": []},
            "operations": [],
        }
        tests = run_parser_tests(parser_output)
        assert any(t["id"] == "SYM_BAD-VAR" and not t["passed"] for t in tests)

    def test_call_graph_integrity(self):
        parser_output = {
            "symbol_table": [],
            "paragraphs": ["PARA-A", "PARA-B"],
            "control_flow": {
                "calls": [{"from": "PARA-A", "to": "PARA-B"}],
                "loops": [],
                "branches": [],
            },
            "operations": [],
        }
        tests = run_parser_tests(parser_output)
        call_test = next(t for t in tests if t["id"].startswith("CALL_"))
        assert call_test["passed"]

    def test_call_graph_broken_target(self):
        parser_output = {
            "symbol_table": [],
            "paragraphs": ["PARA-A"],
            "control_flow": {
                "calls": [{"from": "PARA-A", "to": "NONEXISTENT"}],
                "loops": [],
                "branches": [],
            },
            "operations": [],
        }
        tests = run_parser_tests(parser_output)
        call_test = next(t for t in tests if "NONEXISTENT" in t["id"])
        assert not call_test["passed"]

    def test_reserved_word_check(self):
        parser_output = {
            "symbol_table": [],
            "paragraphs": ["PERFORM"],  # reserved word!
            "control_flow": {"calls": [], "loops": [], "branches": []},
            "operations": [],
        }
        tests = run_parser_tests(parser_output)
        reserved_test = next(t for t in tests if t["id"] == "RESERVED_PERFORM")
        assert not reserved_test["passed"]


class TestConversionTests:
    def test_do_while_detected(self):
        java = """
        public class Test {
            public void test() {
                do {
                    System.out.println("No!");
                } while(true);
            }
        }
        """
        tests = run_conversion_tests(java, {"symbol_table": []})
        do_test = next(t for t in tests if t["id"] == "NO_DO_WHILE")
        assert not do_test["passed"]

    def test_no_do_while_passes(self):
        java = """
        public class Test {
            public void test() {
                while(true) { break; }
            }
        }
        """
        tests = run_conversion_tests(java, {"symbol_table": []})
        do_test = next(t for t in tests if t["id"] == "NO_DO_WHILE")
        assert do_test["passed"]

    def test_float_violation_detected(self):
        java = "double balance = 0;"
        parser = {
            "symbol_table": [{"name": "BALANCE", "pic": "9(5)V99"}]
        }
        tests = run_conversion_tests(java, parser)
        float_test = next(t for t in tests if t["id"] == "NO_FLOAT_DOUBLE")
        assert not float_test["passed"]

    def test_empty_source_returns_empty(self):
        tests = run_conversion_tests("", {"symbol_table": []})
        assert tests == []


class TestOrchestratorIntegration:
    def test_full_report_structure(self):
        parser_output = {
            "symbol_table": [{"name": "X", "kind": "string"}],
            "paragraphs": [],
            "control_flow": {"calls": [], "loops": [], "branches": []},
            "operations": [],
        }
        report = run_testing_agent(
            parser_output=parser_output,
            analysis_output={},
            java_source="public class Test {\n    public static void main(String[] args) {\n        System.out.println(\"TEST\");\n    }\n}",
            cobol_source="",
        )
        assert "parser_tests" in report
        assert "conversion_tests" in report
        assert "behavioral_tests" in report
        assert "summary" in report
        assert "is_pipeline_green" in report
        assert report["summary"]["total"] > 0
