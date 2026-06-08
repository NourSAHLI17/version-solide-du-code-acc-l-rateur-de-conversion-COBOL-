"""Tests for javac compile-and-repair loop."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.java_compile_repair import (
    CompileRepairResult,
    JavacError,
    JavacResult,
    attempt_incompatible_types_fix,
    attempt_symbol_fix,
    compile_and_repair,
    convert_cobol_star_comments,
    parse_javac_errors,
    run_javac,
)


_BROKEN = """
public class Test {
    private static class LoanRecord { private String loanStatus; }
    void foo() { LoanRecord r = new LoanRecord(); r.status = "AC"; }
}
"""

_FIXED = """
public class Test {
    private static class LoanRecord { private String loanStatus; }
    void foo() { LoanRecord r = new LoanRecord(); r.loanStatus = "AC"; }
}
"""

_JAVAC_FAIL = """Test.java:4: error: cannot find symbol
  symbol:   variable status
  location: variable r of type LoanRecord
"""


class JavaCompileRepairTests(unittest.TestCase):
    def test_convert_cobol_star_comments(self):
        src = "* 1000-SELECT-FEE-RATE;\n    private int x;\n"
        fixed, changed = convert_cobol_star_comments(src)
        self.assertTrue(changed)
        self.assertIn("// 1000-SELECT-FEE-RATE;", fixed)
        self.assertNotIn("* 1000", fixed)

    def test_parse_javac_errors(self):
        errors = parse_javac_errors(_JAVAC_FAIL)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].error_type, "cannot_find_symbol")
        self.assertEqual(errors[0].symbol, "status")

    def test_compile_and_repair_symbol_fix(self):
        call_count = 0

        def fake_javac(_files, *, work_dir):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return JavacResult(success=False, returncode=1, stdout="", stderr=_JAVAC_FAIL)
            return JavacResult(success=True, returncode=0, stdout="", stderr="")

        with patch("app.services.java_compile_repair.run_javac", side_effect=fake_javac):
            result = compile_and_repair({"Test.java": _BROKEN})

        self.assertTrue(result.success)
        self.assertIn("r.loanStatus", result.java_files["Test.java"])
        self.assertNotIn("r.status", result.java_files["Test.java"])
        self.assertTrue(result.repair_notes)

    def test_attempt_incompatible_types_bigdecimal_to_int(self):
        src = {
            "T.java": "class T {\n  void m() {\n    int x = rec.loanDaysPastDue;\n  }\n}\n",
        }
        err = JavacError(
            file="T.java",
            line=3,
            column=20,
            message="incompatible types: java.math.BigDecimal cannot be converted to int",
            error_type="incompatible_types",
        )
        self.assertTrue(attempt_incompatible_types_fix(err, src))
        self.assertIn(".intValue()", src["T.java"])

    def test_attempt_symbol_fix_uses_reconciler(self):
        sources = {"Test.java": _BROKEN}
        from app.services.java_compile_repair import JavacError

        err = JavacError(
            file="Test.java",
            line=4,
            column=10,
            message="cannot find symbol",
            error_type="cannot_find_symbol",
            symbol="status",
        )
        self.assertTrue(attempt_symbol_fix(err, sources, symbol_table=None))
        self.assertIn("loanStatus", sources["Test.java"])

    def test_no_progress_stops_loop(self):
        def always_fail(_files, *, work_dir):
            return JavacResult(success=False, returncode=1, stdout="", stderr="X.java:1: error: bad\n")

        with patch("app.services.java_compile_repair.run_javac", side_effect=always_fail):
            with patch(
                "app.services.java_compile_repair._dispatch_repair",
                return_value=False,
            ):
                result = compile_and_repair(
                    {"X.java": "public class X { bad syntax here }"},
                    max_iterations=5,
                )
        self.assertFalse(result.success)
        self.assertTrue(result.remaining_errors or result.stderr)
        self.assertTrue(any("no applicable repairs" in line for line in result.iteration_log))

    def test_stall_detection_stops_loop(self):
        fail_stderr = "X.java:1: error: cannot find symbol\n  symbol:   variable foo\n"

        def always_same_errors(_files, *, work_dir):
            return JavacResult(success=False, returncode=1, stdout="", stderr=fail_stderr)

        with patch("app.services.java_compile_repair.run_javac", side_effect=always_same_errors):
            with patch(
                "app.services.java_compile_repair._apply_validated_repair",
                return_value=True,
            ):
                result = compile_and_repair(
                    {"X.java": "public class X { void m() { foo(); } }"},
                    max_iterations=5,
                )
        self.assertFalse(result.success)
        self.assertTrue(any("STALLED" in line for line in result.iteration_log))

    def test_deduplicate_field_declarations(self):
        from app.services.java_compile_repair import deduplicate_field_declarations

        src = """public class T {
    private String ZERO = "";
    private String ZERO = "";
    void m() {}
}
"""
        fixed, n = deduplicate_field_declarations(src)
        self.assertEqual(n, 1)
        self.assertEqual(fixed.count("private String ZERO"), 1)
        self.assertIn("DEDUP", fixed)

    def test_deduplicate_preserves_same_name_across_nested_classes(self):
        from app.services.java_compile_repair import deduplicate_field_declarations

        src = """public class Outer {
    public static class Inner {
        private String wsProgramName = "";
    }
    private String wsProgramName = "";
}
"""
        fixed, n = deduplicate_field_declarations(src)
        self.assertEqual(n, 0)
        self.assertEqual(fixed.count("wsProgramName"), 2)

    def test_remove_type_shadow_fields(self):
        from app.services.java_compile_repair import remove_type_shadow_fields

        src = """public class T {
    // TODO: auto-declared missing variable 'BigDecimal'
    private String BigDecimal = "";
    private BigDecimal x = BigDecimal.ZERO;
}
"""
        fixed, n = remove_type_shadow_fields(src)
        self.assertEqual(n, 1)
        self.assertNotIn("private String BigDecimal", fixed)
        self.assertIn("BigDecimal.ZERO", fixed)
        self.assertIn("SHADOW-FIX", fixed)


if __name__ == "__main__":
    unittest.main()
