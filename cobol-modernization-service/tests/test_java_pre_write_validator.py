"""Tests for post-generation Java pre-write validation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.converters.cobol_name_converter import enrich_symbol_table_java_names
from app.services.java_pre_write_validator import (
    JavaPreWriteValidationError,
    validate_java_before_write,
    write_java_file,
)

_VALID = """\
package demo;

public class Demo {
    private static final int MAX = 1;
    private int count;

    public static void main(String[] args) {
        new Demo().run();
    }

    public void run() {
        count = MAX;
        System.out.println(count);
    }
}
"""


class JavaPreWriteValidatorTests(unittest.TestCase):
    def test_valid_source_passes(self):
        self.assertEqual(validate_java_before_write(_VALID), [])

    def test_rejects_orphan_method_outside_class(self):
        bad = _VALID + "\nprivate void orphan() {\n}\n"
        errors = validate_java_before_write(bad)
        self.assertTrue(any("outside class" in e.lower() for e in errors))

    def test_rejects_unbalanced_braces(self):
        bad = _VALID.replace("}\n", "", 1)
        errors = validate_java_before_write(bad)
        self.assertTrue(any("brace" in e.lower() for e in errors))

    def test_rejects_multiple_top_level_classes(self):
        bad = _VALID + "\npublic class Second {\n}\n"
        errors = validate_java_before_write(bad)
        self.assertTrue(any("top-level class" in e.lower() for e in errors))

    def test_rejects_missing_newline_terminator(self):
        bad = _VALID.rstrip("\n")
        errors = validate_java_before_write(bad)
        self.assertTrue(any("newline" in e.lower() for e in errors))

    def test_rejects_stub_only_methods(self):
        bad = """\
public class Stub {
    public static void main(String[] args) {
    }
}
"""
        errors = validate_java_before_write(bad)
        self.assertTrue(
            any("substantive" in e.lower() or "stub" in e.lower() for e in errors)
        )

    def test_write_java_file_skips_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Bad.java"
            with self.assertRaises(JavaPreWriteValidationError):
                write_java_file(path, "public class Bad {")
            self.assertFalse(path.exists())

    def test_rejects_non_canonical_loan_field_with_parser_output(self):
        bad = """\
package demo;

public class Demo {
    private static class LoanRecord {
        private String loanStatus;
    }

    private void run(LoanRecord loan) {
        loan.status = "A";
    }
}
"""
        parser_output = {
            "symbol_table": enrich_symbol_table_java_names(
                [{"name": "LOAN-STATUS", "pic": "X(1)", "java_field": "loanStatus"}]
            ),
        }
        errors = validate_java_before_write(bad, parser_output=parser_output)
        self.assertTrue(any("non-canonical" in e.lower() for e in errors))
        self.assertTrue(any("loanStatus" in e for e in errors))

    def test_rejects_dangling_canonical_field_reference(self):
        bad = """\
public class Demo {
    private void run() {
        int x = this.loanStatus;
    }
}
"""
        parser_output = {
            "symbol_table": enrich_symbol_table_java_names(
                [{"name": "LOAN-STATUS", "pic": "9(5)", "java_field": "loanStatus"}]
            ),
        }
        errors = validate_java_before_write(bad, parser_output=parser_output)
        self.assertTrue(any("dangling" in e.lower() for e in errors))

    def test_rejects_non_canonical_loan_record_class(self):
        bad = """\
public class Demo {
    private static class Loan {
        private String loanStatus;
    }
}
"""
        parser_output = {"symbol_table": []}
        errors = validate_java_before_write(bad, parser_output=parser_output)
        self.assertTrue(any("LoanRecord" in e for e in errors))

    def test_write_java_file_writes_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Demo.java"
            write_java_file(path, _VALID)
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))
            self.assertTrue(text.rstrip().endswith("}"))


if __name__ == "__main__":
    unittest.main()
