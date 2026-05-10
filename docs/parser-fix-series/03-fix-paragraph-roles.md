# Fix 03 — Paragraph Role Classification

## File: Analysis layer (the agent/prompt that produces `sections[*].role`)

## Problem
12/14 paragraphs are labeled `"Terminate program execution"`. The classifier
keys on STOP RUN in the entry paragraph and propagates it everywhere.

## Fix — Priority-ordered rule system

For each paragraph, check its own operations, name, and call relationships.
First matching rule wins.

| Priority | Rule | Signals | Role template |
|---|---|---|---|
| 1 | Entry point | First paragraph OR has STOP_RUN + calls 2+ paragraphs | "Program entry point and main orchestrator" |
| 2 | Menu display | Name has MENU/SHOW + has DISPLAY(5+) + has ACCEPT | "Display menu options and capture user selection" |
| 3 | Routing | Has EVALUATE + 2+ conditional PERFORM calls | "Route execution based on {subject} value" |
| 4 | Data add | Name has ADD/INSERT/NEW + has ACCEPT + MOVE-to-array(2+) | "Collect input and add a new {entity} to the roster" |
| 5 | Search/find | Has PERFORM VARYING + EXIT PERFORM + sets found-flag + name has FIND/CHECK/SEARCH | "Search {table} for a matching record and set found-flag" |
| 6 | Calculation | Has COMPUTE operations + name has CALC/DETERMINE/PROCESS | "Calculate derived values using arithmetic expressions" |
| 7 | View/display | DISPLAY(5+) referencing subscripted vars + name has VIEW/DISPLAY | "Display detailed record information" |
| 8 | Update/enter | Has ACCEPT + MOVE-to-array + name has UPDATE/ENTER/EDIT | "Accept updated values and store in the record" |
| 9 | Reset/clear | MOVE ZEROS/SPACES to array fields(2+) + name has RESET/CLEAR/DELETE | "Clear all computed fields and reset for a new period" |
| 10 | Report | Has loop + ADD-to-accumulator + DISPLAY totals + name has REPORT/SUMMARY | "Generate summary report with per-record detail and totals" |
| 11 | Fallback | None of above | "Utility paragraph performing {operation_types}" |

## Expected output for PAYROLL-CALC

| Paragraph | Role |
|---|---|
| 0000-MAIN | Program entry point and main orchestrator |
| 1000-SHOW-MENU | Display menu options and capture user selection |
| 2000-ROUTE-CHOICE | Route execution based on WS-MENU-CHOICE value |
| 3000-ADD-EMPLOYEE | Collect input and add a new employee to the roster |
| 3100-VIEW-EMPLOYEE | Display detailed record information |
| 3200-ENTER-HOURS | Accept updated values and store in the record |
| 3300-RUN-PAYROLL | Iterate roster and trigger pay calculation for eligible employees |
| 3400-PAY-SUMMARY | Generate summary report with per-record detail and totals |
| 3500-RESET-PAY-PERIOD | Clear all computed fields and reset for a new period |
| 8000-CHECK-DUPLICATE-ID | Search roster for a matching record and set found-flag |
| 8100-FIND-BY-ID | Search roster for a matching record and set found-flag |
| 8200-CALCULATE-PAY | Calculate derived values using arithmetic expressions |
| 8300-DETERMINE-TAX-RATE | Calculate derived values using arithmetic expressions |
| 9000-DISPLAY-EMPLOYEE | Display detailed record information |

## Key rule
The role must describe what THIS paragraph does, never inherited from the entry point.
