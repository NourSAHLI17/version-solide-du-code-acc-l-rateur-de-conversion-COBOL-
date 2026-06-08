# Prompt — Fix Missing Verb Operations in cobol_parser.py

## Context

You are working on `app/parsers/cobol_parser.py`, specifically the `_parse_operation()`
method of the `ParserLayer` class. This method parses a single COBOL statement text
(already uppercased) and returns a structured dict representing the operation, or
`None` if the statement is not a recognized operation.

The current implementation is missing handlers for several COBOL verbs:
- `COMPUTE` — arithmetic with an expression (most critical)
- `MULTIPLY` — `MULTIPLY A BY B GIVING C`
- `DIVIDE` — `DIVIDE A INTO B GIVING C REMAINDER R`
- `STRING` — `STRING A DELIMITED SIZE INTO B`
- `UNSTRING` — `UNSTRING A DELIMITED ',' INTO B C`
- `INSPECT` — `INSPECT A TALLYING B FOR ALL 'X'`

Additionally, the `_extract_warnings()` method emits INFO warnings for COMPUTE,
STRING, and UNSTRING when they are detected but not parsed. Once the operations above
are added, those INFO entries must be removed.

## The existing `_parse_operation()` signature and context

```python
def _parse_operation(
    self,
    upper_text: str,      # already uppercased statement text, period stripped
    paragraph: Optional[str],  # current paragraph name or None
    line_number: int,
) -> Optional[Dict[str, object]]:
```

The method returns either a single dict, a list of dicts (for multi-target MOVE),
or `None`. It has access to `self._parse_operand(token)` which parses a data-name
or literal with optional subscript into:
```python
{
    "name": str,
    "subscript": Optional[str],
    "is_literal": bool,
    "is_figurative": bool,
    "is_array_element": bool,
}
```

It also has access to `self.FIGURATIVE_CONSTANTS` and `self.RESERVED_WORDS`.

## Your task

Add handler blocks to `_parse_operation()` for each missing verb listed above.
Each handler must:

1. Use a regex to match the statement. The regex must be anchored (`^`) and handle
   optional trailing periods (`\.?$`).
2. Call `self._parse_operand()` on any data-name tokens (targets and sources).
3. Return a dict with at minimum: `type`, `paragraph`, and the key operands.
4. If the target is an array element (subscripted), include `target_subscript` and
   `target_is_array_element: True`.
5. Match the output structure style used by the existing ADD and SUBTRACT handlers.

### Required output structures

**COMPUTE:**
```python
{
    "type": "COMPUTE",
    "target": "WS-TOTAL",          # data-name only, no subscript if unsubscripted
    "target_subscript": "I",       # only if subscripted
    "target_is_array_element": True, # only if subscripted
    "rounded": True,               # True if ROUNDED keyword present
    "expression": "WS-QTY * WS-PRICE",  # raw expression string, trimmed
    "paragraph": "3000-CALC-TOTALS",
}
```

**MULTIPLY:**
```python
{
    "type": "MULTIPLY",
    "value": "WS-QTY",             # multiplier
    "target": "WS-PRICE",          # multiplicand / GIVING target
    "giving": "WS-TOTAL",          # only if GIVING clause present
    "rounded": False,
    "paragraph": "...",
}
```

**DIVIDE:**
```python
{
    "type": "DIVIDE",
    "value": "3",                  # divisor
    "target": "WS-SUM",            # dividend
    "giving": "WS-AVG",            # only if GIVING clause present
    "remainder": "WS-REM",         # only if REMAINDER clause present
    "rounded": False,
    "paragraph": "...",
}
```

**STRING:**
```python
{
    "type": "STRING",
    "sources": ["WS-FIRST", "WS-LAST"],  # all source data-names
    "target": "WS-FULL-NAME",
    "paragraph": "...",
}
```

**UNSTRING:**
```python
{
    "type": "UNSTRING",
    "source": "WS-INPUT-LINE",
    "targets": ["WS-FIELD-1", "WS-FIELD-2"],
    "paragraph": "...",
}
```

**INSPECT:**
```python
{
    "type": "INSPECT",
    "target": "WS-WORK-FIELD",
    "mode": "TALLYING",   # or "REPLACING" or "CONVERTING"
    "paragraph": "...",
}
```

### After adding the handlers

In `_extract_warnings()`, find the block that emits INFO warnings for these verbs:

```python
verb_candidates = {"COMPUTE", "MULTIPLY", "DIVIDE", "STRING", "UNSTRING", "INSPECT", "SEARCH", "SET"}
for line in lines:
    verb = line["upper"].split(" ", 1)[0].rstrip(".")
    if verb in verb_candidates and verb not in supported_ops:
        _add("INFO", "low",
             f"Operation {verb} detected but not serialized into operations")
```

Update `supported_ops` to include the newly handled verbs:

```python
supported_ops = {
    "MOVE", "ADD", "SUBTRACT", "COMPUTE", "MULTIPLY", "DIVIDE",
    "STRING", "UNSTRING", "INSPECT",
    "READ", "WRITE", "REWRITE", "DELETE", "ACCEPT", "DISPLAY",
    "CALL", "OPEN", "CLOSE",
    "EXIT", "EXIT_PERFORM", "EXIT_PERFORM_CYCLE", "EXIT_PROGRAM",
    "STOP_RUN", "STOP-RUN", "GOBACK", "DELETE_FILE"
}
```

## Constraints

- Do not change the method signature.
- Do not change the return type contract (single dict, list, or None).
- Do not add new imports — the existing `re` and `typing` imports are sufficient.
- Place each new handler block in the order: COMPUTE, MULTIPLY, DIVIDE, STRING,
  UNSTRING, INSPECT. Insert them after the existing SUBTRACT handler and before the
  EXIT PERFORM handler.
- Each handler should follow exactly the same style as the existing ADD and SUBTRACT
  handlers: one `re.match()` call, extract groups, call `_parse_operand()`, build
  dict, attach paragraph, return.
- All regex patterns must be compiled inline (not as class-level constants) to match
  the existing style.
- Add a unit test for each handler in `tests/test_cobol_parser.py` covering:
  basic case, ROUNDED variant (for COMPUTE/MULTIPLY/DIVIDE), subscripted target.
