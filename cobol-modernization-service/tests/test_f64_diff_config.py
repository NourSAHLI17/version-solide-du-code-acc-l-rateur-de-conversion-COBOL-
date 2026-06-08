"""F64 — per-program tolerance config for behavioral diff."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.e2e.baseline_metrics import KEY_METRICS
from tests.e2e.behavioral_diff import build_synthetic_stdout_baseline, compare_stdout
from tests.e2e.smart_comparator import (
    compare_generated_file,
    compare_stdout as compare_stdout_configured,
    load_diff_config,
)


class TestF64DiffConfigFiles(unittest.TestCase):
    def test_all_main_programs_have_config(self):
        baseline_dir = Path(__file__).parent / "e2e" / "baseline"
        for prog in ("LOANEVAL", "RECOVRY", "RISKSCOR", "RPTMONTH"):
            cfg = load_diff_config(prog, baseline_dir)
            self.assertIn("stdout_tolerance", cfg, prog)
            self.assertIn("exact_fields", cfg["stdout_tolerance"], prog)


class TestF64StdoutTolerance(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline_dir = Path(__file__).parent / "e2e" / "baseline"

    def test_timestamp_line_ignored_loaneval(self):
        """Stray timestamp difference must PASS when line is in ignore_fields."""
        cfg = load_diff_config("LOANEVAL", self.baseline_dir)
        baseline = (
            "LOANEVAL v6.0 - START 20260525-120000\n"
            "LOANEVAL COMPLETED.\n"
            "  READ        : 00000800\n"
            "  APPROVED    : 00000454\n"
            "  CONDITIONAL : 00000102\n"
            "  DECLINED    : 00000170\n"
            "  ERRORS      : 00000074\n"
        )
        actual = baseline.replace("20260525-120000", "20261231-235959")
        self.assertTrue(compare_stdout_configured(baseline, actual, cfg))

    def test_class_count_exact_mismatch_fails_riskscor(self):
        """CLASS 1 off by one must FAIL (exact_fields)."""
        cfg = load_diff_config("RISKSCOR", self.baseline_dir)
        baseline = (
            "RISKSCOR COMPLETED.\n"
            "  CLASS 1: 000726\n"
            "  CLASS 2: 000000\n"
            "  CLASS 3: 000000\n"
            "  CLASS 4: 000000\n"
            "  TOTAL PROV: 000000000000000\n"
        )
        actual = baseline.replace("000726", "000727")
        self.assertFalse(compare_stdout_configured(baseline, actual, cfg))

    def test_loaneval_timestamp_noise_passes_via_behavioral_diff(self):
        km = KEY_METRICS["LOANEVAL"]
        synthetic = build_synthetic_stdout_baseline("LOANEVAL", km)
        baseline = "LOANEVAL v6.0 - START 20260525-120000\n" + synthetic
        actual = "LOANEVAL v6.0 - START 20990101-000000\n" + synthetic
        ok, detail = compare_stdout(
            "LOANEVAL", baseline, actual, km, baseline_dir=self.baseline_dir
        )
        self.assertTrue(ok, detail)

    def test_synthetic_riskscor_class_drift_fails(self):
        km = KEY_METRICS["RISKSCOR"]
        synthetic = build_synthetic_stdout_baseline("RISKSCOR", km)
        actual = synthetic.replace("000726", "000725")
        ok, detail = compare_stdout(
            "RISKSCOR", "", actual, km, baseline_dir=self.baseline_dir
        )
        self.assertFalse(ok, detail)


class TestF64GeneratedFileTolerance(unittest.TestCase):
    def test_ignore_byte_ranges(self):
        cfg = load_diff_config("RISKSCOR")
        rec_len = 200
        record = b"A" * 10 + b"00000000" + b"B" * (rec_len - 18)
        noisy = b"A" * 10 + b"99999999" + b"B" * (rec_len - 18)
        expected = {
            "filename": "BCTSUBM.dat",
            "record_count": 2,
            "bytes": record + record,
        }
        actual = {
            "filename": "BCTSUBM.dat",
            "record_count": 2,
            "bytes": noisy + noisy,
        }
        self.assertTrue(compare_generated_file(expected, actual, cfg))

    def test_record_count_mismatch_fails(self):
        cfg = load_diff_config("RISKSCOR")
        expected = {"filename": "BCTSUBM.dat", "record_count": 4, "bytes": b"x" * 40}
        actual = {"filename": "BCTSUBM.dat", "record_count": 3, "bytes": b"x" * 30}
        self.assertFalse(compare_generated_file(expected, actual, cfg))


if __name__ == "__main__":
    unittest.main()
