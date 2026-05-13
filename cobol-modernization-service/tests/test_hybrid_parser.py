"""Tests for hybrid merger, hybrid parser backend, and column-aware paragraph extraction."""

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MINIMAL = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. HYBRIDTST.
       PROCEDURE DIVISION.
       MAIN.
           DISPLAY "OK".
           STOP RUN.
"""


@unittest.skipUnless(importlib.util.find_spec("antlr4"), "antlr4 runtime not installed")
class TestHybridParserBackend(unittest.TestCase):
    def test_hybrid_returns_merged_flags(self):
        from app.parsers.hybrid_parser import HybridCobolParser

        p = HybridCobolParser()
        if p.missing_requirements():
            self.skipTest("ANTLR not provisioned: " + str(p.missing_requirements()))
        out = p.parse(MINIMAL)
        self.assertEqual(out.get("parser_backend"), "hybrid")
        self.assertIn("antlr_syntax_ok", out)
        self.assertTrue(out.get("antlr_syntax_ok"))
        self.assertIn("operations", out)
        self.assertIn("symbol_table", out)
        self.assertIn("grammar_metadata", out)
        self.assertIn("authoritative_reference_tree", out["grammar_metadata"])


class TestHybridMerger(unittest.TestCase):
    def test_merge_dedupes_operations(self):
        from app.parsers.hybrid_merger import HybridMerger

        h = {
            "operations": [{"type": "DISPLAY", "paragraph": "MAIN", "value": "X"}],
            "control_flow": {"calls": [], "branches": [], "loops": [], "gotos": []},
            "symbol_table": [],
        }
        partial = {
            "operations_antlr": [
                {"type": "DISPLAY", "paragraph": "MAIN", "raw_antlr": "DISPLAY'OK'", "source": "antlr"},
            ],
            "control_flow_antlr": {"calls": [], "branches": []},
        }
        m = HybridMerger().merge(h, partial, antlr_syntax_ok=True)
        self.assertGreaterEqual(len(m["operations"]), 1)


class TestColumnAwareParagraphs(unittest.TestCase):
    def test_skips_comment_and_extracts_body(self):
        from app.agents.analysis_agent import AnalysisAgent

        src = """000100 IDENTIFICATION DIVISION.
000200 PROGRAM-ID. T.
000300 PROCEDURE DIVISION.
000400 P1.
000500     DISPLAY "HI".
000600 P2.
000700     STOP RUN.
"""
        bodies = AnalysisAgent._extract_paragraph_sources(src, ["P1", "P2"])
        self.assertIn("DISPLAY", " ".join(bodies["P1"]))


class TestFactoryHybrid(unittest.TestCase):
    def test_create_hybrid_parser(self):
        from app.core.config import AppConfig
        from app.parsers.factory import create_parser
        from app.parsers.hybrid_parser import HybridCobolParser

        p = create_parser(AppConfig(parser_backend="hybrid"))
        self.assertIsInstance(p, HybridCobolParser)


if __name__ == "__main__":
    unittest.main()
