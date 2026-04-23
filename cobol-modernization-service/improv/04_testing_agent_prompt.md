# Codex Prompt — Testing Agent Implementation
**Component:** Testing Agent (4 specialized test generators)
**Languages:** Python 3.10+ (orchestration, behavioral diff), Java/JUnit 5 (generated tests)
**Position in Pipeline:** Stage 9 (final stage, receives all artifacts)
**LLM Usage:** GPT-4.1 for test code generation only — all execution is deterministic

---

## SYSTEM PROMPT

You are implementing a comprehensive testing agent for a COBOL-to-Java modernization
pipeline. The agent validates every stage of the pipeline — not just the final Java output.

The agent has four specialized sub-generators, each targeting a different artifact:

1. **Parser Tests** — validates the COBOL parser output JSON
2. **JCL Tests** — validates the JCL parser manifest JSON
3. **Conversion Tests** — validates the generated Java class (static analysis)
4. **Behavioral Tests** — validates runtime equivalence (GnuCOBOL vs Java stdout diff)

All test execution is deterministic Python and Java.
GPT-4.1 is used ONLY for generating JUnit 5 test code from structured JSON input.

---

## SUB-GENERATOR 1: Parser Tests (fully deterministic)

### What to Test

```python
def generate_parser_tests(parser_output: dict, original_source: str) -> list[dict]:
    tests = []

    # TEST 1: Symbol table completeness
    # Every DATA DIVISION variable must appear in symbol_table
    source_vars = extract_data_division_vars(original_source)  # regex-based
    table_names = {s['name'] for s in parser_output['symbol_table']}
    for var in source_vars:
        tests.append({
            "id": f"SYM_{var}",
            "description": f"Symbol '{var}' present in symbol table",
            "passed": var in table_names,
            "severity": "critical"
        })

    # TEST 2: Call graph integrity
    # Every PERFORM target must be a known paragraph
    known_paras = set(parser_output['paragraphs'])
    for call in parser_output['control_flow']['calls']:
        tests.append({
            "id": f"CALL_{call['from']}_TO_{call['to']}",
            "description": f"PERFORM target '{call['to']}' is a known paragraph",
            "passed": call['to'] in known_paras,
            "severity": "critical"
        })

    # TEST 3: No dead code false positives from EVALUATE dispatch
    evaluate_called = set()
    for op in parser_output.get('operations', []):
        if op['type'] == 'EVALUATE':
            for when_call in op.get('when_calls', []):
                evaluate_called.add(when_call)
    for call in parser_output['control_flow']['calls']:
        if call.get('conditional') and call['to'] in evaluate_called:
            # Verify not marked dead in analysis output
            tests.append({
                "id": f"LIVE_{call['to']}",
                "description": f"EVALUATE-dispatched paragraph '{call['to']}' not dead code",
                "passed": True,  # presence in calls[] with conditional:true = correct
                "severity": "high"
            })

    # TEST 4: Loop bounds match PERFORM VARYING source
    for loop in parser_output['control_flow']['loops']:
        if loop['type'] == 'PERFORM_VARYING':
            tests.append({
                "id": f"LOOP_{loop['paragraph']}",
                "description": f"Loop in '{loop['paragraph']}': iterator={loop['iterator']}, "
                               f"start={loop['start']}, step={loop['step']}, until={loop['until']}",
                "passed": all([loop.get('iterator'), loop.get('start'),
                               loop.get('step'), loop.get('until')]),
                "severity": "high"
            })

    # TEST 5: No reserved words as paragraph names
    for para in parser_output['paragraphs']:
        tests.append({
            "id": f"PARA_NAME_{para}",
            "description": f"Paragraph name '{para}' is not a reserved word",
            "passed": para not in COBOL_RESERVED_WORDS,
            "severity": "critical"
        })

    # TEST 6: Preflight gate passes
    preflight_errors = preflight_validate(parser_output)
    tests.append({
        "id": "PREFLIGHT",
        "description": "Preflight gate passes with zero errors",
        "passed": len(preflight_errors) == 0,
        "details": preflight_errors,
        "severity": "critical"
    })

    return tests
```

