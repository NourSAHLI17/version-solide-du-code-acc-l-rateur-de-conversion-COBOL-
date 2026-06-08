import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.analysis_agent import AnalysisAgent, _ANALYSIS_LLM_BATCH_SIZE
from app.parsers.cobol_parser import ParserLayer


class AnalysisLlmReliabilityTests(unittest.TestCase):
    def test_paragraph_batches_max_four(self):
        names = [f"P{i:04d}" for i in range(17)]
        batches = AnalysisAgent._analysis_paragraph_batches(names, batch_size=4)
        self.assertEqual(len(batches), 5)
        self.assertEqual(len(batches[0]), 4)
        self.assertEqual(_ANALYSIS_LLM_BATCH_SIZE, 4)

    def test_parse_json_lenient_trailing_comma(self):
        raw = '{"sections":[{"name":"A","role":"test",}]}'
        data = AnalysisAgent._parse_json_lenient(raw)
        self.assertIsInstance(data, dict)
        self.assertEqual(len(data["sections"]), 1)

    def test_compact_parser_subset_omits_unrelated_symbols(self):
        agent = AnalysisAgent()
        po = ParserLayer().parse(Path("tests/fixtures/autoprem/AUTOPREM.cbl").read_text(encoding="utf-8"))
        subset = agent._compact_parser_subset_for_analysis(po, ["2260-COMPUTE-ACCIDENT-LOAD"])
        sym_names = {s["name"] for s in subset.get("symbol_table_entries") or []}
        self.assertIn("PR-ACCIDENT-LOAD", sym_names)
        payload = agent._compact_json_dumps(subset)
        self.assertLess(len(payload), 80_000)

    def test_filter_pr_accident_write_only_warning(self):
        ops = [
            {
                "type": "COMPUTE",
                "paragraph": "2200-COMPUTE-PREMIUM",
                "target": "PR-NET-PREMIUM",
                "expression": "PR-BASE-PREMIUM * PR-AGE-COEF + PR-ACCIDENT-LOAD",
            }
        ]
        warnings = [
            {"message": "Variable PR-ACCIDENT-LOAD is written but never read — possible dead assignment"},
        ]
        kept = AnalysisAgent._filter_parser_write_only_warnings(warnings, ops)
        self.assertEqual(kept, [])

    def test_normalize_sections_fills_missing(self):
        rows = [{"name": "4100-DISPLAY-QUOTE", "role": "Show quote"}]
        out, notes = AnalysisAgent._normalize_llm_sections(
            rows,
            ["4100-DISPLAY-QUOTE", "3000-DISPLAY-SUMMARY"],
        )
        self.assertEqual(len(out), 2)
        self.assertTrue(any("synthesized" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
