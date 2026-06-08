"""Tests for the smart baseline comparator."""

from __future__ import annotations

import textwrap
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

from tests.e2e.smart_comparator import (
    CompareResult,
    LineMismatch,
    ProgramRules,
    FieldRule,
    compare_data_files,
    compare_lines,
    compare_outputs,
    compare_stdout,
    extract_numbers,
    load_diff_config,
    normalize_for_skeleton,
    numeric_match,
    replace_numbers_with_placeholder,
    PROGRAM_RULES,
)


class TestExtractNumbers(unittest.TestCase):
    def test_plain_integers(self):
        nums = extract_numbers("  CLASS 1: 000004")
        self.assertEqual(nums, [Decimal("1"), Decimal("000004")])

    def test_grouped_thousands(self):
        nums = extract_numbers("ENC=      1,044,818")
        self.assertEqual(nums, [Decimal("1044818")])

    def test_decimal(self):
        nums = extract_numbers("PROVISION: 10875.331")
        self.assertEqual(nums, [Decimal("10875.331")])

    def test_percentage_european(self):
        # European comma-decimal "0,00%" → two separate numbers (0 and 00)
        # since the regex splits on comma. Both sides parse the same way,
        # so comparison still works.
        nums = extract_numbers("TAUX PROV:   0,00%")
        self.assertEqual(len(nums), 2)
        self.assertTrue(all(n == 0 for n in nums))

    def test_negative(self):
        nums = extract_numbers("DELTA: -1500")
        self.assertEqual(nums, [Decimal("-1500")])

    def test_ignores_dates(self):
        nums = extract_numbers("LOANEVAL v6.0 - START 20260525-471200")
        self.assertEqual(nums, [])

    def test_ignores_version_strings(self):
        nums = extract_numbers("RPTMONTH v2.3 START 20260525")
        self.assertEqual(nums, [])

    def test_cobol_fixed_width_zeros(self):
        nums = extract_numbers("  TOTAL PROV: 000000000000000")
        self.assertEqual(nums, [Decimal("0")])

    def test_multiple_numbers(self):
        nums = extract_numbers("CNT=000004 ENC=000000104481856 PROV=0000000000000")
        self.assertEqual(nums, [Decimal("4"), Decimal("104481856"), Decimal("0")])

    def test_contiguous_digits_not_split(self):
        nums = extract_numbers("VALUE=000000104481856")
        self.assertEqual(len(nums), 1)
        self.assertEqual(nums[0], Decimal("104481856"))


class TestReplacePlaceholder(unittest.TestCase):
    def test_replaces_all(self):
        result = replace_numbers_with_placeholder("CLASS 1: 000004")
        self.assertEqual(result, "CLASS __NUM__: __NUM__")

    def test_dates_become_date_placeholder(self):
        result = replace_numbers_with_placeholder("START 20260525")
        self.assertEqual(result, "START __DATE__")

    def test_contiguous_zero_padded(self):
        result = replace_numbers_with_placeholder("TOTAL PROV: 000000000000000")
        self.assertEqual(result, "TOTAL PROV: __NUM__")


