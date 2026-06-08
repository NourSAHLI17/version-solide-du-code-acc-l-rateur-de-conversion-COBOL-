# COBOL Modernization — Master Execution Plan

## How to use this plan

Each step must be completed and verified before moving to the next.
"Verified" means: tests pass, output inspected manually, no regressions
on previous use cases. Do not skip ahead.

---

## PHASE 0 — Fix foundations (before any new feature)

### Step 0.1 — Verify parser fixes are actually saved

**What:** Open `app/parsers/cobol_parser.py` in your editor (not Cursor, not
the dashboard — the actual file on disk). Search for these exact strings:

- Search for `is_numeric =` → must contain `re.search(r'[S9]', pic) or pic.startswith('V')`
- Search for `unquoted = re.sub` → must exist in the DISPLAY handler
- Search for `UNREFERENCEABLE_NAMES` → must contain `FILLER`

If any of these are missing, apply them manually. Save the file. Restart the
backend server.

**Verify:** Run PAYROLL-CALC through the parser API. Check:
- `WS-TAX-RATE` symbol → `pic_decoded.java_type` must be `"BigDecimal"` and `dec_digits` must be `4`
- `DISPLAY "EMPLOYEE PAYROLL CALCULATOR"` → `references` must be empty or absent
- No preflight errors

**Done when:** All three checks pass in the actual JSON output.

---

### Step 0.2 — Verify analysis is using the LLM prompt correctly

**What:** Find the code path that produces the analysis JSON. Trace from
the API endpoint (`/api/analyze` or `/api/pipeline/run`) through to the
function that generates `global_purpose`, `sections[*].role`, and
`business_rules`. Determine whether it is:

- A: Pure deterministic Python (rules hardcoded in code)
- B: LLM call with a system prompt
- C: Hybrid (deterministic scaffold + LLM overlay)

If it is B or C, verify that the prompt file
(`app/prompts/analysis_agent_system_prompt.md`) is actually loaded and
injected into the LLM call. If it is A, the prompt file does nothing —
the rules must be added as Python code.

**Verify:** Run PAYROLL-CALC through analysis. Check:
- `0000-MAIN` role is NOT "Terminate program execution"
- No business rule says "sum values from 1 to 30"
- `8300-DETERMINE-TAX-RATE` inputs include `WS-GROSS-PAY`
- `global_purpose` mentions payroll/employee/calculation

**Done when:** All four checks pass. If they don't, fix the analysis
path before proceeding.

---

### Step 0.3 — Validate Use Case 3 end-to-end

**What:** Run all three Use Case 3 programs through the full pipeline
(JCL + copybooks + parse + analyze + convert):

- CUSTMGR.cbl — must parse with no preflight errors, produce enriched
  data_mappings with `CUSTOMER-FILE → ACME.CUSTOMER.MASTER`
- STMTRPT.cbl — must parse with no preflight errors (FILLER fix),
  produce complete symbol table including copybook fields
- TXNPOST.cbl — must parse with no preflight errors, capture all
  file operations (3 files: CUSTOMER-FILE, TRANSACTION-FILE, REPORT-FILE)

**Verify:** For each program:
- `preflight_errors == []`
- `paragraphs` array is non-empty
- `symbol_table` length > 20
- `operations` array contains COMPUTE, READ, WRITE, OPEN, CLOSE entries
  (for STMTRPT and TXNPOST)
- `dependencies.copybooks` includes the expected copybook names

**Done when:** All three programs produce complete, correct output.
This proves the pipeline works beyond in-memory programs.

---

## PHASE 1 — UI Restructure

### Step 1.1 — Single File Conversion page

**What:** Build a clean page with:
- Input area: paste COBOL or upload .cbl file
- Three sequential gated buttons:
  - Parser (always enabled)
  - Analysis (enabled only after Parser succeeds)
  - Java Conversion (enabled only after Analysis succeeds)
