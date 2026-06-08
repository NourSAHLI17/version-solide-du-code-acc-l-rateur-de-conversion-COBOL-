# Fix 04 — Business Rule Extraction

## File: Analysis layer (agent/prompt that produces `business_rules`)

## Problem
"sum values from 1 to 30 into TOTAL" appears in 13/14 paragraphs.
This rule is hallucinated — the program iterates a 30-element table, it does
not sum the integers 1 to 30.

## Root cause
The analysis LLM confuses `PERFORM VARYING WS-IDX FROM 1 BY 1 UNTIL WS-IDX > 30`
(a loop boundary) with a mathematical summation.

## Fix — Source-construct-only extraction

Business rules must ONLY be emitted when a specific source pattern is found.
Never from inference, never from "what this code looks like it might do."

### Allowed patterns → rules

| Source pattern | Rule template |
|---|---|
| `OCCURS N TIMES` + loop `UNTIL > N` | "{entity} capacity is limited to N entries" |
| `COMPUTE target ROUNDED = expression` | "{target} = {expression}, rounded" |
| `EVALUATE TRUE` with `WHEN field < threshold` | "Rate brackets: {list of thresholds}" |
| `IF hours > standard-hours` (overtime check) | "Overtime applies when hours exceed {threshold}" |
| `ACCEPT CONFIRM` + `IF = 'Y'` | "User confirmation required before {action}" |
| `MOVE ZEROS/SPACES` to all array fields | "All fields cleared on {action}" |
| `IF ACTIVE = 'Y' AND COMPUTED = 'N' AND HOURS > 0` | "Only eligible records are processed" |
| `EXIT PERFORM` after first match | "Only the first matching record is affected" |

### Forbidden patterns (never emit these)

| Pattern | Why it's wrong |
|---|---|
| Loop boundary treated as summation | `UNTIL I > 30` is capacity, not math |
| Generic description of what a verb does | "MOVE copies data" is not a business rule |
| Inferred intent not in source | "confirm before delete" when no ACCEPT exists |

### Expected business rules for PAYROLL-CALC

```json
[
  "Employee capacity is limited to 30 entries",
  "Duplicate employee IDs are rejected",
  "Regular pay = hours * hourly rate (max 40 regular hours)",
  "Overtime at 1.5x rate for hours exceeding 40",
  "Tax brackets: <500=5%, <1500=12%, <3000=22%, >=3000=30%",
  "Net pay = gross pay - tax amount",
  "Payroll processes only active employees with hours entered and pay not yet computed",
  "User confirmation required before pay period reset",
  "Reset clears hours, gross, tax, net, and pay-computed flag"
]
```

## Key rule
If you cannot point to the exact COBOL construct (line, condition, or clause) that
implies the rule, do NOT emit the rule.
