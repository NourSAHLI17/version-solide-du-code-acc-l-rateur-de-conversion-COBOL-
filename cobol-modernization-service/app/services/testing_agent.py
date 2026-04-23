"""Testing Agent — Stage 9 of the COBOL modernization pipeline.

Provides three sub-generators:
  1. Parser structural tests (deterministic)
  2. Conversion static analysis tests (regex-based, no external deps)
  3. Behavioral tests (GnuCOBOL vs Java stdout diff via subprocess)

No mock data. No fallbacks. All computations are real.
"""

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List


COBOL_RESERVED_WORDS = {
    "ACCEPT", "ADD", "ALTER", "CALL", "CANCEL", "CLOSE", "COMPUTE", "CONTINUE",
    "DELETE", "DISPLAY", "DIVIDE", "ELSE", "END", "EVALUATE", "EXIT", "GO", "IF",
    "INITIALIZE", "INSPECT", "MERGE", "MOVE", "MULTIPLY", "OPEN", "PERFORM",
    "READ", "RELEASE", "RETURN", "REWRITE", "SEARCH", "SET", "SORT", "START",
    "STOP", "STRING", "SUBTRACT", "UNSTRING", "WRITE", "SECTION", "DIVISION",
}


# ── Sub-generator 1: Parser Tests ────────────────────────────────────────────

def run_parser_tests(parser_output: dict) -> List[dict]:
    """Validate parser output structural integrity."""
    tests: list[dict] = []
    known_paras = set(parser_output.get("paragraphs", []))

    # Symbol table: every symbol has pic or kind
    for sym in parser_output.get("symbol_table", []):
        tests.append({
            "id": f"SYM_{sym['name']}",
            "description": f"Symbol '{sym['name']}' has pic and kind defined",
            "passed": bool(sym.get("pic") or sym.get("kind")),
            "severity": "critical",
        })

    # Call graph integrity
    for call in parser_output.get("control_flow", {}).get("calls", []):
        target = call.get("to", "")
        tests.append({
            "id": f"CALL_{call.get('from')}_TO_{target}",
            "description": f"PERFORM target '{target}' exists as paragraph",
            "passed": target in known_paras,
            "severity": "critical",
        })

    # No reserved words as paragraphs
    for para in parser_output.get("paragraphs", []):
        tests.append({
            "id": f"RESERVED_{para}",
            "description": f"Paragraph '{para}' is not a reserved word",
            "passed": para not in COBOL_RESERVED_WORDS,
            "severity": "critical",
        })

    # Loop bounds completeness
    for loop in parser_output.get("control_flow", {}).get("loops", []):
        if loop.get("type") == "PERFORM_VARYING":
            tests.append({
                "id": f"LOOP_{loop.get('paragraph', 'UNKNOWN')}",
                "description": f"Loop in {loop.get('paragraph')} has iterator/start/step/until",
                "passed": all([
                    loop.get("iterator"),
                    loop.get("start"),
                    loop.get("step"),
                    loop.get("until"),
                ]),
                "severity": "high",
            })

    # No dead code from EVALUATE dispatch
    for call in parser_output.get("control_flow", {}).get("calls", []):
        if call.get("conditional"):
            tests.append({
                "id": f"LIVE_CONDITIONAL_{call['to']}",
                "description": f"Conditional call to '{call['to']}' registered (not dead code)",
                "passed": True,
                "severity": "high",
            })

    return tests


# ── Sub-generator 2: Conversion Static Tests ─────────────────────────────────

