"""Tests for post-generation Java field-name reconciliation."""

from __future__ import annotations

import time
import unittest

from app.converters.cobol_name_converter import enrich_symbol_table_java_names
from app.services.java_name_reconciler import (
    RISKSCOR_LOAN_RECORD_JAVA_FIELDS,
    reconcile_names,
)


_LOAN_RECORD_CLASS = """
    private static class LoanRecord {
        private int loanId;
        private int loanCustId;
        private String loanStatus;
        private String loanClass;
        private java.math.BigDecimal loanOutstanding;
        private int loanDaysPastDue;
        private java.math.BigDecimal loanProvisionRate;
        private java.math.BigDecimal loanProvisionAmt;
    }
"""


class JavaNameReconcilerTests(unittest.TestCase):
    def test_user_sample_r_status_to_loan_status(self):
        """F34 acceptance: legacy r.status → r.loanStatus when canonical is declared."""
        source = """
public class Test {
    private static class LoanRecord { private String loanStatus; }
    void foo() { LoanRecord r = new LoanRecord(); r.status = "AC"; }
}
"""
        symbol_table = enrich_symbol_table_java_names(
            [{"name": "LOAN-STATUS", "pic": "X(2)", "java_field": "loanStatus"}]
        )
        fixed, notes = reconcile_names(source, symbol_table=symbol_table, program_name="TEST")
        self.assertIn("r.loanStatus", fixed)
        self.assertNotIn("r.status", fixed)
        self.assertTrue(notes)

    def test_riskscor_aliases_on_rec_receiver(self):
        source = f"""\
public class RiskscorService {{
{_LOAN_RECORD_CLASS}
    private LoanRecord rec = new LoanRecord();

    void run() {{
        rec.status = "AC";
        rec.classNum = "1";
        rec.outstanding = java.math.BigDecimal.ZERO;
        rec.custId = 42;
    }}
}}
"""
        fixed, notes = reconcile_names(source, symbol_table=None, program_name="RISKSCOR")
        self.assertIn("rec.loanStatus", fixed)
        self.assertIn("rec.loanClass", fixed)
        self.assertIn("rec.loanOutstanding", fixed)
        self.assertIn("rec.loanCustId", fixed)
        self.assertNotIn("rec.status", fixed)
        self.assertNotIn("rec.classNum", fixed)
        self.assertTrue(any("status" in n and "loanStatus" in n for n in notes))

    def test_fuzzy_rename_when_unambiguous(self):
        source = """\
public class Demo {
    private String loanStatus;
    void m() { this.stat = "x"; }
}
"""
        fixed, notes = reconcile_names(source, symbol_table=None)
        self.assertIn("this.loanStatus", fixed)
        self.assertTrue(notes)

    def test_ambiguous_adds_todo_header(self):
        source = """\
public class Demo {
    private String loanStatus;
    private String loanStat;
    void m() { this.stat = "x"; }
}
"""
        fixed, _notes = reconcile_names(source, symbol_table=None)
        self.assertIn("// TODO: Resolve these name mismatches", fixed)
        self.assertIn("'stat'", fixed)

    def test_symbol_table_drives_alias_targets(self):
        symbol_table = enrich_symbol_table_java_names(
            [{"name": "LOAN-STATUS", "pic": "X(2)", "java_field": "loanStatus"}]
        )
        source = f"""\
public class X {{
{_LOAN_RECORD_CLASS}
    void m(LoanRecord rec) {{ rec.status = "A"; }}
}}
"""
        fixed, notes = reconcile_names(source, symbol_table=symbol_table)
        self.assertIn("rec.loanStatus", fixed)
        self.assertTrue(notes)

    def test_riskscor_canonical_field_set(self):
        self.assertIn("loanClass", RISKSCOR_LOAN_RECORD_JAVA_FIELDS)
        self.assertIn("loanProvisionRate", RISKSCOR_LOAN_RECORD_JAVA_FIELDS)

    def test_non_riskscor_dynamic_alias_from_symbol_table(self):
        """F34 generic: symbol-table-driven alias works for arbitrary programs."""
        source = """\
public class Calcfee {
    private java.math.BigDecimal lkReqLoanAmt;
    private String lkReqLoanType;

    void selectFeeRate() {
        java.math.BigDecimal amt = this.loanAmt;
        String tp = this.loanType;
    }
}
"""
        symbol_table = enrich_symbol_table_java_names([
            {"name": "LK-REQ-LOAN-AMT", "pic": "9(13)V99", "java_field": "lkReqLoanAmt"},
            {"name": "LK-REQ-LOAN-TYPE", "pic": "X(4)", "java_field": "lkReqLoanType"},
        ])
        fixed, notes = reconcile_names(
            source, symbol_table=symbol_table, program_name="CALCFEE"
        )
        self.assertIn("this.lkReqLoanAmt", fixed)
        self.assertIn("this.lkReqLoanType", fixed)
        self.assertNotIn("this.loanAmt", fixed)
        self.assertNotIn("this.loanType", fixed)
        self.assertTrue(notes)

    def test_dynamic_alias_does_not_override_declared(self):
        """When the short name IS declared, no alias rename should occur."""
        source = """\
public class Demo {
    private String custName;
    private String wsCustName;

    void m() {
        String x = this.custName;
    }
}
"""
        symbol_table = enrich_symbol_table_java_names([
            {"name": "WS-CUST-NAME", "pic": "X(30)", "java_field": "wsCustName"},
        ])
        fixed, notes = reconcile_names(source, symbol_table=symbol_table, program_name="DEMO")
        self.assertIn("this.custName", fixed)
        self.assertFalse(any("custName" in n for n in notes))

    def test_import_package_segments_not_treated_as_fields(self):
        source = """\
import java.math.BigDecimal;
import java.util.regex.Pattern;

public class Demo {
    private BigDecimal loanOutstanding;
    void m() { loanOutstanding = BigDecimal.ZERO; }
}
"""
        fixed, _notes = reconcile_names(source, symbol_table=None, program_name="DEMO")
        self.assertNotIn("// TODO: Resolve these name mismatches", fixed)
        self.assertNotIn("'math'", fixed)
        self.assertNotIn("'regex'", fixed)

    def test_reconcile_large_source_completes_quickly(self):
        """Regression: per-line javalang re-parse caused multi-minute stalls (FX3)."""
        body_lines = [
            "        rec.status = \"AC\";",
            "        rec.outstanding = java.math.BigDecimal.ZERO;",
        ] * 200
        source = f"""\
public class RiskscorService {{
{_LOAN_RECORD_CLASS}
    private LoanRecord rec = new LoanRecord();
    void run() {{
{chr(10).join(body_lines)}
    }}
}}
"""
        start = time.monotonic()
        fixed, notes = reconcile_names(source, symbol_table=None, program_name="RISKSCOR")
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 5.0, f"reconcile took {elapsed:.1f}s")
        self.assertIn("rec.loanStatus", fixed)
        self.assertTrue(notes)


if __name__ == "__main__":
    unittest.main()
