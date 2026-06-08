# COBOL Modernization — Remaining Fixes (Cursor Prompt)

You are working on a COBOL-to-Java modernization service with three pipeline stages:
**Parser** (`app/parsers/cobol_parser.py`), **Analysis** (LLM-driven semantic analysis),
and **Converter** (LLM-driven Java code generation). The parser is deterministic Python
code. The analysis and converter are LLM agents consuming the parser JSON.

The following fixes have already been applied: FILLER duplicate halt, multi-line
COMPUTE joining, preflight split (fatal/non-fatal), copybook metadata propagation,
context enricher wiring, escaped JSON in API responses, hybrid backend scaffold.

There are 9 remaining issues to reach 10/10 output quality. Apply ALL of them.

---

## PARSER FIXES (apply to `app/parsers/cobol_parser.py`)

### Fix 1 — `_decode_pic()`: V-prefix PIC returns wrong type

In `_decode_pic()`, find this line:
```python
is_numeric = bool(re.match(r"S?9", pic))
```
Replace with:
```python
is_numeric = bool(re.search(r'[S9]', pic)) or pic.startswith('V')
```

**Why:** PIC `V9(4)` starts with `V`, not `9` or `S`. The current regex misses it,
causing `java_type: "String"` and `dec_digits: 0` for pure-decimal fields. After this
fix, `V9(4)` correctly returns `is_numeric: true, dec_digits: 4, java_type: "BigDecimal"`.

**Test:** Parse a COBOL program with `01 WS-RATE PIC V9(4) VALUE ZEROS.` and assert
the symbol's `pic_decoded.java_type == "BigDecimal"` and `pic_decoded.dec_digits == 4`.

---

### Fix 2 — DISPLAY handler: strip quoted strings before reference extraction

In `_parse_operation()`, find the DISPLAY handler. Before the `re.finditer` loop that
extracts variable references, add:
```python
unquoted = re.sub(r'"[^"]*"', ' ', raw_value)
unquoted = re.sub(r"'[^']*'", ' ', unquoted)
```
Then change the `re.finditer` to scan `unquoted` instead of `raw_value`.

**Why:** `DISPLAY "EMPLOYEE PAYROLL CALCULATOR"` currently produces
`references: ["CALCULATOR", "EMPLOYEE", "PAYROLL"]`. These are English words inside
a string literal, not variable references. After this fix, pure-literal DISPLAY
statements have empty references, while mixed statements like
`DISPLAY "Name: " WS-NAME` correctly extract only `["WS-NAME"]`.

**Test:** `DISPLAY "HELLO WORLD"` → no references.
`DISPLAY "ID: " WS-ID` → references = `["WS-ID"]`.

---

## ANALYSIS FIXES (apply to the analysis agent prompt / LLM system prompt)

### Fix 3 — Paragraph role classification

**Current bug:** 12/14 paragraphs are labeled "Terminate program execution" because
the classifier inherits the STOP RUN label from the entry point to all paragraphs.

**Rule:** Each paragraph's role must describe what THAT SPECIFIC PARAGRAPH does based
on its own operations, name, and call relationships. Never inherit roles from the
entry point. Use this priority system:

1. First paragraph OR has STOP_RUN + calls others → "Program entry point and main orchestrator"
2. Name has MENU/SHOW + many DISPLAYs + ACCEPT → "Display menu options and capture user selection"
3. Has EVALUATE + conditional PERFORMs → "Route execution based on {subject} value"
4. Name has ADD/INSERT + ACCEPT + MOVE-to-array → "Collect input and add a new record"
5. Has EXIT PERFORM + sets found-flag + name has FIND/CHECK → "Search for matching record"
6. Has COMPUTE + name has CALC/DETERMINE → "Calculate derived values"
7. Many DISPLAYs of subscripted vars + name has VIEW/DISPLAY → "Display record details"
8. ACCEPT + MOVE-to-array + name has UPDATE/ENTER → "Accept and store updated values"
9. MOVE ZEROS to array fields + name has RESET/CLEAR → "Clear fields and reset"
10. Loop + ADD accumulators + DISPLAY totals + name has REPORT/SUMMARY → "Generate summary report"

---

### Fix 4 — Business rule extraction

**Current bug:** "sum values from 1 to 30 into TOTAL" appears in 13 paragraphs.
This is hallucinated. The program iterates a 30-element OCCURS table — that is a
loop boundary, not a summation formula.

**Rule:** Business rules must ONLY come from these specific source constructs:

- OCCURS N + loop UNTIL > N → "Capacity limited to N entries" (NOT "sum 1 to N")
- COMPUTE expression → "{target} = {expression}" (quote the actual expression)
- EVALUATE TRUE with thresholds → "Rate brackets: {list}"
- IF hours > threshold → "Overtime when exceeding {threshold}"
- ACCEPT CONFIRM + IF 'Y' → "Confirmation required before {action}"
- MOVE ZEROS/SPACES to all fields → "All fields cleared on {action}"
- Compound IF with flags → "Only records meeting {conditions} are processed"

If you cannot point to the exact COBOL line that implies a rule, do NOT emit it.
Never infer rules from what the code "might be intended to do."

