import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.parsers.antlr_parser import AntlrCobolParser


class AntlrScaffoldTests(unittest.TestCase):
    def setUp(self):
        self.parser = AntlrCobolParser()

    def test_placeholder_grammar_files_exist(self):
        self.assertTrue((self.parser.grammar_root / "Cobol85Lexer.g4").exists())
        self.assertTrue((self.parser.grammar_root / "Cobol85Parser.g4").exists())

    def test_generated_layout_files_exist(self):
        self.assertTrue((self.parser.generated_root / "__init__.py").exists())
        self.assertTrue((self.parser.generated_root / "README.md").exists())
        self.assertTrue((self.parser.generated_root / "parse_tree_adapter.py").exists())

    def test_missing_requirements_reports_runtime_or_generated_gaps(self):
        missing = self.parser.missing_requirements()
        self.assertTrue(any("antlr4" in item or "generated file" in item for item in missing))

    def test_parse_raises_clear_diagnostic(self):
        with self.assertRaises(RuntimeError) as context:
            self.parser.parse("PROCEDURE DIVISION.")

        message = str(context.exception)
        self.assertIn("ANTLR parser backend is scaffolded but not ready", message)
        self.assertIn("parse-tree adapter", message)


if __name__ == "__main__":
    unittest.main()
