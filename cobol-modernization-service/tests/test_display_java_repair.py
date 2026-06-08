"""Tests for deterministic DISPLAY → println repair."""

from __future__ import annotations

import unittest

from app.services.display_java_repair import (
    convert_display_to_println,
    convert_display_statements,
    repair_display_java,
)


class DisplayJavaRepairTests(unittest.TestCase):
    def test_convert_literal_display(self) -> None:
        line = convert_display_to_println("'RISKSCOR COMPLETED.'", {})
        self.assertEqual(line, '        System.out.println("RISKSCOR COMPLETED.");')

    def test_convert_literal_and_field(self) -> None:
        lookup = {
            "WSCLASS1COUNT": {"java": "wsClass1Count", "pic": "PIC 9(6)", "java_type": "int"},
        }
        line = convert_display_to_println("'  CLASS 1: ' WS-CLASS1-COUNT", lookup)
        self.assertIn('System.out.println("  CLASS 1: " + String.format("%06d", wsClass1Count))', line)

    def test_convert_display_statements_from_todo(self) -> None:
        body = (
            "        // TODO: original statement referenced undeclared: X\n"
            "        // Original: DISPLAY 'RECOVRY COMPLETED.'\n"
            "        return;"
        )
        out = convert_display_statements(body, {})
        self.assertIn('System.out.println("RECOVRY COMPLETED.")', out)

    def test_repair_injects_into_run_method(self) -> None:
        java = """
public class RecovryApplication {
    public void run() {
        openFiles();
        if (wsReturnCode != 0) {
            return;
        }
        closeFiles();
        wsReturnCode = 0;
        return;
    }
}
""".strip()
        parser_output = {
            "program_name": "RECOVRY",
            "paragraph_table": [{"cobol": "0000-MAIN", "java_method": "run"}],
            "operations": [
                {"type": "DISPLAY", "paragraph": "0000-MAIN", "value": "'RECOVRY v2.5 START ' WS-TODAY-DATE"},
                {"type": "DISPLAY", "paragraph": "0000-MAIN", "value": "'RECOVRY ABEND: ' WS-ERROR-MESSAGE"},
                {"type": "DISPLAY", "paragraph": "0000-MAIN", "value": "'RECOVRY COMPLETED.'"},
            ],
            "symbol_table": [
                {"name": "WS-TODAY-DATE", "pic": "9(8)", "java_field": "wsTodayDate"},
                {"name": "WS-ERROR-MESSAGE", "pic": "X(80)", "java_field": "wsErrorMessage"},
            ],
        }
        fixed, notes = repair_display_java(java, parser_output=parser_output)
        self.assertTrue(notes)
        self.assertIn('System.out.println("RECOVRY v2.5 START "', fixed)
        self.assertIn('System.out.println("RECOVRY COMPLETED.")', fixed)
        self.assertIn('System.out.println("RECOVRY ABEND: "', fixed)


if __name__ == "__main__":
    unittest.main()
