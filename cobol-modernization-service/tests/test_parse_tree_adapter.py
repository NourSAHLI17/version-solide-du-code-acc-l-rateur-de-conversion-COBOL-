"""Integration tests for ANTLR + heuristic hybrid parse_tree_adapter."""

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MINIMAL_VALID_COBOL = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. HELLO.
       PROCEDURE DIVISION.
           STOP RUN.
"""


@unittest.skipUnless(importlib.util.find_spec("antlr4"), "antlr4-python3-runtime not installed")
class TestParseTreeAdapter(unittest.TestCase):
    def test_valid_program_antlr_ok_and_heuristic_fields(self):
        from app.parsers.generated.parse_tree_adapter import parse_with_generated_antlr

        out = parse_with_generated_antlr(MINIMAL_VALID_COBOL)
        self.assertEqual(out.get("parser_backend"), "antlr")
        self.assertTrue(out.get("antlr_syntax_ok"), msg=out.get("antlr_errors"))
        self.assertEqual(out.get("antlr_errors"), [])
        self.assertIn("symbol_table", out)
        self.assertIn("operations", out)
        self.assertIn("parser_revision", out)
        self.assertEqual(out.get("antlr_adapter_revision"), "2026-05-10")

    def test_garbage_source_antlr_fails_heuristic_may_preflight(self):
        from app.parsers.generated.parse_tree_adapter import parse_with_generated_antlr

        out = parse_with_generated_antlr("@@@ not cobol @@@")
        self.assertEqual(out.get("parser_backend"), "antlr")
        self.assertFalse(out.get("antlr_syntax_ok"))
        self.assertTrue(len(out.get("antlr_errors") or []) >= 1)


@unittest.skipUnless(importlib.util.find_spec("antlr4"), "antlr4-python3-runtime not installed")
class TestAntlrCobolParserIntegration(unittest.TestCase):
    def test_antlr_parser_end_to_end(self):
        from app.parsers.antlr_parser import AntlrCobolParser

        p = AntlrCobolParser()
        if p.missing_requirements():
            self.skipTest("ANTLR artifacts incomplete: " + str(p.missing_requirements()))
        out = p.parse(MINIMAL_VALID_COBOL)
        self.assertEqual(out.get("parser_backend"), "antlr")
        self.assertTrue(out.get("antlr_syntax_ok"))


if __name__ == "__main__":
    unittest.main()
