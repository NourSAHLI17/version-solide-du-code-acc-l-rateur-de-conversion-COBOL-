# Use Case 3 Test Failure — Root Cause Diagnosis

## Your symptoms

1. **CUSTMGR.cbl** — parser output comes fully generated (works).
2. **STMTRPT.cbl** — parser output is completely empty (everything is `[]`).
3. **TXNPOST.cbl** — parser output is completely empty (everything is `[]`).

The parser output for STMTRPT shows:

```json
{
  "preflight_errors": [
    "Duplicate data name FILLER detected in data declarations."
  ],
  "divisions": [],
  "symbol_table": [],
  "operations": []
}
```

---

## Root cause — TWO bugs, not one

### Bug 1: `FILLER` treated as a duplicate data name (in `_preflight_check`)

This is the **blocking bug**. Your `_preflight_check()` method collects all data
declarations, counts how many times each name appears, and if any name appears more
than once, it flags it as a duplicate and **halts the entire parse**.

Here is the code in `cobol_parser.py` lines 1460–1470:

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

The problem: **`FILLER` is a special reserved name in COBOL that is explicitly allowed
to appear multiple times.** It is not a real data name — it is a placeholder that tells
the compiler "I need this space but I will never reference this field by name." It is
impossible to reference a `FILLER` field. Every COBOL programmer uses `FILLER` dozens
of times in a single program.

In STMTRPT.cbl, after copybook expansion:
- STMTRPT source itself has **4 FILLER** fields (in `WS-TXN-DETAIL`)
- RPTHDCPY.cpy has **11 FILLER** fields (in report header/footer layouts)
- Total: **15 FILLER** entries — all legitimate, all standard COBOL

Your preflight check sees `FILLER` appear 15 times, flags it as a "duplicate data name",
and calls `_build_preflight_failure()` which sets every output array to empty.

CUSTMGR.cbl works because it does not COPY RPTHDCPY.cpy and has **zero** `FILLER` fields
in its own source. TXNPOST.cbl fails because it also COPY's RPTHDCPY.cpy (which has
11 FILLER fields) and has 5 more in its own `WS-DETAIL-LINE`.

### Bug 2: Copybook expansion may not be running before the parser

Looking at the raw parser output, it shows `"copybooks": []` in dependencies. If the
copybook resolver were running before the parser, the expanded source would contain
the copybook content (and the dependency extractor would find `COPY` references). The
fact that dependencies.copybooks is empty AND the parser sees FILLER (which only comes
from expanded copybook RPTHDCPY) suggests one of two things:

**Scenario A** — Copybooks ARE being expanded (because FILLER from RPTHDCPY is visible
to the preflight check), but the dependency extractor runs on the expanded source where
`COPY` statements have already been replaced. In this case, `dependencies.copybooks`
is empty because the `COPY` lines no longer exist in the expanded source.

**Scenario B** — Copybooks are NOT being expanded, and the parser is somehow seeing the
FILLER fields from its own source only. But STMTRPT only has 4 FILLER fields in its
own source — still enough to trigger the duplicate check.

In either scenario, **Bug 1 is the blocking issue.** Even 2 FILLER fields would trigger
the halt.

---

## Fix for Bug 1: Exclude FILLER from duplicate detection

In `_preflight_check()`, add one line:

```python
declarations = self._collect_data_declarations(lines)
seen_names = set()
duplicate_names = set()
for declaration in declarations:
    name = declaration["name"]
    if name == "FILLER":       # ← ADD THIS LINE
        continue                # ← ADD THIS LINE
    if name in seen_names:
        duplicate_names.add(name)
    seen_names.add(name)
```

**Why this is correct:** The COBOL standard (ISO 1989) explicitly states that `FILLER`
is a reserved word that may appear in any number of data description entries. No COBOL
compiler treats multiple `FILLER` entries as an error. The word `FILLER` is specifically
defined to be unreferenceable — it exists only to pad record layouts and align fields
to specific byte offsets.

