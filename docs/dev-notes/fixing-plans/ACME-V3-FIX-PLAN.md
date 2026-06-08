# ACME Bank v3 — Complete Fix Plan

**Goal**: Take the COBOL→Java pipeline from "3 of 6 programs convert, with semantic bugs" to "6 of 6 programs convert correctly and pass behavioral tests against real data."

**Approach**: Fix in dependency order. Source bugs first (cheap, unblock testing of everything else), then parser bugs (block 50% of programs), then converter bugs (silent data corruption), then analyzer + scoring (quality).

**Target outcome**: All 6 programs parse → analyze with real LLM output → convert to Java → compile with javac → run against the .dat files → produce output matching the COBOL baseline within tolerance.

---

## Execution order at a glance

| Phase | Fixes | Duration | Blocks |
|---|---|---|---|
| **Phase A — Source cleanup** | F1–F7 | 1-2 hours | Everything downstream |
| **Phase B — Parser fixes** | F8–F11 | 4-6 hours | 50% of programs converting |
| **Phase C — Converter correctness** | F12–F15 | 8-12 hours | Output being trustworthy |
| **Phase D — Analyzer quality** | F16–F19 | 4-6 hours | Conversion quality |
| **Phase E — Scoring & validation** | F20–F22 | 3-4 hours | Honest scores |
| **Phase F — End-to-end verification** | F23–F25 | 2-3 hours | Confidence |

**Total estimated effort**: 22–33 hours of focused work.

---

# PHASE A — Source Code Cleanup (do first, unblocks everything)

These are bugs in my own COBOL that have nothing to do with the pipeline. Even with a perfect parser, these would fail. Fix them first so we have a clean baseline to test the pipeline against.

---

## Fix F1 — RPTCOPY2.cpy line 11 exceeds column 72

**Severity**: HIGH — silently corrupts the copybook, cascades to LOANEVAL, RECOVRY, RPTMONTH, RISKSCOR

**File**: `/acme-bank-v3/copybooks/RPTCOPY2.cpy`

**Problem**:
```cobol
LINE 11:           05 RPT-BANK-NAME        PIC X(25)     VALUE 'ACME BANK TUNISIE S.A.'.
                                                                          ^col 78 ^col 79
```
Line is 79 chars. COBOL fixed-format truncates at column 72. The closing `'.'` is dropped, leaving an open string literal. GnuCOBOL then emits cascading errors (`continuation character expected`, `syntax error unexpected PAGE`, etc.) for the rest of the file.

**Fix**: Either shorten the literal OR re-align the line so it fits in columns 12-72.

**Cursor prompt**:
```
Open /acme-bank-v3/copybooks/RPTCOPY2.cpy. On line 11 the value 'ACME BANK TUNISIE S.A.' makes the line 79 columns long, which exceeds COBOL fixed-format column 72 and breaks the entire copybook. Change the line so it ends at or before column 72. Use VALUE 'ACME BANK SA'. Keep PIC X(25). Then verify by running awk 'length > 72 { print NR": "length }' on the file and confirm zero lines exceed 72 columns.
```

**Verification**:
```bash
awk 'length > 72 { print NR": "length }' /acme-bank-v3/copybooks/RPTCOPY2.cpy
# Should output nothing
```

---

## Fix F2 — RPTCOPY2.cpy lines 46-48 broken continuation indicator

**Severity**: HIGH — same cascade impact as F1

**File**: `/acme-bank-v3/copybooks/RPTCOPY2.cpy`

**Problem**:
```cobol
LINE 45:        05 FILLER               PIC X(137)
LINE 46:           VALUE '=========================================
LINE 47:        -         '========================================
LINE 48:        -         '====================='.
```
The continuation indicator `-` must be in column 7 exactly, but the current indentation puts it somewhere else. Fixed-format COBOL is unforgiving about this.

**Fix**: Either move `-` to exactly column 7, OR replace the multi-line continuation with a simpler construct that builds the separator differently.

**Cursor prompt**:
```
Open /acme-bank-v3/copybooks/RPTCOPY2.cpy. Look at the RPT-SEPARATOR and RPT-THIN-SEP definitions (around lines 44-54) that use multi-line string continuation with '-' in column 7. The current code is fragile and breaks if column 7 is not exact.

Replace both 01-level definitions with a simpler approach using PIC X(137) VALUE ALL '='. and PIC X(137) VALUE ALL '-'. respectively. This produces the same runtime effect (a row of equals or dashes filling 137 columns) without needing continuation lines. Example:

       01 RPT-SEPARATOR.
          05 FILLER               PIC X(137) VALUE ALL '='.

       01 RPT-THIN-SEP.
          05 FILLER               PIC X(137) VALUE ALL '-'.

Apply the same simplification anywhere else in the file that uses '-' continuation.
```

**Verification**:
```bash
cd /tmp && cp /acme-bank-v3/copybooks/RPTCOPY2.cpy .
# create a minimal test wrapper
cat > test_rptcopy.cbl << 'EOF'
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTRPT.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY RPTCOPY2.
       PROCEDURE DIVISION.
           DISPLAY RPT-SEPARATOR.
           STOP RUN.
EOF
cobc -x -std=ibm-strict test_rptcopy.cbl
# Should compile with no errors about RPTCOPY2
```

---

## Fix F3 — CALCFEE.cbl missing SPECIAL-NAMES DECIMAL-POINT IS COMMA

**Severity**: HIGH — fails to compile

**File**: `/acme-bank-v3/src/CALCFEE.cbl`

**Problem**: Lines 31-40 use European-format decimals (`VALUE 1,5000`) but no `SPECIAL-NAMES` declaration. Compiler reads `1,5000` as two values, errors with `only level 88 items may have multiple values`.

**Fix**: Add SPECIAL-NAMES to CONFIGURATION SECTION.

**Cursor prompt**:
```
Open /acme-bank-v3/src/CALCFEE.cbl. Find the CONFIGURATION SECTION (around line 22-24). It currently has SOURCE-COMPUTER and OBJECT-COMPUTER but no SPECIAL-NAMES. The program uses comma as decimal separator (e.g. VALUE 1,5000 on line 31) which requires a SPECIAL-NAMES declaration.

Add immediately after OBJECT-COMPUTER. IBM-MAINFRAME.:

       SPECIAL-NAMES.
           DECIMAL-POINT IS COMMA.

Then verify by running: cobc -m -std=ibm-strict CALCFEE.cbl 2>&1 | grep -i error
There should be no errors about "multiple values" or "level 88".
```

**Verification**:
```bash
cd /tmp && cp /acme-bank-v3/src/CALCFEE.cbl .
cobc -m -std=ibm-strict CALCFEE.cbl 2>&1 | grep -i "error\|warning" | head -5
# Should show no errors about decimal/multiple values
```

---

## Fix F4 — CHKAML.cbl needs same SPECIAL-NAMES check

**Severity**: MEDIUM — verify; may or may not be needed

**File**: `/acme-bank-v3/src/CHKAML.cbl`

**Problem**: CHKAML may use comma decimals — needs verification.

**Cursor prompt**:
```
Open /acme-bank-v3/src/CHKAML.cbl. Search for any VALUE clauses containing a comma (e.g. VALUE 10000,00 or similar). If found AND there is no SPECIAL-NAMES. DECIMAL-POINT IS COMMA. declaration in CONFIGURATION SECTION, add it after OBJECT-COMPUTER:

       SPECIAL-NAMES.
           DECIMAL-POINT IS COMMA.

If no comma-decimal literals exist, do nothing. Verify with:
grep -n "VALUE .*[0-9],[0-9]" /acme-bank-v3/src/CHKAML.cbl
```