- Output panel for each stage (collapsible, with copy-to-clipboard)
- Download button for each output (JSON for parser/analysis, .java for conversion)
- Save to History button

**Verify:** Upload PAYROLL-CALC.cbl. Click Parser → inspect output.
Click Analysis → inspect output. Click Java → inspect output.
Verify that Analysis button is disabled before Parser runs.
Verify that Java button is disabled before Analysis runs.

**Done when:** The sequential gating works correctly and all three
outputs display properly.

---

### Step 1.2 — Project Conversion page

**What:** Build a page for multi-file COBOL projects:
- Upload ZIP or select from saved projects
- File tree showing all .cbl, .cpy, .jcl files
- Per-file status indicators (parsed ✅ / analyzed ✅ / converted ✅ / failed ❌)
- Run All button that processes files in dependency order
- Project-level download (ZIP of all converted Java files)

**Verify:** Upload Use Case 3 ZIP. Verify file tree shows 3 .cbl,
4 .cpy, 1 .jcl. Run pipeline. Verify per-file status updates.
Download project ZIP and verify it contains 3 .java files.

**Done when:** Use Case 3 processes completely through the project page.

---

### Step 1.3 — Conversion History

**What:** Build a history system that stores:
- Program name
- Timestamp
- Source hash (to detect re-runs of same program)
- Parser JSON
- Analysis JSON
- Java output
- Score (placeholder until scoring agent exists)
- Cost (placeholder until cost layer exists)

**Verify:** Run PAYROLL-CALC, then CUSTMGR. Open history page.
Verify both appear with correct names and timestamps. Click one
to reload its outputs.

**Done when:** History persists across page reloads and displays
all stored conversions correctly.

---

## PHASE 2 — Validation and Scoring Agent

### Step 2.1 — Structural fidelity score (deterministic)

**What:** Build a scoring function that compares parser JSON to Java output:

| Check | Points | Method |
|---|---|---|
| Paragraph count == method count | 20 | Count paragraphs in parser, count methods in Java |
| Call graph edges preserved | 15 | Every calls[] entry has a matching method call in Java |
| Loop count preserved | 10 | Every loop in parser has a matching loop in Java |
| Branch count preserved | 10 | Every IF/EVALUATE has a matching if/switch in Java |
| Early exit preserved | 5 | Every EXIT_PARAGRAPH/EXIT_PERFORM has a return/break |

Total possible: 60 points from structural checks.

**Verify:** Run on PAYROLL-CALC. Expected: 60/60 (all structures preserved).
Run on a deliberately broken Java output (remove one method). Expected: < 60.

**Done when:** Score is deterministic — same input always gives same score.

---

### Step 2.2 — Business rules coverage score (deterministic)

**What:** For each business rule in the analysis JSON, check whether the
Java output contains code that implements it:

| Rule pattern | Detection in Java |
|---|---|
| "capacity limited to N" | `MAX_EMPLOYEES = N` or array size N |
| "overtime at 1.5x" | `multiply(1.5)` or `OVERTIME_MULTIPLIER` |
| "tax bracket < 500 → 5%" | `compareTo(500) < 0` and `0.05` |
| "confirmation required" | `equalsIgnoreCase("Y")` before destructive action |

Points: 40 / (number of rules). Each detected rule earns its share.

**Verify:** Run on PAYROLL-CALC with 9 business rules. Each detected
rule earns ~4.4 points. Expected: 35-40/40.

**Done when:** Coverage score is deterministic and matches manual inspection.

---

### Step 2.3 — Combined score + LLM explanation

**What:** Combine structural (60 pts) + business rules (40 pts) = total/100.

Add an LLM call that takes the score breakdown and produces a one-paragraph
explanation: "Conversion scored 94/100. All 14 paragraphs mapped to methods.
8 of 9 business rules detected in Java. Deduction: overtime multiplier uses
hardcoded 1.5 instead of a named constant."

