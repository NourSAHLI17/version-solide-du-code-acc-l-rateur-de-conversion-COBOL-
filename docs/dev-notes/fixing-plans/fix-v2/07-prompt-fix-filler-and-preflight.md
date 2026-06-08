# Prompt — Fix Preflight FILLER Bug and Harden Duplicate Detection

## Context

You are working on `app/parsers/cobol_parser.py`, specifically the `_preflight_check()`
method and the `_collect_data_declarations()` method. There is a critical bug: the
duplicate data name check treats `FILLER` as a regular data name, so any COBOL program
with 2 or more FILLER entries triggers a preflight halt that empties the entire parse
output.

`FILLER` is a COBOL reserved word that is explicitly allowed to appear any number of
times. It is unreferenceable — no COBOL statement can use `FILLER` as a data-name
operand. It exists solely to pad record layouts and align byte offsets. Every real-world
COBOL report program has dozens of FILLER entries.

## Current buggy code (lines 1460–1470)

```python
declarations = self._collect_data_declarations(lines)
seen_names = set()
duplicate_names = set()
for declaration in declarations:
    name = declaration["name"]
    if name in seen_names:
        duplicate_names.add(name)
    seen_names.add(name)
for name in sorted(duplicate_names):
    errors.append(f"Duplicate data name {name} detected in data declarations.")
```

## Your tasks

### Task 1 — Exclude unreferenceable names from duplicate detection

Add a class-level constant and skip logic:

```python
UNREFERENCEABLE_NAMES = {"FILLER"}
```

In the duplicate detection loop, skip any name in this set:

```python
for declaration in declarations:
    name = declaration["name"]
    if name in self.UNREFERENCEABLE_NAMES:
        continue
    if name in seen_names:
        duplicate_names.add(name)
    seen_names.add(name)
```

### Task 2 — Downgrade duplicate detection from halt to warning

The current behavior when a duplicate is found is to add it to `preflight_errors`,
which triggers `_build_preflight_failure()` and produces completely empty output.
This is too aggressive. In real COBOL, duplicate data names at different levels are
common and legal (COBOL uses qualification: `CUST-ID OF CUSTOMER-RECORD` vs
`CUST-ID OF TRANSACTION-RECORD`).

Change the behavior:
1. Remove the duplicate data name check from `_preflight_check()` entirely.
2. Move it into `_extract_warnings()` as a W007 warning with severity "medium".
3. Still skip FILLER names.

The new warning entry:

```python
# In _extract_warnings()
declarations = self._collect_data_declarations(lines)
seen_names = set()
for decl in declarations:
    name = decl["name"]
    if name in self.UNREFERENCEABLE_NAMES:
        continue
    if name in seen_names:
        _add("W007", "medium",
             f"Data name {name} declared more than once — "
             f"ensure references use qualification (OF clause)",
             symbol=name)
    seen_names.add(name)
```

### Task 3 — Also handle the _extract_symbol_table FILLER case

In `_extract_symbol_table()`, FILLER entries are currently added to the symbol table
like regular fields. This is technically correct — they occupy bytes in the record
layout and the converter needs to know they exist for byte-offset calculations. However,
they should be marked so the converter can skip them during field mapping:

In the symbol construction block, after `symbol["kind"] = self._infer_symbol_kind(symbol)`:

```python
if name == "FILLER":
    symbol["unreferenceable"] = True
```

### Task 4 — Make preflight checks non-fatal where possible

The preflight check should only halt parsing for truly unrecoverable issues:
- Undeclared PERFORM VARYING iterators → KEEP as halt (loop would crash)
- Missing FD entries → DOWNGRADE to warning (parser can still extract paragraphs)
- Duplicate data names → DOWNGRADE to warning (COBOL allows qualified references)
- Reserved word as paragraph name → DOWNGRADE to warning (unusual but parseable)

Restructure `_preflight_check()` to separate fatal errors from non-fatal warnings:

```python
def _preflight_check(self, lines, source_format):
    errors = []  # Only truly blocking issues
    warnings = []  # Issues that should be flagged but not halt parsing

    # Fatal: undeclared iterators (cannot build correct loop semantics)
    declared_names = {d["name"] for d in self._collect_data_declarations(lines)}
    for iterator in self._collect_perform_varying_iterators(lines):
        if iterator not in declared_names:
            errors.append(f"PERFORM VARYING uses undeclared index {iterator}.")

    # Non-fatal: missing FDs
    select_files = self._collect_selected_files(lines)
    fd_files = self._collect_fd_files(lines)
    missing_fds = sorted(select_files - fd_files)
    for file_name in missing_fds:
        warnings.append(f"FILE-CONTROL references {file_name} but no matching FD.")

    # Non-fatal: reserved word paragraph names
    paragraphs = self._extract_paragraph_index(lines, source_format, allow_reserved=True)
    for para in paragraphs:
        if para in self.RESERVED_WORDS and para not in self.COBOL_SCOPE_TERMINATORS:
            if para not in {"STOP-RUN", "EXIT", "GOBACK", "CONTINUE"}:
                warnings.append(f"Reserved word '{para}' used as paragraph name.")

    return errors, warnings
```

Then update the `parse()` method to handle the two-tuple return:

```python
errors, preflight_warnings = self._preflight_check(lines, source_format)
if errors:
    result = self._build_preflight_failure(lines, source_format, errors)
    result["warnings"] = [{"code": "PREFLIGHT", "severity": "high", "message": w}
                          for w in preflight_warnings]
    return result

# Continue with full parsing...
# At the end, merge preflight_warnings into the warnings list:
warnings = self._extract_warnings(lines, symbol_table, control_flow, operations)
for w in preflight_warnings:
    warnings.append({"code": "PREFLIGHT", "severity": "medium", "message": w})
```

## Constraints

- Do not remove the preflight check entirely — keep it as a guard for truly fatal issues.
- `FILLER` must never appear in duplicate detection regardless of how many times it occurs.
- The change must be backward compatible: programs that currently parse successfully
  must continue to produce identical output.
- STMTRPT.cbl, TXNPOST.cbl, and CUSTMGR.cbl from Use Case 3 must all parse
  successfully after this fix.

## Unit tests to add

```python
def test_filler_not_treated_as_duplicate():
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST-FILLER.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-REPORT-LINE.
          05 FILLER  PIC X(10) VALUE SPACES.
          05 WS-NAME PIC X(20).
          05 FILLER  PIC X(5)  VALUE SPACES.
          05 WS-AMT  PIC 9(7)V99.
          05 FILLER  PIC X(10) VALUE SPACES.
       PROCEDURE DIVISION.
       MAIN-PARA.
           DISPLAY WS-NAME.
           STOP RUN.
    """
    result = ParserLayer().parse(source)
    assert result["preflight_errors"] == []
    assert len(result["symbol_table"]) > 0
    assert "WS-NAME" in [s["name"] for s in result["symbol_table"]]
    filler_count = sum(1 for s in result["symbol_table"] if s["name"] == "FILLER")
    assert filler_count == 3

def test_duplicate_non_filler_produces_warning_not_halt():
    source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST-DUP.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 REC-A.
          05 CUST-ID PIC 9(7).
       01 REC-B.
          05 CUST-ID PIC 9(7).
       PROCEDURE DIVISION.
       MAIN-PARA.
           STOP RUN.
    """
    result = ParserLayer().parse(source)
    assert result["preflight_errors"] == []  # not a halt
    assert len(result["symbol_table"]) > 0   # parsing continued
    warning_messages = [w["message"] for w in result["warnings"]]
    assert any("CUST-ID" in m for m in warning_messages)
```
