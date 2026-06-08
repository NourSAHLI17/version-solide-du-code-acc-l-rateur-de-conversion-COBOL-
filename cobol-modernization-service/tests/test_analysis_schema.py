"""F52 — Lenient LLM analysis schema validation."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.analysis import AnalysisOutput
from app.services.analysis_schema import (
    AnalysisFallback,
    lenient_repair,
    parse_llm_analysis,
    parse_llm_chunk_from_data,
    parse_llm_chunk_response,
)


class AnalysisSchemaTests(unittest.TestCase):
    def test_lenient_repair_sections_dict(self):
        data = {"program_name": "CALCFEE", "sections": {"name": "MAIN", "role": "run"}}
        fixed = lenient_repair(data)
        self.assertIsInstance(fixed["sections"], list)
        self.assertEqual(fixed["sections"][0]["name"], "MAIN")

    def test_lenient_repair_rule_alias(self):
        data = {
            "program_name": "X",
            "business_rules": [{"rule": "compute fee"}],
        }
        fixed = lenient_repair(data)
        self.assertEqual(fixed["business_rules"][0]["description"], "compute fee")

    def test_lenient_repair_complexity_case(self):
        data = {"program_name": "X", "complexity": "Low"}
        fixed = lenient_repair(data)
        self.assertEqual(fixed["complexity"], "low")

    def test_parse_llm_analysis_minimal_on_partial_failure(self):
        raw = json.dumps(
            {
                "program_name": "CALCFEE",
                "complexity": "medium",
                "sections": [{"name": "MAIN", "role": "entry", "business_rules": []}],
            }
        )
        out = parse_llm_analysis(raw, "CALCFEE")
        self.assertIsInstance(out, AnalysisOutput)
        self.assertEqual(out.program_name, "CALCFEE")

    def test_parse_llm_chunk_paragraph_analyses(self):
        raw = json.dumps(
            {
                "paragraph_analyses": [
                    {
                        "name": "MAIN",
                        "role": "stop",
                        "business_rules": ["stop run"],
                        "risk_flags": [],
                        "warnings": [],
                    }
                ]
            }
        )
        rows, gp, reason = parse_llm_chunk_response(raw, "TST")
        self.assertIsNone(reason)
        self.assertIsNotNone(rows)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "MAIN")

    def test_parse_llm_chunk_invalid_json(self):
        rows, gp, reason = parse_llm_chunk_response("not json", "TST")
        self.assertIsNone(rows)
        self.assertEqual(reason, "invalid_json")

    def test_parse_llm_analysis_raises_on_invalid_json(self):
        with self.assertRaises(AnalysisFallback) as ctx:
            parse_llm_analysis("not json at all", "TST")
        self.assertEqual(ctx.exception.reason, "invalid_json")

    def test_chunk_from_data_trailing_comma_style(self):
        data = {
            "program_name": "TST",
            "sections": [{"name": "A", "role": "do work", "business_rules": []}],
        }
        rows, _, reason = parse_llm_chunk_from_data(data, "TST")
        self.assertIsNone(reason)
        self.assertEqual(rows[0]["name"], "A")


if __name__ == "__main__":
    unittest.main()
