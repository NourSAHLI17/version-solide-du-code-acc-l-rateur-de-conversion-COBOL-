import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.analysis_prompt_utils import (
    clean_analysis_for_prompt,
    deduplicate_rules,
    get_chunk_rules,
    prepare_analysis_for_conversion_prompt,
)


class AnalysisPromptUtilsTests(unittest.TestCase):
    def test_deduplicate_rules_collapses_pattern_counts(self):
        rules = [
            "[pattern] MOVE 3 statement(s)",
            "[pattern] MOVE 1 statement(s)",
            "Minimum balance 100",
            "Minimum balance 100",
        ]
        out = deduplicate_rules(rules)
        self.assertEqual(len(out), 2)
        self.assertTrue(any(r.startswith("[pattern] MOVE") for r in out))
        self.assertIn("Minimum balance 100", out)

    def test_clean_analysis_strips_noise_fields(self):
        raw = {
            "program_name": "LOANEVAL",
            "business_rules": ["Rule A"],
            "all_business_rules": ["Rule A"],
            "risk_flags": ["WS-LOAN-STATUS"],
            "warnings": ["line exceeds column 72 in source", "real warning"],
            "sections": [
                {"name": "DEAD", "is_dead_code": True, "business_rules": ["x"]},
                {"name": "MAIN", "business_rules": ["Rule B"]},
            ],
            "analysis_engine": "llm",
        }
        cleaned = clean_analysis_for_prompt(raw)
        self.assertNotIn("all_business_rules", cleaned)
        self.assertNotIn("risk_flags", cleaned)
        self.assertNotIn("analysis_engine", cleaned)
        self.assertEqual(len(cleaned["sections"]), 1)
        self.assertEqual(cleaned["sections"][0]["name"], "MAIN")
        self.assertEqual(cleaned["warnings"], ["real warning"])

    def test_get_chunk_rules_caps_global_specific(self):
        sections = [{"name": "A", "business_rules": ["Section rule"]}]
        globals_ = [f"Global rule {i}" for i in range(20)]
        rules = get_chunk_rules(sections, globals_)
        self.assertIn("Section rule", rules)
        global_in = [r for r in rules if r.startswith("Global rule")]
        self.assertLessEqual(len(global_in), 15)

    def test_prepare_analysis_replaces_top_level_rules(self):
        analysis = {
            "business_rules": ["[pattern] X 1 statement(s)", "Global threshold 500"],
            "sections": [
                {"name": "P1", "business_rules": ["[pattern] X 3 statement(s)"]},
            ],
        }
        prepared = prepare_analysis_for_conversion_prompt(analysis)
        self.assertNotIn("all_business_rules", prepared)
        self.assertIsInstance(prepared["business_rules"], list)


if __name__ == "__main__":
    unittest.main()
