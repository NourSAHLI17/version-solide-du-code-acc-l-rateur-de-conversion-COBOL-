"""Tests for interactive stdin detection and auto-injection."""

from __future__ import annotations

import unittest

from app.services.behavioral_interactive_stdin import (
    apply_interactive_stdin_to_scenarios,
    detect_interactive_program,
    resolve_interactive_stdin,
)


class BehavioralInteractiveStdinTests(unittest.TestCase):
    def test_detects_accept_in_cobol_source(self):
        src = "       PROCEDURE DIVISION.\n           ACCEPT WS-MENU-CHOICE.\n"
        self.assertTrue(detect_interactive_program(cobol_source=src))

    def test_auto_injects_menu_exit_when_empty(self):
        stdin, notes = resolve_interactive_stdin("", interactive=True, program_name="PAYROLL-CALC")
        self.assertEqual(stdin, "0\n")
        self.assertTrue(notes)

    def test_preserves_explicit_stdin(self):
        stdin, notes = resolve_interactive_stdin("42\n", interactive=True)
        self.assertEqual(stdin, "42\n")
        self.assertEqual(notes, [])

    def test_apply_to_scenarios(self):
        scenarios = [{"scenario_id": "default", "label": "Default", "scripted_input": ""}]
        out, notes = apply_interactive_stdin_to_scenarios(
            scenarios,
            cobol_source="           ACCEPT WS-CHOICE.\n",
            program_name="DEMO",
        )
        self.assertEqual(out[0]["scripted_input"], "0\n")
        self.assertTrue(notes)


if __name__ == "__main__":
    unittest.main()