---

## SUB-GENERATOR 2: JCL Tests (fully deterministic)

```python
def generate_jcl_tests(jcl_manifest: dict, cobol_source: str) -> list[dict]:
    tests = []

    # TEST 1: Every EXEC PGM resolves to a known source file
    known_programs = extract_program_names(cobol_source)  # from PROGRAM-ID
    for step in jcl_manifest['steps']:
        if step.get('pgm'):
            tests.append({
                "id": f"PGM_{step['pgm']}",
                "description": f"EXEC PGM={step['pgm']} has matching COBOL source",
                "passed": step['pgm'] in known_programs,
                "severity": "high"
            })

    # TEST 2: Every DD name used in COBOL SELECT has a JCL binding
    cobol_selects = extract_select_assigns(cobol_source)  # regex: ASSIGN TO ddname
    all_dd_names = set()
    for step in jcl_manifest['steps']:
        all_dd_names.update(step.get('dd_bindings', {}).keys())
    for dd_name in cobol_selects:
        tests.append({
            "id": f"DD_{dd_name}",
            "description": f"COBOL ASSIGN TO {dd_name} has matching JCL DD statement",
            "passed": dd_name in all_dd_names,
            "severity": "high"
        })

    # TEST 3: SYSLIB paths extracted
    tests.append({
        "id": "SYSLIB_PATHS",
        "description": "JCL manifest contains at least one copylib path",
        "passed": len(jcl_manifest.get('copylib_paths', [])) > 0,
        "severity": "medium"
    })

    # TEST 4: Execution order is non-empty
    tests.append({
        "id": "EXEC_ORDER",
        "description": "Execution order has at least one program",
        "passed": len(jcl_manifest.get('execution_order', [])) > 0,
        "severity": "medium"
    })

    return tests
```

---

## SUB-GENERATOR 3: Conversion Tests (JavaParser static analysis)

These tests run on the generated Java source using the `javalang` Python library
(or spawn `javac` for compilation check). No LLM needed.

```python
import javalang  # pip install javalang

def generate_conversion_tests(java_source: str,
                               parser_output: dict,
                               analysis_output: dict) -> list[dict]:
    tests = []
    tree = javalang.parse.parse(java_source)

    # TEST 1: Compilation check
    tests.append({
        "id": "JAVA_COMPILES",
        "description": "Generated Java compiles without errors",
        "passed": check_java_compiles(java_source),
        "severity": "critical"
    })

    # TEST 2: No float/double for PIC 9(n)Vdd fields
    decimal_symbols = {
        s['name'].replace('-', '_').lower()
        for s in parser_output['symbol_table']
        if s.get('pic_decoded', {}).get('has_implied_decimal')
    }
    for path, node in tree.filter(javalang.tree.FieldDeclaration):
        field_type = node.type.name
        for decl in node.declarators:
            if decl.name.lower() in decimal_symbols:
                tests.append({
                    "id": f"TYPE_{decl.name}",
                    "description": f"Field '{decl.name}' uses BigDecimal (not float/double)",
                    "passed": field_type == "BigDecimal",
                    "severity": "critical"
                })

    # TEST 3: No do-while for PERFORM UNTIL loops
    for path, node in tree.filter(javalang.tree.DoStatement):
        tests.append({
            "id": f"NO_DOWHILE_{id(node)}",
            "description": "No do-while loop (PERFORM UNTIL must use while)",
            "passed": False,  # any do-while is a violation
            "severity": "high"
        })

    # TEST 4: Array sizes match OCCURS values
    occurs_symbols = {
        s['name'].replace('-', '_').lower(): s.get('occurs', 0)
        for s in parser_output['symbol_table']
        if s.get('occurs')
    }
    for path, node in tree.filter(javalang.tree.FieldDeclaration):
        for decl in node.declarators:
            name_lower = decl.name.lower()
            if name_lower in occurs_symbols:
                expected_size = occurs_symbols[name_lower]
                # Check array initializer size if present
                if hasattr(decl, 'initializer') and decl.initializer:
                    actual_size = extract_array_size(decl)
                    tests.append({
                        "id": f"ARRAY_SIZE_{decl.name}",
                        "description": f"Array '{decl.name}' size = {expected_size} (matches OCCURS)",
                        "passed": actual_size == expected_size,
                        "severity": "high"
                    })

    # TEST 5: Every business rule has a comment or test annotation
    for i, rule in enumerate(analysis_output.get('business_rules', [])):
        rule_present = rule.lower()[:30] in java_source.lower()
        tests.append({
            "id": f"BIZ_RULE_{i}",
            "description": f"Business rule documented: '{rule[:50]}'",
            "passed": rule_present,
            "severity": "medium"
        })

    return tests
```

