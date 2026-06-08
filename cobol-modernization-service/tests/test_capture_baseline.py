"""Tests for the portable baseline capture abstraction (F39).

These tests exercise path resolution, staging, and result structure
without requiring GnuCOBOL to be installed.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.e2e.capture_baseline import (
    MAIN_PROGS,
    SUB_PROGS,
    INPUT_DATS,
    PLACEHOLDER_DATS,
    find_cobc,
    resolve_paths,
    stage_work_dir,
    capture_baseline,
    build_main_program_baseline,
    write_baseline_json_files,
)
from tests.e2e.baseline_metrics import KEY_METRICS, SUB_PROGRAM_BASELINES


class TestResolvePaths(unittest.TestCase):
    def test_defaults_derive_from_service_root(self):
        root = Path("/fake/cobol-modernization-service")
        paths = resolve_paths(root)
        self.assertEqual(paths["seq_dir"], Path("/fake/acme-bank-v3/src/sequential"))
        self.assertEqual(paths["cpy_dir"], Path("/fake/acme-bank-v3/copybooks"))
        self.assertEqual(paths["data_dir"], Path("/fake/acme-bank-v3/data"))
        self.assertEqual(
            paths["baseline_dir"],
            root / "tests" / "e2e" / "baseline",
        )

    def test_overrides_respected(self):
        root = Path("/fake/service")
        paths = resolve_paths(
            root,
            seq_dir=Path("/custom/seq"),
            baseline_dir=Path("/custom/out"),
        )
        self.assertEqual(paths["seq_dir"], Path("/custom/seq"))
        self.assertEqual(paths["baseline_dir"], Path("/custom/out"))


class TestStageWorkDir(unittest.TestCase):
    def test_placeholders_created(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work"
            seq = Path(td) / "seq"
            data = Path(td) / "data"
            work.mkdir()
            seq.mkdir()
            data.mkdir()
            (seq / "CALCFEE.cbl").write_text("dummy", encoding="utf-8")
            (data / "LOANFILE.dat").write_text("data", encoding="utf-8")

            stage_work_dir(work, seq, data)

            self.assertTrue((work / "CALCFEE.cbl").exists())
            self.assertTrue((work / "LOANFILE.dat").exists())
            for ph in PLACEHOLDER_DATS:
                self.assertTrue((work / ph).exists())


class TestCaptureBaselineErrors(unittest.TestCase):
    def test_raises_when_cobc_not_found(self):
        with patch("tests.e2e.capture_baseline.find_cobc", return_value=None):
            with self.assertRaises(RuntimeError) as ctx:
                capture_baseline(Path("/fake"), cobc_path=None)
            self.assertIn("cobc", str(ctx.exception))

    def test_raises_when_seq_dir_missing(self):
        with self.assertRaises(RuntimeError) as ctx:
            capture_baseline(
                Path("/fake"),
                cobc_path="cobc",
                seq_dir=Path("/nonexistent/seq"),
            )
        self.assertIn("Sequential variant directory", str(ctx.exception))


class TestConstants(unittest.TestCase):
    def test_main_progs_populated(self):
        self.assertIn("RISKSCOR", MAIN_PROGS)
        self.assertIn("LOANEVAL", MAIN_PROGS)

    def test_sub_progs_populated(self):
        self.assertIn("CALCFEE", SUB_PROGS)
        self.assertIn("CHKAML", SUB_PROGS)

    def test_input_dats_are_set(self):
        self.assertIsInstance(INPUT_DATS, set)
        self.assertIn("LOANFILE.dat", INPUT_DATS)


class TestBaselineJson(unittest.TestCase):
    def test_riskscor_key_metrics_curated(self):
        m = KEY_METRICS["RISKSCOR"]
        self.assertEqual(m["CLASS_1_count"], 726)
        self.assertEqual(m["CLASS_2_count"], 0)
        self.assertEqual(m["CLASS_3_count"], 0)
        self.assertEqual(m["CLASS_4_count"], 0)
        self.assertEqual(m["TOTAL_PROVISION"], "0.00")

    def test_build_json_from_fixture_stdout(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "RISKSCOR_stdout.txt").write_text(
                "RISKSCOR COMPLETED.\n  CLASS 1: 000004\n",
                encoding="utf-8",
            )
            (base / "RISKSCOR_exitcode.txt").write_text("0", encoding="utf-8")
            doc = build_main_program_baseline(
                base, "RISKSCOR", cobol_compiler="GnuCOBOL test"
            )
            self.assertEqual(doc["program"], "RISKSCOR")
            self.assertEqual(doc["exit_code"], 0)
            self.assertEqual(doc["key_metrics"]["CLASS_1_count"], 726)
            self.assertIn("stdout_md5", doc)

    def test_sub_program_baselines_have_test_cases(self):
        self.assertGreaterEqual(len(SUB_PROGRAM_BASELINES["CHKAML"]["test_cases"]), 2)
        pep = SUB_PROGRAM_BASELINES["CHKAML"]["test_cases"][1]
        self.assertEqual(pep["name"], "pep_hit")
        self.assertEqual(pep["expected_output"]["clear"], "Y")


if __name__ == "__main__":
    unittest.main()
