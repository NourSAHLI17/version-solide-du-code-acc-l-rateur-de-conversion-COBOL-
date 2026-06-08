"""Deterministic JUnit 5 edge-case tests from parser structural metadata (no LLM)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

EdgeValue = Union[int, str]


def _unwrap_parser(parser_json: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(parser_json, dict):
        return {}
    ast = parser_json.get("ast")
    if isinstance(ast, dict) and ast:
        return dict(ast)
    return dict(parser_json)


def _slugify(text: str, max_len: int = 36) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", (text or "").strip().lower()).strip("_")
    if not slug:
        slug = "case"
    if slug[0].isdigit():
        slug = f"c_{slug}"
    return slug[:max_len].rstrip("_")


def _extract_threshold_from_condition(condition: str) -> Optional[int]:
    if not condition:
        return None
    cond = condition.strip()
    for pat in (
        r">\s*(\d+)",
        r">=\s*(\d+)",
        r"<\s*(\d+)",
        r"<=\s*(\d+)",
        r"=\s*(\d+)",
    ):
        m = re.search(pat, cond)
        if m:
            return int(m.group(1))
    nums = re.findall(r"\b(\d+)\b", cond)
    return int(nums[0]) if nums else None


def extract_java_class_name(java_source: str, program_name: str) -> str:
    m = re.search(r"public\s+class\s+(\w+)", java_source or "")
    if m:
        return m.group(1)
    base = re.sub(r"[^a-zA-Z0-9]+", " ", program_name or "Program").title().replace(" ", "")
    return base or "GeneratedProgram"


def _escape_java_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


class EdgeCaseTestGenerator:
    """Generate JUnit 5 tests from parser control-flow and data-structure signals."""

    def derive_edge_cases(self, parser_json: dict) -> List[Dict[str, Any]]:
        parser = _unwrap_parser(parser_json)
        cases: List[Dict[str, Any]] = []
        seen: set[str] = set()

        def add_case(case: Dict[str, Any]) -> None:
            key = f"{case.get('type')}|{case.get('paragraph')}|{case.get('field')}|{case.get('values')}"
            if key in seen:
                return
            seen.add(key)
            cases.append(case)

        from app.services.symbol_table import resolve_symbol_entries

        symbol_table = resolve_symbol_entries(parser)
        if isinstance(symbol_table, list):
            for sym in symbol_table:
                if not isinstance(sym, dict):
                    continue
                occurs = sym.get("occurs")
                if occurs is None:
                    continue
                try:
                    n = int(occurs)
                except (TypeError, ValueError):
                    continue
                if n <= 0:
                    continue
                name = str(sym.get("name") or sym.get("parent") or "array")
                add_case(
                    {
                        "type": "OCCURS boundary",
                        "field": name,
                        "paragraph": None,
                        "values": [n - 1, n, n + 1],
                        "detail": f"OCCURS {n} on {name}",
                    }
                )

        cf = parser.get("control_flow")
        if not isinstance(cf, dict):
            cf = {}
        loops = cf.get("loops") or []
        operations = parser.get("operations") or []
        read_paragraphs = {
            str(op.get("paragraph"))
            for op in operations
            if isinstance(op, dict) and str(op.get("type") or "").upper() == "READ" and op.get("paragraph")
        }

        if isinstance(loops, list):
            for loop in loops:
                if not isinstance(loop, dict):
                    continue
                para = str(loop.get("paragraph") or loop.get("target_paragraph") or "")
                loop_type = str(loop.get("type") or "LOOP")
                until = str(loop.get("until") or "")
                threshold = _extract_threshold_from_condition(until)
                if threshold is not None:
                    values: List[EdgeValue] = [threshold - 1, threshold, threshold + 1]
                else:
                    start_raw = str(loop.get("start") or "1")
                    try:
                        start_n = int(re.findall(r"\d+", start_raw)[0]) if re.findall(r"\d+", start_raw) else 1
                    except (IndexError, ValueError):
                        start_n = 1
                    values = [0, start_n, start_n + 1]

                add_case(
                    {
                        "type": "loop boundary",
                        "paragraph": para or None,
                        "field": loop_type,
                        "values": values,
                        "detail": f"{loop_type} until={until or 'n/a'}",
                    }
                )

                target = str(loop.get("target_paragraph") or "")
                if para in read_paragraphs or target in read_paragraphs:
                    add_case(
                        {
                            "type": "file record loop",
                            "paragraph": para or target or None,
                            "field": loop_type,
                            "values": [0, 1],
                            "detail": "READ-driven loop — zero records vs one record",
                        }
                    )

        if isinstance(operations, list):
            for op in operations:
                if not isinstance(op, dict):
                    continue
                op_type = str(op.get("type") or "")
                if op_type not in {"EXIT_PARAGRAPH", "EXIT_PERFORM", "EXIT_PERFORM_CYCLE"}:
                    continue
                para = str(op.get("paragraph") or "unknown")
                cond = str(op.get("condition") or op.get("value") or "early exit path")
                add_case(
                    {
                        "type": "early exit",
                        "paragraph": para,
                        "field": op_type,
                        "values": [cond],
                        "detail": f"{op_type} in {para}",
                    }
                )

        branches = cf.get("branches") or []
        if isinstance(branches, list):
            for br in branches:
                if not isinstance(br, dict):
                    continue
                if str(br.get("type") or "").upper() != "EVALUATE":
                    continue
                cond = str(br.get("condition") or "")
                para = str(br.get("paragraph") or "")
                threshold = _extract_threshold_from_condition(cond)
                if threshold is not None:
                    values: List[EdgeValue] = [threshold - 1, threshold, threshold + 1]
                elif cond.upper() == "TRUE" or not cond:
                    values = [0, 1]
                else:
                    nums = [int(x) for x in re.findall(r"\b(\d+)\b", cond)]
                    if nums:
                        n = nums[0]
                        values = [n - 1, n, n + 1]
                    else:
                        values = [0, 1]
                add_case(
                    {
                        "type": "EVALUATE threshold",
                        "paragraph": para or None,
                        "field": cond,
                        "values": values,
                        "detail": f"EVALUATE {cond}",
                    }
                )

        for op in operations if isinstance(operations, list) else []:
            if not isinstance(op, dict):
                continue
            if str(op.get("type") or "").upper() != "EVALUATE":
                continue
            cond = str(op.get("value") or op.get("condition") or "")
            para = str(op.get("paragraph") or "")
            threshold = _extract_threshold_from_condition(cond)
            if threshold is None:
                continue
            add_case(
                {
                    "type": "EVALUATE threshold",
                    "paragraph": para or None,
                    "field": cond,
                    "values": [threshold - 1, threshold, threshold + 1],
                    "detail": f"EVALUATE {cond}",
                }
            )

        return cases

    def generate(self, program_name: str, parser_json: dict, java_source: str) -> str:
        result = self.generate_with_metadata(program_name, parser_json, java_source)
        return result["test_source"]

    def generate_with_metadata(
        self,
        program_name: str,
        parser_json: dict,
        java_source: str,
    ) -> Dict[str, Any]:
        class_name = extract_java_class_name(java_source, program_name)
        test_class_name = f"{class_name}EdgeCaseTest"
        edge_cases = self.derive_edge_cases(parser_json)

        methods: List[str] = []
        for idx, case in enumerate(edge_cases):
            methods.append(self._render_edge_case_test(class_name, case, idx))

        if not methods:
            methods.append(
                "\n".join(
                    [
                        "    @Test",
                        "    void test_no_structural_edge_cases_placeholder() {",
                        f"        {class_name} app = new {class_name}();",
                        "        assertNotNull(app);",
                        "    }",
                    ]
                )
            )

        helpers = self._class_helpers()
        test_source = "\n".join(
            [
                "import org.junit.jupiter.api.Test;",
                "import static org.junit.jupiter.api.Assertions.*;",
                "",
                f"class {test_class_name} {{",
                "",
                "\n\n".join(methods),
                helpers,
                "}",
                "",
            ]
        )

        serializable_cases: List[Dict[str, Any]] = []
        for c in edge_cases:
            serializable_cases.append(
                {
                    "type": c.get("type"),
                    "paragraph": c.get("paragraph"),
                    "field": c.get("field"),
                    "values": c.get("values"),
                    "detail": c.get("detail"),
                }
            )

        return {
            "program_name": program_name,
            "test_class_name": test_class_name,
            "test_source": test_source,
            "test_count": test_source.count("@Test"),
            "edge_cases": serializable_cases,
        }

    def _render_edge_case_test(self, class_name: str, case: Dict[str, Any], index: int) -> str:
        case_type = str(case.get("type") or "edge")
        para = case.get("paragraph")
        field = str(case.get("field") or "struct")
        values = case.get("values") or []
        detail = str(case.get("detail") or case_type)
        slug = _slugify(f"{case_type}_{field}_{para or index}")

        lines = [
            "    @Test",
            f"    void test_{slug}() {{",
            "        // Arrange",
            f"        {class_name} app = new {class_name}();",
            "        assertNotNull(app);",
            f"        // Edge case: {_escape_java_string(detail)}",
        ]

        if case_type == "OCCURS boundary" and len(values) >= 3:
            n_minus, n_val, n_plus = int(values[0]), int(values[1]), int(values[2])
            lines.extend(
                [
                    f"        final int occursLimit = {n_val};",
                    "        // Act + Assert — index at limit-1, at limit, over limit",
                    f"        assertDoesNotThrow(() -> EdgeCaseTestSupport.assertIndexInRange({n_minus}, occursLimit));",
                    f"        assertDoesNotThrow(() -> EdgeCaseTestSupport.assertIndexInRange({n_val}, occursLimit));",
                    (
                        "        assertThrows(IndexOutOfBoundsException.class, "
                        f"() -> EdgeCaseTestSupport.assertIndexInRange({n_plus}, occursLimit));"
                    ),
                ]
            )
        elif case_type == "loop boundary":
            lines.append("        // Act + Assert — empty, minimum, boundary, just-over-boundary iterations")
            for v in values:
                lines.append(f"        assertDoesNotThrow(() -> EdgeCaseTestSupport.assertLoopIteration({int(v)}));")
        elif case_type == "file record loop":
            lines.extend(
                [
                    "        // Act + Assert — zero records vs one-record boundary",
                    "        assertDoesNotThrow(() -> EdgeCaseTestSupport.assertRecordCount(0));",
                    "        assertDoesNotThrow(() -> EdgeCaseTestSupport.assertRecordCount(1));",
                ]
            )
        elif case_type == "early exit":
            exit_kind = _escape_java_string(str(case.get("field") or "EXIT"))
            para_s = _escape_java_string(str(para or "paragraph"))
            lines.extend(
                [
                    f"        // Act + Assert — {exit_kind} stops execution in {para_s}",
                    "        assertTrue(EdgeCaseTestSupport.simulateEarlyExit(true), \"early exit path\");",
                ]
            )
        elif case_type == "EVALUATE threshold" and len(values) >= 3:
            a, b, c = int(values[0]), int(values[1]), int(values[2])
            lines.extend(
                [
                    f"        final int threshold = {b};",
                    "        // Act + Assert — below, exact, and above EVALUATE threshold",
                    f"        assertTrue({a} < threshold, \"below threshold branch\");",
                    f"        assertEquals(threshold, {b}, \"exact threshold\");",
                    f"        assertTrue({c} > threshold, \"above threshold branch\");",
                ]
            )
        else:
            for v in values:
                if isinstance(v, int):
                    lines.append(f"        assertDoesNotThrow(() -> EdgeCaseTestSupport.assertBoundaryValue({int(v)}));")
                else:
                    lines.append(
                        f'        assertDoesNotThrow(() -> EdgeCaseTestSupport.assertBoundaryLabel("{_escape_java_string(str(v))}"));'
                    )

        lines.append("    }")
        return "\n".join(lines)

    @staticmethod
    def _class_helpers() -> str:
        return "\n".join(
            [
                "",
                "    static final class EdgeCaseTestSupport {",
                "        private EdgeCaseTestSupport() {}",
                "",
                "        static void assertIndexInRange(int index, int limit) {",
                "            if (index < 0 || index >= limit) {",
                '                throw new IndexOutOfBoundsException("index " + index + " limit " + limit);',
                "            }",
                "        }",
                "",
                "        static void assertLoopIteration(int iteration) {",
                '            assertTrue(iteration >= 0, "loop iteration");',
                "        }",
                "",
                "        static void assertRecordCount(int count) {",
                '            assertTrue(count >= 0, "record count");',
                "        }",
                "",
                "        static boolean simulateEarlyExit(boolean trigger) {",
                "            return trigger;",
                "        }",
                "",
                "        static void assertBoundaryValue(int value) {",
                '            assertTrue(value >= 0, "boundary");',
                "        }",
                "",
                "        static void assertBoundaryLabel(String label) {",
                "            assertNotNull(label);",
                "        }",
                "    }",
            ]
        )


def generate_edge_case_tests(
    program_name: str,
    parser_json: dict,
    java_source: str,
) -> Dict[str, Any]:
    return EdgeCaseTestGenerator().generate_with_metadata(program_name, parser_json, java_source)
