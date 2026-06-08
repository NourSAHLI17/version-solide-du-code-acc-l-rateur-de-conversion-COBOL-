"""Regression tests for deferred Java class assembly."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from app.converters.java_class_builder import (
    FieldDecl,
    GenerationError,
    InnerClass,
    JavaClassBuilder,
    JavaFileAssembler,
    MethodDecl,
    finalize_java_source,
    rescue_methods_outside_class,
    validate_class_structure,
    validate_member_ordering,
)
from app.services.pipeline_service import PipelineService
from app.services.riskscor_java_repair import repair_riskscor_rewrite_java

ACME = Path(__file__).resolve().parents[2] / "acme-bank-v3"
RISKSCOR = ACME / "src" / "RISKSCOR.cbl"


class JavaClassBuilderTests(unittest.TestCase):
    def test_validate_rejects_method_outside_class(self):
        bad = """
package demo;

public class Demo {
    private void inside() {
    }
}
private String orphan() {
    return "";
}
"""
        with self.assertRaises(GenerationError) as ctx:
            validate_class_structure(bad)
        self.assertIn("outside class body", str(ctx.exception))

    def test_finalize_moves_orphan_methods_inside(self):
        bad = """
package demo;

public class Riskscor {
    private static class LoanRecord {
        int loanId;
    }
}
    private String formatLoanRecord(LoanRecord rec) {
        return "";
    }
    private LoanRecord parseLoanRecord(String line) {
        return new LoanRecord();
    }
"""
        fixed = finalize_java_source(bad)
        validate_class_structure(fixed)
        self.assertIn("private String formatLoanRecord", fixed)
        self.assertIn("private LoanRecord parseLoanRecord", fixed)
        self.assertEqual(fixed.count("private String formatLoanRecord"), 1)
        self.assertEqual(fixed.count("private LoanRecord parseLoanRecord"), 1)

    def test_rescue_methods_outside_class_reopens_premature_close(self):
        bad = """
public class App {
    private void early() {
    }
}
    private void orphan() {
    }
}
"""
        fixed, rescued = rescue_methods_outside_class(bad)
        self.assertTrue(rescued)
        validate_class_structure(fixed)
        self.assertIn("private void orphan()", fixed)
        self.assertLess(fixed.index("orphan"), fixed.rindex("}"))

    def test_brace_balance_single_top_level_class(self):
        java = finalize_java_source(
            """
package x;
public class App {
  public void run() { }
}
"""
        )
        depth = 0
        class_count = 0
        for line in java.splitlines():
            if re.search(r"\bclass\s+\w+", line) and depth == 0:
                class_count += 1
            depth += line.count("{") - line.count("}")
        self.assertEqual(depth, 0)
        self.assertGreaterEqual(class_count, 1)


class RiskscorRewriteStructureTests(unittest.TestCase):
    def test_repair_rewrite_methods_stay_inside_class(self):
        bad_java = """
package com.modernized.riskscor;

