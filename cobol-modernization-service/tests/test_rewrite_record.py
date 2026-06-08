"""Tests for REWRITE copy-then-modify record serialization (F13)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.converters.record_layout import layout_as_dict, layout_from_copybook_path, parse_display_field
from app.converters.rewrite_record import (
    RISKSCOR_LOAN_WRITTEN_FIELDS,
    collect_rewrite_targets,
    detect_written_record_fields,
    format_record_rewrite,
)
from app.parsers.cobol_parser import ParserLayer
from app.services.pipeline_service import PipelineService
from app.services.riskscor_java_repair import repair_riskscor_rewrite_java

ACME = Path(__file__).resolve().parents[2] / "acme-bank-v3"
LOANCOPY = ACME / "copybooks" / "LOANCOPY.cpy"
LOANFILE = ACME / "data" / "LOANFILE.dat"
RISKSCOR = ACME / "src" / "RISKSCOR.cbl"

VALID_LOAN_STATUS = frozenset({"AC", "RS", "LT", "SD", "WO"})
VALID_LOAN_CLASS = frozenset({"1", "2", "3", "4"})


class RewriteDetectionTests(unittest.TestCase):
    def test_detect_riskscor_written_loan_fields(self):
        src = RISKSCOR.read_text(encoding="utf-8")
        layout = layout_from_copybook_path(LOANCOPY)
        pipeline = PipelineService()
        out = pipeline.run_pipeline(src, {"copylib_paths": [str(ACME / "copybooks")]})
        written = collect_rewrite_targets(
            out,
            src,
            layout,
            explicit=set(RISKSCOR_LOAN_WRITTEN_FIELDS),
        )
        self.assertIn("LOAN-CLASS", written)
        self.assertIn("LOAN-PROVISION-RATE", written)
        self.assertIn("LOAN-PROVISION-AMT", written)


class LoanFileRewriteIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = layout_from_copybook_path(LOANCOPY)
        cls.by_name = layout_as_dict(cls.layout)

    def _first_record(self) -> str:
        line = LOANFILE.read_text(encoding="utf-8").splitlines()[0].rstrip("\r\n")
        self.assertEqual(len(line), 238)
        return line

    def test_rewrite_preserves_all_fields_except_loan_class(self):
        raw = self._first_record()
        original = {
            f.name: parse_display_field(raw, f)
            for f in self.layout
        }
        rewritten = format_record_rewrite(
            raw,
            self.layout,
            {"LOAN-CLASS": "2"},
            written_fields={"LOAN-CLASS"},
        )
        self.assertEqual(len(rewritten), 238)
        for field in self.layout:
            new_val = parse_display_field(rewritten, field)
            if field.name == "LOAN-CLASS":
                self.assertEqual(new_val, "2")
            else:
                self.assertEqual(
                    new_val,
                    original[field.name],
                    f"field {field.name} changed unexpectedly",
                )

    def test_rebuilt_from_scratch_would_corrupt_status(self):
        """Naive StringBuilder rebuild shifts fields — copy-then-modify does not."""
        raw = self._first_record()
        status = self.by_name["LOAN-STATUS"]
        wrong_status = raw[36:38]
        correct_status = raw[31:33]
        self.assertNotEqual(wrong_status, correct_status)
        self.assertIn(correct_status, VALID_LOAN_STATUS)
        rewritten = format_record_rewrite(
            raw,
            self.layout,
            {"LOAN-CLASS": "3"},
            written_fields={"LOAN-CLASS"},
        )
        self.assertIn(parse_display_field(rewritten, status), VALID_LOAN_STATUS)
        self.assertNotEqual(parse_display_field(rewritten, status), "00")

    def test_riskscor_rewrite_fields_on_first_five_records(self):
        status_f = self.by_name["LOAN-STATUS"]
        class_f = self.by_name["LOAN-CLASS"]
        lines = [
            ln.rstrip("\r\n")
            for ln in LOANFILE.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ][:5]
        for line in lines:
            rec = format_record_rewrite(
                line,
                self.layout,
                {"LOAN-CLASS": parse_display_field(line, class_f)},
                written_fields={"LOAN-CLASS"},
            )
            self.assertIn(parse_display_field(rec, status_f), VALID_LOAN_STATUS)
            self.assertIn(parse_display_field(rec, class_f), VALID_LOAN_CLASS)


class RiskscorJavaRepairTests(unittest.TestCase):
    def test_repair_injects_copy_then_modify_format(self):
        bad_java = """
public class Riskscor {
    private static class LoanRecord {
        int loanId;
        String loanClass;
    }
    private String formatLoanRecord(LoanRecord rec) {
        StringBuilder sb = new StringBuilder();
        sb.append(String.format("%010d", rec.loanId));
        sb.append(repeat(" ", 18));
        return sb.toString();
    }
    private LoanRecord parseLoanRecord(String line) {
        LoanRecord rec = new LoanRecord();
        rec.loanId = Integer.parseInt(line.substring(0, 10));
        return rec;
    }
}
"""
        src = RISKSCOR.read_text(encoding="utf-8")
        out = PipelineService().run_pipeline(src, {"copylib_paths": [str(ACME / "copybooks")]})
        fixed, notes = repair_riskscor_rewrite_java(
            bad_java,
            program_name="RISKSCOR",
            parser_output=out,
            cobol_source=src,
        )
        self.assertIn("riskscor_rewrite_copy_then_modify_applied", notes)
        self.assertIn("rec.rawLine", fixed)
        self.assertIn("char[] chars = rec.rawLine.toCharArray()", fixed)
        self.assertIn("CobolRecordRewrite.overwrite(chars, 33, 34", fixed)
        self.assertNotIn("StringBuilder sb = new StringBuilder()", fixed)

    def test_repair_syncs_loan_record_fields_with_parse(self):
        bad_java = """
public class Riskscor {
    private LoanRecord currentLoan;
    private LoanRecord parseLoanRecord(String line) {
        LoanRecord rec = new LoanRecord();
        rec.custId = 1;
        return rec;
    }
    private static class LoanRecord {
        int loanId;
        int custId;
        String status;
    }
}
"""
        src = RISKSCOR.read_text(encoding="utf-8")
        out = PipelineService().run_pipeline(src, {"copylib_paths": [str(ACME / "copybooks")]})
        fixed, notes = repair_riskscor_rewrite_java(
            bad_java,
            program_name="RISKSCOR",
            parser_output=out,
            cobol_source=src,
        )
        self.assertIn("loan_record_field_refs_normalized", notes)
        self.assertIn("rec.loanCustId", fixed)
        self.assertNotIn("rec.custId", fixed)
        self.assertIn("String loanStatus;", fixed)
        self.assertIn("BigDecimal loanOutstanding;", fixed)
        self.assertIn("rec.loanStatus = CobolRecordRewrite.parseString", fixed)


if __name__ == "__main__":
    unittest.main()