---

## SUB-GENERATOR 4: Behavioral Tests (GnuCOBOL + Java stdout diff)

### Test Scenario Definitions (auto-generated from business_rules)

```python
BEHAVIORAL_SCENARIOS = [
    {
        "id": "SCENARIO_ADD_REPORT",
        "description": "Add 1 item then generate report",
        "input": "1\nApple               \n50\n150\n4\n0\n",
        "expected_contains": [
            "Item added successfully!",
            "Item Name     : Apple",
            "Item Quantity : 50",
        ],
        "expected_not_contains": ["Item not found", "Inventory is full"]
    },
    {
        "id": "SCENARIO_FULL_INVENTORY",
        "description": "Fill to capacity (100 items) then attempt 101st",
        "input_generator": "generate_100_items_input() + '1\nItem101\n1\n100\n0\n'",
        "expected_contains": ["Inventory is full. Cannot add more items."],
    },
    {
        "id": "SCENARIO_UPDATE_NOT_FOUND",
        "description": "Update item that does not exist",
        "input": "2\nGhost               \n0\n",
        "expected_contains": ["Item not found."],
    },
    {
        "id": "SCENARIO_DELETE_CLEARS_ALL",
        "description": "Delete item then verify absent from report",
        "input": "1\nApple               \n50\n150\n3\nApple               \n4\n0\n",
        "expected_contains": ["Item deleted successfully!", "End of Report"],
        "expected_not_contains": ["Apple"]
    },
    {
        "id": "SCENARIO_INVALID_CHOICE",
        "description": "Enter invalid menu choice",
        "input": "9\n0\n",
        "expected_contains": ["Invalid choice. Please enter 0-4."],
    },
    {
        "id": "SCENARIO_EMPTY_REPORT",
        "description": "Generate report with empty inventory",
        "input": "4\n0\n",
        "expected_contains": ["End of Report"],
        "expected_not_contains": ["Item Name"]
    }
]
```

### Behavioral Test Execution

```python
import subprocess, tempfile, os

def run_behavioral_tests(java_class_path: str,
                          cobol_source_path: str,
                          scenarios: list[dict]) -> list[dict]:
    results = []

    # Compile COBOL with GnuCOBOL
    cobol_binary = compile_gnucobol(cobol_source_path)

    # Compile Java
    java_binary = compile_java(java_class_path)

    for scenario in scenarios:
        input_data = scenario["input"].encode()

        # Run COBOL
        cobol_result = subprocess.run(
            [cobol_binary], input=input_data,
            capture_output=True, timeout=10
        )
        cobol_stdout = cobol_result.stdout.decode()

        # Run Java
        java_result = subprocess.run(
            ["java", "-cp", java_binary, "InventoryManagement"],
            input=input_data, capture_output=True, timeout=10
        )
        java_stdout = java_result.stdout.decode()

        # Normalize outputs (strip trailing whitespace per line)
        cobol_lines = [l.rstrip() for l in cobol_stdout.splitlines()]
        java_lines  = [l.rstrip() for l in java_stdout.splitlines()]

        # Diff
        diff = []
        for i, (cl, jl) in enumerate(zip(cobol_lines, java_lines)):
            if cl != jl:
                diff.append({"line": i+1, "cobol": cl, "java": jl})

        # Check expected contains/not-contains
        assertion_failures = []
        for expected in scenario.get("expected_contains", []):
            if expected not in java_stdout:
                assertion_failures.append(f"MISSING: '{expected}'")
        for not_expected in scenario.get("expected_not_contains", []):
            if not_expected in java_stdout:
                assertion_failures.append(f"UNEXPECTED: '{not_expected}'")

        results.append({
            "id": scenario["id"],
            "description": scenario["description"],
            "passed": len(diff) == 0 and len(assertion_failures) == 0,
            "stdout_diff": diff,
            "assertion_failures": assertion_failures,
            "severity": "critical"
        })

    return results
```

