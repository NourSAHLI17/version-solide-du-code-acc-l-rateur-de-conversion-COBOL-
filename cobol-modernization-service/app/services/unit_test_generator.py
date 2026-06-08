"""Deterministic JUnit 5 unit test generation from converted Java (no LLM)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

COVERAGE_STRATEGY = "public methods with deterministic branch/value assertions"


def _unwrap_parser(parser_json: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(parser_json, dict):
        return {}
    ast = parser_json.get("ast")
    if isinstance(ast, dict) and ast:
        return dict(ast)
    return dict(parser_json)


def _unwrap_analysis(analysis_json: Any) -> Dict[str, Any]:
    if isinstance(analysis_json, dict):
        return dict(analysis_json)
    return {}


def extract_java_class_name(java_source: str, program_name: str) -> str:
    m = re.search(r"public\s+class\s+(\w+)", java_source or "")
    if m:
        return m.group(1)
    base = re.sub(r"[^a-zA-Z0-9]+", " ", program_name or "Program").title().replace(" ", "")
    return base or "GeneratedProgram"


def _slugify(name: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_")
    if not slug:
        return "method"
    if slug[0].isdigit():
        slug = f"m_{slug}"
    return slug[:max_len].rstrip("_")


def _name_aliases(cobol_name: str) -> List[str]:
    base = cobol_name.strip()
    if not base:
        return []
    upper = base.upper()
    parts = [x for x in upper.split("-") if x]
    variants: List[str] = []
    variants.append(upper.replace("-", "_").lower())
    variants.append("_".join(x.lower() for x in parts))
    if parts:
        camel = "".join(p.title() for p in parts)
        variants.append(camel)
        variants.append(camel[:1].lower() + camel[1:] if camel else "")
        variants.append("".join(parts).lower())
    seen = set()
    out: List[str] = []
    for v in variants:
        v = v.strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _paragraph_method_map(parser_json: Dict[str, Any]) -> Dict[str, str]:
    """Map COBOL paragraph names to likely Java method names."""
    from app.converters.cobol_name_converter import CobolNameConverter

    parser = _unwrap_parser(parser_json)
    mapping: Dict[str, str] = {}
    paragraph_table = parser.get("paragraph_table") or []
    if isinstance(paragraph_table, list) and paragraph_table:
        for entry in paragraph_table:
            if not isinstance(entry, dict):
                continue
            cobol = str(entry.get("cobol") or "").strip()
            java_method = str(entry.get("java_method") or "").strip()
            if cobol and java_method:
                mapping[java_method.lower()] = cobol
        return mapping
    paragraphs = parser.get("paragraphs") or []
    names: List[str] = []
    if isinstance(paragraphs, list):
        for p in paragraphs:
            if isinstance(p, str) and p.strip():
                names.append(p.strip())
            elif isinstance(p, dict) and p.get("name"):
                names.append(str(p["name"]).strip())
    for para in names:
        canonical = CobolNameConverter.to_java_method(para)
        if canonical:
            mapping[canonical.lower()] = para
        for alias in _name_aliases(para):
            mapping[alias.lower()] = para
    return mapping


def _section_roles(analysis_json: Dict[str, Any]) -> Dict[str, str]:
    roles: Dict[str, str] = {}
    for sec in analysis_json.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        name = str(sec.get("name") or "").strip()
        role = str(sec.get("role") or "").strip()
        if name:
            roles[name] = role
    return roles


def _split_params(param_str: str) -> List[Dict[str, str]]:
    if not param_str or not param_str.strip():
        return []
    parts: List[str] = []
    depth = 0
    current: List[str] = []
    for ch in param_str:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    out: List[Dict[str, str]] = []
    for raw in parts:
        raw = raw.strip()
        if not raw:
            continue
        tokens = raw.split()
        if len(tokens) >= 2:
            ptype = " ".join(tokens[:-1]).strip()
            pname = tokens[-1].strip()
        else:
            ptype = raw
            pname = f"arg{len(out)}"
        out.append({"type": ptype, "name": pname})
    return out


def _is_void(return_type: str) -> bool:
    rt = return_type.strip().lower()
    return rt == "void" or rt == ""


def _fixture_for_type(ptype: str, index: int) -> str:
    t = ptype.lower()
    if "string" in t:
        if index == 0:
            return '"test"'
        if index == 1:
            return '"Y"'
        return '""'
    if "boolean" in t or t == "bool":
        return "true" if index % 2 == 0 else "false"
    if "long" in t:
        return str([0, 1, 10][index % 3])
    if "double" in t or "float" in t or "bigdecimal" in t:
        return str([0.0, 1.0, 10.5][index % 3])
    if "int" in t or re.search(r"\bbyte\b|\bshort\b|\bchar\b", t):
        return str([0, 1, 10][index % 3])
    return "null"


def _java_literal_for_fixture(fixture: str) -> str:
    if fixture == "null":
        return "null"
    if fixture.startswith('"'):
        return fixture
    return fixture


def _dependency_hints(body: str) -> Dict[str, Any]:
    """Detect dependencies that need mocks or deterministic fixtures."""
    hints: Dict[str, Any] = {
        "file_io": bool(re.search(r"\bnew\s+[\w.]*File\b", body, re.IGNORECASE)),
        "scanner": bool(re.search(r"\bnew\s+Scanner\b", body)),
        "stream_io": bool(
            re.search(r"\b(InputStream|OutputStream|Reader|Writer|BufferedReader)\b", body)
        ),
        "external_new": bool(re.search(r"\bnew\s+[\w.]+\s*\(", body)),
    }
    helpers = []
    for m in re.finditer(r"\b(this\.)?(\w+)\s*\([^)]*\)\s*;", body):
        callee = m.group(2)
        if callee not in {"if", "for", "while", "switch", "return", "new"}:
            helpers.append(callee)
    hints["helper_calls"] = list(dict.fromkeys(helpers))[:5]
    return hints


def _infer_numeric_expected(fixtures: List[str], body: str) -> Optional[str]:
    """Best-effort expected value for simple arithmetic returns."""
    if len(fixtures) < 2:
        return None
    if re.search(r"return\s+\w+\s*\*\s*\w+", body):
        try:
            vals = [float(f) for f in fixtures[:2]]
            product = vals[0] * vals[1]
            if product == int(product):
                return str(int(product))
            return str(product)
        except ValueError:
            return None
    m = re.search(r"return\s+(-?\d+(?:\.\d+)?)\s*;", body)
    if m:
        return m.group(1)
    return None


def _assertion_for_return(
    return_type: str,
    fixtures: List[str],
    body: str,
    variant: str,
    call_expr: str,
) -> List[str]:
    rt = (return_type or "").lower()
    lines: List[str] = []
    if variant != "happy_path":
        if "throws" in body.lower() or "throw new" in body:
            exc = "IllegalArgumentException"
            if "IOException" in body:
                exc = "IOException"
            return [
                f"        assertThrows({exc}.class, () -> {call_expr});",
            ]
        return [
            f"        assertDoesNotThrow(() -> {call_expr});",
        ]

    expected = _infer_numeric_expected(fixtures, body)
    if expected is not None:
        if "double" in rt or "float" in rt or "." in expected:
            return [f"        assertEquals({expected}, (double) result, 0.001);"]
        if "long" in rt:
            return [f"        assertEquals({expected}L, result);"]
        return [f"        assertEquals({expected}, result);"]

    if "boolean" in rt:
        if "return true" in body.replace(" ", ""):
            return ["        assertTrue(result);"]
        if "return false" in body.replace(" ", ""):
            return ["        assertFalse(result);"]

    if "string" in rt:
        return ['        assertNotNull(result);', '        assertFalse(result.isEmpty());']

    return ["        assertNotNull(result);"]


def _render_mock_setup(hints: Dict[str, Any]) -> List[str]:
    if not any(hints.get(k) for k in ("file_io", "scanner", "stream_io", "external_new")):
        return []
    lines = [
        "        // Arrange — dependency stubs (deterministic test doubles)",
    ]
    if hints.get("file_io"):
        lines.append("        // Stub File I/O: inject a temp path or mock File factory before Act")
    if hints.get("scanner"):
        lines.append('        // Stub Scanner input: use new Scanner("line1\\nline2\\n") for stdin')
    if hints.get("stream_io"):
        lines.append("        // Stub stream I/O with ByteArrayInputStream / StringReader")
    helpers = hints.get("helper_calls") or []
    if helpers:
        lines.append(f"        // Helper calls detected: {', '.join(helpers[:3])}")
    return lines


def _method_body_snippet(java_source: str, method_name: str) -> str:
    m = re.search(
        rf"\b{re.escape(method_name)}\s*\([^)]*\)\s*\{{",
        java_source or "",
        re.DOTALL,
    )
    if not m:
        return ""
    start = m.end()
    depth = 1
    i = start
    src = java_source or ""
    while i < len(src) and depth > 0:
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    return src[start : max(start, i - 1)]


class UnitTestGenerator:
    """Generate method-level JUnit 5 unit tests from Java source and structural metadata."""

    METHOD_PATTERN = re.compile(
        r"public\s+(?:static\s+)?(?:final\s+)?"
        r"([\w<>,\[\]\s.]+?)\s+(\w+)\s*\(([^)]*)\)\s*(?:throws\s+([\w\s,]+))?",
        re.MULTILINE,
    )
    CONSTRUCTOR_PATTERN = re.compile(
        r"public\s+(\w+)\s*\(([^)]*)\)\s*(?:throws\s+([\w\s,]+))?\s*\{",
        re.MULTILINE,
    )

    def extract_public_methods(self, java_source: str) -> List[Dict[str, Any]]:
        source = java_source or ""
        class_name = ""
        cm = re.search(r"public\s+class\s+(\w+)", source)
        if cm:
            class_name = cm.group(1)

        methods: List[Dict[str, Any]] = []
        seen: set[str] = set()

        if class_name:
            for m in self.CONSTRUCTOR_PATTERN.finditer(source):
                name = m.group(1).strip()
                if name != class_name:
                    continue
                params_raw = m.group(2) or ""
                throws = (m.group(3) or "").strip()
                key = f"{name}({params_raw})"
                if key in seen:
                    continue
                seen.add(key)
                methods.append(
                    {
                        "name": name,
                        "return_type": class_name,
                        "params": _split_params(params_raw),
                        "throws": throws,
                        "kind": "constructor",
                        "is_static": False,
                        "is_void": True,
                    }
                )

        for m in self.METHOD_PATTERN.finditer(source):
            return_type = m.group(1).strip()
            name = m.group(2).strip()
            params_raw = m.group(3) or ""
            throws = (m.group(4) or "").strip()

            if name == class_name:
                kind = "constructor"
                return_type = class_name
            else:
                kind = "method"

            key = f"{name}({params_raw})"
            if key in seen:
                continue
            seen.add(key)

            params = _split_params(params_raw)
            is_static = bool(re.search(rf"public\s+static\s+[\w<>,\[\]\s.]+\s+{re.escape(name)}\s*\(", source))
            methods.append(
                {
                    "name": name,
                    "return_type": return_type,
                    "params": params,
                    "throws": throws,
                    "kind": kind,
                    "is_static": is_static,
                    "is_void": _is_void(return_type) if kind == "method" else True,
                }
            )

        return methods

    def _classify_method(
        self,
        method: Dict[str, Any],
        parser_json: Dict[str, Any],
        analysis_json: Dict[str, Any],
    ) -> str:
        name = str(method.get("name") or "")
        java_blob = str(parser_json.get("_java_blob") or "")
        if method.get("throws"):
            return "throws_on_invalid"
        if method.get("kind") == "constructor":
            return "constructor"
        if _is_void(str(method.get("return_type") or "")):
            if method.get("params"):
                return "side_effect"
            return "no_return"
        if not _is_void(str(method.get("return_type") or "")):
            return "returns_value"
        return "no_return"

    def derive_test_cases(
        self,
        java_source: str,
        parser_json: dict,
        analysis_json: dict,
    ) -> List[Dict[str, Any]]:
        parser = _unwrap_parser(parser_json)
        analysis = _unwrap_analysis(analysis_json)
        parser["_java_blob"] = (java_source or "").lower()

        para_map = _paragraph_method_map(parser)
        roles = _section_roles(analysis)
        methods = self.extract_public_methods(java_source)
        cases: List[Dict[str, Any]] = []

        cf = parser.get("control_flow") if isinstance(parser.get("control_flow"), dict) else {}
        has_branches = bool(cf.get("branches"))

        for method in methods:
            name = str(method["name"])
            shape = self._classify_method(method, parser, analysis)
            linked_para = para_map.get(name.lower())
            role = roles.get(linked_para or "", "") if linked_para else ""

            fixtures: List[str] = []
            param_names: List[str] = []
            for i, p in enumerate(method.get("params") or []):
                fixtures.append(_fixture_for_type(str(p.get("type") or ""), i))
                param_names.append(str(p.get("name") or f"arg{i}"))

            body = _method_body_snippet(java_source, name)
            dep_hints = _dependency_hints(body)
            needs_mock = bool(
                dep_hints.get("file_io")
                or dep_hints.get("scanner")
                or dep_hints.get("stream_io")
                or dep_hints.get("external_new")
                or "file" in role.lower()
                or "io" in role.lower()
            )
            has_local_branches = bool(re.search(r"\bif\s*\(", body))

            cases.append(
                {
                    "method_name": name,
                    "shape": shape,
                    "fixtures": fixtures,
                    "param_names": param_names,
                    "return_type": method.get("return_type"),
                    "needs_mock": needs_mock,
                    "dep_hints": dep_hints,
                    "method_body": body,
                    "linked_paragraph": linked_para,
                    "test_variant": "happy_path",
                }
            )

            para_has_branches = False
            if linked_para and isinstance(cf.get("branches"), list):
                para_has_branches = any(
                    isinstance(b, dict) and str(b.get("paragraph") or "") == linked_para
                    for b in cf.get("branches")
                )

            if (
                method.get("params")
                or (has_branches and para_has_branches)
                or has_local_branches
                or shape == "throws_on_invalid"
            ):
                invalid_fixtures = []
                for i, p in enumerate(method.get("params") or []):
                    t = str(p.get("type") or "").lower()
                    if "int" in t or "long" in t:
                        invalid_fixtures.append("-1")
                    elif "string" in t:
                        invalid_fixtures.append('""')
                    else:
                        invalid_fixtures.append(_fixture_for_type(t, i + 2))
                cases.append(
                    {
                        "method_name": name,
                        "shape": "branch_or_exception" if shape != "throws_on_invalid" else "throws_on_invalid",
                        "fixtures": invalid_fixtures if invalid_fixtures else fixtures,
                        "param_names": param_names,
                        "return_type": method.get("return_type"),
                        "needs_mock": needs_mock,
                        "dep_hints": dep_hints,
                        "method_body": body,
                        "linked_paragraph": linked_para,
                        "test_variant": "branch_or_invalid",
                    }
                )

        if not cases and methods:
            m = methods[0]
            cases.append(
                {
                    "method_name": m["name"],
                    "shape": "no_return",
                    "fixtures": [],
                    "param_names": [],
                    "return_type": m.get("return_type"),
                    "needs_mock": False,
                    "linked_paragraph": None,
                    "test_variant": "happy_path",
                }
            )

        return cases

    def generate(self, program_name: str, parser_json: dict, analysis_json: dict, java_source: str) -> str:
        return self.generate_with_metadata(program_name, parser_json, analysis_json, java_source)["test_source"]

    def generate_with_metadata(
        self,
        program_name: str,
        parser_json: dict,
        analysis_json: dict,
        java_source: str,
    ) -> Dict[str, Any]:
        class_name = extract_java_class_name(java_source, program_name)
        test_class_name = f"{class_name}UnitTest"
        cases = self.derive_test_cases(java_source, parser_json, analysis_json)

        methods: List[str] = []
        method_counts: Dict[str, int] = {}

        for case in cases:
            method_name = str(case["method_name"])
            method_counts[method_name] = method_counts.get(method_name, 0) + 1
            methods.append(self._render_test_method(class_name, case))

        if not methods:
            methods.append(
                "\n".join(
                    [
                        "    @Test",
                        "    void test_placeholder_noPublicMethods() {",
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

        methods_covered = [
            {"name": name, "test_count": count} for name, count in sorted(method_counts.items())
        ]

        return {
            "program_name": program_name,
            "test_class_name": test_class_name,
            "test_source": test_source,
            "test_count": test_source.count("@Test"),
            "methods_covered": methods_covered,
            "coverage_strategy": COVERAGE_STRATEGY,
        }

    def _render_test_method(self, class_name: str, case: Dict[str, Any]) -> str:
        method_name = str(case["method_name"])
        variant = str(case.get("test_variant") or "happy_path")
        shape = str(case.get("shape") or "no_return")
        slug = _slugify(method_name)
        suffix = "happyPath" if variant == "happy_path" else "branchPath"
        if shape == "returns_value":
            test_method = f"test_{slug}_{suffix}_returnsValue"
        elif shape == "constructor":
            test_method = f"test_{slug}_{suffix}_constructs"
        elif shape == "throws_on_invalid" or (variant != "happy_path" and shape == "branch_or_exception"):
            test_method = f"test_{slug}_{suffix}_invalidInput"
        else:
            test_method = f"test_{slug}_{suffix}_runs"

        fixtures = case.get("fixtures") or []
        arg_list = ", ".join(_java_literal_for_fixture(str(f)) for f in fixtures)
        needs_mock = bool(case.get("needs_mock"))
        dep_hints = case.get("dep_hints") or {}
        body = str(case.get("method_body") or "")
        return_type = str(case.get("return_type") or "")
        linked = case.get("linked_paragraph")

        lines = [
            "    @Test",
            f"    void {test_method}() {{",
            "        // Arrange",
        ]
        if needs_mock:
            lines.extend(_render_mock_setup(dep_hints if isinstance(dep_hints, dict) else {}))
        if shape == "constructor":
            if arg_list:
                lines.append(f"        {class_name} app = new {class_name}({arg_list});")
            else:
                lines.append(f"        {class_name} app = new {class_name}();")
        else:
            lines.append(f"        {class_name} app = new {class_name}();")

        if linked:
            lines.append(f"        // Linked COBOL paragraph: {linked}")

        lines.append("        // Act")
        if shape == "constructor":
            lines.append("        assertNotNull(app);")
        else:
            call = f"app.{method_name}({arg_list})" if arg_list else f"app.{method_name}()"
            if shape == "returns_value":
                lines.append(f"        var result = {call};")
                lines.append("        // Assert")
                lines.extend(
                    _assertion_for_return(return_type, fixtures, body, variant, call)
                )
            elif shape == "throws_on_invalid" or (
                variant != "happy_path" and shape == "branch_or_exception"
            ):
                lines.append("        // Assert")
                lines.extend(_assertion_for_return(return_type, fixtures, body, variant, call))
            else:
                lines.append(f"        assertDoesNotThrow(() -> {call});")
                lines.append("        // Assert")
                if re.search(r"this\.\w+\s*=", body):
                    lines.append("        assertNotNull(app);")
                else:
                    lines.append("        assertNotNull(app);")

        lines.append("    }")
        return "\n".join(lines)


def generate_unit_tests(
    program_name: str,
    parser_json: dict,
    analysis_json: dict,
    java_source: str,
) -> Dict[str, Any]:
    return UnitTestGenerator().generate_with_metadata(
        program_name, parser_json, analysis_json, java_source
    )
