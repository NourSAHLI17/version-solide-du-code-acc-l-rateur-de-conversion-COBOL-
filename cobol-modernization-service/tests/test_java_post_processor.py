"""Tests for unified Java post-processing pipeline."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.java_post_processor import (
    apply_all_post_processing,
    strip_cross_package_imports,
)


class JavaPostProcessorTests(unittest.TestCase):
    def test_strip_cross_package_imports(self) -> None:
        src = (
            "package com.modernized.calcfee;\n"
            "import com.modernized.loaneval.Loaneval;\n"
            "public class Calcfee { }\n"
        )
        out = strip_cross_package_imports(src)
        self.assertNotIn("import com.modernized.", out)
        self.assertIn("public class Calcfee", out)

    def test_apply_all_post_processing_renames_calcfee(self) -> None:
        src = "public class Calcfee {\n  public void run() { }\n}\n"
        out, notes = apply_all_post_processing(src, "CALCFEE", None)
        self.assertIn("public class CalcFee", out)
        self.assertTrue(any("fix_program_class_declaration" in n for n in notes))

    def test_apply_all_post_processing_strips_mapping_notes(self) -> None:
        src = (
            "public class Demo {\n"
            "  public void run() { }\n"
            "}\n\n"
            "## MAPPING NOTES\n"
            "- block -> main\n"
        )
        out, notes = apply_all_post_processing(src, "DEMO", None)
        self.assertNotIn("MAPPING", out)
        self.assertTrue(any("strip_mapping_notes" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
