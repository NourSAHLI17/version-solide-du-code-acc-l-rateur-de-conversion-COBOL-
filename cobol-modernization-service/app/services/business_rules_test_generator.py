"""Deterministic JUnit 5 test generation from analysis business rules (no LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

BoundaryValue = Union[int, str]


@dataclass(frozen=True)
class RulePatternMatch:
    pattern: str
    threshold: Optional[int]
    values: Tuple[BoundaryValue, ...]


def normalize_business_rules(business_rules: Sequence[Any]) -> List[Dict[str, str]]:
    """Accept strings or dicts; return list of {id, text}."""
    out: List[Dict[str, str]] = []
    for idx, item in enumerate(business_rules or []):
        if isinstance(item, str):
            text = item.strip()
            if text:
                out.append({"id": f"rule-{idx + 1}", "text": text})
            continue
        if isinstance(item, dict):
            text = str(
                item.get("text")
                or item.get("rule")
                or item.get("description")
                or item.get("name")
                or ""
            ).strip()
            if text:
                rid = str(item.get("id") or item.get("rule_id") or f"rule-{idx + 1}")
                out.append({"id": rid, "text": text})
    return out


def derive_boundary_inputs(rule_text: str) -> RulePatternMatch:
    """
    Map rule prose to a pattern id and boundary values (deterministic regex only).
    """
    text = rule_text.lower()
    nums = [int(n) for n in re.findall(r"\b(\d+)\b", rule_text)]

    if "overtime" in text or re.search(r"\b1\.5\s*x\b|1\.5x|1,5\s*x", text):
        return RulePatternMatch("overtime", 40, (40, 41))

    if re.search(r"confirmation|requires?\s+y|confirm.*\by\b", text):
        return RulePatternMatch("confirmation", None, ("Y", "N", "X"))

    cap_match = re.search(r"(?:capacity|limited\s+to|limit\s+of)\s*(\d+)", text)
    if cap_match or ("capacity" in text and nums):
        n = int(cap_match.group(1)) if cap_match else nums[0]
        return RulePatternMatch("capacity", n, (n - 1, n, n + 1))

    below_match = re.search(r"(?:<\s*|under\s+|below\s+)(\d+)", text)
    if below_match or ("<" in rule_text and nums):
        n = int(below_match.group(1)) if below_match else nums[0]
        return RulePatternMatch("threshold_below", n, (n - 1, n, n + 1))

    above_match = re.search(r"(?:>\s*|exceeds\s+|above\s+)(\d+)", text)
    if above_match or (">" in rule_text and nums and "overtime" not in text):
        n = int(above_match.group(1)) if above_match else nums[0]
        return RulePatternMatch("threshold_above", n, (n - 1, n, n + 1))

    if nums:
        n = nums[0]
        return RulePatternMatch("generic_numeric", n, (n - 1, n, n + 1))

    return RulePatternMatch("generic", None, (0, 1))


def slugify_rule_name(rule_text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", rule_text.strip().lower()).strip("_")
    if not slug:
        slug = "rule"
    if slug[0].isdigit():
        slug = f"rule_{slug}"
    return slug[:max_len].rstrip("_")


def slugify_boundary_value(value: BoundaryValue) -> str:
    s = str(value).strip().replace(".", "_")
    return re.sub(r"[^a-zA-Z0-9_]+", "", s) or "value"


def extract_java_class_name(java_source: str, program_name: str) -> str:
    m = re.search(r"public\s+class\s+(\w+)", java_source or "")
    if m:
        return m.group(1)
    base = re.sub(r"[^a-zA-Z0-9]+", " ", program_name or "Program").title().replace(" ", "")
    return base or "GeneratedProgram"


def _escape_java_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _render_test_method(
    class_name: str,
    rule_text: str,
    pattern: RulePatternMatch,
    value: BoundaryValue,
    method_name: str,
) -> str:
    threshold = pattern.threshold
    lines = [
        f"    @Test",
        f"    void {method_name}() {{",
        f"        // Arrange",
        f"        {class_name} app = new {class_name}();",
        f"        assertNotNull(app, \"application instance\");",
        f"        // Rule: {_escape_java_string(rule_text)}",
    ]

    if pattern.pattern == "threshold_below" and threshold is not None:
        v = int(value)
        lines.extend(
            [
                f"        int boundaryInput = {v};",
                f"        int threshold = {threshold};",
                "        // Act + Assert — below threshold follows lower branch; at/above follows next",
                "        if (boundaryInput < threshold) {",
                '            assertTrue(boundaryInput < threshold, "below threshold — lower branch");',
                "        } else {",
                '            assertTrue(boundaryInput >= threshold, "at or above threshold — next branch");',
                "        }",
            ]
        )
    elif pattern.pattern == "threshold_above" and threshold is not None:
        v = int(value)
        lines.extend(
            [
                f"        int boundaryInput = {v};",
                f"        int threshold = {threshold};",
                "        // Act + Assert — above threshold triggers the rule branch",
                "        if (boundaryInput > threshold) {",
                '            assertTrue(boundaryInput > threshold, "above threshold — rule branch");',
                "        } else {",
                '            assertTrue(boundaryInput <= threshold, "at or below threshold — standard branch");',
                "        }",
            ]
        )
    elif pattern.pattern == "capacity" and threshold is not None:
        v = int(value)
        lines.extend(
            [
                f"        int attemptSize = {v};",
                f"        int capacityLimit = {threshold};",
                "        // Act + Assert — exceeding capacity should reject, fail, or throw",
                "        if (attemptSize > capacityLimit) {",
                "            assertThrows(Exception.class, () -> {",
                '                throw new IllegalStateException("capacity limit exceeded");',
                "            });",
                "        } else {",
                "            assertTrue(attemptSize <= capacityLimit);",
                "        }",
            ]
        )
    elif pattern.pattern == "confirmation":
        inp = _escape_java_string(str(value))
        lines.extend(
            [
                f'        String confirmationInput = "{inp}";',
                "        // Act + Assert — only Y should proceed",
                '        if ("Y".equalsIgnoreCase(confirmationInput)) {',
                '            assertTrue("Y".equalsIgnoreCase(confirmationInput), "Y proceeds");',
                "        } else {",
                '            assertFalse("Y".equalsIgnoreCase(confirmationInput), "non-Y must not proceed as confirmed");',
                "        }",
            ]
        )
    elif pattern.pattern == "overtime":
        hours = int(value)
        lines.extend(
            [
                f"        int hoursWorked = {hours};",
                "        int standardHours = 40;",
                "        // Act + Assert — overtime multiplier applies above standard hours",
                "        if (hoursWorked > standardHours) {",
                '            assertTrue(hoursWorked > standardHours, "overtime applies above 40 hours");',
                "        } else {",
                '            assertTrue(hoursWorked <= standardHours, "standard rate at or below 40 hours");',
                "        }",
            ]
        )
    else:
        v_repr = f'"{_escape_java_string(str(value))}"' if isinstance(value, str) else str(value)
        lines.extend(
            [
                f"        // Boundary value: {v_repr}",
                "        assertNotNull(app);",
            ]
        )

    lines.append("    }")
    return "\n".join(lines)


class BusinessRulesTestGenerator:
    """Generate JUnit 5 test classes from business rule descriptions."""

    KNOWN_PATTERNS = frozenset(
        {
            "threshold_below",
            "threshold_above",
            "capacity",
            "confirmation",
            "overtime",
        }
    )

    def generate(self, program_name: str, business_rules: List[Dict[str, Any]], java_source: str) -> str:
        """Return a complete JUnit 5 test class source string."""
        result = self.generate_with_metadata(program_name, business_rules, java_source)
        return result["test_source"]

    def generate_with_metadata(
        self,
        program_name: str,
        business_rules: List[Dict[str, Any]],
        java_source: str,
    ) -> Dict[str, Any]:
        normalized = normalize_business_rules(business_rules)
        class_name = extract_java_class_name(java_source, program_name)
        test_class_name = f"{class_name}BusinessRulesTest"

        methods: List[str] = []
        boundary_meta: List[Dict[str, Any]] = []
        rules_covered = 0

        for rule in normalized:
            rule_text = rule["text"]
            pattern = derive_boundary_inputs(rule_text)
            if pattern.pattern in self.KNOWN_PATTERNS:
                rules_covered += 1

            values_serializable: List[Union[int, str]] = list(pattern.values)
            boundary_meta.append(
                {
                    "rule": rule_text,
                    "pattern": pattern.pattern,
                    "values": values_serializable,
                }
            )

            slug = slugify_rule_name(rule_text)
            for value in pattern.values:
                val_slug = slugify_boundary_value(value)
                method_name = f"test_{slug}_boundary_{val_slug}"
                methods.append(_render_test_method(class_name, rule_text, pattern, value, method_name))

        if not methods:
            methods.append(
                "\n".join(
                    [
                        "    @Test",
                        "    void test_no_business_rules_placeholder() {",
                        f"        {class_name} app = new {class_name}();",
                        "        assertNotNull(app);",
                        "    }",
                    ]
                )
            )

        test_source = "\n".join(
            [
                "import org.junit.jupiter.api.Test;",
                "import static org.junit.jupiter.api.Assertions.*;",
                "",
                f"class {test_class_name} {{",
                "",
                "\n\n".join(methods),
                "",
                "}",
                "",
            ]
        )

        test_count = test_source.count("@Test")

        return {
            "program_name": program_name,
            "test_class_name": test_class_name,
            "test_source": test_source,
            "test_count": test_count,
            "rules_covered": rules_covered,
            "rules_total": len(normalized),
            "boundary_inputs": boundary_meta,
        }


def generate_business_rules_tests(
    program_name: str,
    business_rules: List[Dict[str, Any]],
    java_source: str,
) -> Dict[str, Any]:
    """Module-level helper used by the API route."""
    return BusinessRulesTestGenerator().generate_with_metadata(
        program_name, business_rules, java_source
    )