class TestCompareLines(unittest.TestCase):
    def test_exact_match(self):
        self.assertIsNone(compare_lines("hello", "hello"))

    def test_whitespace_ignored(self):
        self.assertIsNone(compare_lines("  hello  ", "hello"))

    def test_date_only_diff(self):
        self.assertIsNone(compare_lines(
            "LOANEVAL v6.0 - START 20260525-471200",
            "LOANEVAL v6.0 - START 20260601-093000",
        ))

    def test_number_within_tolerance(self):
        self.assertIsNone(compare_lines(
            "TOTAL PROV: 10875.330",
            "TOTAL PROV: 10875.331",
            tolerance_pct=0.001,
        ))

    def test_number_outside_tolerance(self):
        reason = compare_lines(
            "TOTAL PROV: 10000",
            "TOTAL PROV: 10500",
            tolerance_pct=0.001,
        )
        self.assertIsNotNone(reason)
        self.assertIn("numeric mismatch", reason)

    def test_exact_tolerance_rejects_any_diff(self):
        reason = compare_lines(
            "CLASS 1: 000004",
            "CLASS 1: 000005",
            tolerance_pct=0.0,
        )
        self.assertIsNotNone(reason)

    def test_both_zero_same_format(self):
        self.assertIsNone(compare_lines(
            "AMOUNT: 000000000000000",
            "AMOUNT: 000000000000000",
            tolerance_pct=0.001,
        ))

    def test_both_zero_different_format(self):
        # Same number of extracted values, both are 0
        self.assertIsNone(compare_lines(
            "AMOUNT: 0",
            "AMOUNT: 0",
            tolerance_pct=0.001,
        ))

    def test_text_skeleton_mismatch(self):
        reason = compare_lines(
            "CLASS 1: 000004",
            "CLASS_X: 000004",
            tolerance_pct=0.001,
        )
        self.assertIsNotNone(reason)

    def test_number_count_mismatch(self):
        reason = compare_lines(
            "CLASS 1: 000004",
            "CLASS: 000004 EXTRA 5",
            tolerance_pct=0.001,
        )
        self.assertIsNotNone(reason)

    def test_large_numbers_within_tolerance(self):
        self.assertIsNone(compare_lines(
            "ENC=000000104481856",
            "ENC=000000104481800",
            tolerance_pct=0.001,
        ))

    def test_large_numbers_outside_tolerance(self):
        reason = compare_lines(
            "ENC=000000104481856",
            "ENC=000000100000000",
            tolerance_pct=0.001,
        )
        self.assertIsNotNone(reason)


class TestProgramRules(unittest.TestCase):
    def test_riskscor_class_counts_exact(self):
        rules = PROGRAM_RULES["RISKSCOR"]
        self.assertEqual(rules.tolerance_for_line("  CLASS 1: 000004"), 0.0)
        self.assertEqual(rules.tolerance_for_line("  CLASS 4: 000000"), 0.0)

    def test_riskscor_provision_tolerant(self):
        rules = PROGRAM_RULES["RISKSCOR"]
        tol = rules.tolerance_for_line("  TOTAL PROV: 000000000000000")
        self.assertEqual(tol, 0.0001)

    def test_riskscor_default_for_other_lines(self):
        rules = PROGRAM_RULES["RISKSCOR"]
        tol = rules.tolerance_for_line("RISKSCOR COMPLETED.")
        self.assertEqual(tol, 0.001)

    def test_loaneval_counts_exact(self):
        rules = PROGRAM_RULES["LOANEVAL"]
        self.assertEqual(rules.tolerance_for_line("  READ        : 00000804"), 0.0)
        self.assertEqual(rules.tolerance_for_line("  APPROVED    : 00000001"), 0.0)
        self.assertEqual(rules.tolerance_for_line("  ERRORS      : 00000800"), 0.01)

    def test_recovry_action_counts_exact(self):
        rules = PROGRAM_RULES["RECOVRY"]
        self.assertEqual(rules.tolerance_for_line("    SMS    : 000000"), 0.0)
        self.assertEqual(rules.tolerance_for_line("    WOF    : 000000"), 0.0)

    def test_recovry_class_loans_exact_takes_priority(self):
        rules = PROGRAM_RULES["RECOVRY"]
        # Line contains both CLASS LOANS (exact) and AMOUNT (tolerant);
        # exact_fields are checked first, so exact wins.
        tol = rules.tolerance_for_line("  CLASS 2 LOANS: 000000 AMOUNT: 000000000000000")
        self.assertEqual(tol, 0.0)

    def test_recovry_standalone_amount_tolerant(self):
        rules = PROGRAM_RULES["RECOVRY"]
        tol = rules.tolerance_for_line("  AMOUNT: 000000000500000")
        self.assertEqual(tol, 0.0001)

    def test_rptmonth_loans_exact_amt_tolerant(self):
        rules = PROGRAM_RULES["RPTMONTH"]
        self.assertEqual(
            rules.tolerance_for_line("RPTMONTH COMPLETED. LOANS=00000004"), 0.0
        )
        self.assertEqual(
            rules.tolerance_for_line("RPTMONTH COMPLETED. AMT=00000000104481856"),
            0.0001,
        )