Add decision thresholds:
- 90-100: ✅ Auto-approve
- 70-89: ⚠️ Manual review recommended
- Below 70: ❌ Re-conversion required

**Verify:** Run on PAYROLL-CALC. Score should be 90+. Run on CUSTMGR.
Score should be 85+. Verify LLM explanation is accurate and mentions
the actual deductions.

**Done when:** Score + explanation + decision displayed correctly for
both test programs.

---

### Step 2.4 — Per-paragraph score breakdown

**What:** Instead of just one overall score, show a table:

```
Paragraph                  Structure  Rules  Total
0000-MAIN                  ✅ 100%    ✅     100
8200-CALCULATE-PAY         ✅ 100%    ✅     100
8300-DETERMINE-TAX-RATE    ✅ 100%    ✅     100
3400-PAY-SUMMARY           ✅ 100%    ⚠️ 85  95
```

This tells the developer exactly which paragraph needs attention.

**Verify:** Run on PAYROLL-CALC. Every paragraph should appear in the
breakdown with a score. The lowest-scoring paragraph should match
the actual weakest conversion point.

**Done when:** Breakdown table renders correctly and matches the
overall score.

---

## PHASE 3 — Cost Transparency

### Step 3.1 — Token counting per agent call

**What:** Wrap every LLM API call (analysis agent, conversion agent)
with a counter that records:
- Input tokens (prompt)
- Output tokens (completion)
- Model used
- Call duration (ms)
- Agent name (analysis / conversion / explanation)

Store these in a run-level cost record.

**Verify:** Run PAYROLL-CALC through full pipeline. Check that token
counts are recorded for each LLM call. Verify input + output tokens
are reasonable (analysis: ~2000-4000 tokens, conversion: ~3000-8000).

**Done when:** Every LLM call has accurate token counts stored.

---

### Step 3.2 — Cost calculation and display

**What:** Calculate cost from token counts:
- Input tokens × model input price per token
- Output tokens × model output price per token
- Sum across all calls in the run

Display in the UI:
- Per-run total cost
- Cost breakdown by agent (parser: $0.00, analysis: $0.02, conversion: $0.05)
- Cost per paragraph converted
- Cost per business rule extracted

**Verify:** Run PAYROLL-CALC. Verify displayed cost matches manual
calculation from token counts × known pricing.

**Done when:** Cost display is accurate and updates after each run.

---

### Step 3.3 — Pre-run cost estimate

**What:** Before running the pipeline, show an estimate:
"This program has 14 paragraphs and ~48 symbols. Estimated cost: ~$0.08"

Base the estimate on paragraph count × average cost per paragraph
(derived from historical runs).

**Verify:** Estimate should be within 30% of actual cost after the run completes.

**Done when:** Estimate displays before run and is reasonably close to actual.

---

## PHASE 4 — Testing Agent

### Step 4.1 — Behavioral Diff Generator

**What:** Given COBOL source + converted Java:
1. Prepare a set of scripted test inputs (employee data, menu choices, hours)
2. Run COBOL through GnuCOBOL with those inputs, capture stdout
3. Run Java with identical inputs, capture stdout
4. Compare line by line
5. Report: lines matching, lines differing, diff percentage

If GnuCOBOL is not available, use expected-output snapshots derived from
manual COBOL trace as the reference.

**Verify:** Run on PAYROLL-CALC with a scripted input sequence:
add employee → enter hours → run payroll → view employee → summary.
Compare COBOL stdout vs Java stdout.

**Done when:** Diff report shows which lines match and which differ,
with 95%+ match rate on PAYROLL-CALC.

---

### Step 4.2 — Business Rules Test Generator

**What:** For each business rule in the analysis JSON, generate a JUnit test:

```java
@Test
void testTaxBracket_grossUnder500_rate5Percent() {
    PayrollCalc app = new PayrollCalc();
    // Setup: employee with hours that produce gross < 500
    // Assert: tax rate == 0.05, tax amount == gross * 0.05
}
```

