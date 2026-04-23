# Codex Prompt — COBOL Parser Layer Fine-Tuning
**Component:** COBOL Parser (column-aware, fully deterministic)
**Language:** Python 3.10+
**Position in Pipeline:** Stage 3b (after Preflight Gate, receives expanded source)

---

## SYSTEM PROMPT

You are implementing a production-grade COBOL parser for a modernization pipeline.
Your parser receives a fully COPY-expanded COBOL source file (all COPY statements
already resolved). It must extract a complete, correct AST with zero false positives.

All parsing is deterministic. No LLM calls. No inference.
Every decision is based on column position, keyword matching, and grammar rules
from IBM Enterprise COBOL for z/OS Language Reference.

---

## FIXED-FORMAT COLUMN LAYOUT (MANDATORY ENFORCEMENT)

| Columns | Zone | Rule |
|---|---|---|
| 1–6 | Sequence area | Strip before tokenization — never parse |
| 7 | Indicator | `*`=comment, `/`=page-eject comment, `-`=continuation, `D`=debug line, ` `=normal |
| 8–11 | Area A | Division headers, Section headers, Paragraph names, FD entries, 01/77/78/88 level items |
| 12–72 | Area B | Statements, subordinate data items (02–49), inline PERFORM bodies |
| 73–80 | Identification | Ignore completely |

```python
def parse_line(raw_line: str) -> dict:
    line = raw_line.rstrip('\n\r')
    # Pad to at least 7 chars
    line = line.ljust(7)
    seq_area   = line[0:6]    # discard
    indicator  = line[6]       # critical
    area_a     = line[7:11]   # paragraph/section/division names
    area_b     = line[11:72]  # statements
    return {
        "indicator": indicator,
        "area_a": area_a,
        "area_b": area_b,
        "is_comment": indicator in ('*', '/'),
        "is_continuation": indicator == '-',
        "is_debug": indicator == 'D'
    }
```

---

## REQUIREMENT 1: Paragraph vs. Section Discriminator

A label in Area A is a PARAGRAPH name if:
- It is an alphanumeric token ending with `.` (period)
- The next non-blank token is NOT `SECTION`

A label in Area A is a SECTION name if:
- It is followed by the keyword `SECTION`

```python
def classify_area_a_label(area_a_token: str, area_b_token: str) -> str:
    clean = area_a_token.rstrip('.').strip()
    if not clean:
        return "none"
    next_word = area_b_token.strip().split()[0].upper() if area_b_token.strip() else ""
    if next_word == "SECTION":
        return "section"
    if is_division_keyword(clean):
        return "division"
    if is_valid_paragraph_name(clean, column=8):
        return "paragraph"
    return "unknown"
```

---

## REQUIREMENT 2: Paragraph Name Validation

```python
import re

VALID_PARAGRAPH_NAME = re.compile(r'^[A-Z0-9][A-Z0-9\-]{0,29}$')

# Complete IBM Enterprise COBOL reserved words (partial list — expand with full IBM list)
COBOL_RESERVED_WORDS = {
    'ACCEPT','ADD','ALTER','CALL','CANCEL','CLOSE','COMPUTE','CONTINUE',
    'DELETE','DISPLAY','DIVIDE','ELSE','END','EVALUATE','EXIT','GO','IF',
    'INITIALIZE','INSPECT','MERGE','MOVE','MULTIPLY','OPEN','PERFORM',
    'READ','RELEASE','RETURN','REWRITE','SEARCH','SET','SORT','START',
    'STOP','STRING','SUBTRACT','UNSTRING','WRITE','SECTION','DIVISION',
    'WORKING-STORAGE','PROCEDURE','DATA','ENVIRONMENT','IDENTIFICATION',
    'LINKAGE','FILE','LOCAL-STORAGE','SCREEN','REPORT','COMMUNICATION',
    'PROGRAM-ID','AUTHOR','DATE-WRITTEN','INSTALLATION','DATE-COMPILED',
    'SECURITY','OBJECT-COMPUTER','SOURCE-COMPUTER','SPECIAL-NAMES',
    'FILE-CONTROL','I-O-CONTROL','SELECT','ASSIGN','ORGANIZATION',
    'ACCESS','RECORD','KEY','STATUS','FD','SD','RD','CD'
}

def is_valid_paragraph_name(name: str, column: int) -> bool:
    if not (8 <= column <= 11):
        return False
    if not VALID_PARAGRAPH_NAME.match(name.upper()):
        return False
    if name.upper() in COBOL_RESERVED_WORDS:
        return False
    # Numeric-only names are valid in COBOL (e.g. 0000-INIT)
    return True
```

---

## REQUIREMENT 3: Continuation Line Merging

Lines with `-` in column 7 continue the previous logical line.
The content starts at column 12 (Area B) of the continuation line.
If the previous line ended with an open string literal, the continuation
starts AFTER the first `"` on the continuation line.

