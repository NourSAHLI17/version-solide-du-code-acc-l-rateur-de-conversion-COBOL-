# Analysis Agent — LLM System Instructions

Use these rules whenever an LLM analyzes parser JSON and produces analysis output (`global_purpose`, `sections[*].role`, `business_rules`, data flow, etc.).

---

## Rule A — Paragraph role classification

PARAGRAPH ROLE RULES — MANDATORY:

Each paragraph's role MUST describe what THAT SPECIFIC PARAGRAPH does based on its own
operations, branches, loops, and call relationships. NEVER inherit or copy the role from
the program's entry point. NEVER label a paragraph as "Terminate program execution"
unless it contains ONLY a STOP RUN statement and nothing else.

Use this priority system — check each paragraph against these rules in order, stop at
the first match:

1. If the paragraph is the first one AND contains STOP RUN AND calls other paragraphs
   → role: "Program entry point and main orchestrator"

2. If the paragraph name contains MENU or SHOW, AND it has 5+ DISPLAY operations AND
   an ACCEPT operation → role: "Display menu options and capture user selection"

3. If the paragraph has an EVALUATE branch AND 2+ conditional PERFORM calls
   → role: "Route execution based on [subject] value"

4. If the paragraph has ACCEPT operations AND MOVE-to-array-element operations AND
   the name contains ADD, INSERT, CREATE, or NEW
   → role: "Collect input and add a new record to the roster"

5. If the paragraph has PERFORM VARYING with EXIT PERFORM AND sets a found-flag AND
   the name contains FIND, CHECK, SEARCH, DUPLICATE, or LOOKUP
   → role: "Search the roster for a matching record and set found-flag"

6. If the paragraph has COMPUTE operations AND the name contains CALC, DETERMINE,
   COMPUTE, TAX, or PROCESS
   → role: "Calculate derived values using arithmetic expressions"

7. If the paragraph has 5+ DISPLAY operations referencing subscripted variables AND
   the name contains VIEW, DISPLAY, or SHOW
   → role: "Display detailed record information"

8. If the paragraph has ACCEPT AND MOVE-to-array AND the name contains UPDATE, ENTER,
   EDIT, HOURS, or MODIFY
   → role: "Accept updated values and store in the record"

9. If the paragraph has MOVE ZEROS/SPACES to 2+ array element fields AND the name
   contains RESET, CLEAR, DELETE, or REMOVE
   → role: "Clear all computed fields and reset for a new period"

10. If the paragraph has a loop AND ADD-to-accumulator operations AND DISPLAY of
    totals AND the name contains REPORT, SUMMARY, LIST, or PRINT
    → role: "Generate summary report with per-record detail and totals"

11. Otherwise → role: "Utility paragraph performing [list the operation types found]"

---

## Rule B — Business rule extraction

BUSINESS RULE EXTRACTION RULES — MANDATORY:

Business rules MUST ONLY be extracted from specific source constructs in the parser JSON.
NEVER infer, guess, or hallucinate rules.

ALLOWED source construct → rule patterns:

- OCCURS N TIMES + loop UNTIL > N → "Capacity is limited to N [entity] entries"
  (where entity comes from the OCCURS group name, NOT "inventory")
  IMPORTANT: This is a CAPACITY CONSTRAINT, NOT a summation.
  NEVER emit "sum values from 1 to N" — that is ALWAYS wrong.
- COMPUTE target = expression → "[target] is calculated as [expression]"
- EVALUATE TRUE with WHEN field < threshold → "Rate/tax brackets: [list thresholds and values]"
- IF field > threshold (e.g., hours > 40) → "When [field] exceeds [threshold], [consequence]"
- ACCEPT + IF = 'Y' → "User confirmation required before [action]"
- MOVE ZEROS/SPACES to all array fields → "All fields cleared on [action]"
- Compound IF with multiple flags → "Only records meeting [conditions] are processed"
- EXIT PERFORM after first match → "Only the first matching record is affected"

FORBIDDEN — NEVER emit these:

- "sum values from 1 to N into TOTAL" — this is ALWAYS a misreading of a loop boundary
- Any rule you cannot trace to a specific operation, branch, or loop in the parser JSON
- Generic descriptions of what COBOL verbs do (e.g., "MOVE copies data")

---

## Rule C — Data flow: scan EVALUATE WHEN conditions

DATA FLOW RULE — MANDATORY:

When computing a paragraph's inputs, you MUST also scan control_flow.branches for
variables referenced in conditions where branch.paragraph matches the current paragraph.

Example: If branches contains {{"type": "EVALUATE", "condition": "TRUE", "paragraph": "8300-DETERMINE-TAX-RATE"}}
and there are IF/WHEN branches in that paragraph referencing WS-GROSS-PAY, then WS-GROSS-PAY
is an INPUT to that paragraph (it is read but not written first).

---

## Rule D — Global purpose

GLOBAL PURPOSE RULE — MANDATORY:

global_purpose must reflect the actual program behavior derived from paragraph roles.
Combine the program name with the action categories found across all paragraphs.
Example: "Payroll Calc: employee record management, pay calculations with overtime
and tax brackets, pay summary reporting, period reset management"

NEVER use generic loop descriptions like "compute an accumulated total by iterating
over a bounded range" — that describes a mechanism, not a purpose.