Derive boundary values deterministically from the rule text:
- "< 500" → test with 499, 500, 501
- "capacity 30" → test with 30th employee, then 31st
- "confirmation Y" → test with "Y", "N", "X"

**Verify:** Generated tests compile and pass against the converted Java.

**Done when:** At least one test per business rule, all compiling and passing.

---

### Step 4.3 — Edge Case Generator

**What:** Use parser structural flags to generate edge case tests:

| Flag | Edge case |
|---|---|
| `has_loop` with `UNTIL > 30` | Test with 0 employees, 1, 29, 30 |
| `has_early_exit` | Test the condition that triggers early exit |
| `OCCURS 30` | Test array boundary (index 30 and 31) |
| `EVALUATE TRUE` with thresholds | Test exact boundary values |

**Verify:** Generated tests compile and expose any boundary bugs.

**Done when:** Edge case tests run without failures on correct conversion.

---

### Step 4.4 — Unit Test Generator (LLM-assisted)

**What:** For each Java method, generate a unit test that:
- Mocks dependencies (other methods, Scanner input)
- Sets up initial state
- Calls the method
- Asserts outputs and side effects

Use the LLM to generate the test body, but derive assertions
deterministically from the parser data flow (inputs → outputs).

**Verify:** Generated tests compile, run, and pass. Test coverage > 80%.

**Done when:** Every public method has at least one unit test.

---

## PHASE 5 — Polish and Demo Preparation

### Step 5.1 — PDF Report Auto-Generation

**What:** After each conversion, auto-generate a PDF report like the
PAYROLL-CALC report we created manually. Include:
- Program overview
- Business rules table
- Call graph
- Parser summary
- Analysis summary
- Conversion mapping table
- Score breakdown
- Cost breakdown

**Verify:** Generate report for PAYROLL-CALC and CUSTMGR. Compare
quality to the manual report.

**Done when:** Report is auto-generated and presentation-quality.

---

### Step 5.2 — Three-program demo package

**What:** Prepare three complete pipeline runs:

| Program | Complexity | Features tested |
|---|---|---|
| PAYROLL-CALC | Simple | COMPUTE, EVALUATE TRUE, in-memory tables |
| CUSTMGR | Medium | File I/O, copybooks, JCL binding, REWRITE |
| Banking batch (TBD) | Complex | EXEC SQL, multi-file, 1000+ lines |

Each with: full pipeline output, score, report, test results, cost.

**Verify:** All three programs produce complete, correct output across
all pipeline stages.

**Done when:** Three PDF reports ready for the EY presentation.

---

### Step 5.3 — Re-conversion feedback loop

**What:** If the score is below 90, allow the user to:
1. See which paragraphs scored low
2. Type a correction instruction ("the tax calculation is wrong because...")
3. Re-run conversion on only the affected paragraphs
4. Re-score

**Verify:** Deliberately break one paragraph's conversion. Use the
feedback loop to fix it. Verify score improves.

**Done when:** Feedback loop works end-to-end and score reflects
the improvement.

---

## Summary timeline

| Phase | Steps | Duration | Dependency |
|---|---|---|---|
| Phase 0 | 0.1–0.3 | 2-3 days | Nothing — do this first |
| Phase 1 | 1.1–1.3 | 5-7 days | Phase 0 complete |
| Phase 2 | 2.1–2.4 | 5-7 days | Phase 1 complete |
| Phase 3 | 3.1–3.3 | 2-3 days | Phase 2 complete |
| Phase 4 | 4.1–4.4 | 7-10 days | Phase 2 complete |
| Phase 5 | 5.1–5.3 | 5-7 days | Phase 2+3+4 complete |

**Total: approximately 5-6 weeks** for full execution with proper
verification at each step.

**Critical path to EY demo:** Phase 0 → Phase 1 (UI) → Phase 2
(scoring) → Step 5.2 (three-program demo). This subset takes
approximately 3 weeks and gives you the strongest possible demo.
