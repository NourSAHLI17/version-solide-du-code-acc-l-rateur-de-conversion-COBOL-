# Prompt — Fix Context Enricher Wrong Fallback in Multi-Program JCL

## Context

You are working on `app/parsers/context_enricher.py`, specifically the `_map_files()`
method. There is a bug where the fallback logic silently uses the wrong JCL step's
DD bindings when no step matches the current program name.

## Current buggy code

```python
# Fallback if no exact program_name match in JCL
if not dd_bindings and jcl_manifest.get("steps"):
    for step in jcl_manifest.get("steps", []):
        # Prefer steps with actual bindings
        if step.get("dd_bindings"):
            dd_bindings = step.get("dd_bindings", {})
            break
```

## Why this is wrong

In a JCL job with multiple EXEC steps:

```
//STEP1    EXEC PGM=TXNPOST
//CUSTFILE DD   DSN=ACME.CUSTOMER.MASTER,DISP=SHR
//TXNFILE  DD   DSN=ACME.TRANSACTIONS.DAILY,DISP=SHR
//
//STEP2    EXEC PGM=STMTRPT
//CUSTFILE DD   DSN=ACME.CUSTOMER.MASTER,DISP=SHR
//TXNFILE  DD   DSN=ACME.TRANSACTIONS.DAILY,DISP=SHR
//STMTRPT  DD   DSN=ACME.REPORTS.STMTRPT(+1),DISP=...
```

When enriching STMTRPT, `_map_files()` should find STEP2 (where `pgm=STMTRPT`). But
if the program name matching fails (e.g., due to a case mismatch or a PROC indirection),
the fallback iterates through ALL steps and grabs the first one with dd_bindings —
which is STEP1 (TXNPOST). This maps STMTRPT's `STATEMENT-FILE` to TXNPOST's DD
bindings, producing a wrong `physical_dataset` with no error or warning.

## Your tasks

### Task 1 — Replace the silent fallback with explicit UNRESOLVED

Remove the fallback loop entirely. When no step matches, set every file mapping to
`UNRESOLVED` with a descriptive warning:

```python
def _map_files(self, ast, jcl_manifest):
    mappings = {}
    file_bindings = ast.get("dependencies", {}).get("file_bindings", {})
    if not file_bindings:
        return mappings

    program_name = ast.get("program_name")
    dd_bindings = {}

    if jcl_manifest and program_name:
        for step in jcl_manifest.get("steps", []):
            if step.get("pgm") == program_name:
                dd_bindings = step.get("dd_bindings", {})
                break

    # If no matching step found, mark all as UNRESOLVED
    # DO NOT fall back to another step's bindings
    if not dd_bindings and file_bindings:
        for logical_name, dd_name in file_bindings.items():
            mappings[logical_name] = {
                "logical_name": logical_name,
                "jcl_dd_name": dd_name,
                "physical_dataset": "UNRESOLVED",
                "disposition": "UNKNOWN",
                "resolution_warning": (
                    f"No JCL step found with PGM={program_name}. "
                    f"Cannot resolve physical dataset for {logical_name}."
                ),
            }
        return mappings

    # Normal mapping for matched step
    for logical_name, dd_name in file_bindings.items():
        entry = {
            "logical_name": logical_name,
            "jcl_dd_name": dd_name,
            "physical_dataset": "UNKNOWN",
            "disposition": "UNKNOWN",
        }
        if dd_name in dd_bindings:
            dd_block = dd_bindings[dd_name]
            entry["physical_dataset"] = dd_block.get("dsn", "UNKNOWN")
            entry["disposition"] = dd_block.get("disp", "UNKNOWN")
        mappings[logical_name] = entry

    return mappings
```

### Task 2 — Add case-insensitive program name matching

COBOL program names are case-insensitive. JCL PGM= values are typically uppercase.
The parser may produce the program name in mixed case. Add normalization:

```python
if jcl_manifest and program_name:
    program_name_upper = program_name.upper()
    for step in jcl_manifest.get("steps", []):
        if step.get("pgm", "").upper() == program_name_upper:
            dd_bindings = step.get("dd_bindings", {})
            break
```

### Task 3 — Also search by step DD name match when PGM name fails

Sometimes the JCL calls a PROC that internally calls the program, so `step.pgm` is
the PROC name, not the COBOL program name. Add a secondary match on DD name overlap:

```python
if not dd_bindings and jcl_manifest and file_bindings:
    # Secondary: find step whose DD names overlap with file_bindings values
    expected_dds = set(file_bindings.values())
    best_match = None
    best_overlap = 0
    for step in jcl_manifest.get("steps", []):
        step_dds = set(step.get("dd_bindings", {}).keys())
        overlap = len(expected_dds & step_dds)
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = step
    if best_match and best_overlap >= len(expected_dds) // 2:
        dd_bindings = best_match.get("dd_bindings", {})
```

This secondary match only triggers when at least half the expected DD names are found
in a step. It never falls back to a step with zero overlap.

## Unit tests

```python
def test_multi_program_jcl_correct_step():
    ast = {
        "program_name": "STMTRPT",
        "dependencies": {"file_bindings": {"CUSTOMER-FILE": "CUSTFILE"}}
    }
    jcl = {
        "steps": [
            {"step_name": "STEP1", "pgm": "TXNPOST",
             "dd_bindings": {"CUSTFILE": {"dsn": "WRONG.DATASET"}}},
            {"step_name": "STEP2", "pgm": "STMTRPT",
             "dd_bindings": {"CUSTFILE": {"dsn": "ACME.CUSTOMER.MASTER"}}},
        ]
    }
    result = ContextEnricher().enrich(ast, jcl)
    assert result["data_mappings"]["CUSTOMER-FILE"]["physical_dataset"] \
        == "ACME.CUSTOMER.MASTER"

def test_no_matching_step_produces_unresolved():
    ast = {
        "program_name": "UNKNOWN-PGM",
        "dependencies": {"file_bindings": {"MY-FILE": "MYDD"}}
    }
    jcl = {
        "steps": [
            {"step_name": "STEP1", "pgm": "TXNPOST",
             "dd_bindings": {"CUSTFILE": {"dsn": "SOME.DATASET"}}},
        ]
    }
    result = ContextEnricher().enrich(ast, jcl)
    assert result["data_mappings"]["MY-FILE"]["physical_dataset"] == "UNRESOLVED"
    assert "resolution_warning" in result["data_mappings"]["MY-FILE"]

def test_case_insensitive_program_match():
    ast = {
        "program_name": "Stmtrpt",  # mixed case from parser
        "dependencies": {"file_bindings": {"CUSTOMER-FILE": "CUSTFILE"}}
    }
    jcl = {
        "steps": [
            {"step_name": "STEP2", "pgm": "STMTRPT",  # uppercase in JCL
             "dd_bindings": {"CUSTFILE": {"dsn": "ACME.CUSTOMER.MASTER"}}},
        ]
    }
    result = ContextEnricher().enrich(ast, jcl)
    assert result["data_mappings"]["CUSTOMER-FILE"]["physical_dataset"] \
        == "ACME.CUSTOMER.MASTER"
```
