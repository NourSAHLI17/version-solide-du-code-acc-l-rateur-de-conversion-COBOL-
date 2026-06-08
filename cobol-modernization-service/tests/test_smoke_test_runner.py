"""Tests for the smoke test runner."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.smoke_test_runner import (
    SmokeTestResult,
    _compare_baseline,
    _extract_file_control_names,
    _generate_wrapper_source,
    run_smoke_test,
)


class TestExtractFileControlNames(unittest.TestCase):
    def test_empty_parser(self):
        self.assertEqual(_extract_file_control_names({}), [])

    def test_files_with_assign(self):
        parser = {
            "files": [
                {"name": "CUSTFILE", "assign": "CUSTFILE"},
                {"name": "LOANFILE", "assign": "'LOANFILE.dat'"},
            ]
        }
        names = _extract_file_control_names(parser)
        self.assertIn("CUSTFILE", names)
        self.assertIn("LOANFILE", names)
        self.assertIn("LOANFILE.dat", names)

    def test_dependencies_files(self):
        parser = {
            "dependencies": {
                "files": ["SCORFILE", "COLFILE"],
                "file_kinds": {"SCORFILE": "indexed", "COLFILE": "sequential"},
            }
        }
        names = _extract_file_control_names(parser)
        self.assertIn("SCORFILE", names)
        self.assertIn("COLFILE", names)

    def test_deduplication(self):
        parser = {
            "files": [{"name": "X", "assign": "X"}],
            "dependencies": {"files": ["X"], "file_kinds": {"X": "seq"}},
        }
        names = _extract_file_control_names(parser)
        self.assertEqual(names.count("X"), 1)


class TestGenerateWrapper(unittest.TestCase):
    def test_no_wrapper_if_main_exists(self):
        java = "public class Foo { public static void main(String[] args) {} }"
        self.assertIsNone(_generate_wrapper_source(java, "Foo", "FOO"))

    def test_wrapper_for_void_method(self):
        java = "public class ChkAml { public void checkAml() {} }"
        wrapper = _generate_wrapper_source(java, "ChkAml", "CHKAML")
        self.assertIsNotNone(wrapper)
        self.assertIn("ChkAmlSmokeTest", wrapper)
        self.assertIn("public static void main", wrapper)
        self.assertIn("checkAml()", wrapper)

    def test_wrapper_for_return_method(self):
        java = "public class Calc { public int compute() { return 42; } }"
        wrapper = _generate_wrapper_source(java, "Calc", "CALC")
        self.assertIsNotNone(wrapper)
        self.assertIn("compute()", wrapper)
        self.assertIn("[SMOKE]", wrapper)

    def test_no_wrapper_if_no_methods(self):
        java = "public class Empty { private int x = 5; }"
        self.assertIsNone(_generate_wrapper_source(java, "Empty", "EMPTY"))


class TestCompareBaseline(unittest.TestCase):
    def test_matching_output(self):
        match, diff = _compare_baseline("hello\nworld", "hello\nworld")
        self.assertTrue(match)
        self.assertEqual(diff, "")

    def test_whitespace_matching(self):
        match, _ = _compare_baseline("hello\nworld\n", "  hello\nworld  ")
        self.assertTrue(match)

    def test_different_output(self):
        match, diff = _compare_baseline("hello\nworld", "hello\nplanet")
        self.assertFalse(match)
        self.assertIn("-planet", diff)
        self.assertIn("+world", diff)


class TestRunSmokeTest(unittest.TestCase):
    def test_no_java_code(self):
        result = run_smoke_test("", program_name="EMPTY")
        self.assertFalse(result.passed)
        self.assertFalse(result.compiled)
        self.assertEqual(result.error, "no Java code provided")

    def test_result_serialization(self):
        result = run_smoke_test("", program_name="TEST")
        d = result.to_dict()
        self.assertIn("program_name", d)
        self.assertIn("passed", d)
        self.assertIn("compiled", d)
        self.assertIn("test_cases", d)
        self.assertIn("pass_count", d)
        self.assertIn("fail_count", d)

    @patch("app.services.smoke_test_runner._compile_java")
    def test_compile_failure(self, mock_compile):
        mock_compile.return_value = (False, "error: something", {})
        result = run_smoke_test(
            "public class Bad { syntax error }",
            program_name="BAD",
        )
        self.assertFalse(result.passed)
        self.assertFalse(result.compiled)
        self.assertIn("compilation failed", result.error or "")

    def test_simple_passing_program(self):
        java = '''
public class SimplePass {
    public static void main(String[] args) {
        System.out.println("Hello smoke test");
    }
}
'''
        result = run_smoke_test(java, program_name="SIMPLEPASS")
        # Only passes if javac+java are available
        if result.compiled:
            self.assertTrue(result.passed)
            self.assertEqual(len(result.test_cases), 1)
            self.assertEqual(result.test_cases[0].exit_code, 0)
            self.assertIn("Hello smoke test", result.test_cases[0].stdout)
        else:
            self.assertFalse(result.passed)

    def test_failing_program(self):
        java = '''
public class FailProg {
    public static void main(String[] args) {
        System.exit(1);
    }
}
'''
        result = run_smoke_test(java, program_name="FAILPROG")
        if result.compiled:
            self.assertFalse(result.passed)
            self.assertEqual(result.test_cases[0].exit_code, 1)


if __name__ == "__main__":
    unittest.main()