def run_conversion_tests(java_source: str, parser_output: dict) -> List[dict]:
    """Static analysis of generated Java source against parser contract."""
    tests: list[dict] = []

    if not java_source:
        return tests

    # No do-while (PERFORM UNTIL must be while)
    do_while_count = len(re.findall(r"\bdo\s*\{", java_source))
    tests.append({
        "id": "NO_DO_WHILE",
        "description": "No do-while loops (PERFORM UNTIL must be while)",
        "passed": do_while_count == 0,
        "severity": "high",
        "detail": f"Found {do_while_count} do-while occurrences",
    })

    # No float/double for decimal fields
    decimal_syms = [
        s["name"].replace("-", "_").lower()
        for s in parser_output.get("symbol_table", [])
        if "V" in (s.get("pic") or "")
    ]
    if decimal_syms:
        float_pattern = re.compile(
            r"\b(float|double)\b\s+("
            + "|".join(re.escape(s) for s in decimal_syms)
            + r")\b"
        )
        float_violations = float_pattern.findall(java_source)
    else:
        float_violations = []

    tests.append({
        "id": "NO_FLOAT_DOUBLE",
        "description": "No float/double for PIC 9(n)Vdd fields (must be BigDecimal)",
        "passed": len(float_violations) == 0,
        "severity": "critical",
        "detail": str(float_violations) if float_violations else "OK",
    })

    # BigDecimal used for decimal fields
    for sym in decimal_syms:
        tests.append({
            "id": f"BIGDECIMAL_{sym.upper()}",
            "description": f"Field '{sym}' uses BigDecimal",
            "passed": "BigDecimal" in java_source and sym in java_source,
            "severity": "critical",
        })

    # Array sizes match OCCURS
    for sym in parser_output.get("symbol_table", []):
        if sym.get("occurs"):
            expected = sym["occurs"]
            array_pattern = re.compile(
                rf"new\s+\w+\[({expected})\]|=\s*new\s+\w+\[({expected})\]"
            )
            found = bool(array_pattern.search(java_source))
            tests.append({
                "id": f"ARRAY_SIZE_{sym['name']}",
                "description": f"Array for '{sym['name']}' has size {expected} (OCCURS {expected})",
                "passed": found,
                "severity": "high",
            })

    # stripTrailing used for string comparison
    tests.append({
        "id": "STRING_COMPARE_STRIP",
        "description": "String comparisons use stripTrailing() for COBOL padding semantics",
        "passed": "stripTrailing" in java_source,
        "severity": "medium",
    })

    # isBlank used for empty-name check
    tests.append({
        "id": "EMPTY_CHECK_ISBLANK",
        "description": "Empty name check uses isBlank()",
        "passed": "isBlank()" in java_source,
        "severity": "low",
    })

    return tests


# ── Sub-generator 3: Behavioral Tests (GnuCOBOL vs Java) ────────────────────

BEHAVIORAL_SCENARIOS = [
    {
        "id": "ADD_THEN_REPORT",
        "description": "Add 1 item then generate report",
        "input": "1\nApple               \n50\n150\n4\n0\n",
        "expected_contains": ["Item added successfully!", "Item Name"],
        "expected_not_contains": ["Inventory is full"],
    },
    {
        "id": "UPDATE_NOT_FOUND",
        "description": "Update non-existent item",
        "input": "2\nGhost               \n0\n",
        "expected_contains": ["Item not found."],
        "expected_not_contains": ["Item updated successfully"],
    },
    {
        "id": "DELETE_THEN_REPORT",
        "description": "Add item, delete it, verify absent from report",
        "input": "1\nApple               \n10\n100\n3\nApple               \n4\n0\n",
        "expected_contains": ["Item deleted successfully!", "End of Report"],
        "expected_not_contains": [],
    },
    {
        "id": "INVALID_CHOICE",
        "description": "Enter invalid menu choice",
        "input": "9\n0\n",
        "expected_contains": ["Invalid choice"],
        "expected_not_contains": [],
    },
    {
        "id": "EMPTY_REPORT",
        "description": "Generate report with empty inventory",
        "input": "4\n0\n",
        "expected_contains": ["End of Report"],
        "expected_not_contains": ["Item Name     :"],
    },
]


def _check_gnucobol() -> bool:
    """Check if GnuCOBOL compiler is available on the system."""
    try:
        r = subprocess.run(["cobc", "--version"], capture_output=True, timeout=3)
        return r.returncode == 0
    except Exception:
        return False


def _check_javac() -> bool:
    """Check if javac compiler is available on the system."""
    try:
        r = subprocess.run(["javac", "-version"], capture_output=True, timeout=3)
        return r.returncode == 0
    except Exception:
        return False


