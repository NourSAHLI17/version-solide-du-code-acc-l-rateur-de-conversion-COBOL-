"""Tests for repair_summary UI formatting."""

from __future__ import annotations

import unittest

from app.services.repair_summary import (
    build_repair_summary,
    extract_manual_review_items,
    format_repair_notes_for_ui,
)


class RepairSummaryTests(unittest.TestCase):
    def test_formats_rename_note(self):
        summary = format_repair_notes_for_ui(
            ["Auto-renamed reference status → loanStatus (1 on loan receiver)"],
            "",
        )
        self.assertIn("Renamed status → loanStatus", summary["auto_repairs"][0])

    def test_formats_semicolon_iteration(self):
        summary = format_repair_notes_for_ui(
            [
                "iteration 1: repaired semicolon_expected at T.java:247 (';' expected)",
            ],
            "",
        )
        self.assertEqual(summary["auto_repairs"][0], "Added missing semicolon at line 247")

    def test_aggregates_package_repairs(self):
        summary = format_repair_notes_for_ui(
            [
                "iteration 1: repaired package_does_not_exist at T.java:3 (package org.springframework.stereotype does not exist)",
                "iteration 1: repaired package_does_not_exist at T.java:4 (package org.springframework.beans.factory.annotation does not exist)",
                "iteration 1: repaired package_does_not_exist at T.java:5 (package org.springframework.context does not exist)",
            ],
            "",
            java_profile="plain_java",
        )
        self.assertEqual(len(summary["auto_repairs"]), 1)
        self.assertIn("Removed 3 Spring/framework imports", summary["auto_repairs"][0])
        self.assertIn("plain Java profile", summary["auto_repairs"][0])

    def test_extracts_manual_review_todos(self):
        java = """
class T {
    void m() {
        // TODO: Type mismatch (manual review): BigDecimal cannot be converted to int
        int x = 0;
        // TODO: Unresolvable name "customAttribute" — candidates: [foo, bar]
    }
}
"""
        items = extract_manual_review_items(java)
        self.assertGreaterEqual(len(items), 2)
        messages = [i["message"] for i in items]
        self.assertTrue(any("Type mismatch" in m for m in messages))
        self.assertTrue(any("customAttribute" in m for m in messages))

    def test_mapping_notes_profile_sanitization(self):
        notes = """--- PROFILE SANITIZATION (plain_java) ---
removed import: org.springframework.stereotype.Service
removed import: org.springframework.beans.factory.annotation.Autowired
removed annotation: org.springframework.stereotype.Service
"""
        summary = build_repair_summary([], "", mapping_notes=notes, java_profile="plain_java")
        self.assertTrue(any("Spring/framework" in line for line in summary["auto_repairs"]))


if __name__ == "__main__":
    unittest.main()
