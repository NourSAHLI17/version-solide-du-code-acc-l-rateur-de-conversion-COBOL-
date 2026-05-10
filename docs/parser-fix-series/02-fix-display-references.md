# Fix 02 — Display Reference False Positives

## File: `app/parsers/cobol_parser.py` → `_parse_operation()` DISPLAY handler

## Problem
`DISPLAY "EMPLOYEE PAYROLL CALCULATOR"` produces
`references: ["CALCULATOR", "EMPLOYEE", "PAYROLL"]`.
These are words inside a string literal, not variable references.

## Root cause
The regex scans the entire `raw_value` including content inside quotation marks.

## Fix
Strip quoted strings before extracting references:
```python
# In the DISPLAY handler, before the reference extraction loop:
unquoted = re.sub(r'"[^"]*"', ' ', raw_value)
unquoted = re.sub(r"'[^']*'", ' ', unquoted)
# Then scan `unquoted` instead of `raw_value` for references
```

## Expected behavior
| Statement | references |
|---|---|
| `DISPLAY "HELLO WORLD"` | `[]` |
| `DISPLAY "Name: " WS-NAME` | `["WS-NAME"]` |
| `DISPLAY WS-ID " " EMP-NAME(WS-IDX)` | `["EMP-NAME", "WS-ID", "WS-IDX"]` |

## Test
```python
def test_display_no_refs_for_pure_literal():
    op = ParserLayer()._parse_operation('DISPLAY "EMPLOYEE PAYROLL"', "MAIN", 1)
    assert "references" not in op or op["references"] == []

def test_display_refs_mixed():
    op = ParserLayer()._parse_operation('DISPLAY "Name: " WS-NAME', "MAIN", 1)
    assert op["references"] == ["WS-NAME"]
```