**Verification**:
```bash
grep -n "VALUE .*[0-9],[0-9]" /acme-bank-v3/src/CHKAML.cbl
# If output exists, SPECIAL-NAMES must be present
grep -A1 "SPECIAL-NAMES" /acme-bank-v3/src/CHKAML.cbl
```

---

## Fix F5 — LOANEVAL.cbl missing WS-GTR-FS in ERRCOPY2

**Severity**: MEDIUM — referenced but not defined, causes compile error

**File**: `/acme-bank-v3/copybooks/ERRCOPY2.cpy`

**Problem**: LOANEVAL references `WS-GTR-FS` (guarantee file status) but ERRCOPY2 only defines status variables for CUST, LOAN, COL, SCR, RPT, LOG, REJ, OUT. WS-GTR-FS is missing.

**Fix**: Add WS-GTR-FS to ERRCOPY2 alongside the other file status variables.

**Cursor prompt**:
```
Open /acme-bank-v3/copybooks/ERRCOPY2.cpy. Find the FILE-STATUS-BLOCK 01-level (around line 20). After the WS-COL-FS definition and its 88-levels, add:

          05 WS-GTR-FS            PIC X(2)      VALUE SPACES.
             88 GTR-FS-OK         VALUE '00'.
             88 GTR-FS-EOF        VALUE '10'.
             88 GTR-FS-NOTFOUND   VALUE '23'.

Keep all existing file status variables unchanged.

Then verify the field appears in expansion by running grep:
grep "WS-GTR-FS\|GTR-FS-OK" /acme-bank-v3/copybooks/ERRCOPY2.cpy
```

**Verification**:
```bash
grep -c "WS-GTR-FS" /acme-bank-v3/copybooks/ERRCOPY2.cpy
# Should output 1
```

---

## Fix F6 — LOANEVAL.cbl: COPY ERRCOPY2 ordering

**Severity**: HIGH — fields not visible when referenced

**File**: `/acme-bank-v3/src/LOANEVAL.cbl`

**Problem**: LOANEVAL uses `WS-LOAN-FS`, `WS-CUST-FS`, etc. in SELECT statements (FILE-CONTROL section), but the `COPY ERRCOPY2.` happens later in WORKING-STORAGE. The variables need to be visible BEFORE the SELECT statements reference them.

**Actually**: re-checking COBOL semantics — FILE STATUS variables in SELECT are resolved at runtime against the WORKING-STORAGE definitions, so order shouldn't matter in standard COBOL. However, some compilers (and the parser) need the symbol table populated first. Best practice is to declare file-status variables before the FD entries that reference them.

**Fix**: Reorder so `COPY ERRCOPY2.` is the first thing in WORKING-STORAGE SECTION, before any other declarations.

**Cursor prompt**:
```
Open /acme-bank-v3/src/LOANEVAL.cbl. Find the WORKING-STORAGE SECTION header. Move the line "COPY ERRCOPY2." so it appears immediately after WORKING-STORAGE SECTION., before any other 01-level declarations and before COPY RPTCOPY2.

Old structure:
       WORKING-STORAGE SECTION.
       COPY ERRCOPY2.
       COPY RPTCOPY2.
       01 WS-SQL-VARS. ...

Should become (verify it's already this order, but enforce explicitly):
       WORKING-STORAGE SECTION.
      *--- File status variables must come first for FD compatibility ---
       COPY ERRCOPY2.
      *--- Add WS-GTR-FS inline if not added to ERRCOPY2 yet ---
       COPY RPTCOPY2.
       01 WS-SQL-VARS. ...

Apply the same reordering to RECOVRY.cbl, RISKSCOR.cbl, RPTMONTH.cbl — ERRCOPY2 should always be the first COPY in WORKING-STORAGE.
```

**Verification**:
```bash
for f in /acme-bank-v3/src/*.cbl; do
    echo "=== $f ==="
    grep -n "WORKING-STORAGE\|^       COPY " "$f" | head -8
done
```

---

## Fix F7 — Truncate all comment lines exceeding column 72

**Severity**: LOW — comments are harmless to compilation but produce false-positive warnings

**Files**: All `.cpy` and `.cbl` files

**Problem**: 13 comment lines exceed column 72 (listed in the analysis doc §4.1).

**Cursor prompt**:
```
For each of these files, find any line that exceeds 72 characters and wrap or shorten so all lines fit in columns 1-72:

- /acme-bank-v3/copybooks/COLLATCOPY.cpy (line 5)
- /acme-bank-v3/copybooks/LOANCOPY.cpy (line 7)
- /acme-bank-v3/copybooks/RECOVCOPY.cpy (line 9)
- /acme-bank-v3/copybooks/RPTCOPY2.cpy (line 11 — already fixed in F1)
- /acme-bank-v3/src/CALCFEE.cbl (line 7)
- /acme-bank-v3/src/LOANEVAL.cbl (lines 8, 15, 217)
- /acme-bank-v3/src/RISKSCOR.cbl (lines 3, 6, 136)
- /acme-bank-v3/src/RPTMONTH.cbl (lines 3, 111)

For comment lines (start with * in column 7), simply shorten the text or break across two comment lines. Preserve the comment marker pattern "      *".

Run this check after to verify zero lines exceed 72:
for f in /acme-bank-v3/copybooks/*.cpy /acme-bank-v3/src/*.cbl; do
    awk 'length > 72 { print FILENAME":"NR" ["length"]" }' "$f"
done
Should output nothing.
```

**Verification**:
```bash
for f in /acme-bank-v3/copybooks/*.cpy /acme-bank-v3/src/*.cbl; do
    awk 'length > 72 { print FILENAME":"NR" ["length"]" }' "$f"
done
# Should produce zero output
```

---

### Phase A completion check

After F1-F7, run this to confirm all programs compile with GnuCOBOL:
```bash
cd /acme-bank-v3
mkdir -p /tmp/compile_test
cp copybooks/*.cpy /tmp/compile_test/
cp src/*.cbl /tmp/compile_test/
cd /tmp/compile_test
echo "=== Main programs (should produce executables) ==="
for prog in LOANEVAL RECOVRY RISKSCOR RPTMONTH; do
    echo "--- $prog ---"
    cobc -x -std=ibm-strict $prog.cbl 2>&1 | head -3
done
echo "=== Sub-programs (should compile as modules) ==="
for prog in CHKAML CALCFEE; do
    echo "--- $prog ---"
    cobc -m -std=ibm-strict $prog.cbl 2>&1 | head -3
done
```

Phase A is done when GnuCOBOL produces zero errors for any of the 6 programs.

---

# PHASE B — Parser Fixes (unblocks 50% of programs)

Now that the source is clean, fix the two parser bugs that cause valid COBOL to be rejected.

---

## Fix F8 — Parser must accept `SD` as a valid file description

**Severity**: HIGH — blocks LOANEVAL + RECOVRY

**Location**: Wherever the parser validates that every `SELECT` has a matching `FD`. Likely in the file `cobol_parser.py` or similar.

**Problem**: The parser searches only for `FD <name>` and complains "no matching FD entry was found" when it sees `SD <name>`. But SORT files use `SD` (Sort Description), not `FD`. This is standard COBOL since 1968.

**Fix**: Make the parser accept either `FD` or `SD` as the file-description entry.