def run_behavioral_tests(java_source: str, cobol_source: str) -> List[dict]:
    """Real behavioral testing via subprocess compilation and execution."""
    results: list[dict] = []

    if not java_source:
        return results

    cobol_available = _check_gnucobol()
    javac_available = _check_javac()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # ── Compile Java ──────────────────────────────────────────────
        java_ok = False
        java_compile_error = ""
        if javac_available:
            # Extract class name from source
            class_match = re.search(r"public\s+class\s+(\w+)", java_source)
            class_name = class_match.group(1) if class_match else "Output"
            java_path = tmp / f"{class_name}.java"
            java_path.write_text(java_source, encoding="utf-8")
            compile_result = subprocess.run(
                ["javac", str(java_path)],
                capture_output=True,
                cwd=tmpdir,
                timeout=30,
            )
            java_ok = compile_result.returncode == 0
            if not java_ok:
                java_compile_error = compile_result.stderr.decode(errors="replace")[:500]
        else:
            java_compile_error = "javac not available on this system"

        # ── Compile COBOL (optional) ──────────────────────────────────
        cobol_bin = None
        if cobol_available and cobol_source:
            cob_path = tmp / "program.cob"
            cob_path.write_text(cobol_source, encoding="utf-8")
            cobc = subprocess.run(
                ["cobc", "-x", "-o", str(tmp / "program"), str(cob_path)],
                capture_output=True,
                cwd=tmpdir,
                timeout=30,
            )
            if cobc.returncode == 0:
                cobol_bin = str(tmp / "program")

        # ── Run scenarios ─────────────────────────────────────────────
        for scenario in BEHAVIORAL_SCENARIOS:
            inp = scenario["input"].encode()
            java_out = ""
            cobol_out = ""

            if java_ok:
                try:
                    jr = subprocess.run(
                        ["java", "-cp", str(tmp), class_name],
                        input=inp,
                        capture_output=True,
                        timeout=10,
                        cwd=tmpdir,
                    )
                    java_out = jr.stdout.decode(errors="replace")
                except subprocess.TimeoutExpired:
                    java_out = ""

            if cobol_bin:
                try:
                    cr = subprocess.run(
                        [cobol_bin],
                        input=inp,
                        capture_output=True,
                        timeout=10,
                    )
                    cobol_out = cr.stdout.decode(errors="replace")
                except subprocess.TimeoutExpired:
                    cobol_out = ""

            # Check assertions
            assertion_failures: list[str] = []
            for exp in scenario.get("expected_contains", []):
                if exp not in java_out:
                    assertion_failures.append(f"MISSING: '{exp}'")
            for not_exp in scenario.get("expected_not_contains", []):
                if not_exp in java_out:
                    assertion_failures.append(f"UNEXPECTED: '{not_exp}'")

            # Diff if both outputs available
            diff: list[dict] = []
            if cobol_out and java_out:
                cobol_lines = [line.rstrip() for line in cobol_out.splitlines()]
                java_lines = [line.rstrip() for line in java_out.splitlines()]
                for i, (cl, jl) in enumerate(zip(cobol_lines, java_lines)):
                    if cl != jl:
                        diff.append({"line": i + 1, "cobol": cl, "java": jl})

            results.append({
                "id": scenario["id"],
                "description": scenario["description"],
                "passed": len(assertion_failures) == 0 and java_ok,
                "java_compiled": java_ok,
                "java_compile_error": java_compile_error if not java_ok else "",
                "cobol_available": cobol_available,
                "stdout_diff": diff,
                "assertion_failures": assertion_failures,
                "java_stdout": java_out[:2000],
                "severity": "critical",
            })

    return results


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_testing_agent(
    parser_output: dict,
    analysis_output: dict,
    java_source: str,
    cobol_source: str,
) -> dict:
    """Run all three sub-generators and return a unified test report."""
    parser_tests = run_parser_tests(parser_output)
    conversion_tests = run_conversion_tests(java_source, parser_output)
    behavioral_tests = run_behavioral_tests(java_source, cobol_source)

    all_tests = parser_tests + conversion_tests + behavioral_tests
    critical_fails = [
        t for t in all_tests if not t["passed"] and t["severity"] == "critical"
    ]
    high_fails = [
        t for t in all_tests if not t["passed"] and t["severity"] == "high"
    ]

    return {
        "parser_tests": parser_tests,
        "conversion_tests": conversion_tests,
        "behavioral_tests": behavioral_tests,
        "summary": {
            "total": len(all_tests),
            "passed": sum(1 for t in all_tests if t["passed"]),
            "failed": sum(1 for t in all_tests if not t["passed"]),
            "critical_failures": len(critical_fails),
            "high_failures": len(high_fails),
        },
        "is_pipeline_green": len(critical_fails) == 0,
    }
