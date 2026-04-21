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

    def test_antlr_parser_raises_clear_scaffold_error(self):
        parser = AntlrCobolParser()
        with self.assertRaises(RuntimeError) as context:
            parser.parse("PROCEDURE DIVISION.")

        self.assertIn("ANTLR parser backend is scaffolded but not ready", str(context.exception))

    def test_factory_rejects_unknown_backend(self):
        with self.assertRaises(ValueError):
            create_parser(AppConfig(parser_backend="unknown"))


if __name__ == "__main__":
    unittest.main()