**Cursor prompt**:
```
Open the COBOL parser source file (most likely cobol_parser.py or parser.py in the backend). Search for the code that validates SELECT entries have matching FD declarations. The error message text "no matching FD entry was found" is a good search anchor.

Currently the code likely does something like:
    if select_name not in fd_names:
        errors.append(f"FILE-CONTROL references {select_name} but no matching FD entry was found.")

Modify it to:
1. Parse both FD and SD entries from the FILE SECTION
2. Merge them into a single set/dict before validation
3. The validation should accept either as a match

Example fix:
    # Build complete file description set (both FD and SD)
    file_descriptions = {}
    for entry in file_section.findall(r"^\s+(FD|SD)\s+(\S+)", re.MULTILINE):
        kind, name = entry
        file_descriptions[name] = kind
    
    for select_name in select_names:
        if select_name not in file_descriptions:
            errors.append(f"FILE-CONTROL references {select_name} but no FD or SD entry was found.")

Add a marker field to each parsed file so downstream code knows whether it was FD (regular) or SD (sort work):
    {"name": "SORT-WORK-FILE", "kind": "SD", "fields": [...], ...}

The analyzer and converter need to know an SD file is a sort work area, not a persistent file, so they generate Java differently (in-memory List<T> with Comparator, not file I/O).

Add a unit test:
def test_parser_accepts_sd_for_sort_files():
    src = '''
           IDENTIFICATION DIVISION.
           PROGRAM-ID. TESTSORT.
           ENVIRONMENT DIVISION.
           INPUT-OUTPUT SECTION.
           FILE-CONTROL.
               SELECT SORT-WORK ASSIGN TO "SORTWK.dat".
           DATA DIVISION.
           FILE SECTION.
           SD SORT-WORK.
           01 SORT-REC.
              05 SORT-KEY PIC 9(4).
           WORKING-STORAGE SECTION.
           PROCEDURE DIVISION.
           MAIN.
               SORT SORT-WORK ON ASCENDING KEY SORT-KEY
                   INPUT PROCEDURE LOAD-INPUT
                   OUTPUT PROCEDURE WRITE-OUTPUT.
               STOP RUN.
           LOAD-INPUT. EXIT.
           WRITE-OUTPUT. EXIT.
    '''
    result = parse(src)
    assert not any("no matching FD" in e for e in result.errors)
    assert any(f["name"] == "SORT-WORK" and f["kind"] == "SD" for f in result.files)
```

**Verification**: After this fix, re-running `LOANEVAL.cbl` and `RECOVRY.cbl` through the pipeline should not produce "no matching FD" errors.

---

## Fix F9 — Parser must register `INDEXED BY <name>` as an index declaration

**Severity**: HIGH — blocks LOANEVAL + RPTMONTH

**Location**: The parser's symbol table builder, wherever it processes WORKING-STORAGE SECTION data items.

**Problem**: When the parser encounters `05 WS-CL-ENTRY OCCURS 4 TIMES INDEXED BY CL-IDX.`, it registers `WS-CL-ENTRY` as a data name but ignores the `INDEXED BY CL-IDX` part. Later, when the procedure division does `PERFORM VARYING CL-IDX FROM 1 BY 1`, the parser says "undeclared index."

**Fix**: When processing `OCCURS ... INDEXED BY <name1> [<name2> ...]`, register each `<nameN>` in the symbol table as an identifier of kind "index."

**Cursor prompt**:
```
Open the COBOL parser source file. Search for where OCCURS clauses are processed. You're looking for code that handles patterns like "OCCURS n TIMES" or "OCCURS n TIMES INDEXED BY <name>".

Currently the parser probably extracts the data name and the OCCURS count but ignores INDEXED BY. Add this logic:

1. When parsing a data item that has OCCURS ... INDEXED BY, extract the list of index names:
   regex: r"OCCURS\s+\d+\s+TIMES\s+(?:INDEXED\s+BY\s+([A-Z][A-Z0-9-]*(?:\s+[A-Z][A-Z0-9-]*)*))?"

2. For each extracted index name, register it in the symbol table:
   for index_name in indexed_by_names:
       symbol_table[index_name] = {
           "kind": "index",
           "parent_table": data_item_name,
           "occurs_count": occurs_count
       }

3. Modify the PERFORM VARYING validator to accept "index" identifiers as valid varying targets, alongside numeric data items.

Example: when validating PERFORM VARYING SECTOR-IDX FROM 1 BY 1, the validator should:
   - look up SECTOR-IDX in symbol_table
   - if kind == "index" OR kind == "numeric_data_item", accept
   - else flag as "undeclared index"

Add a unit test:
def test_parser_recognizes_indexed_by():
    src = '''
           IDENTIFICATION DIVISION.
           PROGRAM-ID. TESTIDX.
           DATA DIVISION.
           WORKING-STORAGE SECTION.
           01 WS-TABLE.
              05 WS-ENTRY OCCURS 10 TIMES INDEXED BY MY-IDX.
                 10 WS-VALUE PIC 9(4).
           PROCEDURE DIVISION.
           MAIN.
               PERFORM VARYING MY-IDX FROM 1 BY 1 UNTIL MY-IDX > 10
                   DISPLAY WS-VALUE(MY-IDX)
               END-PERFORM.
               STOP RUN.
    '''
    result = parse(src)
    assert not any("undeclared index" in e for e in result.errors)
    assert result.symbols["MY-IDX"]["kind"] == "index"
```

**Verification**: After this fix, LOANEVAL and RPTMONTH should not produce "undeclared index" errors.

---

## Fix F10 — Parser should handle COPY statement properly inside FD

**Severity**: MEDIUM — may surface only after F8/F9 fixed

**Location**: Parser's COPY statement handler

**Problem**: When `FD SCORE-FILE` includes `COPY SCORECOPY.`, the parser needs to expand SCORECOPY inline so that `RECORD KEY IS SCR-RESULT-ID` (declared in the SELECT) can be validated against the FD's record fields.

**Cursor prompt**:
```
Open the COBOL parser. Find the COPY statement handler. Verify that when a COPY appears inside an FD (file description) block, the copybook's 01-level record is included in the FD's record list, AND that record key fields declared in the SELECT can be resolved against the expanded copybook.

Test case:
       SELECT SCORE-FILE
           ASSIGN TO "SCORFILE.dat"
           ORGANIZATION IS INDEXED
           ACCESS MODE IS DYNAMIC
           RECORD KEY IS SCR-RESULT-ID    ← This field comes from SCORECOPY
           FILE STATUS IS WS-SCR-FS.
       ...
       FD SCORE-FILE RECORD CONTAINS 229 CHARACTERS.
       COPY SCORECOPY.                    ← Expands here, defines SCR-RESULT-ID

The parser must:
1. Note the RECORD KEY name during SELECT parsing
2. When the FD is parsed, expand any COPY statements inside it
3. Validate that the RECORD KEY name appears among the expanded fields
4. Add a regression test for this exact pattern

If currently the parser flags "SCR-RESULT-ID is not defined" because it can't see the field, this is the bug to fix.
```

**Verification**: Re-running LOANEVAL.cbl through the pipeline after F8/F9 should no longer report `SCR-RESULT-ID is not defined`.

---

## Fix F11 — Parser column-awareness verification

**Severity**: MEDIUM — defensive check

**Location**: Parser's source reader / column handler

**Problem**: We don't know whether the parser respects COBOL fixed-format column rules. If it reads beyond column 72, it would silently accept code that won't compile on a real mainframe. If it stops at column 72, it might miss things if our source has accidental column overruns (which F1-F7 just fixed).

