"""Validation services for equivalence and structured output comparison."""

from __future__ import annotations

import difflib
import json
from typing import Any, Dict, List


class ValidationService:
    """
    Compare expected vs actual *text/JSON* outputs (golden-file style).

    This is not behavioral verification — it does not compile or run COBOL/Java.
    Runtime equivalence is handled by run_behavioral_diff() on POST /api/testing/behavioral-diff.

    Example:
        Input:
            expected_output='{"status":"OK"}', actual_output='{\n  "status": "OK"\n}'
        Output:
            {
              "is_equivalent": True,
              "comparison_mode": "json_structure",
              "differences": [],
              "warnings": []
            }
    """

    def validate_outputs(self, expected_output: str, actual_output: str) -> Dict[str, object]:
        """
        Compare two outputs and return a structured validation report.

        Args:
            expected_output: Reference output from the legacy or golden system.
            actual_output: Observed output from the converted system.

        Returns:
            A report containing equivalence status, comparison mode,
            differences, and warnings.

        Example:
            Input:
                expected_output="A\nB", actual_output="A\nC"
            Output:
                {
                  "is_equivalent": False,
                  "comparison_mode": "line_diff",
                  "differences": ["- B", "+ C"],
                  "warnings": []
                }
        """

        warnings: List[str] = []
        if not expected_output:
            warnings.append("Expected output was empty; validation confidence is reduced.")
        if not actual_output:
            warnings.append("Actual output was empty; validation confidence is reduced.")

        json_comparison = self._compare_json_outputs(expected_output, actual_output)
        if json_comparison is not None:
            json_comparison["warnings"] = warnings
            return json_comparison

        normalized_expected = self._normalize_text(expected_output)
        normalized_actual = self._normalize_text(actual_output)
        if normalized_expected == normalized_actual:
            return {
                "is_equivalent": True,
                "comparison_mode": "normalized_text",
                "differences": [],
                "warnings": warnings,
            }

        line_differences = self._line_diff(expected_output, actual_output)
        return {
            "is_equivalent": False,
            "comparison_mode": "line_diff",
            "differences": line_differences or ["Output mismatch"],
            "warnings": warnings,
        }

    def _compare_json_outputs(self, expected_output: str, actual_output: str) -> Dict[str, object] | None:
        """
        Compare outputs as JSON when both payloads are valid JSON documents.

        Example:
            Input:
                expected_output='{"value":1}', actual_output='{"value":2}'
            Output:
                {
                  "is_equivalent": False,
                  "comparison_mode": "json_structure",
                  "differences": ["value: expected 1, got 2"]
                }
        """

        expected_json = self._try_parse_json(expected_output)
        actual_json = self._try_parse_json(actual_output)
        if expected_json is None or actual_json is None:
            return None

        differences = self._json_diff(expected_json, actual_json)
        return {
            "is_equivalent": not differences,
            "comparison_mode": "json_structure",
            "differences": differences,
        }

    def _try_parse_json(self, value: str) -> Any | None:
        """
        Parse JSON safely and return `None` when parsing fails.

        Example:
            Input:
                '{"status":"OK"}'
            Output:
                {"status": "OK"}
        """

        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return None

    def _normalize_text(self, value: str) -> str:
        """
        Normalize text for whitespace-insensitive comparison.

        Example:
            Input:
                "A  \n B"
            Output:
                "A\nB"
        """

        lines = [line.rstrip() for line in value.splitlines()]
        return "\n".join(line for line in lines if line.strip())

    def _line_diff(self, expected_output: str, actual_output: str) -> List[str]:
        """
        Produce a unified diff-style list for text outputs.

        Example:
            Input:
                expected_output="A", actual_output="B"
            Output:
                ["- A", "+ B"]
        """

        diff = difflib.ndiff(expected_output.splitlines(), actual_output.splitlines())
        return [line for line in diff if line.startswith("- ") or line.startswith("+ ")]

    def _json_diff(self, expected: Any, actual: Any, path: str = "") -> List[str]:
        """
        Recursively compare JSON-compatible values.

        Example:
            Input:
                expected={"a": 1}, actual={"a": 2}
            Output:
                ["a: expected 1, got 2"]
        """

        differences: List[str] = []

        if type(expected) is not type(actual):
            location = path or "$"
            return [f"{location}: expected {type(expected).__name__}, got {type(actual).__name__}"]

        if isinstance(expected, dict):
            expected_keys = set(expected.keys())
            actual_keys = set(actual.keys())
            for key in sorted(expected_keys - actual_keys):
                location = f"{path}.{key}" if path else key
                differences.append(f"{location}: missing in actual output")
            for key in sorted(actual_keys - expected_keys):
                location = f"{path}.{key}" if path else key
                differences.append(f"{location}: unexpected key in actual output")
            for key in sorted(expected_keys & actual_keys):
                location = f"{path}.{key}" if path else key
                differences.extend(self._json_diff(expected[key], actual[key], location))
            return differences

        if isinstance(expected, list):
            if len(expected) != len(actual):
                location = path or "$"
                differences.append(f"{location}: expected list length {len(expected)}, got {len(actual)}")
            for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
                location = f"{path}[{index}]" if path else f"[{index}]"
                differences.extend(self._json_diff(expected_item, actual_item, location))
            return differences

        if expected != actual:
            location = path or "$"
            differences.append(f"{location}: expected {expected!r}, got {actual!r}")

        return differences
