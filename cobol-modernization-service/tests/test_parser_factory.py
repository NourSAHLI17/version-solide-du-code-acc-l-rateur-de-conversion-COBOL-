import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import AppConfig
from app.parsers.antlr_parser import AntlrCobolParser
from app.parsers.cobol_parser import ParserLayer
from app.parsers.factory import create_parser


class ParserFactoryTests(unittest.TestCase):
    def test_factory_returns_heuristic_parser_by_default(self):
        parser = create_parser(AppConfig(parser_backend="heuristic"))
        self.assertIsInstance(parser, ParserLayer)

    def test_factory_returns_antlr_parser_when_requested(self):
        parser = create_parser(AppConfig(parser_backend="antlr"))
        self.assertIsInstance(parser, AntlrCobolParser)

    @unittest.skipUnless(importlib.util.find_spec("antlr4"), "antlr4 runtime not installed")
    def test_antlr_parser_returns_dict_when_provisioned(self):
        parser = AntlrCobolParser()
        if parser.missing_requirements():
            self.skipTest("ANTLR generation incomplete")
        src = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. TST.
       PROCEDURE DIVISION.
           STOP RUN.
"""
        out = parser.parse(src)
        self.assertIsInstance(out, dict)
        self.assertEqual(out.get("parser_backend"), "antlr")

    def test_factory_rejects_unknown_backend(self):
        with self.assertRaises(ValueError):
            create_parser(AppConfig(parser_backend="unknown"))


if __name__ == "__main__":
    unittest.main()
