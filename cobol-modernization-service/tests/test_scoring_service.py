"""Tests for deterministic conversion scoring."""

from __future__ import annotations

import json
import unittest

from app.parsers.cobol_parser import ParserLayer
from app.services.scoring_service import (
    DECISION_AUTO,
    DECISION_MANUAL,
    DECISION_RECONVERT,
    score_conversion,
)


class ScoringServiceTests(unittest.TestCase):
    def setUp(self):
        self.parser = ParserLayer()

    def test_same_input_same_score(self):
        parser_output = {
            "program_name": "DEMO",
            "paragraphs": ["A"],
            "control_flow": {"calls": [], "loops": [], "branches": [], "gotos": []},
            "operations": [],
        }
        analysis = {"sections": [], "business_rules": []}
        java = "public class Demo { void a() { if (true) { return; } } }"
        s1 = score_conversion(parser_output, analysis, java)
        s2 = score_conversion(parser_output, analysis, java)
        self.assertEqual(s1, s2)

    def test_high_score_friendly_java(self):
        source = """
       PROCEDURE DIVISION.
       A.
           PERFORM B.
           STOP RUN.
       B.
           DISPLAY "OK".
        """
        po = self.parser.parse(source)
        paragraphs = po.get("paragraphs") or []
        self.assertGreaterEqual(len(paragraphs), 2)
        analysis = {
            "sections": [
                {
                    "name": "A",
                    "business_rules": ["capacity limited to 100 records"],
                }
            ],
            "business_rules": [],
        }
        java = """
        public class Demo {
          public static final int MAX_RECORDS = 100;
          void a() { b(); }
          void b() { System.out.println("OK"); }
        }
        """
        out = score_conversion(po, json.dumps(analysis), java)
        self.assertGreaterEqual(out["structural_score"], 40)
        self.assertGreaterEqual(out["business_rules_score"], 20)
        self.assertGreaterEqual(out["total_score"], 60)
        bd = out["paragraph_breakdown"]
        self.assertTrue(isinstance(bd, list) and len(bd) >= 1)
        self.assertIn("paragraph", bd[0])

    def test_broken_java_lowers_score(self):
        source = """
       PROCEDURE DIVISION.
       A.
           PERFORM B.
           STOP RUN.
       B.
           DISPLAY "OK".
        """
        po = self.parser.parse(source)
        analysis = {"sections": [], "business_rules": []}
        good_java = """
        public class Demo {
          void a() { b(); }
          void b() {}
        }
        """
        bad_java = "// no methods\npublic class X { }\n"
        good = score_conversion(po, analysis, good_java)
        bad = score_conversion(po, analysis, bad_java)
        self.assertGreater(good["total_score"], bad["total_score"])

    def test_missing_business_rules_lowers_rules_score(self):
        parser_output = {
            "program_name": "R",
            "paragraphs": ["P1"],
            "control_flow": {"calls": [], "loops": [], "branches": [], "gotos": []},
            "operations": [],
        }
        analysis = {
            "sections": [
                {"name": "P1", "business_rules": ["capacity limited to 99 staff"]},
                {"name": "P1", "business_rules": ["overtime paid at 1.5x rate"]},
            ],
            "business_rules": [],
        }
        java_match_one = "class X { static int MAX_STAFF = 99; void p1(){} }"
        out = score_conversion(parser_output, analysis, java_match_one)
        self.assertLess(out["business_rules_score"], 40)

    def test_paragraph_breakdown_populated(self):
        po = self.parser.parse("""
       PROCEDURE DIVISION.
       MAIN-PARA.
           STOP RUN.
        """)
        out = score_conversion(po, "{}", "public class X { void mainPara() { return; } }")
        self.assertTrue(len(out["paragraph_breakdown"]) >= 1)

    def test_decision_thresholds(self):
        # Synthetic: force-like totals via minimal parser (no branches/calls) but
        # full business rules credit and decent structure.
        po = {
            "program_name": "SYN",
            "paragraphs": ["P"],
            "control_flow": {"calls": [], "loops": [], "branches": [], "gotos": []},
            "operations": [],
        }
        java = "class Syn { void p() { while(true) break; if (true) {} switch(x){} return; } }"
        # With no calls/loops in parser, structural still gets branch/heuristic from java
        high_analysis = {"sections": [], "business_rules": []}
        out = score_conversion(po, high_analysis, java)
        d = out["decision"]
        self.assertIn(
            d,
            (DECISION_AUTO, DECISION_MANUAL, DECISION_RECONVERT),
        )
        # Direct decision helper behaviour
        from app.services.scoring_service import conversion_decision_from_total

        self.assertEqual(conversion_decision_from_total(95), DECISION_AUTO)
        self.assertEqual(conversion_decision_from_total(75), DECISION_MANUAL)
        self.assertEqual(conversion_decision_from_total(50), DECISION_RECONVERT)


