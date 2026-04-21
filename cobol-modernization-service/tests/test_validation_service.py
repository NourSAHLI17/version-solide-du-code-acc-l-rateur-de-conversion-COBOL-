import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.validation.service import ValidationService


class ValidationServiceTests(unittest.TestCase):
    def setUp(self):
        self.validator = ValidationService()

    def test_json_equivalence_ignores_formatting(self):
        result = self.validator.validate_outputs(
            '{"status":"OK","count":1}',
            '{\n  "count": 1,\n  "status": "OK"\n}',
        )

        self.assertEqual(result["is_equivalent"], True)
        self.assertEqual(result["comparison_mode"], "json_structure")
        self.assertEqual(result["differences"], [])

    def test_json_diff_reports_field_changes(self):
        result = self.validator.validate_outputs(
            '{"status":"OK","count":1}',
            '{"status":"FAIL","count":1}',
        )

        self.assertEqual(result["is_equivalent"], False)
        self.assertEqual(result["comparison_mode"], "json_structure")
        self.assertIn("status: expected 'OK', got 'FAIL'", result["differences"])

    def test_normalized_text_equivalence_ignores_trailing_whitespace(self):
        result = self.validator.validate_outputs(
            "A   \nB\n",
            "A\nB",
        )

        self.assertEqual(result["is_equivalent"], True)
        self.assertEqual(result["comparison_mode"], "normalized_text")

    def test_line_diff_reports_text_mismatch(self):
        result = self.validator.validate_outputs(
            "APPROVED\n100",
            "REJECTED\n100",
        )

        self.assertEqual(result["is_equivalent"], False)
        self.assertEqual(result["comparison_mode"], "line_diff")
        self.assertIn("- APPROVED", result["differences"])
        self.assertIn("+ REJECTED", result["differences"])


if __name__ == "__main__":
    unittest.main()