---

### Fix 5 — Data flow: scan EVALUATE WHEN conditions for variable references

**Current bug:** `8300-DETERMINE-TAX-RATE` uses `WS-GROSS-PAY` in
`EVALUATE TRUE / WHEN WS-GROSS-PAY < 500` but the analysis reports `inputs: []`.

**Rule:** When computing a paragraph's inputs, also extract variable names from
`control_flow.branches` where `branch.paragraph == this_paragraph`. Any variable
in a branch condition that was not written earlier in the same paragraph is an input.

---

### Fix 6 — Global purpose derivation

**Current bug:** `"compute an accumulated total by iterating over a bounded range"`.

**Rule:** Derive global_purpose from the program name + the set of paragraph roles.
Combine action categories (record management, calculations, reporting, lookup, data
entry, period management) with the human-readable program name.

Expected for PAYROLL-CALC:
`"Employee payroll calculation: record management, calculations, tax bracket determination, overtime processing, reporting"`

---

## CONVERTER FIXES (apply to the conversion agent prompt / LLM system prompt)

### Fix 7 — Respect the `rounded` flag on COMPUTE/arithmetic operations

**Current bug:** All COMPUTE results use `RoundingMode.HALF_UP` regardless of whether
the COBOL source has the ROUNDED keyword.

**Rule:** Check `operation.rounded` from the parser JSON:
- `rounded: true` → `RoundingMode.HALF_UP` (COBOL rounds to nearest)
- `rounded: false` → `RoundingMode.DOWN` (COBOL truncates excess decimals)

This applies to COMPUTE, MULTIPLY, DIVIDE, ADD GIVING, SUBTRACT GIVING.

**Example:**
```java
// COMPUTE WS-TAX-AMOUNT ROUNDED = WS-GROSS-PAY * WS-TAX-RATE
taxAmount = grossPay.multiply(taxRate).setScale(2, RoundingMode.HALF_UP);

// COMPUTE WS-NET-PAY = WS-GROSS-PAY - WS-TAX-AMOUNT (no ROUNDED)
netPay = grossPay.subtract(taxAmount).setScale(2, RoundingMode.DOWN);
```

---

### Fix 8 — Flag field naming convention

**Current bug:** `isActive()` returns `String "Y"/"N"` — violates JavaBeans convention
where `isXxx()` must return boolean.

**Rule:** For COBOL PIC X fields used as Y/N flags:
- Rename getter to `getActiveFlag()` returning String, OR
- Convert to boolean: `isActive()` returning boolean, with `setActive(true/false)`

Apply consistently to ALL flag fields in the same class. In PAYROLL-CALC this
affects `EMP-ACTIVE` and `EMP-PAY-COMPUTED`.

---

### Fix 9 — Preserve the COBOL paragraph call graph in Java methods

**Current bug:** COBOL `1000-SHOW-MENU` calls `2000-ROUTE-CHOICE` internally via
PERFORM. Java `run()` calls `showMenu()` and `routeChoice()` as siblings — the
call hierarchy is flattened.

**Rule:** Use `control_flow.calls` from the parser output as the source of truth.
If the calls array contains `{"from": "1000-SHOW-MENU", "to": "2000-ROUTE-CHOICE"}`,
then Java method `showMenu()` must call `routeChoice()` internally. Never pull
nested calls up to the parent method level.

**Correct:**
```java
private void showMenu() {
    // ... display menu, accept choice ...
    routeChoice();  // called from within showMenu, matching COBOL
}
```

---

## VALIDATION CHECKLIST

After applying all 9 fixes, verify with PAYROLL-CALC.cbl:

**Parser (run `pytest tests/test_payroll_multiline_statements.py`):**
- [ ] `WS-TAX-RATE` symbol: `pic_decoded.java_type == "BigDecimal"`, `dec_digits == 4`
- [ ] `DISPLAY "EMPLOYEE PAYROLL CALCULATOR"`: no variable references
- [ ] `DISPLAY "Employee: " EMP-NAME(WS-FOUND-IDX)`: references = `["EMP-NAME", "WS-FOUND-IDX"]`
- [ ] All 6 COMPUTE operations present with correct `rounded` flags

**Analysis (inspect analysis JSON output):**
- [ ] `0000-MAIN` role contains "entry point" or "orchestrator", NOT "terminate"
- [ ] `8200-CALCULATE-PAY` role contains "calculate", NOT "terminate"
- [ ] No business rule mentions "sum values from 1 to 30"
- [ ] Business rules include overtime threshold (40 hours) and tax brackets
- [ ] `8300-DETERMINE-TAX-RATE` inputs include `WS-GROSS-PAY`
- [ ] `global_purpose` mentions "payroll" or "calculation", NOT "accumulated total"

**Converter (inspect generated Java):**
- [ ] `netPay` line uses `RoundingMode.DOWN` (the one COMPUTE without ROUNDED)
- [ ] All other arithmetic uses `RoundingMode.HALF_UP`
- [ ] No method named `isXxx()` returns String
- [ ] `showMenu()` calls `routeChoice()` internally
- [ ] `run()` does NOT call `routeChoice()` directly
