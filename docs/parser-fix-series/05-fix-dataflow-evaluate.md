# Fix 05 — Data Flow: EVALUATE WHEN Variables Missing from Inputs

## File: Analysis layer (data flow computation)

## Problem
`8300-DETERMINE-TAX-RATE` reads `WS-GROSS-PAY` inside `EVALUATE TRUE / WHEN WS-GROSS-PAY < 500`.
The analysis reports `inputs: []` for this paragraph.

## Root cause
Data flow only tracks variables from MOVE source, ADD source, and IF condition references.
EVALUATE WHEN conditions are not scanned. The EVALUATE operation itself has
`"value": "TRUE"` with no references — the condition variables are in the `branches`
array, not in the operation.

## Fix
When computing paragraph inputs, also scan `control_flow.branches` for variables
in conditions belonging to this paragraph:

```python
for branch in branches:
    if branch.get("paragraph") == para_name:
        condition = branch.get("condition", "")
        for token in re.findall(r"[A-Z][A-Z0-9-]+", condition):
            if token not in RESERVED_WORDS and token in known_symbols:
                if token not in already_written_set:
                    inputs.add(token)
```

## Expected result
```json
{
  "name": "8300-DETERMINE-TAX-RATE",
  "inputs": ["WS-GROSS-PAY"],
  "outputs": ["WS-TAX-RATE"]
}
```

## Also applies to
Any paragraph using EVALUATE with variable comparisons in WHEN clauses. Examples:
`EVALUATE TRUE WHEN CUST-BALANCE > CREDIT-LIMIT` → `CUST-BALANCE` and
`CREDIT-LIMIT` must be in inputs.