**Cursor prompt**:
```
Open the COBOL parser. Find the source reader/tokenizer. Check whether it:
1. Treats columns 1-6 as sequence area (skipped)
2. Treats column 7 as indicator (* for comment, - for continuation, / for form feed)
3. Treats columns 8-72 as code (areas A and B)
4. Treats columns 73-80 as identification area (ignored)

If the parser reads the entire line without column awareness, add a column_aware=True option (it's already mentioned in the parser output as "paragraph_source_extraction: column_aware" — verify this is actually enforced).

If the parser silently accepts code beyond column 72, fix it to truncate at column 72. Then emit a warning (not error) when a line was truncated, so users know to shorten.

Add a unit test:
def test_parser_truncates_at_column_72():
    # Line that has actual code past column 72
    src = "       MOVE 'A' TO X-VAR-WITH-VERY-LONG-NAME-EXCEEDING-COLUMN-72."
    # X-VAR-WITH-VERY-LONG-NAME-EXCEEDING-COLUMN-72 ends past col 72
    result = parse(src)
    assert any("line exceeds column 72" in w for w in result.warnings)
```

**Verification**: Run the parser with a deliberately-overlong line and confirm it either truncates or warns.

---

### Phase B completion check

```bash
# After F8-F11, re-upload acme-bank-v3 to the pipeline
# Expected outcome:
# - LOANEVAL.cbl: Parse Done (no more "SD" or "INDEXED BY" errors)
# - RECOVRY.cbl: Parse Done
# - RPTMONTH.cbl: Parse Done
# - RISKSCOR.cbl: Parse Done (was already)
# - CHKAML.cbl: Parse Done
# - CALCFEE.cbl: Parse Done
```

If any program still fails to parse, the error message will reveal what other construct is unsupported. Add those to a follow-up patch.

---

# PHASE C — Converter Correctness (silent data corruption)

These bugs cause the generated Java to **compile cleanly but produce garbage output**. The most dangerous category because they pass the build but fail at runtime.

---

## Fix F12 — Fix byte offset calculation in record parsing (CRITICAL)

**Severity**: CRITICAL — every record will be parsed wrong

**Location**: The converter's code that generates `parseLoanRecord`, `parseCustomerRecord`, etc. from copybook layouts.

**Problem**: The generated Java reads `loanStatus` from positions `[36:38]` when the actual COBOL field is at `[31:33]`. This causes silent data corruption — Java compiles, runs, produces results, but the results are wrong.

**Root cause**: The offset calculator probably has a bug in how it handles one specific PIC clause. Most likely candidates:
1. `PIC 9(n)V9(m)` — the V is implicit (0 bytes) but maybe being counted as 1
2. `PIC S9(n)` — the S is implicit sign (0 bytes for DISPLAY usage) but maybe counted as 1
3. Group items being double-counted (parent group + children)
4. FILLER fields being skipped instead of counted

**Cursor prompt**:
```
Open the converter source that generates field offset calculations. Search for code that walks copybook 01-level records and computes byte positions.

Currently the bug produces:
  rec.loanStatus = parseString(line, 36, 38);   // WRONG - should be [31:33]
  rec.loanClass = parseString(line, 38, 39);    // WRONG - should be [33:34]

The correct LOANCOPY layout is:
[ 0:10]  LOAN-ID            PIC 9(10)            -- 10 bytes
[10:18]  LOAN-CUST-ID       PIC 9(8)             -- 8 bytes
[18:28]  LOAN-ACCT-ID       PIC 9(10)            -- 10 bytes
[28:31]  LOAN-TYPE          PIC X(3)             -- 3 bytes
[31:33]  LOAN-STATUS        PIC X(2)             -- 2 bytes
[33:34]  LOAN-CLASS         PIC X(1)             -- 1 byte
[34:47]  LOAN-ORIGINAL-AMT  PIC 9(11)V99         -- 13 bytes (11 + 2, V is implicit)
[47:60]  LOAN-OUTSTANDING   PIC 9(11)V99         -- 13 bytes
[60:69]  LOAN-MONTHLY-PMT   PIC 9(7)V99          -- 9 bytes (7 + 2)
[69:75]  LOAN-INTEREST-RATE PIC 9(2)V9(4)        -- 6 bytes (2 + 4)
[75:76]  LOAN-RATE-TYPE     PIC X(1)             -- 1 byte
[76:84]  LOAN-START-DATE    PIC 9(8)
[84:92]  LOAN-MATURITY-DATE PIC 9(8)
[92:100] LOAN-LAST-PMT-DATE PIC 9(8)
[100:108] LOAN-NEXT-PMT-DATE PIC 9(8)
[108:112] LOAN-PAYMENTS-MADE PIC 9(4)
[112:116] LOAN-PAYMENTS-TOTAL PIC 9(4)
[116:120] LOAN-DAYS-PAST-DUE PIC 9(4)
[120:123] LOAN-MISSED-PMTS PIC 9(3)
[123:129] LOAN-PROVISION-RATE PIC 9(2)V9(4)      -- 6 bytes
[129:140] LOAN-PROVISION-AMT PIC 9(9)V99         -- 11 bytes
[140:143] LOAN-COLLATERAL-TYPE PIC X(3)
[143:156] LOAN-COLLATERAL-VAL PIC 9(11)V99       -- 13 bytes
[156:164] LOAN-GUARANTOR-ID PIC 9(8)
[164:168] LOAN-BRANCH-CODE PIC 9(4)
[168:174] LOAN-OFFICER-ID PIC 9(6)
[174:214] LOAN-PURPOSE PIC X(40)
[214:222] LOAN-RESTRUCTURE-DT PIC 9(8)
[222:230] LOAN-WRITE-OFF-DT PIC 9(8)
[230:238] LOAN-FILLER PIC X(8)

Total: 238 bytes.

Tasks:
1. Find the function that computes byte size from a PIC clause. Verify it returns:
   - PIC X(n) → n
   - PIC 9(n) → n
   - PIC 9(n)V9(m) → n+m (V contributes 0 bytes)
   - PIC 9(n)V99 → n+2 (V contributes 0 bytes, "99" = 2 digits)
   - PIC S9(n) → n (S contributes 0 bytes in default DISPLAY usage)
   - PIC ZZ,ZZ9 → count Z+9+, (comma is a literal char in display fields)
   Write unit tests for each of these patterns.

2. Find the function that walks the record and accumulates offsets. Verify that:
   - It iterates fields in declaration order
   - It uses CUMULATIVE offset (each field starts where the previous ended)
   - It correctly handles GROUP items (the parent is the SUM of its children, NOT an independent block)
   - It correctly handles FILLER (FILLER fields take up space, just don't get a name)

3. Re-generate parseLoanRecord for RISKSCOR and verify against actual data:
   Use this Python helper to compute expected offsets from LOANCOPY.cpy and compare to the Java output.
   
4. Add an integration test:
   - Take the actual LOANFILE.dat sample data
   - Run the generated Java parseLoanRecord on the first 5 records
   - Verify loanStatus is "AC", "RS", "LT", "SD", or "WO" (valid status codes)
   - Verify loanClass is "1", "2", "3", or "4"
   - If any record has loanStatus = "00" or loanClass = " " (space), the offsets are wrong.
```

**Verification**:
```bash
# After regenerating, take the first line of LOANFILE.dat and verify:
HEAD=$(head -1 /acme-bank-v3/data/LOANFILE.dat)
echo "Position 31-33 (LOAN-STATUS):  ${HEAD:31:2}"
echo "Position 33-34 (LOAN-CLASS):   ${HEAD:33:1}"
# Should show valid status (AC/RS/LT/SD/WO) and valid class (1/2/3/4)
```

---

## Fix F13 — REWRITE must preserve all fields, not just modified ones

**Severity**: CRITICAL — destroys the data file

**Location**: Converter logic for `REWRITE` statement