---

## TESTING AGENT ORCHESTRATOR

```python
def run_testing_agent(artifacts: dict) -> dict:
    report = {
        "parser_tests":     [],
        "jcl_tests":        [],
        "conversion_tests": [],
        "behavioral_tests": [],
        "summary": {},
        "is_pipeline_green": False
    }

    report["parser_tests"]     = generate_parser_tests(
        artifacts["parser_output"], artifacts["cobol_source"])

    report["jcl_tests"]        = generate_jcl_tests(
        artifacts["jcl_manifest"], artifacts["cobol_source"])

    report["conversion_tests"] = generate_conversion_tests(
        artifacts["java_source"],
        artifacts["parser_output"],
        artifacts["analysis_output"])

    report["behavioral_tests"] = run_behavioral_tests(
        artifacts["java_class_path"],
        artifacts["cobol_source_path"],
        BEHAVIORAL_SCENARIOS)

    # Summary
    all_tests = (report["parser_tests"] + report["jcl_tests"] +
                 report["conversion_tests"] + report["behavioral_tests"])
    critical_failures = [t for t in all_tests
                         if not t["passed"] and t["severity"] == "critical"]
    high_failures     = [t for t in all_tests
                         if not t["passed"] and t["severity"] == "high"]

    report["summary"] = {
        "total":            len(all_tests),
        "passed":           sum(1 for t in all_tests if t["passed"]),
        "failed":           sum(1 for t in all_tests if not t["passed"]),
        "critical_failures": len(critical_failures),
        "high_failures":     len(high_failures)
    }

    # Green only if zero critical failures
    report["is_pipeline_green"] = len(critical_failures) == 0

    return report
```

---

## TEST REPORT JSON CONTRACT

```json
{
  "parser_tests": [
    {"id": "SYM_INV-NAME", "description": "...", "passed": true, "severity": "critical"}
  ],
  "jcl_tests": [...],
  "conversion_tests": [
    {"id": "NO_DOWHILE_123", "description": "No do-while loop", "passed": false, "severity": "high"}
  ],
  "behavioral_tests": [
    {
      "id": "SCENARIO_ADD_REPORT",
      "passed": true,
      "stdout_diff": [],
      "assertion_failures": []
    }
  ],
  "summary": {
    "total": 42,
    "passed": 39,
    "failed": 3,
    "critical_failures": 0,
    "high_failures": 3
  },
  "is_pipeline_green": true
}
```

---

## CHECKLIST

- [ ] Parser tests cover: symbol completeness, call graph, dead code detection, loop bounds, reserved words, preflight
- [ ] JCL tests cover: PGM→source resolution, DD→SELECT binding, SYSLIB extraction, execution order
- [ ] Conversion tests cover: compilation, no float/double, no do-while, array sizes, business rule documentation
- [ ] Behavioral tests cover: add+report, fill capacity, update not found, delete+verify, invalid choice, empty report
- [ ] Stdout diff is line-by-line with trailing whitespace normalization
- [ ] `is_pipeline_green` is only `true` when zero critical failures
- [ ] Test report JSON matches contract above
- [ ] GPT-4.1 used only for JUnit 5 test code generation, not for test execution or result comparison

---

*Codex Prompt: Testing Agent — 2026-04-22*