public class Riskscor {
    private static class LoanRecord {
        int loanId;
        String loanClass;
    }
    private String formatLoanRecord(LoanRecord rec) {
        StringBuilder sb = new StringBuilder();
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
        parser_output = PipelineService().run_pipeline(
            src,
            {"copylib_paths": [str(ACME / "copybooks")]},
        )
        fixed, notes = repair_riskscor_rewrite_java(
            bad_java,
            program_name="RISKSCOR",
            parser_output=parser_output,
            cobol_source=src,
        )
        self.assertIn("riskscor_rewrite_copy_then_modify_applied", notes)
        validate_class_structure(fixed)
        self.assertIn("CobolRecordRewrite.overwrite", fixed)
        self.assertNotIn("sb.append(String.format", fixed)
        self.assertEqual(fixed.count("private String formatLoanRecord"), 1)
        self.assertEqual(fixed.count("private LoanRecord parseLoanRecord"), 1)

    def test_assembler_preserves_field_initializer_new(self):
        src = """
package demo;
public class Riskscor {
    public LoanRecord loanRecord = new LoanRecord();
    public CustomerRecord customerRecord = new CustomerRecord();
    private String formatLoanRecord(LoanRecord rec) { return ""; }
}
"""
        built = JavaFileAssembler.from_java_source(src).build(validate=False)
        self.assertNotIn("=;", built)
        self.assertIn("customerRecord = new CustomerRecord()", built)
        self.assertEqual(built.count("customerRecord"), 1)

    def test_assembler_upsert_replaces_by_name(self):
        assembler = JavaFileAssembler.from_java_source(
            "package t;\npublic class T {\n  private void foo() { }\n}\n"
        )
        assembler.upsert_method("foo", "    private void foo() {\n        return 1;\n    }")
        built = assembler.build()
        self.assertIn("return 1", built)
        self.assertNotIn("private void foo() { }", built)


class MemberOrderingTests(unittest.TestCase):
    def test_fields_ordered_static_final_then_instance(self):
        builder = JavaClassBuilder(class_name="Demo")
        builder.fields = [
            FieldDecl(source="private int zInstance;"),
            FieldDecl(source="private static int bStatic;"),
            FieldDecl(source="private static final int aStaticFinal = 1;"),
            FieldDecl(source="private final int yInstanceFinal = 2;"),
        ]
        java = builder.build()
        idx_static_final = java.index("aStaticFinal")
        idx_static = java.index("bStatic")
        idx_inst_final = java.index("yInstanceFinal")
        idx_inst = java.index("zInstance")
        self.assertLess(idx_static_final, idx_static)
        self.assertLess(idx_static, idx_inst_final)
        self.assertLess(idx_inst_final, idx_inst)

    def test_constructors_default_before_parameterized(self):
        builder = JavaClassBuilder(class_name="Demo")
        builder.upsert_method(
            MethodDecl.from_source(
                "    public Demo(String x) {\n        this.x = x;\n    }\n",
                class_name="Demo",
            )
        )
        builder.upsert_method(
            MethodDecl.from_source("    public Demo() {\n    }\n", class_name="Demo")
        )
        java = builder.build()
        self.assertLess(java.index("public Demo() {"), java.index("public Demo(String"))

    def test_private_methods_paragraph_order_then_helpers(self):
        builder = JavaClassBuilder(class_name="Riskscor")
        builder.upsert_method(
            MethodDecl(
                name="formatLoanRecord",
                source="    private String formatLoanRecord(LoanRecord rec) {\n        return \"\";\n    }",
            )
        )
        builder.upsert_method(
            MethodDecl(
                name="parseLoanRecord",
                source="    private LoanRecord parseLoanRecord(String line) {\n        return null;\n    }",
            )
        )
        builder.upsert_method(
            MethodDecl(
                name="openFiles",
                source=(
                    "    private void openFiles() {\n"
                    "        // COBOL paragraph: 0100-OPEN-FILES\n"
                    "    }"
                ),
                paragraph="0100-OPEN-FILES",
            )
        )
        builder.upsert_method(
            MethodDecl(
                name="mainProcedure",
                source=(
                    "    private void mainProcedure() {\n"
                    "        // COBOL paragraph: 0000-MAIN\n"
                    "    }"
                ),
                paragraph="0000-MAIN",
            )
        )
        builder.upsert_method(
            MethodDecl(
                name="processLoan",
                source=(
                    "    private void processLoan() {\n"
                    "        // COBOL paragraph: 0200-PROCESS-LOAN\n"
                    "    }"
                ),
                paragraph="0200-PROCESS-LOAN",
            )
        )
        java = builder.build()
        main_idx = java.index("mainProcedure")
        open_idx = java.index("openFiles")
        process_idx = java.index("processLoan")
        parse_idx = java.index("parseLoanRecord")
        format_idx = java.index("formatLoanRecord")
        self.assertLess(main_idx, open_idx)
        self.assertLess(open_idx, process_idx)
        self.assertLess(process_idx, format_idx)
        self.assertLess(format_idx, parse_idx)

    def test_inner_classes_after_methods(self):
        builder = JavaClassBuilder(class_name="Demo")
        builder.inner_classes = [
            InnerClass(
                name="Inner",
                source="private static class Inner {\n    int x;\n}",
            )
        ]
        builder.upsert_method("    private void zLast() {\n    }\n")
        java = builder.build()
        self.assertLess(java.index("zLast"), java.index("class Inner"))

    def test_validate_rejects_method_before_field(self):
        bad = """
public class Demo {
    private void orphan() {
    }
    private int count;
}
"""
        with self.assertRaises(GenerationError) as ctx:
            validate_member_ordering(bad, "Demo")
        self.assertIn("ordering violation", str(ctx.exception))

    def test_finalize_reorders_members(self):
        scrambled = """
package demo;
public class App {
    private void zebra() { }
    private static final int A = 1;
    private static class ZInner { }
    private void alpha() {
        // COBOL paragraph: 0100-ALPHA
    }
}
"""
        fixed = finalize_java_source(scrambled)
        validate_member_ordering(fixed, "App")
        self.assertLess(fixed.index("A = 1"), fixed.index("alpha"))
        self.assertLess(fixed.index("alpha"), fixed.index("zebra"))
        self.assertLess(fixed.index("zebra"), fixed.index("class ZInner"))


if __name__ == "__main__":
    unittest.main()
