
f4 = '''# COBOL Modernization Pipeline — Problems Faced & How They Were Solved

---

## Problem 1 — Parser Missing All Arithmetic Operations

### What Happened

Running the pipeline on PAYROLL-CALC revealed that the heuristic parser produced
zero entries in `operations[]` for any arithmetic. A payroll program with 6 COMPUTE
statements, 4 ADD accumulators, and tax calculations had this in its parser output:

```json
{ "operations": [] }
```

### Root Cause

The main statement parsing loop in `cobol_parser.py` had handlers for MOVE,
DISPLAY, ACCEPT, and PERFORM — but no handlers for COMPUTE, ADD, SUBTRACT,
MULTIPLY, or DIVIDE. These verbs were silently skipped.

### Why This Cascaded

The analysis agent received empty operations[] and had no arithmetic context.
It fabricated business rules from prior LLM context, producing:
- role = "Terminate program execution" on 12 of 14 paragraphs
- business_rules = ["sum values from 1 to 30 into TOTAL"] everywhere

The Java was still correct because the Conversion Agent read the COBOL source
directly — but this was luck, not reliability.

### How It Was Solved

**Short-term:** Added COMPUTE, ADD, SUBTRACT, MULTIPLY, DIVIDE regex handlers
to the heuristic parser as fallback.

**Long-term (final solution):** The ANTLR hybrid parser formally extracts all
arithmetic verbs using the expert grammar. The heuristic fallback provides a
second safety net.

---

## Problem 2 — ANTLR Backend Was a Stub

### What Happened

The project had `backend/antlr/Cobol85Lexer.g4` and `backend/antlr/Cobol85Parser.g4`
as 10-line placeholder files. The ANTLR backend always raised RuntimeError:

```python
raise RuntimeError("ANTLR artifacts not found")
```

The pipeline silently fell back to heuristic every time. ANTLR had never
successfully parsed a single line of COBOL.

### Root Cause

The grammar files were placeholder stubs created to reserve the file names.
The real expert grammar (7,300+ lines from antlr/grammars-v4) was never
downloaded or used.

### How It Was Solved

1. The developer downloaded two folders from GitHub:
   - `grammars_v4_master/` — antlr/grammars-v4 repository (contains real Cobol85.g4)
   - `antlr4/` — antlr/antlr4 repository (ANTLR toolchain)

2. The real grammar was generated into Python artifacts:
   ```bash
   antlr4 -Dlanguage=Python3 -visitor -listener \
     -o app/parsers/generated/ \
     grammars_v4_master/cobol85/Cobol85.g4
   ```

3. Generated artifacts confirmed newer than grammar source (timestamps verified).

4. `scripts/regenerate_antlr.sh` created to document and execute regeneration.

---

## Problem 3 — Analysis Agent Hallucinating Output

### What Happened

The deterministic analysis agent produced garbage:
- `"role": "Terminate program execution"` on 12 of 14 paragraphs
- `"business_rules": ["sum values from 1 to 30 into TOTAL"]` on every paragraph
- `"global_purpose": "compute an accumulated total"` (completely wrong)

### Root Cause (Multi-Layered)

1. Parser missing COMPUTE/ADD → operations[] empty → analysis had no data
2. Agent sent only parser AST, not COBOL source → no code to read
3. One prompt for all 14 paragraphs → model mixed contexts across paragraphs
4. Deterministic rules too generic → defaulted to boilerplate output

### How It Was Solved

Complete rewrite of the analysis agent:
1. **Input:** Now receives BOTH parser output AND raw COBOL source
2. **Per-chunk calls:** Segmenter + chunker boundaries determine call granularity
3. **Overlay pattern:** LLM provides role/business_rules/risk_flags; deterministic
   layer provides inputs/outputs/structural flags
4. **Same LLM client** as conversion agent (invoke_prompt reused)

---

## Problem 4 — EVALUATE WHEN PERFORM Targets Not in calls[]

### What Happened

Paragraphs dispatched via EVALUATE WHEN PERFORM (menu routing) appeared as
dead code because calls[] only tracked direct PERFORM statements.

Example:
```cobol
2000-ROUTE-CHOICE.
    EVALUATE WS-MENU-CHOICE
        WHEN 1 PERFORM 3000-ADD-EMPLOYEE
        WHEN 2 PERFORM 3100-VIEW-EMPLOYEE
    END-EVALUATE.
```

`3000-ADD-EMPLOYEE` and `3100-VIEW-EMPLOYEE` had `called_by = []` and
`is_dead_code = true` in the analysis output.

### How It Was Solved

The ANTLR visitor `visitEvaluateStatement` explicitly walks WHEN clauses
and registers any PERFORM targets found inside them as calls:

```python
for when_ctx in ctx.evaluateWhenPhrase():
    for stmt in when_ctx.statement():
        if stmt.performStatement():
            target = stmt.performStatement()...procedureName(0)
            self.calls.append({
                "type": "PERFORM", "from": current_para,
                "to": target, "conditional": True,
                "condition": "EVALUATE-WHEN"
            })
```

---

## Problem 5 — PIC V-Only Fields Decoded as String

### What Happened

`WS-TAX-RATE PIC V9(4)` (pure decimal field, no integer digits) was mapped
to `java_type = "String"` instead of `BigDecimal`.

### Root Cause

The `_decode_pic()` function did not handle PIC strings starting with V
(no integer digits before the decimal point). It fell through to the
string/other fallback.

### How It Was Solved

Added a specific case in `_decode_pic()` before the fallback:

```python
if pic.startswith("V"):
    dec_match = re.match(r"^V9\((\d+)\)$", pic)
    decimal_digits = int(dec_match.group(1)) if dec_match else pic.count("9")
    return {
        "java_type": "BigDecimal",
        "decimal_digits": decimal_digits,
        "integer_digits": 0,
        "is_decimal": True
    }
```

---

## Problem 6 — Paragraph Source Extraction Getting Wrong Lines

### What Happened

The paragraph source extraction used a naive string search that would match:
- Comment lines (column 7 = *) as if they were code
- Paragraph names in PERFORM statements as paragraph starts
- Continuation lines as new paragraphs

This caused the LLM to receive incorrect source slices.

### Root Cause

COBOL has a fixed-format layout with specific column semantics. A general
string search ignores this structure.

### How It Was Solved

`column_aware_paragraphs.py` was created implementing proper COBOL column logic:
- Detects 6-digit sequence number prefix in columns 1-6
- Checks column 7 indicator — skips * and / (comment/eject) lines
- Only matches paragraph names in Area A (columns 8-11)
- First occurrence of each paragraph name wins

Auto-enabled when `ANALYSIS_ENGINE=llm` regardless of flag setting.

---

## Problem 7 — Tests Breaking When Real LLM Keys Present

### What Happened

After implementing `ANALYSIS_ENGINE=llm` as default, running the test suite
with real API keys caused deterministic tests to fail because the LLM produced
different output than the hardcoded expected strings.

Example failure:
```
AssertionError: expected role == "Process employee records"
got role == "Calculate gross pay with overtime..."
```

### How It Was Solved

Three-layer test isolation:
1. `tests/test_analysis_agent.py` forces `ANALYSIS_ENGINE=deterministic` in setUp
2. `tests/test_conversion_agent.py` forces `ANALYSIS_ENGINE=deterministic` in setUp
3. `tests/test_payroll_multiline_statements.py` uses autouse pytest fixture

LLM integration tests in `tests/test_analysis_llm_pipeline.py` use a mocked
LLM client, never hitting the real API.

---

## Problem 8 — Non-Uniform Response Contract

### What Happened

Preflight-halt responses and error/abort paths did not include
`analysis_engine` and `analysis_revision` fields. Downstream code that
accessed these fields would raise KeyError on halt responses.

### How It Was Solved

All response paths now include:
```python
"analysis_engine":            "n/a",
"analysis_revision":          0,       # ANALYSIS_REVISION_HALTED
"paragraph_source_extraction": "n/a"
```

Constants defined:
```python
ANALYSIS_REVISION_LLM           = 2
ANALYSIS_REVISION_DETERMINISTIC = 1
ANALYSIS_REVISION_HALTED        = 0
```

---

## Problem 9 — ANTLR Regeneration Undocumented

### What Happened

The generated Python artifacts in `app/parsers/generated/` were produced during
development but there was no executable record of how to regenerate them if they
were ever deleted, outdated, or corrupted.

The `antlr4/` folder at project root was added as a local ANTLR toolchain source
but was described only in prose documentation, not in any runnable script.

### How It Was Solved

`scripts/regenerate_antlr.sh` created with:
- `--verify` flag to check artifacts exist without regenerating
- Jar resolution: checks `antlr4/` folder first, falls back to pip antlr4 CLI
- Explicit grammar source paths printed before running
- Auto-verify after regeneration
- Test: `test_regenerate_antlr_script.py` verifies existence and executable bit

---
*File 4 of 5 — Problems & Solutions*
'''

with open("output/G4_problems_and_solutions.md", "w", encoding="utf-8") as f:
    f.write(f4)
print(f"G4: {len(f4):,} chars")