```python
def merge_continuation_lines(parsed_lines: list[dict]) -> list[dict]:
    merged = []
    buffer = None
    for pl in parsed_lines:
        if pl["is_continuation"] and buffer:
            # Append Area B content, handling string continuation
            cont_content = pl["area_b"]
            if buffer.get("in_string"):
                # Find and skip the opening quote on continuation line
                quote_pos = cont_content.find('"')
                if quote_pos >= 0:
                    cont_content = cont_content[quote_pos+1:]
            buffer["area_b"] += cont_content
            buffer["continuation_lines"] = buffer.get("continuation_lines", 0) + 1
        else:
            if buffer:
                merged.append(buffer)
            buffer = pl.copy()
    if buffer:
        merged.append(buffer)
    return merged
```

---

## REQUIREMENT 4: 88-Level Condition Name Extraction

88-level items are boolean condition aliases for a parent field.
They MUST be extracted and associated with their parent.

```cobol
01 FOUND-FLAG    PIC X    VALUE 'N'.
   88 ITEM-FOUND         VALUE 'Y'.
   88 ITEM-NOT-FOUND     VALUE 'N'.
   88 SEARCH-ACTIVE      VALUES 'Y' 'S'.
```

Parser output for 88-level items:
```json
{
  "name": "FOUND-FLAG",
  "level": 1,
  "pic": "X",
  "value": "'N'",
  "kind": "string",
  "condition_names": [
    {"name": "ITEM-FOUND",    "values": ["Y"],      "kind": "condition_88"},
    {"name": "ITEM-NOT-FOUND","values": ["N"],       "kind": "condition_88"},
    {"name": "SEARCH-ACTIVE", "values": ["Y", "S"],  "kind": "condition_88"}
  ]
}
```

Java generation target:
```java
private char foundFlag = 'N';
private boolean isItemFound()     { return foundFlag == 'Y'; }
private boolean isItemNotFound()  { return foundFlag == 'N'; }
private boolean isSearchActive()  { return foundFlag == 'Y' || foundFlag == 'S'; }
```

---

## REQUIREMENT 5: PERFORM THRU Resolution

```cobol
PERFORM PARA-A THRU PARA-Z.
```

This executes all paragraphs from PARA-A to PARA-Z in source order.
The parser must:
1. Identify the start paragraph and end paragraph
2. Find all paragraphs between them in source order
3. Register ALL of them as called (conditional: false) in the call graph

```python
def resolve_perform_thru(from_para: str, to_para: str,
                          paragraph_order: list[str]) -> list[str]:
    try:
        start_idx = paragraph_order.index(from_para)
        end_idx   = paragraph_order.index(to_para)
        if start_idx > end_idx:
            return [from_para]  # malformed THRU — log warning
        return paragraph_order[start_idx:end_idx + 1]
    except ValueError:
        return []  # paragraph not found — preflight will catch
```

---

## REQUIREMENT 6: REDEFINES Detection

```cobol
01 WORK-AREA        PIC X(10).
01 WORK-NUMERIC REDEFINES WORK-AREA PIC 9(10).
```

REDEFINES creates a union-type overlay — both names refer to the same memory.
Extract and flag:

```json
{
  "name": "WORK-NUMERIC",
  "level": 1,
  "pic": "9(10)",
  "kind": "numeric",
  "redefines": "WORK-AREA",
  "risk_flag": "redefines_present"
}
```

---

## REQUIREMENT 7: PIC Clause Full Grammar

| PIC Symbol | Meaning | Java Type |
|---|---|---|
| `9(n)` | Numeric, n digits | `int` (if no V) |
| `9(n)V9(d)` | Implied decimal | `BigDecimal` |
| `S9(n)` | Signed numeric | `int` (check sign handling) |
| `X(n)` | Alphanumeric | `String` (padded to n) |
| `A(n)` | Alphabetic only | `String` |
| `Z(n)` | Numeric, leading zeros suppressed (display) | `String` (formatted) |
| `9(n)P(d)` | Scaled integer (P = implied zeros) | `BigDecimal` |
| `V` | Implied decimal point (no storage) | Part of `BigDecimal` scale |
| `S` | Sign (leading or trailing) | Affects `BigDecimal` or `int` |

```python
def decode_pic(pic_str: str) -> dict:
    pic = pic_str.upper().strip()
    has_v = 'V' in pic
    has_s = pic.startswith('S')
    is_numeric = bool(re.match(r'S?9', pic))
    is_string  = pic.startswith('X') or pic.startswith('A')

    int_digits = sum(int(m) if m else 1
                     for m in re.findall(r'9\((\d+)\)|9(?!\()', pic.split('V')[0]))
    dec_digits = 0
    if has_v:
        dec_part = pic.split('V')[1]
        dec_digits = sum(int(m) if m else 1
                         for m in re.findall(r'9\((\d+)\)|9(?!\()', dec_part))

    if is_numeric:
        java_type = "BigDecimal" if has_v else "int"
    elif is_string:
        java_type = "String"
    else:
        java_type = "String"  # default for complex PIC

    return {
        "raw": pic_str,
        "is_numeric": is_numeric,
        "is_string": is_string,
        "has_implied_decimal": has_v,
        "is_signed": has_s,
        "int_digits": int_digits,
        "dec_digits": dec_digits,
        "java_type": java_type,
        "storage_length": int_digits + dec_digits
    }
```

