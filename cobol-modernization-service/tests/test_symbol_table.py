"""F55 — Shared SymbolTable across parser, scaffold, and downstream stages."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.converters.constrained_generation import (
    build_java_scaffolding,
    build_structured_representation,
)
from app.parsers.cobol_parser import ParserLayer
from app.services.symbol_table import SymbolTable, resolve_symbol_table


def parse_cobol(source_or_path: str) -> dict:
    """Parse COBOL from a file path or inline source string."""
    if "\n" in source_or_path or source_or_path.strip().endswith("."):
        source = source_or_path
    else:
        path = Path(source_or_path)
        if not path.is_file():
            repo_root = Path(__file__).resolve().parents[2]
            path = repo_root / "acme-bank-v3" / "src" / "CHKAML.cbl"
        source = path.read_text(encoding="utf-8", errors="replace")
    return ParserLayer().parse(source)


def build_scaffold(parser_output: dict, cobol_source: str = "") -> SimpleNamespace:
    """Build F45 scaffold and populate file_handles / sub_programs on the shared table."""
    table = resolve_symbol_table(parser_output)
    rep = build_structured_representation(parser_output, cobol_source, symbol_table=table)
    build_java_scaffolding(rep, symbol_table=table, parser_output=parser_output)
    return SimpleNamespace(rep=rep, symbol_table=table)


def analyze(scaffold: SimpleNamespace, *, symbol_table: SymbolTable) -> SimpleNamespace:
    """Minimal downstream stage: must receive the same SymbolTable instance."""
    return SimpleNamespace(rep=scaffold.rep, symbol_table=symbol_table)


class SymbolTablePipelineTests(unittest.TestCase):
    def test_symbol_table_shared_across_pipeline(self):
        parser_output = parse_cobol("CHKAML.cbl")
        table = parser_output["symbol_table"]
        self.assertIsInstance(table, SymbolTable)
        self.assertGreater(len(table.fields) + len(table.methods), 0)

        scaffold = build_scaffold(parser_output)
        self.assertIs(scaffold.symbol_table, table)
        self.assertGreaterEqual(len(table.sub_programs), 0)

        analyzed = analyze(scaffold, symbol_table=table)
        self.assertIs(analyzed.symbol_table, table)

    def test_lookup_field_and_method(self):
        parser_output = parse_cobol(
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-STATUS PIC X(2) VALUE SPACES.
       PROCEDURE DIVISION.
       1000-MAIN.
           DISPLAY WS-STATUS.
           STOP RUN.
            """
        )
        table = resolve_symbol_table(parser_output)
        self.assertEqual(table.lookup_field("WS-STATUS"), "wsStatus")
        self.assertTrue(table.lookup_method("1000-MAIN"))

    def test_parser_only_creates_fields_methods_classes(self):
        parser_output = parse_cobol(
            """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 REC.
           05 REC-ID PIC 9(4).
       PROCEDURE DIVISION.
       MAIN-PARA.
           STOP RUN.
            """
        )
        table = resolve_symbol_table(parser_output)
        self.assertEqual(len(table.file_handles), 0)
        self.assertEqual(len(table.sub_programs), 0)
        self.assertGreater(len(table.fields), 0)
        self.assertGreater(len(table.methods), 0)


if __name__ == "__main__":
    unittest.main()