**Problem**: When COBOL says `REWRITE LOAN-RECORD`, it writes back the entire 238-byte record. The current Java converter reads only the fields the program uses (8 of 40), then on REWRITE pads the unused positions with spaces — corrupting LOANFILE for subsequent reads.

**Cursor prompt**:
```
Open the converter source that handles the REWRITE statement. The current generated code looks like:

private String formatLoanRecord(LoanRecord rec) {
    StringBuilder sb = new StringBuilder();
    sb.append(String.format("%010d", rec.loanId));
    sb.append(String.format("%08d", rec.loanCustId));
    sb.append(repeat(" ", 18));        // ← drops ACCT-ID, TYPE
    ...
}

This is wrong. The COBOL REWRITE writes back the entire record including fields the program didn't touch. Subsequent programs (RPTMONTH reads after RISKSCOR rewrites) need those fields preserved.

Fix: Use a copy-then-modify pattern.

1. The LoanRecord class should hold the original line (raw bytes) AND the parsed fields:

   private static class LoanRecord {
       String rawLine;              // ← Original 238-byte line, preserved
       int loanId;                  // parsed for use
       int loanCustId;
       String loanStatus;
       String loanClass;
       BigDecimal loanOutstanding;
       int loanDaysPastDue;
       BigDecimal loanProvisionRate;
       BigDecimal loanProvisionAmt;
   }

2. When parsing, store rawLine alongside parsed fields:
   rec.rawLine = line;  // entire 238 bytes
   rec.loanStatus = parseString(line, 31, 33);
   ...

3. When REWRITE happens, start from rawLine and selectively overwrite only modified field positions:
   
   private String formatLoanRecord(LoanRecord rec) {
       char[] chars = rec.rawLine.toCharArray();
       
       // Overwrite only the fields RISKSCOR modifies:
       overwrite(chars, 33, 34, rec.loanClass);
       overwrite(chars, 123, 129, formatDecimal(rec.loanProvisionRate, 2, 4));
       overwrite(chars, 129, 140, formatDecimal(rec.loanProvisionAmt, 9, 2));
       
       return new String(chars);
   }
   
   private void overwrite(char[] chars, int start, int end, String value) {
       int len = end - start;
       String padded = value.length() >= len ? value.substring(0, len) : padLeft(value, len);
       for (int i = 0; i < len; i++) {
           chars[start + i] = padded.charAt(i);
       }
   }

4. The converter must:
   - Detect which fields the program WRITES (assignments, MOVE TO, etc.)
   - Only overwrite those positions in REWRITE output
   - Preserve everything else from rawLine

5. Add an integration test:
   - Read the first LOAN record
   - Modify LOAN-CLASS via the Java
   - Run REWRITE
   - Read the file back
   - Verify all 40 fields are preserved except LOAN-CLASS
```

**Verification**:
```bash
# After fix, the test should pass:
# 1. Run RISKSCOR.java once
# 2. Compare LOANFILE.dat with baseline (only LOAN-CLASS and PROVISION fields should differ)
# 3. md5sum of bytes 0-122 + bytes 140-end should be unchanged
```

---

## Fix F14 — Sub-program calls must use the Java method signature

**Severity**: HIGH — currently sub-programs are generated as classes but not called

**Location**: Converter logic for `CALL '<name>' USING <params>`

**Problem**: LOANEVAL has `CALL 'CHKAML' USING WS-AML-REQUEST WS-AML-RESPONSE`. The pipeline generated `ChkAmlService` as a Java class but I don't see where LOANEVAL's Java instantiates and calls it. Since LOANEVAL didn't get converted, this is unverified — but when it DOES get converted (after F8/F9), the CALL must map correctly.

**Cursor prompt**:
```
Open the converter source that handles CALL statements. When the COBOL has:

    CALL 'CHKAML' USING WS-AML-REQUEST WS-AML-RESPONSE

The Java should generate:

    private final ChkAmlService chkAmlService = new ChkAmlService();
    ...
    // Build request from working storage
    ChkAmlService.AmlRequest amlReq = new ChkAmlService.AmlRequest(
        wsAmlRequest.getCustId(),
        wsAmlRequest.getCin(),
        wsAmlRequest.getName(),
        wsAmlRequest.getDob(),
        wsAmlRequest.getNationality(),
        wsAmlRequest.getAmount()
    );
    
    // Call sub-program
    ChkAmlService.AmlResponse amlResp = chkAmlService.checkAml(amlReq);
    
    // Copy response back to working storage
    wsAmlResponse.setClear(amlResp.getClear());
    wsAmlResponse.setScore(amlResp.getScore());
    wsAmlResponse.setReason(amlResp.getReason());

For this to work, the converter must:
1. Know the package name of the called sub-program (e.g. com.modernized.chkaml.ChkAmlService)
2. Know its method name (checkAml, calculate, etc.)
3. Know its request/response class structure
4. Map COBOL parameter records to Java parameter objects

This requires the analyzer to identify CALL targets and their signatures. Verify the analyzer extracts:
{
  "external_calls": [
    {
      "program_name": "CHKAML",
      "type": "sub_program",
      "java_package": "com.modernized.chkaml",
      "java_class": "ChkAmlService",
      "java_method": "checkAml",
      "request_class": "AmlRequest",
      "response_class": "AmlResponse",
      "request_fields": [...],
      "response_fields": [...]
    }
  ]
}

The converter then uses this metadata to generate the call site code.

If the analyzer doesn't yet extract this, that's an analyzer fix (Phase D). For now, the converter should at minimum produce a TODO comment marker so the user can manually wire it up:

    // TODO: CALL 'CHKAML' USING WS-AML-REQUEST WS-AML-RESPONSE
    // Sub-program needs to be wired in - import com.modernized.chkaml.ChkAmlService
```

**Verification**: After F8/F9 and F14, LOANEVAL.java should contain calls to ChkAmlService.checkAml() and CalcFee.calculate().

---

## Fix F15 — Internal SORT with INPUT/OUTPUT PROCEDURE conversion

**Severity**: HIGH — LOANEVAL and RECOVRY rely on this

**Location**: Converter logic for the `SORT` verb with INPUT PROCEDURE / OUTPUT PROCEDURE

**Problem**: COBOL's internal SORT with procedures is fundamentally different from simple SORT. The INPUT PROCEDURE feeds records via RELEASE, and the OUTPUT PROCEDURE consumes them via RETURN. The natural Java equivalent is:

```java
List<SortRecord> sortBuffer = new ArrayList<>();
inputProcedure(sortBuffer);  // populates buffer
sortBuffer.sort(comparator);  // SORT key
outputProcedure(sortBuffer);  // consumes sorted buffer
```