class FourCategoryModelTests(unittest.TestCase):
    """Tests for the 4-category scoring model (parse/analyze/convert/semantic)."""

    def test_category_scores_present(self):
        po = {
            "program_name": "DEMO",
            "paragraphs": ["A"],
            "control_flow": {"calls": [], "loops": [], "branches": []},
            "operations": [],
        }
        out = score_conversion(po, {"sections": [], "business_rules": []}, "public class Demo { void a() {} }")
        self.assertIn("category_scores", out)
        cats = out["category_scores"]
        for key in ("parse", "analyze", "convert", "semantic"):
            self.assertIn(key, cats)
            self.assertIn("score", cats[key])
            self.assertIn("max", cats[key])
            self.assertIn("notes", cats[key])

    def test_parse_full_marks_no_errors(self):
        po = {
            "program_name": "CLEAN",
            "paragraphs": ["MAIN"],
            "control_flow": {"calls": []},
            "operations": [],
        }
        out = score_conversion(po, {}, "class X {}")
        self.assertEqual(out["category_scores"]["parse"]["score"], 20)

    def test_parse_zero_on_errors(self):
        po = {"errors": ["Something went wrong"], "program_name": "BAD"}
        out = score_conversion(po, {}, "class X {}")
        self.assertEqual(out["category_scores"]["parse"]["score"], 0)

    def test_parse_ten_on_warnings(self):
        po = {
            "program_name": "WARN",
            "paragraphs": [],
            "warnings": ["minor issue"],
            "control_flow": {"calls": []},
            "operations": [],
        }
        out = score_conversion(po, {}, "class X {}")
        self.assertEqual(out["category_scores"]["parse"]["score"], 10)

    def test_analyze_llm_full_marks(self):
        analysis = {
            "analysis_engine": "llm",
            "business_rules": ["rule1", "rule2", "rule3"],
        }
        po = {"program_name": "T"}
        out = score_conversion(po, analysis, "class X {}")
        self.assertEqual(out["category_scores"]["analyze"]["score"], 20)

    def test_analyze_deterministic_with_rules(self):
        analysis = {
            "analysis_engine": "deterministic",
            "fallback_reason": "llm_unavailable",
            "business_rules": ["r1", "r2", "r3"],
        }
        po = {"program_name": "T"}
        out = score_conversion(po, analysis, "class X {}")
        self.assertEqual(out["category_scores"]["analyze"]["score"], 10)

    def test_analyze_deterministic_structural_only(self):
        analysis = {
            "analysis_engine": "deterministic",
            "business_rules": [],
            "complexity": "medium",
        }
        po = {"program_name": "T"}
        out = score_conversion(po, analysis, "class X {}")
        self.assertEqual(out["category_scores"]["analyze"]["score"], 5)

    def test_convert_full_marks_compiled_no_todos(self):
        po = {"program_name": "T", "paragraphs": []}
        out = score_conversion(po, {}, "public class T { void main() {} }", compile_success=True)
        self.assertEqual(out["category_scores"]["convert"]["score"], 20)

    def test_convert_fifteen_compiled_with_todos(self):
        java = "public class T { void main() { // TODO: handle CALL } }"
        po = {"program_name": "T"}
        out = score_conversion(po, {}, java, compile_success=True)
        self.assertEqual(out["category_scores"]["convert"]["score"], 15)

    def test_convert_five_on_compile_failure(self):
        po = {"program_name": "T"}
        out = score_conversion(po, {}, "public class T {", compile_success=False)
        self.assertEqual(out["category_scores"]["convert"]["score"], 5)

    def test_convert_zero_no_java(self):
        po = {"program_name": "T"}
        out = score_conversion(po, {}, "")
        self.assertEqual(out["category_scores"]["convert"]["score"], 0)

    def test_semantic_detail_present(self):
        po = {
            "program_name": "T",
            "paragraphs": ["A"],
            "control_flow": {"calls": [], "loops": [], "branches": []},
            "operations": [],
        }
        java = "public class T { public static void main(String[] a) { } void a() {} }"
        out = score_conversion(po, {"business_rules": ["check capacity"]}, java)
        self.assertIn("semantic_detail", out)
        sd = out["semantic_detail"]
        for key in ("structural_fidelity", "business_rule_coverage", "code_completeness", "integration_readiness"):
            self.assertIn(key, sd)
            self.assertGreaterEqual(sd[key], 0)
            self.assertLessEqual(sd[key], 10)

    def test_total_is_sum_of_four_categories(self):
        po = {
            "program_name": "SUM",
            "paragraphs": ["M"],
            "control_flow": {"calls": [], "loops": [], "branches": []},
            "operations": [],
        }
        java = "public class Sum { public static void main(String[] a) {} void m() {} }"
        analysis = {"analysis_engine": "llm", "business_rules": ["rule A", "rule B", "rule C"]}
        out = score_conversion(po, analysis, java, compile_success=True)
        cats = out["category_scores"]
        cat_total = sum(cats[k]["score"] for k in ("parse", "analyze", "convert", "semantic"))
        self.assertEqual(out["total_score"], min(100, cat_total))

    def test_backward_compatible_fields_exist(self):
        po = {"program_name": "BC", "paragraphs": []}
        out = score_conversion(po, {}, "public class BC {}")
        for key in ("structural_score", "business_rules_score", "total_score",
                     "decision", "summary", "paragraph_breakdown", "details"):
            self.assertIn(key, out, f"Missing backward-compat key: {key}")

    def test_failed_parse_caps_total(self):
        po = {"errors": ["parse failed"], "program_name": "FAIL"}
        out = score_conversion(po, {}, "", compile_success=False)
        self.assertLessEqual(out["total_score"], 20)

    def test_code_completeness_deductions(self):
        java_unbalanced = "public class X { void a() { { }"
        po = {"program_name": "T"}
        out = score_conversion(po, {}, java_unbalanced)
        sd = out["semantic_detail"]
        self.assertLess(sd["code_completeness"], 10)

    def test_integration_readiness_forbidden_imports(self):
        java = """
        import org.springframework.stereotype.Service;
        @Service
        public class Bad { }
        """
        po = {"program_name": "T"}
        out = score_conversion(po, {}, java)
        sd = out["semantic_detail"]
        self.assertLess(sd["integration_readiness"], 10)

    def test_analysis_mode_llm(self):
        analysis = {"analysis_engine": "llm", "business_rules": ["r1", "r2", "r3"]}
        po = {"program_name": "T"}
        out = score_conversion(po, analysis, "class X {}")
        am = out["analysis_mode"]
        self.assertEqual(am["engine"], "llm")
        self.assertFalse(am["is_deterministic_fallback"])
        self.assertIsNone(am["fallback_reason"])
        self.assertFalse(am["score_capped"])

    def test_analysis_mode_deterministic(self):
        analysis = {
            "analysis_engine": "deterministic",
            "fallback_reason": "llm_unavailable",
            "business_rules": ["r1", "r2", "r3"],
        }
        po = {"program_name": "T"}
        out = score_conversion(po, analysis, "class X {}")
        am = out["analysis_mode"]
        self.assertEqual(am["engine"], "deterministic")
        self.assertTrue(am["is_deterministic_fallback"])
        self.assertEqual(am["fallback_reason"], "llm_unavailable")
        self.assertTrue(am["score_capped"])
        self.assertLessEqual(out["category_scores"]["analyze"]["score"], 10)

    def test_analysis_mode_fallback_reason_triggers_deterministic(self):
        analysis = {
            "analysis_engine": "unknown",
            "fallback_reason": "api_error",
            "business_rules": [],
        }
        po = {"program_name": "T"}
        out = score_conversion(po, analysis, "class X {}")
        am = out["analysis_mode"]
        self.assertTrue(am["is_deterministic_fallback"])
        self.assertEqual(am["fallback_reason"], "api_error")


if __name__ == "__main__":
    unittest.main()