---

## REQUIREMENT 8: Subscripted Variable Read Detection

When a DISPLAY or IF or MOVE statement references `INV-QUANTITY(I)`,
the variable `INV-QUANTITY` must be registered as READ in the data flow.

```python
SUBSCRIPT_REF = re.compile(r'([A-Z][A-Z0-9\-]*)\s*\(([^)]+)\)', re.IGNORECASE)

def extract_reads_from_display(value_str: str, symbol_names: set) -> list[str]:
    reads = []
    # Extract subscripted references
    for m in SUBSCRIPT_REF.finditer(value_str):
        var_name = m.group(1).upper()
        if var_name in symbol_names:
            reads.append(var_name)
    # Extract plain variable references (token in symbol table)
    for token in value_str.split():
        clean = token.strip('"\' ,.')
        if clean.upper() in symbol_names:
            reads.append(clean.upper())
    return list(set(reads))
```

---

## PREFLIGHT GATE (runs before parser)

```python
def preflight_validate(parser_output: dict) -> list[str]:
    errors = []
    symbol_names = {s['name'] for s in parser_output['symbol_table']}
    known_paragraphs = set(parser_output['paragraphs'])

    # 1. No paragraph/symbol name collision
    for para in parser_output['paragraphs']:
        if para in symbol_names:
            errors.append(f"CONFLICT: '{para}' is both a paragraph and a symbol")

    # 2. Every PERFORM target is a known paragraph
    for call in parser_output['control_flow']['calls']:
        if call['to'] not in known_paragraphs:
            errors.append(f"PHANTOM CALL: '{call['to']}' called but not defined")

    # 3. Every loop iterator exists in symbol table
    for loop in parser_output['control_flow']['loops']:
        if loop.get('iterator') and loop['iterator'] not in symbol_names:
            errors.append(f"UNKNOWN ITERATOR: '{loop['iterator']}'")

    # 4. No reserved word used as paragraph name
    for para in parser_output['paragraphs']:
        if para in COBOL_RESERVED_WORDS:
            errors.append(f"RESERVED WORD AS PARAGRAPH: '{para}'")

    # 5. No unresolved COPY references in expanded source
    for sym in parser_output['symbol_table']:
        if sym.get('source') == 'unresolved_copy':
            errors.append(f"UNRESOLVED COPY SYMBOL: '{sym['name']}' — review required")

    return errors
```

---

## PARSER OUTPUT CONTRACT

```json
{
  "program_name": "INVENTORY-MANAGEMENT",
  "source_format": "fixed",
  "preflight_errors": [],
  "divisions": ["ENVIRONMENT DIVISION", "DATA DIVISION", "PROCEDURE DIVISION"],
  "sections": ["WORKING-STORAGE SECTION"],
  "paragraphs": ["MAIN-PARAGRAPH", "DISPLAY-MENU", "..."],
  "symbol_table": [
    {
      "name": "FOUND-FLAG",
      "level": 1,
      "pic": "X",
      "pic_decoded": {"java_type": "String", "storage_length": 1},
      "value": "'N'",
      "kind": "string",
      "condition_names": [
        {"name": "ITEM-FOUND", "values": ["Y"]},
        {"name": "ITEM-NOT-FOUND", "values": ["N"]}
      ]
    }
  ],
  "control_flow": {
    "branches": [...],
    "loops": [...],
    "calls": [...],
    "gotos": []
  },
  "operations": [...],
  "redefines": [],
  "resolved_copybooks": [...],
  "unresolved_copybooks": [],
  "risk_flags": ["conditional_logic", "loop_logic", "occurs_present"],
  "warnings": []
}
```

---

## CHECKLIST

- [ ] Sequence numbers (cols 1–6) stripped before any processing
- [ ] Indicator column (7) enforces: `*`/`/`=skip, `-`=continuation, `D`=skip if not debug mode
- [ ] Area A (cols 8–11) only used for paragraph/section/division names and level 01/77 items
- [ ] Continuation lines merged before tokenization
- [ ] Section vs. paragraph discriminated by `SECTION` keyword lookahead
- [ ] All paragraph names validated against regex + reserved word list
- [ ] 88-level items extracted with `condition_names[]` array on parent symbol
- [ ] PERFORM THRU expanded to full paragraph range
- [ ] REDEFINES flagged with `redefines` field and `risk_flag`
- [ ] PIC decoded to `java_type`, `int_digits`, `dec_digits`, `has_implied_decimal`
- [ ] Subscripted variables in DISPLAY/IF/MOVE registered in read-set
- [ ] EVALUATE-dispatched PERFORM calls in `calls[]` with `conditional: true`
- [ ] Preflight gate runs after parse, blocks pipeline on any error

---

*Codex Prompt: COBOL Parser Fine-Tuning — 2026-04-22*