**Cursor prompt**:
```
Open the converter source that handles the SORT verb. When the COBOL is:

    SORT SORT-WORK-FILE
        ON DESCENDING KEY SORT-COMPONENT-SCORE
        INPUT PROCEDURE IS 4910-LOAD-SORT THRU 4910-EXIT
        OUTPUT PROCEDURE IS 4920-RANK-OUTPUT THRU 4920-EXIT.

The Java should generate:

    private void sortComponents() {
        List<SortComponentRec> sortBuffer = new ArrayList<>();
        
        // INPUT PROCEDURE
        loadSort(sortBuffer);  // calls 4910-LOAD-SORT method
        
        // SORT - descending by SORT-COMPONENT-SCORE
        sortBuffer.sort((a, b) -> Integer.compare(b.sortComponentScore, a.sortComponentScore));
        
        // OUTPUT PROCEDURE
        rankOutput(sortBuffer);  // calls 4920-RANK-OUTPUT method
    }
    
    private void loadSort(List<SortComponentRec> buffer) {
        // Original 4910-LOAD-SORT logic, but RELEASE statements become buffer.add():
        for (int idx = 1; idx <= 5; idx++) {
            SortComponentRec rec = new SortComponentRec();
            rec.sortComponentName = wsCompEntry[idx].wscName;
            rec.sortComponentWeight = wsCompEntry[idx].wscWeight;
            rec.sortComponentScore = wsCompEntry[idx].wscScore;
            buffer.add(rec);  // ← This is the COBOL RELEASE statement
        }
    }
    
    private void rankOutput(List<SortComponentRec> buffer) {
        // Original 4920-RANK-OUTPUT logic, but RETURN statements become iterator.next():
        int idx = 1;
        for (SortComponentRec rec : buffer) {
            if (idx > 5) break;
            wsCompEntry[idx].wscName = rec.sortComponentName;
            wsCompEntry[idx].wscRank = idx;
            idx++;
        }
    }

Tasks:
1. The parser must mark SD files specially (already in F8)
2. The converter recognizes SORT verb with INPUT/OUTPUT PROCEDURE
3. Generates the List<T> + Comparator pattern above
4. RELEASE statements inside INPUT PROCEDURE → buffer.add()
5. RETURN statements inside OUTPUT PROCEDURE → iterator.next() or for-each loop
6. Multiple sort keys (ON DESCENDING ... ON ASCENDING ...) → composite Comparator using thenComparing
7. Add a unit test with a simple SORT example
```

**Verification**: After F8 + F15, LOANEVAL.java and RECOVRY.java should contain functional SORT logic using `List<T>.sort()`.

---

### Phase C completion check

```bash
# Compile all generated Java and run RISKSCOR against real data
cd /tmp/java_test
javac com/modernized/*/*.java
# All should compile

# Run RISKSCOR against the .dat files
cp /acme-bank-v3/data/*.dat .
java com.modernized.riskscor.RiskscorApplication
# Check the output: should show CLASS 1/2/3/4 counts that match expected
# (run COBOL version too if possible, compare class counts)
```

---

# PHASE D — Analyzer Quality (LLM not working)

The current analyzer falls back to deterministic mode silently and produces empty business_rules arrays. Fix this so the converter has actual context.

---

## Fix F16 — Diagnose "no_usable_chunks" failure

**Severity**: HIGH — analyzer is essentially non-functional

**Location**: The chunker code that splits COBOL programs for LLM analysis

**Problem**: For CALCFEE (190 lines, 5 paragraphs), the chunker produces zero usable chunks. This shouldn't happen — CALCFEE is small enough to fit in one chunk.

**Cursor prompt**:
```
Open the analyzer source. Search for "no_usable_chunks" — that's the warning that gets emitted.

Trace the chunking flow:
1. What's the minimum chunk size? If it's too high, small programs produce no chunks.
2. What's the maximum chunk size? If too low, splits produce too-small fragments.
3. What's the chunk boundary detection? (Probably PARAGRAPH or SECTION level.) Verify CALCFEE has parseable paragraph markers.

Add logging to the chunker:
- Total input lines
- Number of paragraph/section boundaries detected
- Size of each candidate chunk
- Reason each chunk was rejected (too small, too big, no business logic detected, etc.)

For CALCFEE specifically:
- It has 5 paragraphs: 0000-MAIN, 1000-SELECT-FEE-RATE, 2000-COMPUTE-FILE-FEE, 3000-COMPUTE-INSURANCE, 4000-COMPUTE-TAX, 5000-COMPUTE-TOTAL
- Each is 5-15 lines
- Total program is 190 lines

This should easily produce 1 single chunk (whole program) or 5 chunks (one per paragraph). The fact that it produces zero usable chunks means either:
- The chunker requires a minimum number of lines/paragraphs that CALCFEE doesn't meet
- The chunker is failing to detect paragraph boundaries
- The "usable" filter is rejecting all chunks for some reason

Fix the chunker so:
- Small programs (under ~500 lines) get one whole-program chunk
- Larger programs get split at section boundaries with overlap
- Minimum useful chunk size is around 10 lines, not 100+
- The "usable" filter should accept any chunk containing IF/EVALUATE/COMPUTE/CALL/MOVE statements

Add a unit test that CALCFEE produces at least 1 chunk.
```

**Verification**:
```bash
# Re-analyze CALCFEE through the pipeline
# Check the warnings array - "no_usable_chunks" should be gone
# Check business_rules array - should have at least 3 entries
```

---

## Fix F17 — Add LLM failure diagnostics

**Severity**: MEDIUM — currently failures are silent

**Location**: The wrapper around the LLM call

**Cursor prompt**:
```
Open the analyzer source. Find where the LLM is called (probably anthropic.Anthropic() or similar client). Wrap the call with comprehensive logging:

try:
    response = llm_client.messages.create(...)
    log.info(f"LLM call succeeded: {len(response.content)} chars, model={response.model}")
    
    # Validate response against schema
    parsed = json.loads(response.content)
    schema_result = validate_schema(parsed)
    if not schema_result.is_valid:
        log.warning(f"LLM response failed schema validation: {schema_result.errors}")
        analysis_engine = "deterministic"
        fallback_reason = "schema_validation_failed"
    else:
        analysis_engine = "llm"
        fallback_reason = None

except RateLimitError as e:
    log.error(f"LLM rate-limited: {e}")
    analysis_engine = "deterministic"
    fallback_reason = "rate_limit"
except APITimeoutError as e:
    log.error(f"LLM timed out: {e}")
    analysis_engine = "deterministic"
    fallback_reason = "timeout"
except APIError as e:
    log.error(f"LLM API error: {e}")
    analysis_engine = "deterministic"
    fallback_reason = f"api_error: {e}"
except json.JSONDecodeError as e:
    log.error(f"LLM produced invalid JSON: {e}")
    analysis_engine = "deterministic"
    fallback_reason = "invalid_json"

# Include fallback_reason in the output
output["analysis_engine"] = analysis_engine
if fallback_reason:
    output["fallback_reason"] = fallback_reason
    output["warnings"].append(f"LLM analysis failed: {fallback_reason}. Output is deterministic fallback.")

This way the user sees WHY the fallback engaged, not just that it did.
```

**Verification**: When the analyzer falls back, the output should contain `fallback_reason: "rate_limit"` or similar.

---

## Fix F18 — Deterministic fallback should still extract patterns

**Severity**: MEDIUM — empty arrays are useless even as fallback

