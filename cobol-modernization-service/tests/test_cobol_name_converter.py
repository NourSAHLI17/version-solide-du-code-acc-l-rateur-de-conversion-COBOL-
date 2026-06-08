"""Unit tests for canonical COBOL → Java naming."""

from __future__ import annotations

import unittest

from app.converters.cobol_name_converter import (
    CobolNameConverter,
    build_paragraph_table,
    enrich_symbol_table_java_names,
    format_explicit_symbol_table_markdown,
)


class CobolNameConverterTests(unittest.TestCase):
    def test_naming_conventions(self):
        assert CobolNameConverter.to_java_field("LOAN-STATUS") == "loanStatus"
        assert CobolNameConverter.to_java_field("WS-CURRENT-IDX") == "wsCurrentIdx"
        assert CobolNameConverter.to_java_field("WS-CURRENT-LOAN-ID") == "wsCurrentLoanId"
        assert CobolNameConverter.to_java_class("LOAN-RECORD") == "LoanRecord"
        assert CobolNameConverter.to_java_class("CHKAML") == "Chkaml"
        assert CobolNameConverter.to_java_method("4910-LOAD-SORT") == "loadSort"
        assert CobolNameConverter.to_java_method("0000-MAIN") == "main"
        assert CobolNameConverter.to_java_constant("CLASS-1") == "CLASS_1"

    def test_enrich_symbol_table_adds_java_field(self):
        symbols = enrich_symbol_table_java_names(
            [{"name": "LOAN-STATUS", "kind": "string"}]
        )
        self.assertEqual(symbols[0]["java_field"], "loanStatus")
        self.assertEqual(symbols[0]["java_name"], "loanStatus")

    def test_build_paragraph_table(self):
        table = build_paragraph_table(["1000-LOAD-CUSTOMER", "2000-PROCESS"])
        self.assertEqual(table[0]["cobol"], "1000-LOAD-CUSTOMER")
        self.assertEqual(table[0]["java_method"], "loadCustomer")

    def test_explicit_symbol_table_markdown(self):
        parser_output = {
            "program_name": "RISKSCOR",
            "symbol_table": enrich_symbol_table_java_names(
                [
                    {
                        "name": "LOAN-STATUS",
                        "pic": "X(1)",
                        "section": "LOANCOPY",
                        "kind": "string",
                    },
                    {
                        "name": "LOAN-RECORD",
                        "level": 1,
                        "kind": "group",
                    },
                ]
            ),
            "paragraph_table": [
                {"cobol": "4000-CLASSIFY-LOAN", "java_method": "classifyLoan"},
            ],
        }
        md = format_explicit_symbol_table_markdown(parser_output, max_rows=50)
        self.assertIn("| COBOL Name | Java Name | Java Type | Source |", md)
        self.assertIn("| LOAN-STATUS | loanStatus |", md)
        self.assertIn("| 4000-CLASSIFY-LOAN | classifyLoan |", md)
        self.assertIn("| LOAN-RECORD | LoanRecord |", md)


if __name__ == "__main__":
    unittest.main()