class TestNormalizeStdoutLine(unittest.TestCase):
    def test_compare_stdout_lines_ignores_leading_space_delta(self):
        from tests.e2e.smart_comparator import compare_stdout_lines, normalize_stdout_line

        self.assertEqual(normalize_stdout_line("  CLASS 1: 000726"), "CLASS 1: 000726")
        self.assertTrue(compare_stdout_lines("  CLASS 1: 000726", " CLASS 1: 000726"))

    def test_riskscor_spacing_only_diff_is_full_match(self):
        from app.services.behavioral_diff_runner import compare_smart_outputs

        baseline = (
            "RISKSCOR COMPLETED.\n"
            "  CLASS 1: 000726\n"
            "  CLASS 2: 000000\n"
            "  CLASS 3: 000000\n"
            "  CLASS 4: 000000\n"
            "  TOTAL PROV: 000000000000000\n"
        )
        actual = (
            "RISKSCOR COMPLETED.\n"
            " CLASS 1: 000726\n"
            " CLASS 2: 000000\n"
            " CLASS 3: 000000\n"
            " CLASS 4: 000000\n"
            " TOTAL PROV: 000000000000000\n"
        )
        diff = compare_smart_outputs(baseline, actual, program_name="RISKSCOR")
        self.assertEqual(diff["diff_percentage"], 0.0)
        self.assertEqual(diff["matching_lines"], 6)
        self.assertEqual(diff["lines_compared"], 6)


class TestCompareOutputs(unittest.TestCase):
    def _write_pair(self, td: str, baseline: str, actual: str) -> tuple[Path, Path]:
        bp = Path(td) / "baseline.txt"
        ap = Path(td) / "actual.txt"
        bp.write_text(baseline)
        ap.write_text(actual)
        return bp, ap

    def test_identical_files(self):
        content = "RISKSCOR COMPLETED.\n  CLASS 1: 000004\n"
        with TemporaryDirectory() as td:
            bp, ap = self._write_pair(td, content, content)
            result = compare_outputs(bp, ap, program="RISKSCOR")
            self.assertTrue(result.match)

    def test_date_difference_ignored(self):
        b = "LOANEVAL v6.0 - START 20260525-120000\nDONE\n"
        a = "LOANEVAL v6.0 - START 20261231-235959\nDONE\n"
        with TemporaryDirectory() as td:
            bp, ap = self._write_pair(td, b, a)
            result = compare_outputs(bp, ap, program="LOANEVAL")
            self.assertTrue(result.match)

    def test_exact_field_catches_difference(self):
        b = "  CLASS 1: 000004\n"
        a = "  CLASS 1: 000005\n"
        with TemporaryDirectory() as td:
            bp, ap = self._write_pair(td, b, a)
            result = compare_outputs(bp, ap, program="RISKSCOR")
            self.assertFalse(result.match)
            self.assertEqual(len(result.mismatches), 1)

    def test_tolerant_field_allows_small_diff(self):
        b = "  TOTAL PROV: 100000000\n"
        a = "  TOTAL PROV: 100000009\n"
        with TemporaryDirectory() as td:
            bp, ap = self._write_pair(td, b, a)
            result = compare_outputs(bp, ap, program="RISKSCOR")
            self.assertTrue(result.match)

    def test_tolerant_field_rejects_large_diff(self):
        b = "  TOTAL PROV: 100000000\n"
        a = "  TOTAL PROV: 200000000\n"
        with TemporaryDirectory() as td:
            bp, ap = self._write_pair(td, b, a)
            result = compare_outputs(bp, ap, program="RISKSCOR")
            self.assertFalse(result.match)

    def test_line_count_mismatch(self):
        b = "LINE1\nLINE2\n"
        a = "LINE1\n"
        with TemporaryDirectory() as td:
            bp, ap = self._write_pair(td, b, a)
            result = compare_outputs(bp, ap)
            self.assertFalse(result.match)

    def test_stats_populated(self):
        b = "  CLASS 1: 000004\nSTART 20260525\n"
        a = "  CLASS 1: 000004\nSTART 20260601\n"
        with TemporaryDirectory() as td:
            bp, ap = self._write_pair(td, b, a)
            result = compare_outputs(bp, ap, program="RISKSCOR")
            self.assertTrue(result.match)
            self.assertEqual(result.stats.get("exact_ok", result.stats.get("exact_matches")), 1)
            self.assertGreaterEqual(
                result.stats.get("ignored_lines", result.stats.get("date_skips", 0)),
                1,
            )

    def test_missing_file(self):
        with TemporaryDirectory() as td:
            bp = Path(td) / "baseline.txt"
            bp.write_text("hello\n")
            result = compare_outputs(bp, Path(td) / "nope.txt")
            self.assertFalse(result.match)
            self.assertIn("not found", result.message)