**Cursor prompt**:
```
Open the analyzer's deterministic fallback code. Currently it returns empty arrays for business_rules, complexity_drivers, risk_points.

Even without LLM, a deterministic analyzer can detect:

1. complexity_drivers - count and report:
   - Number of files opened (>= 5 = high)
   - Number of CALL statements (any = medium driver)
   - Number of EVALUATE blocks (>5 = medium driver)
   - Presence of internal SORT (= driver)
   - Presence of EXEC SQL (= driver)
   - Presence of REDEFINES (= driver)
   - Presence of nested IF >3 levels deep (= driver)

2. business_rules - for each EVALUATE/IF block, extract:
   - source paragraph name
   - condition pattern (e.g. "if X > Y", "when status = 'A'")
   - action pattern (MOVE, ADD, COMPUTE in branches)
   - mark confidence as "low" since it's pattern-extracted not LLM-understood

3. risk_points - flag:
   - Hardcoded credentials or magic numbers
   - File operations without error checking
   - Unbounded loops
   - Recursive PERFORM (program calling itself)

4. dependencies:
   - All COPY statement names
   - All SELECT/FD file names with their organization
   - All CALL targets

5. Use type: "pattern_extracted" or confidence: "low" to mark these as fallback content, distinguishable from LLM-understood rules.

Example output for CALCFEE deterministic fallback:
{
  "business_rules": [
    {
      "id": "RULE-0001",
      "description": "EVALUATE on LK-REQ-LOAN-TYPE: 5 branches mapping to fee rates",
      "source_paragraph": "1000-SELECT-FEE-RATE",
      "type": "lookup_table_pattern",
      "confidence": "low",
      "pattern": "evaluate_when_other"
    },
    {
      "id": "RULE-0002",
      "description": "Conditional bound check: WS-FEE-GROSS clamped between WS-FILE-FEE-MIN and WS-FILE-FEE-MAX",
      "source_paragraph": "2000-COMPUTE-FILE-FEE",
      "type": "range_constraint_pattern",
      "confidence": "low"
    },
    ...
  ],
  "complexity_drivers": [
    "LINKAGE SECTION sub-program",
    "Multiple COMPUTE chains",
    "Conditional clamping"
  ]
}

Even at confidence "low" this is far more useful than empty arrays.
```

**Verification**: For CALCFEE, deterministic fallback should produce at least 3 business_rules entries (pattern-extracted) instead of an empty array.

---

## Fix F19 — Wire analyzer output into converter

**Severity**: MEDIUM — analyzer findings need to influence Java generation

**Cursor prompt**:
```
Open the converter source. Currently the converter generates Java from the parser output mostly mechanically. The analyzer output is mostly ignored.

The converter should use the analyzer's metadata:

1. business_rules → comments in generated Java
   For each business rule, add a JavaDoc comment block above the corresponding method explaining the rule.

2. complexity_drivers → architectural choices
   If "internal SORT" is a driver, generate Java that uses java.util.List + Comparator (not java.util.SortedSet or external sort lib)
   If "EXEC SQL" is a driver, generate JDBC stub methods with TODO markers
   If "high file count" (>5), use try-with-resources patterns

3. dependencies.external_calls → import statements and field declarations
   For each CALL target, generate:
     import com.modernized.<callee>.<Class>;
     private final <Class> <fieldname> = new <Class>();

4. risk_points → flag in JavaDoc
   For each risk point, add @apiNote or @implNote with the risk description.

This makes the generated Java richer and more maintainable, even when the analyzer is in deterministic mode.
```

**Verification**: Look at generated Java; should have meaningful JavaDoc derived from business_rules.

---

# PHASE E — Scoring & Validation

The pipeline currently reports 100/100 for semantically broken conversions. Fix that.

---

## Fix F20 — Score must reflect semantic correctness, not just compilation

**Severity**: HIGH — misleading UX

**Cursor prompt**:
```
Open the scoring module. Currently scores appear to be based on parse success + compile success + maybe some structural checks. Add semantic-correctness validation.

Scoring components (out of 100):

PARSE (20 points)
  + 20 if parser succeeded with no errors
  + 10 if succeeded with warnings only
  + 0 if failed

ANALYZE (20 points)
  + 20 if LLM analysis succeeded and produced ≥3 business_rules
  + 10 if deterministic fallback with ≥3 pattern-extracted rules
  + 5 if deterministic fallback with empty rules but successful structural analysis
  + 0 if failed completely

CONVERT (20 points)
  + 20 if Java is generated AND compiles AND all CALL/COPY references resolve
  + 10 if Java compiles but has TODO markers for unresolved CALLs
  + 5 if Java is generated but fails javac
  + 0 if no Java produced

SEMANTIC VALIDATION (40 points)
  + 10 if record offsets verified against actual .dat files
  + 10 if REWRITE preserves unmodified fields
  + 10 if business rules covered (each rule in analyzer output has corresponding code in Java)
  + 10 if a simple smoke test passes (run Java, check exit code 0)

This way 100/100 means "this conversion is actually correct" not "this conversion compiled."

For the RISKSCOR case from the analysis report, the bad byte offsets would have caused it to score around 70/100 (parse+analyze+convert pass, but semantic validation fails on offset check).

Add a semantic validation phase that:
1. Identifies the program's input files from FILE-CONTROL
2. If those files exist (in /acme-bank-v3/data/), reads the first 5 records
3. Calls the generated parser methods
4. Verifies parsed values are reasonable (e.g. status codes match the 88-level enum)
5. Reports specific failures per field

Display the score breakdown in the UI, not just a single number.
```

**Verification**: RISKSCOR should now score around 70/100, with details showing the byte-offset failure.

---

## Fix F21 — Add smoke test runner

**Severity**: MEDIUM — automated regression detection

**Cursor prompt**:
```
Create a smoke test runner that:

1. Takes the generated Java files
2. Compiles them with javac
3. Stages the .dat files in the working directory
4. Runs each program's main()
5. Captures exit code and stdout
6. Compares against an expected baseline (if exists)
7. Reports pass/fail with diff

For programs without main (sub-programs like CHKAML), generate a wrapper:

public class ChkAmlSmokeTest {
    public static void main(String[] args) {
        ChkAmlService service = new ChkAmlService();
        
        // Test case 1: clean client
        ChkAmlService.AmlRequest req1 = new ChkAmlService.AmlRequest(
            10000001, "12345678", "BENSALAH AHMED", 19850515, "TUN",
            new BigDecimal("5000.00"));
        ChkAmlService.AmlResponse resp1 = service.checkAml(req1);
        System.out.println("Test 1: clear=" + resp1.getClear() + " score=" + resp1.getScore());
        // Expected: clear=Y score<150
        
        // Test case 2: PEP match
        ChkAmlService.AmlRequest req2 = new ChkAmlService.AmlRequest(
            10000002, "12345678", "MOHAMED TRABELSI", 19700101, "TUN",
            new BigDecimal("5000.00"));
        ChkAmlService.AmlResponse resp2 = service.checkAml(req2);
        System.out.println("Test 2: clear=" + resp2.getClear() + " score=" + resp2.getScore());
        // Expected: clear=C score>=150 (PEP hit)
    }
}

Add this to the pipeline as an optional final step. Show smoke test results in the UI alongside scores.
```

**Verification**: After Fix F21, the UI should show smoke test results (e.g. "CHKAML: 5/5 smoke tests passed").

---

## Fix F22 — Surface deterministic fallback prominently in UI

**Severity**: LOW — UX

**Cursor prompt**:
```
In the UI, when a program's analysis is in deterministic mode (analysis_engine: "deterministic"), display a visible warning badge:

⚠️ Deterministic fallback - LLM analysis unavailable

This badge should appear next to the score. Click for details (the fallback_reason from Fix F17).

Cap the analysis score at 50% when in deterministic mode, so users immediately see this needs investigation.
```

---

# PHASE F — End-to-End Verification

After all fixes, validate the full pipeline produces correct, testable output.

---

## Fix F23 — Build end-to-end test harness

**Severity**: HIGH — proves the pipeline actually works

