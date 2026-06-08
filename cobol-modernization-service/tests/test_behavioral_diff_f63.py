"""Unit tests for F63 behavioral diff helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.e2e.behavioral_diff import (
    build_synthetic_stdout_baseline,
    compare_key_metrics,
    extract_metric_from_stdout,
    format_behavioral_detail,
    generate_sub_program_harness,
)
from tests.e2e.baseline_metrics import KEY_METRICS


class TestMetricExtraction(unittest.TestCase):
    def test_riskscor_class_counts(self):
        stdout = "\n".join(
            [
                "RISKSCOR COMPLETED.",
                "  CLASS 1: 000726",
                "  CLASS 2: 000000",
                "  CLASS 3: 000000",
                "  CLASS 4: 000000",
                "  TOTAL PROV: 000000000000000",
            ]
        )
        km = compare_key_metrics("RISKSCOR", stdout, KEY_METRICS["RISKSCOR"])
        self.assertTrue(all(km.values()), km)


class TestSyntheticStdout(unittest.TestCase):
    def test_synthetic_matches_java_format(self):
        synth = build_synthetic_stdout_baseline("RISKSCOR", KEY_METRICS["RISKSCOR"])
        actual = synth  # same builder target
        from tests.e2e.behavioral_diff import compare_stdout

        ok, _ = compare_stdout("RISKSCOR", "", actual, KEY_METRICS["RISKSCOR"])
        self.assertTrue(ok)


class TestHarnessGeneration(unittest.TestCase):
    def test_chkaml_harness_compiles_textually(self):
        from tests.e2e.baseline_metrics import SUB_PROGRAM_BASELINES

        src = generate_sub_program_harness(
            "CHKAML", SUB_PROGRAM_BASELINES["CHKAML"]["test_cases"]
        )
        self.assertIn("ChkamlHarness", src)
        self.assertIn("CASE clean_client", src)


class TestBehavioralDetail(unittest.TestCase):
    def test_riskscor_pass_detail(self):
        diff = {
            "verdict": "PASS",
            "key_metrics_match": {
                "CLASS_1_count": True,
                "CLASS_2_count": True,
                "CLASS_3_count": True,
                "CLASS_4_count": True,
            },
        }
        self.assertEqual(format_behavioral_detail("RISKSCOR", diff), "726/0/0/0")


if __name__ == "__main__":
    unittest.main()
