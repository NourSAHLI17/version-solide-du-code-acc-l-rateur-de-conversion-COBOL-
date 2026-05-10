# Fix 06 — Global Purpose Derivation

## File: Analysis layer (global_purpose field)

## Problem
`"global_purpose": "compute an accumulated total by iterating over a bounded range"`
This is generic and wrong. The program is a payroll calculator.

## Fix
Derive global_purpose from the program name + the collection of paragraph roles:

```python
def derive_global_purpose(program_name, paragraph_roles):
    actions = set()
    for role in paragraph_roles:
        r = role.lower()
        if "add" in r or "collect" in r: actions.add("record management")
        if "calculat" in r or "compute" in r: actions.add("calculations")
        if "report" in r or "summary" in r: actions.add("reporting")
        if "search" in r or "find" in r: actions.add("lookup")
        if "update" in r or "enter" in r: actions.add("data entry")
        if "reset" in r or "clear" in r: actions.add("period management")
        if "menu" in r or "route" in r: actions.add("menu-driven interaction")
    name = program_name.replace("-", " ").replace("_", " ").title()
    return f"{name}: {', '.join(sorted(actions))}"
```

## Expected for PAYROLL-CALC
```json
"global_purpose": "Payroll Calc: calculations, data entry, lookup, menu-driven interaction, period management, record management, reporting"
```

## Key rule
global_purpose must reflect the actual actions the program performs. Never use a
generic loop description.
