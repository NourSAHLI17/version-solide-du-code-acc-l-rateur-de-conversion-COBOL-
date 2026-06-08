"""F56 — Symbol table in LLM prompts and compliance measurement."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.converters.constrained_generation import build_method_body_prompt, MethodSpec
from app.parsers.cobol_parser import ParserLayer
from app.services.symbol_compliance import (
    MIN_SYMBOL_COMPLIANCE,
    ProgramComplianceMetrics,
    build_retry_prompt,
    categorize_invented,
    gate_symbol_compliance,
    inject_todos,
    measure_symbol_compliance,
)
from app.services.symbol_table import SymbolTable, build_symbol_table_from_parser


class SymbolComplianceTests(unittest.TestCase):
    def test_to_llm_context_includes_sections(self):
        from app.services.symbol_table import FieldEntry

        table = SymbolTable("TST")
        table.fields["WS-STATUS"] = FieldEntry(
            cobol_name="WS-STATUS",
            java_name="wsStatus",
            java_type="String",
        )
        ctx = table.to_llm_context()
        self.assertIn("=== AVAILABLE SYMBOLS", ctx)
        self.assertIn("=== FIELDS YOU MAY READ/WRITE ===", ctx)
        self.assertIn("wsStatus", ctx)
        self.assertIn("=== DO NOT INVENT ===", ctx)

    def test_method_body_prompt_includes_symbol_table(self):
        parser_output = ParserLayer().parse(
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-AMT PIC 9(5)V99.
       PROCEDURE DIVISION.
       1000-MAIN.
           DISPLAY WS-AMT.
           STOP RUN.
            """
        )
        table = build_symbol_table_from_parser(parser_output)
        method = MethodSpec(
            java_name="main",
            cobol_paragraph="1000-MAIN",
            cobol_body="DISPLAY WS-AMT.",
        )
        from app.converters.constrained_generation import StructuredRepresentation

        rep = StructuredRepresentation(
            program="TST",
            package="com.modernized.tst",
            class_name="TstApplication",
        )
        prompt = build_method_body_prompt(method, rep, parser_output, symbol_table=table)
        self.assertIn("=== AVAILABLE SYMBOLS", prompt)
        self.assertIn("wsAmt", prompt)
        self.assertIn("CRITICAL RULES", prompt)
        self.assertIn("=== DO NOT INVENT ===", prompt)

    def test_measure_symbol_compliance(self):
        table = SymbolTable("TST")
        from app.services.symbol_table import FieldEntry

        table.fields["WS-AMT"] = FieldEntry(
            cobol_name="WS-AMT", java_name="wsAmt", java_type="BigDecimal",
        )
        output = 'wsAmt = wsAmt;\nif (endOfFile) { return; }'
        compliance, invented = measure_symbol_compliance(output, table)
        self.assertGreater(compliance, 0.0)
        self.assertIn("endOfFile", invented)
        cats = categorize_invented(invented)
        self.assertIn("endOfFile", cats["flag_fields"])

    def test_inject_todos_replaces_whole_statement(self):
        body = (
            "amlRespClear = chkamlService.checkAml(\n"
            "    new AmlRequest(custId));\n"
            ").clear;"
        )
        out = inject_todos(body, ["chkamlService", "AmlRequest"])
        self.assertIn("// TODO: original statement referenced undeclared", out)
        for line in out.splitlines():
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            self.assertNotIn(").clear", stripped)
            self.assertNotIn("chkamlService", stripped)

    def test_inject_todos_leaves_clean_lines(self):
        body = "wsAmt = wsAmt;\nif (\"Y\".equals(wsFlag)) { return; }"
        out = inject_todos(body, ["endOfFile"])
        self.assertIn("wsAmt = wsAmt", out)

    def test_inject_todos_comments_entire_bigdecimal_chain(self):
        body = (
            "scrRawScore = scrWeightIncome.multiply(BigDecimal.valueOf(scrIncomeScore))\n"
            "    .add(scrWeightHistory.multiply(BigDecimal.valueOf(scrHistoryScore)))\n"
            "    .add(scrWeightTenure.multiply(BigDecimal.valueOf(scrTenureScore)));\n"
        )
        out = inject_todos(body, ["scrWeightTenure"])
        self.assertIn("// TODO:", out)
        self.assertNotIn("\n    .add(scrWeightTenure", out)
        for line in out.splitlines():
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            self.assertNotIn(".add(", stripped)

    def test_gate_accepts_compliant_body(self):
        from app.services.symbol_table import FieldEntry

        table = SymbolTable("TST")
        table.fields["WS-AMT"] = FieldEntry(
            cobol_name="WS-AMT", java_name="wsAmt", java_type="BigDecimal",
        )
        body = "wsAmt = wsAmt;"
        accepted, compliance, extra = gate_symbol_compliance(
            body,
            table,
            lambda _p: "",
            "base prompt",
            program="TST",
            method="main",
        )
        self.assertEqual(accepted, body)
        self.assertGreaterEqual(compliance, MIN_SYMBOL_COMPLIANCE)
        self.assertEqual(extra, 0)

    def test_gate_retries_then_accepts(self):
        from app.services.symbol_table import FieldEntry

        table = SymbolTable("TST")
        table.fields["WS-AMT"] = FieldEntry(
            cobol_name="WS-AMT", java_name="wsAmt", java_type="BigDecimal",
        )
        calls: list[str] = []

        def llm(prompt: str) -> str:
            calls.append(prompt)
            return "wsAmt = wsAmt;"

        bad = "if (endOfFile) { return; }"
        metrics = ProgramComplianceMetrics()
        accepted, compliance, extra = gate_symbol_compliance(
            bad,
            table,
            llm,
            "base prompt with symbols",
            program="TST",
            method="main",
            metrics=metrics,
        )
        self.assertGreaterEqual(compliance, MIN_SYMBOL_COMPLIANCE)
        self.assertEqual(extra, 1)
        self.assertEqual(metrics.compliance_retries, 1)
        self.assertIn("wsAmt", accepted)
        self.assertTrue(calls)
        self.assertIn("COMPLIANCE FIXES REQUIRED", calls[0])

    def test_gate_injects_todos_after_max_retries(self):
        from app.services.symbol_table import FieldEntry

        table = SymbolTable("TST")
        table.fields["WS-AMT"] = FieldEntry(
            cobol_name="WS-AMT", java_name="wsAmt", java_type="BigDecimal",
        )

        def llm(_prompt: str) -> str:
            return "if (endOfFile) { loanFileReader.close(); }"

        accepted, _comp, _extra = gate_symbol_compliance(
            "if (endOfFile) { return; }",
            table,
            llm,
            "base",
            program="TST",
            method="main",
        )
        self.assertIn("// TODO: original statement referenced undeclared", accepted)

    def test_build_retry_prompt_includes_guidance(self):
        prompt = build_retry_prompt("BASE", "bad body", ["Fix file handles"])
        self.assertIn("BASE", prompt)
        self.assertIn("bad body", prompt)
        self.assertIn("Fix file handles", prompt)


if __name__ == "__main__":
    unittest.main()
