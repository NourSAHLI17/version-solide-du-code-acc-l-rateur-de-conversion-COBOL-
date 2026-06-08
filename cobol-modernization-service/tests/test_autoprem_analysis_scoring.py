"""AUTOPREM analysis role and paragraph↔Java scoring alignment."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.agents.analysis_agent import AnalysisAgent
from app.parsers.cobol_parser import ParserLayer
from app.services.paragraph_java_matching import paragraph_has_java_method
from app.services.scoring_service import score_conversion
from app.services.segmenter import CobolSegmenter

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "autoprem"
COBOL = FIXTURE / "AUTOPREM.cbl"
JAVA = FIXTURE / "AUTOPREM.reference.java"


class AutopremAnalysisScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cobol = COBOL.read_text(encoding="utf-8")
        cls.java = JAVA.read_text(encoding="utf-8")
        cls.parser_output = ParserLayer().parse(cls.cobol)
        cls.agent = AnalysisAgent()
        cls.segments = CobolSegmenter().segment(cls.cobol, cls.parser_output)["segments"]

    def _section_roles(self) -> dict[str, str]:
        cf = self.parser_output.get("control_flow", {})
        ops = self.parser_output.get("operations", [])
        from app.services.symbol_table import resolve_symbol_entries

        st = resolve_symbol_entries(self.parser_output)
        paras = self.parser_output.get("paragraphs") or []
        out: dict[str, str] = {}
        for seg in self.segments:
            r = self.agent._analyze_segment(seg, self.parser_output, paras, cf, st, ops)
            out[r["name"]] = r["role"]
        return out

    def test_paragraph_java_aliases_match_reference_methods(self):
        from app.services.paragraph_java_matching import java_method_set_lookup

        ml, jb = java_method_set_lookup(self.java)
        expected = {
            "3000-DISPLAY-SUMMARY": "displaySummary",
            "4000-DISPLAY-REJECTED": "displayRejected",
            "4100-DISPLAY-QUOTE": "displayQuote",
            "2100-VALIDATE-QUOTE": "validateQuote",
            "2000-PROCESS-ALL-QUOTES": "processAllQuotes",
            "2500-FINAL-DECISION": "finalDecision",
        }
        for para, _method in expected.items():
            self.assertTrue(
                paragraph_has_java_method(para, ml, jb),
                msg=f"no Java method match for {para}",
            )

    def test_display_and_summary_roles(self):
        roles = self._section_roles()
        self.assertIn("summary", roles["3000-DISPLAY-SUMMARY"].lower())
        self.assertIn("reject", roles["4000-DISPLAY-REJECTED"].lower())
        self.assertIn("quote", roles["4100-DISPLAY-QUOTE"].lower())

    def test_process_all_quotes_is_iterative(self):
        roles = self._section_roles()
        role = roles["2000-PROCESS-ALL-QUOTES"].lower()
        self.assertTrue(
            "iterat" in role or "sequential" in role or "all test quotes" in role,
            msg=roles["2000-PROCESS-ALL-QUOTES"],
        )
        seg = next(s for s in self.segments if s["paragraph_name"] == "2000-PROCESS-ALL-QUOTES")
        cf = self.parser_output.get("control_flow", {})
        ops = self.parser_output.get("operations", [])
        from app.services.symbol_table import resolve_symbol_entries

        st = resolve_symbol_entries(self.parser_output)
        paras = self.parser_output.get("paragraphs") or []
        analyzed = self.agent._analyze_segment(seg, self.parser_output, paras, cf, st, ops)
        self.assertTrue(analyzed["has_loop"])

    def test_scoring_finds_methods_for_all_autoprem_paragraphs(self):
        analysis = {"sections": [], "business_rules": []}
        out = score_conversion(self.parser_output, analysis, self.java, program_name="AUTOPREM")
        missing = [
            row["paragraph"]
            for row in out["paragraph_breakdown"]
            if "no matching Java method" in row.get("notes", "")
        ]
        self.assertEqual(missing, [], msg=f"unmatched: {missing}")

    def test_write_only_warnings_filtered_for_flow_symbols(self):
        ops = list(self.parser_output.get("operations") or [])
        warnings = [
            {"message": "Variable PR-ACCIDENT-LOAD is written but never read — possible dead assignment"},
            {"message": "Variable QT-VEHICLE-VALUE is written but never read — possible dead assignment"},
            {"message": "Variable WS-DISP-POWER is written but never read — possible dead assignment"},
        ]
        kept = AnalysisAgent._filter_parser_write_only_warnings(warnings, ops)
        kept_msgs = [w.get("message", str(w)) if isinstance(w, dict) else str(w) for w in kept]
        self.assertNotIn("PR-ACCIDENT-LOAD", " ".join(kept_msgs))
        self.assertNotIn("QT-VEHICLE-VALUE", " ".join(kept_msgs))
        self.assertNotIn("WS-DISP-POWER", " ".join(kept_msgs))


if __name__ == "__main__":
    unittest.main()