**Extended fix:** There are other names that should also be excluded from duplicate
detection. Some COBOL dialects allow the level-number alone (no name) to define an
anonymous filler. The IBM Enterprise COBOL compiler also permits unnamed group items
in certain contexts. The safest fix is:

```python
UNREFERENCEABLE_NAMES = {"FILLER"}

for declaration in declarations:
    name = declaration["name"]
    if name in UNREFERENCEABLE_NAMES:
        continue
    if name in seen_names:
        duplicate_names.add(name)
    seen_names.add(name)
```

---

## Fix for Bug 2: Preserve copybook dependency info after expansion

If the copybook resolver runs before the parser (which is correct), the expanded source
no longer contains `COPY` statements — they have been replaced by the copybook content.
This means `_extract_dependencies()` cannot find `COPY` lines to extract copybook names.

Two solutions:

**Option A (recommended):** Pass the `CopyResolutionResult.resolved_copybooks` list
into the parser as additional context, and merge it into the dependencies output:

```python
def parse(self, source_code: str, resolved_copybooks: list = None) -> Dict:
    ...
    dependencies = self._extract_dependencies(lines, operations)
    if resolved_copybooks:
        for cb in resolved_copybooks:
            if cb["name"] not in dependencies["copybooks"]:
                dependencies["copybooks"].append(cb["name"])
    ...
```

**Option B:** The copybook resolver inserts source-map comments like
`* >>> COPY CUSTCOPY EXPANDED FROM ./copybooks/CUSTCOPY.cpy <<<`. The parser can
detect these comments and extract the copybook names from them. This requires modifying
the comment-stripping logic to capture these markers before discarding them.

---

## Why CUSTMGR works but STMTRPT and TXNPOST don't

| Program | Own FILLER count | Copybook FILLER count | Total | Preflight result |
|---|---|---|---|---|
| CUSTMGR.cbl | 0 | 0 (no RPTHDCPY) | 0 | ✅ Pass |
| STMTRPT.cbl | 4 | 11 (RPTHDCPY) | 15 | ❌ Halt |
| TXNPOST.cbl | 5 | 11 (RPTHDCPY) | 16 | ❌ Halt |

CUSTMGR only COPY's `CUSTCOPY` and `ERRORCOPY` — neither contains FILLER. STMTRPT and
TXNPOST both COPY `RPTHDCPY` which has 11 FILLER fields in its report header/footer
layouts. This is completely standard COBOL — every report-oriented program uses FILLER
extensively in print line layouts.

---

## Testing the fix

After applying the FILLER exclusion, re-run all three programs:

1. **STMTRPT.cbl** should produce a full parse with:
   - 4 divisions (IDENTIFICATION, ENVIRONMENT, DATA, PROCEDURE)
   - 11 paragraphs (0000-MAIN through 2300-WRITE-CUSTOMER-SUMMARY)
   - ~70 symbols in the symbol table (including expanded copybook fields)
   - Multiple STRING operations, READ/WRITE/START operations
   - Control flow with PERFORM UNTIL loop and nested IF branches

2. **TXNPOST.cbl** should produce a full parse with:
   - 4 divisions
   - 12 paragraphs (0000-MAIN through 9100-WRITE-ERROR-LINE)
   - Multiple file operations (3 files: CUSTOMER-FILE, TRANSACTION-FILE, REPORT-FILE)
   - REWRITE operations for both customer and transaction records
   - ADD operations for accumulators

3. **CUSTMGR.cbl** should continue to work as before — no regression.

---

## Additional issue: the project files are correct

I verified every file in the uploaded zip:
- All 4 copybooks (`CUSTCOPY.cpy`, `TXNCOPY.cpy`, `ERRORCOPY.cpy`, `RPTHDCPY.cpy`)
  are syntactically valid COBOL fixed format with correct column alignment
- All 3 COBOL source files are syntactically valid
- The JCL file (`ACMEPOST.jcl`) is valid JCL with correct DD bindings
- Data files are present and correctly formatted

**The project files have no errors. The issue is entirely in the parser code.**