**Cursor prompt**:
```
Create a test script: /tests/e2e/acme_v3_test.sh

This script should:

1. Upload /acme-bank-v3 (post-Phase-A) to the pipeline
2. Run all phases (parse, analyze, convert, validate)
3. Download the resulting .java files
4. Compile them all with javac
5. Run RISKSCOR against /acme-bank-v3/data/ files
6. Capture output, compare to a baseline file
7. Report PASS/FAIL with diff if any

The baseline file should be generated by:
1. Compiling all COBOL with cobc
2. Running it against the same data
3. Capturing stdout

Save baseline at /tests/e2e/expected_output/acme_v3_riskscor.txt

Acceptance criteria:
- All 6 COBOL programs parse without errors
- All 6 Java files compile cleanly with javac
- RISKSCOR.java run against /acme-bank-v3/data/LOANFILE.dat produces:
  - CLASS 1 count matches COBOL baseline ±0
  - CLASS 2 count matches COBOL baseline ±0
  - CLASS 3 count matches COBOL baseline ±0
  - CLASS 4 count matches COBOL baseline ±0
  - TOTAL PROV matches baseline (within rounding tolerance)
- BCTSUBM.dat output matches baseline byte-for-byte (except date field)
```

---

## Fix F24 — Document the pipeline limitations

**Severity**: LOW — for users

**Cursor prompt**:
```
Create /docs/pipeline_capabilities.md listing:

SUPPORTED CONSTRUCTS:
- Standard COBOL data types (PIC X, 9, V, S, comp, comp-3)
- FD and SD file descriptions
- OCCURS with and without INDEXED BY
- PERFORM (simple, VARYING, UNTIL, THRU)
- EVALUATE with WHEN OTHER
- IF/ELSE nested up to 5 levels
- COMPUTE with ROUNDED
- MOVE, ADD, SUBTRACT, MULTIPLY, DIVIDE
- STRING and UNSTRING
- INSPECT REPLACING / CONVERTING / TALLYING
- REDEFINES
- COPY statement
- CALL (sub-program)
- Internal SORT with INPUT/OUTPUT PROCEDURE
- REWRITE on indexed files (with field preservation)
- ALTERNATE RECORD KEY WITH DUPLICATES
- SPECIAL-NAMES DECIMAL-POINT IS COMMA
- Reference modification (substring)

PARTIALLY SUPPORTED:
- EXEC SQL (recognized, stubbed in Java with TODO)
- PIC clauses with COMP-3 (packed decimal) - basic support
- USAGE BINARY - converted to int/long

NOT SUPPORTED:
- CICS commands (BMS screens, etc.)
- IMS DB calls
- VSAM file types beyond INDEXED
- DECLARE CURSOR (SQL beyond simple SELECT)
- COBOL OO features (CLASS-ID, METHOD-ID)
- Variable-length records (OCCURS DEPENDING ON beyond basic)

KNOWN LIMITATIONS:
- Programs over 5000 lines may exceed analyzer chunking limits
- Cross-program JCL flow not yet automatically wired
- Decimal point in literals must match SPECIAL-NAMES
- All copybook fields must be referenceable from a single 01-level
```

---

## Fix F25 — Re-run acme-bank-v3 through fixed pipeline

**Cursor prompt**:
```
After completing all fixes F1-F24:

1. Apply F1-F7 (source fixes) to /acme-bank-v3
2. Apply F8-F22 (pipeline fixes) to the pipeline code
3. Upload the corrected acme-bank-v3 to the pipeline
4. Verify all 6 programs:
   - Parse: Done (no errors)
   - Analyze: Done (LLM mode if available, ≥3 business rules per program)
   - Java: Done (compiles, passes semantic validation)
   - Score: ≥80/100 with details
5. Download all Java files
6. Run the smoke test harness (F23)
7. Compare output to COBOL baseline
8. All checks pass = pipeline is production-ready for this complexity level

If any step fails, the error message + analysis doc + this fix plan should be enough to diagnose and patch.
```

---

# Appendix A: Fix execution checklist

| ID | Description | Phase | Done? |
|---|---|---|---|
| F1 | RPTCOPY2.cpy line 11 truncate | A | ☐ |
| F2 | RPTCOPY2.cpy continuation lines | A | ☐ |
| F3 | CALCFEE.cbl SPECIAL-NAMES | A | ☐ |
| F4 | CHKAML.cbl SPECIAL-NAMES check | A | ☐ |
| F5 | Add WS-GTR-FS to ERRCOPY2 | A | ☐ |
| F6 | LOANEVAL COPY ordering | A | ☐ |
| F7 | Comment line column 72 cleanup | A | ☐ |
| F8 | Parser accepts SD | B | ☐ |
| F9 | Parser registers INDEXED BY | B | ☐ |
| F10 | Parser handles COPY inside FD | B | ☐ |
| F11 | Parser column awareness | B | ☐ |
| F12 | Byte offset calculation (CRITICAL) | C | ☐ |
| F13 | REWRITE field preservation | C | ☐ |
| F14 | Sub-program CALL conversion | C | ☐ |
| F15 | Internal SORT conversion | C | ☐ |
| F16 | Chunker diagnosis | D | ☐ |
| F17 | LLM failure logging | D | ☐ |
| F18 | Deterministic pattern extraction | D | ☐ |
| F19 | Analyzer→Converter wiring | D | ☐ |
| F20 | Semantic-correctness scoring | E | ☐ |
| F21 | Smoke test runner | E | ☐ |
| F22 | UI fallback badge | E | ☐ |
| F23 | E2E test harness | F | ☐ |
| F24 | Pipeline capability docs | F | ☐ |
| F25 | Final acme-v3 verification | F | ☐ |

# Appendix B: Risk mitigation

**Risk**: Phase B parser fixes break existing passing tests.
**Mitigation**: Before changing parser, capture current test suite output as baseline. Run after each change. Any regression must be fixed before continuing.

**Risk**: Phase C byte-offset fix produces different Java code that doesn't match user expectations.
**Mitigation**: Generate both old and new outputs for a sample program. Diff them. Confirm only offset numbers changed, not structure.

**Risk**: Phase D LLM changes cost more API tokens.
**Mitigation**: Add a cost tracker. Cap per-program at $X. If exceeded, fall back to deterministic with clear warning.

**Risk**: F12 (offset fix) doesn't reveal the root cause and there's a deeper bug.
**Mitigation**: Add unit tests for each PIC pattern BEFORE fixing. If tests pass but integration fails, the bug is elsewhere (probably in group handling or REDEFINES).

# Appendix C: Quick reference - PIC byte sizes

For verifying offset calculator:

| PIC clause | Bytes (USAGE DISPLAY) | Bytes (COMP) | Bytes (COMP-3) |
|---|---|---|---|
| `PIC X(n)` | n | n | n |
| `PIC A(n)` | n | n | n |
| `PIC 9(n)` | n | 2-8 (varies) | (n/2)+1 rounded |
| `PIC S9(n)` | n | 2-8 | (n/2)+1 rounded |
| `PIC 9(n)V9(m)` | n+m | varies | ((n+m)/2)+1 rounded |
| `PIC 9(n)V99` | n+2 | varies | varies |
| `PIC ZZZ9` | 4 | n/a | n/a |
| `PIC ZZZ,ZZ9` | 7 (comma counts) | n/a | n/a |
| `PIC ZZ.99` | 5 (dot counts) | n/a | n/a |

The V (implicit decimal point) is ZERO bytes always.
The S (sign) is ZERO bytes for DISPLAY usage (sign is in the last digit nibble).

# Appendix D: Deliverables after all fixes complete

1. `/acme-bank-v3/` — clean source, passes GnuCOBOL compile
2. Pipeline code — handles SD, INDEXED BY, correct offsets, REWRITE preservation
3. 6 generated .java files — all compile, all pass smoke tests
4. Baseline output file — captured from COBOL run, used for behavioral diff
5. `/tests/e2e/acme_v3_test.sh` — automated end-to-end test
6. `/docs/pipeline_capabilities.md` — what's supported, what's not
7. Updated UI — shows fallback badges, breakdown scores, smoke test results

When all 7 are in place, the pipeline can confidently be demoed to EY.
