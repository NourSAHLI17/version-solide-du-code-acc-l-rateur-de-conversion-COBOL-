"""Tests for COBOL DISPLAY record layout and PIC byte-size calculation (F12)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.converters.record_layout import (
    build_record_layout,
    layout_as_dict,
    layout_from_copybook_path,
    parse_display_field,
    pic_display_byte_size,
)

ACME = Path(__file__).resolve().parents[2] / "acme-bank-v3"
LOANCOPY = ACME / "copybooks" / "LOANCOPY.cpy"
LOANFILE = ACME / "data" / "LOANFILE.dat"

VALID_LOAN_STATUS = frozenset({"AC", "RS", "LT", "SD", "WO"})
VALID_LOAN_CLASS = frozenset({"1", "2", "3", "4"})


class PicDisplayByteSizeTests(unittest.TestCase):
    def test_pic_x(self):
        self.assertEqual(pic_display_byte_size("X(10)"), 10)

    def test_pic_9(self):
        self.assertEqual(pic_display_byte_size("9(8)"), 8)

    def test_pic_9_v9m(self):
        self.assertEqual(pic_display_byte_size("9(11)V99"), 13)

    def test_pic_9_v99_literal(self):
        self.assertEqual(pic_display_byte_size("9(7)V99"), 9)

    def test_pic_9_v9_paren(self):
        self.assertEqual(pic_display_byte_size("9(2)V9(4)"), 6)

    def test_pic_s9(self):
        self.assertEqual(pic_display_byte_size("S9(4)"), 4)

    def test_pic_edited_zz_comma(self):
        self.assertEqual(pic_display_byte_size("ZZ,ZZ9"), 6)


class LoanCopyLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = layout_from_copybook_path(LOANCOPY)
        cls.by_name = layout_as_dict(cls.layout)

    def test_total_record_length_238(self):
        total = sum(f.length for f in self.layout)
        self.assertEqual(total, 238)

    def test_loan_status_offset_31(self):
        field = self.by_name["LOAN-STATUS"]
        self.assertEqual(field.offset, 31)
        self.assertEqual(field.length, 2)

    def test_loan_class_offset_33(self):
        field = self.by_name["LOAN-CLASS"]
        self.assertEqual(field.offset, 33)
        self.assertEqual(field.length, 1)

    def test_not_wrong_offsets_36_38(self):
        """Regression: bad converter used 36/38 instead of 31/33."""
        self.assertNotEqual(self.by_name["LOAN-STATUS"].offset, 36)
        self.assertNotEqual(self.by_name["LOAN-CLASS"].offset, 38)

    def test_cumulative_chain_before_status(self):
        self.assertEqual(self.by_name["LOAN-ID"].offset, 0)
        self.assertEqual(self.by_name["LOAN-CUST-ID"].offset, 10)
        self.assertEqual(self.by_name["LOAN-ACCT-ID"].offset, 18)
        self.assertEqual(self.by_name["LOAN-TYPE"].offset, 28)


class LoanFileIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = layout_from_copybook_path(LOANCOPY)
        cls.by_name = layout_as_dict(cls.layout)
        cls.status = cls.by_name["LOAN-STATUS"]
        cls.loan_class = cls.by_name["LOAN-CLASS"]

    def _records(self, n: int = 5):
        lines = LOANFILE.read_text(encoding="utf-8", errors="replace").splitlines()
        return [ln.rstrip("\n\r") for ln in lines if ln.strip()][:n]

    def test_first_five_records_status_and_class_valid(self):
        for idx, line in enumerate(self._records(5), start=1):
            status = parse_display_field(line, self.status)
            loan_class = parse_display_field(line, self.loan_class)
            self.assertIn(
                status,
                VALID_LOAN_STATUS,
                f"record {idx}: status={status!r} at [{self.status.offset}:{self.status.end}]",
            )
            self.assertIn(
                loan_class,
                VALID_LOAN_CLASS,
                f"record {idx}: class={loan_class!r} at [{self.loan_class.offset}:{self.loan_class.end}]",
            )
            self.assertNotEqual(status, "00", f"record {idx}: wrong offset (numeric spill)")
            self.assertNotEqual(loan_class, " ", f"record {idx}: wrong offset (space pad)")

    def test_first_record_matches_known_slice(self):
        line = self._records(1)[0]
        self.assertEqual(line[31:33], "AC")
        self.assertEqual(line[33:34], "1")


if __name__ == "__main__":
    unittest.main()
