"""Tests for IBM-aligned complexity tier classification."""

import unittest
from pathlib import Path

from app.services.complexity_classifier import classify_complexity_tier, _file_entries
from app.services.pipeline_service import PipelineService

ACME_ROOT = Path(__file__).resolve().parents[2] / "acme-bank-v3" / "src"


class TestComplexityClassifier(unittest.TestCase):
    def test_standard_small_program(self):
        result = classify_complexity_tier(
            {
                "dependencies": {"copybooks": [], "files": [], "external_calls": []},
                "total_lines": 200,
            }
        )
        self.assertEqual(result["tier"], "Standard")
        self.assertLessEqual(result["score"], 4)

    def test_file_entries_not_double_counted(self):
        parser_output = {
            "program_name": "DEMO",
            "files": [{"name": "LOAN-FILE", "organization": "SEQUENTIAL"}],
            "dependencies": {
                "file_entries": [{"name": "LOAN-FILE", "organization": "SEQUENTIAL"}],
                "files": ["LOAN-FILE"],
            },
        }
        self.assertEqual(len(_file_entries(parser_output)), 1)

    def test_copybooks_from_source_when_deps_empty(self):
        if not ACME_ROOT.is_dir():
            self.skipTest("ACME sources not available")
        source = (ACME_ROOT / "RPTMONTH.cbl").read_text(encoding="utf-8")
        parser_output = {
            "program_name": "RPTMONTH",
            "total_lines": 564,
            "files": [{"name": f"F{i}", "organization": "SEQUENTIAL"} for i in range(4)],
            "dependencies": {"copybooks": [], "files": [], "external_calls": []},
        }
        result = classify_complexity_tier(parser_output, source_code=source)
        self.assertEqual(result["tier"], "Complex")
        self.assertGreater(result["score"], 4)

    def test_enterprise_high_io_and_subprograms(self):
        result = classify_complexity_tier(
            {
                "dependencies": {
                    "copybooks": ["A"] * 10,
                    "external_calls": ["CALCFEE", "CHKAML"],
                    "file_entries": [
                        {"organization": "INDEXED"},
                        {"organization": "SEQUENTIAL"},
                        {"organization": "SEQUENTIAL"},
                        {"organization": "SEQUENTIAL"},
                        {"organization": "SEQUENTIAL"},
                        {"organization": "SEQUENTIAL"},
                    ],
                },
                "total_lines": 1200,
                "sorts": [{"type": "SORT"}],
            },
            source_code="       EXEC SQL\n",
        )
        self.assertEqual(result["tier"], "Enterprise")
        self.assertGreater(result["score"], 12)
        self.assertIn("EXEC SQL", result["drivers"])


class TestAcmeComplexityTiers(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not ACME_ROOT.is_dir():
            cls.sources = {}
            return
        cls.service = PipelineService()
        cls.sources = {
            prog: (ACME_ROOT / f"{prog}.cbl").read_text(encoding="utf-8")
            for prog in (
                "CALCFEE",
                "CHKAML",
                "RISKSCOR",
                "RECOVRY",
                "RPTMONTH",
                "LOANEVAL",
            )
            if (ACME_ROOT / f"{prog}.cbl").is_file()
        }

    def _tier(self, program: str) -> str:
        if program not in self.sources:
            self.skipTest("ACME sources not available")
        parser_output = self.service.parse_cobol(self.sources[program])
        result = classify_complexity_tier(parser_output, source_code=self.sources[program])
        return result["tier"]

    def test_calcfee_standard(self):
        self.assertEqual(self._tier("CALCFEE"), "Standard")

    def test_chkaml_standard(self):
        self.assertEqual(self._tier("CHKAML"), "Standard")

    def test_riskscor_complex(self):
        self.assertEqual(self._tier("RISKSCOR"), "Complex")

    def test_recovry_complex(self):
        self.assertEqual(self._tier("RECOVRY"), "Complex")

    def test_rptmonth_complex(self):
        self.assertEqual(self._tier("RPTMONTH"), "Complex")

    def test_loaneval_enterprise(self):
        self.assertEqual(self._tier("LOANEVAL"), "Enterprise")


if __name__ == "__main__":
    unittest.main()