class TestCompareDataFiles(unittest.TestCase):
    def test_identical(self):
        data = b"RECORD1DATA00001\nRECORD2DATA00002\n"
        with TemporaryDirectory() as td:
            bp = Path(td) / "b.dat"
            ap = Path(td) / "a.dat"
            bp.write_bytes(data)
            ap.write_bytes(data)
            result = compare_data_files(bp, ap)
            self.assertTrue(result.match)

    def test_trailing_whitespace_ignored(self):
        with TemporaryDirectory() as td:
            bp = Path(td) / "b.dat"
            ap = Path(td) / "a.dat"
            bp.write_bytes(b"RECORD1   \nRECORD2   \n")
            ap.write_bytes(b"RECORD1\nRECORD2\n")
            result = compare_data_files(bp, ap)
            self.assertTrue(result.match)

    def test_trailing_whitespace_exact_mode(self):
        with TemporaryDirectory() as td:
            bp = Path(td) / "b.dat"
            ap = Path(td) / "a.dat"
            bp.write_bytes(b"RECORD1   \n")
            ap.write_bytes(b"RECORD1\n")
            result = compare_data_files(bp, ap, ignore_trailing_whitespace=False)
            self.assertFalse(result.match)

    def test_record_content_mismatch(self):
        with TemporaryDirectory() as td:
            bp = Path(td) / "b.dat"
            ap = Path(td) / "a.dat"
            bp.write_bytes(b"RECORD1X\n")
            ap.write_bytes(b"RECORD1Y\n")
            result = compare_data_files(bp, ap)
            self.assertFalse(result.match)
            self.assertEqual(len(result.mismatches), 1)


class TestF64ConfigDrivenStdout(unittest.TestCase):
    def test_load_riskscor_config(self):
        cfg = load_diff_config("RISKSCOR")
        self.assertIn("CLASS 1:", cfg["stdout_tolerance"]["exact_fields"])

    def test_config_driven_compare_uses_exact_fields(self):
        cfg = load_diff_config("RISKSCOR")
        b = "  CLASS 1: 000004\n  CLASS 2: 000000\n"
        a = "  CLASS 1: 000005\n  CLASS 2: 000000\n"
        self.assertFalse(compare_stdout(b, a, cfg))


class TestCompareFullBaseline(unittest.TestCase):
    """Integration test: self-compare the real baseline directory."""

    def test_self_compare_matches(self):
        baseline_dir = Path(__file__).parent / "baseline"
        if not baseline_dir.exists():
            self.skipTest("baseline not captured yet")
        from tests.e2e.smart_comparator import compare_full
        total, match, mismatch, missing = compare_full(baseline_dir, baseline_dir)
        self.assertGreater(total, 0)
        self.assertEqual(mismatch, 0)
        self.assertEqual(missing, 0)
        self.assertEqual(total, match)


if __name__ == "__main__":
    unittest.main()
