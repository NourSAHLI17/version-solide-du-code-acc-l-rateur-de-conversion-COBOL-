"""Tests for app.services.java_analysis_enricher."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.java_analysis_enricher import enrich_java_with_analysis


SAMPLE_JAVA = """\
package com.modernized.calcfee;

import java.math.BigDecimal;

public class Calcfee {

    private BigDecimal wsFeeGross = BigDecimal.ZERO;

    public void selectFeeRate() {
        // EVALUATE on LK-REQ-LOAN-TYPE
    }

    public void computeFileFee() {
        // COMPUTE WS-FEE-GROSS
    }

    public void computeInsurance() {
        // COMPUTE LK-RESP-INSURANCE
    }
}
"""

SAMPLE_ANALYSIS = {
    "sections": [
        {
            "name": "1000-SELECT-FEE-RATE",
            "role": "Select fee rate based on loan type",
            "business_rules": [
                "[pattern] EVALUATE on LK-REQ-LOAN-TYPE: 6 branch(es) including WHEN OTHER default",
            ],
        },
        {
            "name": "2000-COMPUTE-FILE-FEE",
            "role": "Calculate gross filing fee",
            "business_rules": [
                "[pattern] Conditional: WS-FEE-GROSS < WS-FILE-FEE-MIN",
                "[pattern] Range clamping: value bounded between min and max",
            ],
        },
        {
            "name": "3000-COMPUTE-INSURANCE",
            "role": "Calculate insurance component",
            "business_rules": [],
        },
    ],
    "risk_points": [
        "financial decision rule",
        "[pattern] File operations without explicit FILE STATUS checking",
    ],
    "complexity_drivers": [
        "dense conditional branching",
        "5 COMPUTE statement(s)",
    ],
    "dependencies": {
        "external_calls": [
            {"program_name": "CHKAML", "type": "sub_program", "using": ["WS-AML-REQUEST"]},
        ],
        "copybooks": [],
        "files": [],
    },
}


class TestEnrichJavaWithAnalysis(unittest.TestCase):

    def test_method_javadoc_injected(self):
        enriched, notes = enrich_java_with_analysis(SAMPLE_JAVA, SAMPLE_ANALYSIS)

        self.assertIn("/**", enriched)
        self.assertIn("Select fee rate based on loan type", enriched)
        self.assertIn("EVALUATE on LK-REQ-LOAN-TYPE", enriched)
        self.assertIn("Calculate gross filing fee", enriched)
        self.assertIn("Range clamping", enriched)
        any_javadoc_note = [n for n in notes if n.startswith("analysis_javadoc:")]
        self.assertGreaterEqual(len(any_javadoc_note), 2)

    def test_class_risk_javadoc_injected(self):
        enriched, notes = enrich_java_with_analysis(SAMPLE_JAVA, SAMPLE_ANALYSIS)

        self.assertIn("@implNote", enriched)
        self.assertIn("Risk points", enriched)
        self.assertIn("financial decision rule", enriched)
        risk_notes = [n for n in notes if "risk" in n]
        self.assertGreater(len(risk_notes), 0)

    def test_dependency_import_and_field(self):
        enriched, notes = enrich_java_with_analysis(SAMPLE_JAVA, SAMPLE_ANALYSIS)

        self.assertIn("import com.modernized.chkaml.Chkaml;", enriched)
        self.assertIn("private final Chkaml chkamlService = new Chkaml();", enriched)
        import_notes = [n for n in notes if "import" in n]
        self.assertGreater(len(import_notes), 0)

    def test_no_duplicate_javadoc_if_already_present(self):
        java_with_javadoc = SAMPLE_JAVA.replace(
            "    public void selectFeeRate() {",
            "    /** Already documented. */\n    public void selectFeeRate() {",
        )
        enriched, notes = enrich_java_with_analysis(java_with_javadoc, SAMPLE_ANALYSIS)
        self.assertEqual(enriched.count("Already documented"), 1)
        javadoc_notes_for_select = [n for n in notes if "selectFeeRate" in n]
        self.assertEqual(len(javadoc_notes_for_select), 0)

    def test_empty_analysis_is_noop(self):
        enriched, notes = enrich_java_with_analysis(SAMPLE_JAVA, None)
        self.assertEqual(enriched, SAMPLE_JAVA)
        self.assertEqual(notes, [])

    def test_string_analysis_parsed(self):
        import json
        enriched, notes = enrich_java_with_analysis(SAMPLE_JAVA, json.dumps(SAMPLE_ANALYSIS))
        self.assertIn("Select fee rate based on loan type", enriched)

    def test_complexity_hint_embedded_sql(self):
        analysis = {
            "sections": [],
            "risk_points": [],
            "complexity_drivers": ["embedded SQL"],
            "dependencies": {"external_calls": []},
        }
        enriched, notes = enrich_java_with_analysis(SAMPLE_JAVA, analysis)
        self.assertIn("TODO: [analysis-hint] Embedded SQL", enriched)

    def test_complexity_hint_high_file_io(self):
        analysis = {
            "sections": [],
            "risk_points": [],
            "complexity_drivers": ["9 files opened (high I/O complexity)"],
            "dependencies": {"external_calls": []},
        }
        enriched, notes = enrich_java_with_analysis(SAMPLE_JAVA, analysis)
        self.assertIn("TODO: [analysis-hint] High file I/O", enriched)

    def test_complexity_hint_internal_sort(self):
        analysis = {
            "sections": [],
            "risk_points": [],
            "complexity_drivers": ["internal SORT operation"],
            "dependencies": {"external_calls": []},
        }
        enriched, notes = enrich_java_with_analysis(SAMPLE_JAVA, analysis)
        self.assertIn("TODO: [analysis-hint] Internal SORT", enriched)
        self.assertIn("java.util.List + Comparator", enriched)

    def test_enriched_java_still_has_valid_structure(self):
        enriched, _ = enrich_java_with_analysis(SAMPLE_JAVA, SAMPLE_ANALYSIS)
        self.assertIn("public class Calcfee {", enriched)
        self.assertIn("public void selectFeeRate()", enriched)
        self.assertIn("public void computeFileFee()", enriched)
        self.assertTrue(enriched.strip().endswith("}"))


if __name__ == "__main__":
    unittest.main()
