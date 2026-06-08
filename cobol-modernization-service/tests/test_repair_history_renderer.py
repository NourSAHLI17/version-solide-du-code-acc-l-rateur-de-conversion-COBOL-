"""Tests for F37 repair history rendering."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.repair_history_renderer import (
    STATUS_BADGES,
    categorize_repairs,
    derive_conversion_status,
    render_repair_history,
    render_status_badge,
)


class TestDeriveConversionStatus(unittest.TestCase):
    def test_baseline_matched_is_highest(self):
        self.assertEqual(
            derive_conversion_status(
                converted=True, compiled=True, verified=True, baseline_matched=True
            ),
            "baseline_matched",
        )

    def test_verified_without_baseline(self):
        self.assertEqual(
            derive_conversion_status(converted=True, compiled=True, verified=True),
            "verified",
        )

    def test_compiled_with_todos_is_repaired(self):
        self.assertEqual(
            derive_conversion_status(
                converted=True, compiled=True, has_manual_todos=True
            ),
            "repaired",
        )

    def test_compiled_without_todos(self):
        self.assertEqual(
            derive_conversion_status(converted=True, compiled=True),
            "compiled",
        )

    def test_converted_only(self):
        self.assertEqual(
            derive_conversion_status(converted=True),
            "converted",
        )

    def test_nothing_is_failed(self):
        self.assertEqual(derive_conversion_status(), "failed")


class TestStatusBadge(unittest.TestCase):
    def test_all_statuses_have_badges(self):
        for status in ["converted", "compiled", "repaired", "verified",
                        "baseline_matched", "partial", "failed"]:
            badge = render_status_badge(status)
            self.assertIn("label", badge)
            self.assertIn("color", badge)
            self.assertIn("icon", badge)

    def test_unknown_status_falls_back_to_failed(self):
        badge = render_status_badge("unknown")
        self.assertEqual(badge["label"], "Failed")


class TestCategorizeRepairs(unittest.TestCase):
    def test_import_repairs_categorized(self):
        result = categorize_repairs(["Removed 3 Spring/framework imports (plain Java profile)"])
        self.assertIn("imports", result)
        self.assertEqual(len(result["imports"]), 1)

    def test_naming_repairs_categorized(self):
        result = categorize_repairs(["Renamed status → loanStatus (name mismatch)"])
        self.assertIn("naming", result)

    def test_syntax_repairs_categorized(self):
        result = categorize_repairs(["Added missing semicolon at line 42"])
        self.assertIn("syntax", result)

    def test_empty_categories_omitted(self):
        result = categorize_repairs(["Renamed x → y (name mismatch)"])
        self.assertNotIn("imports", result)
        self.assertNotIn("syntax", result)


class TestRenderRepairHistory(unittest.TestCase):
    def test_full_render_with_auto_repairs_and_todos(self):
        summary = {
            "auto_repairs": [
                "Removed 3 Spring/framework imports (plain Java profile)",
                "Renamed status → loanStatus (name mismatch)",
                "Added missing semicolon at line 247",
            ],
            "manual_review": [
                {"line": 100, "message": "Type mismatch (manual review)"},
            ],
        }
        result = render_repair_history(summary, compiled=True)
        self.assertEqual(result["status"], "repaired")
        self.assertEqual(result["auto_repair_count"], 3)
        self.assertEqual(result["manual_review_count"], 1)
        self.assertTrue(result["has_unresolved_todos"])
        self.assertIn("imports", result["auto_repairs_categorized"])
        self.assertIn("naming", result["auto_repairs_categorized"])
        badge = result["status_badge"]
        self.assertEqual(badge["label"], "Repaired")

    def test_render_no_repairs(self):
        summary = {"auto_repairs": [], "manual_review": []}
        result = render_repair_history(summary, compiled=True)
        self.assertEqual(result["status"], "compiled")
        self.assertEqual(result["auto_repair_count"], 0)
        self.assertFalse(result["has_unresolved_todos"])

    def test_render_verified(self):
        summary = {"auto_repairs": ["fixed something"], "manual_review": []}
        result = render_repair_history(summary, compiled=True, verified=True)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["status_badge"]["color"], "emerald")

    def test_render_baseline_matched(self):
        summary = {"auto_repairs": [], "manual_review": []}
        result = render_repair_history(
            summary, compiled=True, verified=True, baseline_matched=True
        )
        self.assertEqual(result["status"], "baseline_matched")


class TestHistoryKeyFlexibility(unittest.TestCase):
    """Verify _get_flexible handles both snake_case and camelCase keys."""

    def test_snake_case_keys(self):
        from app.api.routes.history import _get_flexible

        data = {"java_source": "class X{}", "compile_status": "success"}
        self.assertEqual(_get_flexible(data, "java_source", "javaSource"), "class X{}")
        self.assertEqual(_get_flexible(data, "compile_status", "compileStatus"), "success")

    def test_camel_case_keys(self):
        from app.api.routes.history import _get_flexible

        data = {"javaSource": "class Y{}", "compileStatus": "success"}
        self.assertEqual(_get_flexible(data, "java_source", "javaSource"), "class Y{}")
        self.assertEqual(_get_flexible(data, "compile_status", "compileStatus"), "success")

    def test_default_when_missing(self):
        from app.api.routes.history import _get_flexible

        data = {}
        self.assertIsNone(_get_flexible(data, "java_source", "javaSource"))
        self.assertFalse(_get_flexible(data, "baseline_matched", "baselineMatched", default=False))

    def test_repair_summary_camel_case(self):
        from app.api.routes.history import _get_flexible

        data = {
            "repairSummary": {"auto_repairs": ["fixed X"], "manual_review": []},
        }
        result = _get_flexible(data, "repair_summary", "repairSummary")
        self.assertEqual(result["auto_repairs"], ["fixed X"])


if __name__ == "__main__":
    unittest.main()
