import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.parsers.antlr_parser import AntlrCobolParser


class AntlrScaffoldTests(unittest.TestCase):
    def setUp(self):
        self.parser = AntlrCobolParser()

    def test_main_grammar_files_exist(self):
        g = self.parser.grammar_root / "Cobol85.g4"
        self.assertTrue(g.exists())
        text = g.read_text(encoding="utf-8")
        self.assertIn("grammar Cobol85", text)
        self.assertGreater(len(text.splitlines()), 100)

    def test_generated_layout_files_exist(self):
        self.assertTrue((self.parser.generated_root / "__init__.py").exists())
        self.assertTrue((self.parser.generated_root / "README.md").exists())
        self.assertTrue((self.parser.generated_root / "parse_tree_adapter.py").exists())

    def test_missing_requirements_reports_runtime_or_generated_gaps(self):
        missing = self.parser.missing_requirements()
        self.assertIsInstance(missing, list)
        # Either fully provisioned (empty) or reports runtime / missing artifacts
        self.assertTrue(
            len(missing) == 0
            or any("antlr4" in item or "generated file" in item for item in missing),
        )

    def test_parse_raises_when_requirements_missing(self):
        # If anything is missing, parse must explain setup — exercised when deps stripped.
        if self.parser.missing_requirements():
            with self.assertRaises(RuntimeError) as context:
                self.parser.parse("STOP RUN.")
            self.assertIn("ANTLR parser backend is scaffolded but not ready", str(context.exception))

    @unittest.skipUnless(importlib.util.find_spec("antlr4"), "antlr4 runtime not installed")
    def test_parse_returns_json_when_provisioned(self):
        if self.parser.missing_requirements():
            self.skipTest("ANTLR artifacts incomplete")
        src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. TST.
       PROCEDURE DIVISION.
           STOP RUN.
"""
        out = self.parser.parse(src)
        self.assertIsInstance(out, dict)
        self.assertEqual(out.get("parser_backend"), "antlr")
        self.assertIn("antlr_syntax_ok", out)
        self.assertIn("operations", out)


if __name__ == "__main__":
    unittest.main()
