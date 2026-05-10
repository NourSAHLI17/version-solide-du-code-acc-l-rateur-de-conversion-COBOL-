
f3 = '''# COBOL Modernization Pipeline — LLM Analysis Agent
## Architecture, Design Decisions, and Implementation

---

## 1. Why the Analysis Agent Was Rewritten

### The Original Deterministic Agent — What It Did

The original analysis agent was deterministic: it processed the parser AST using
Python logic, pattern-matched on operations[], and returned a structured JSON.

### The Problem — Catastrophic Failure on PAYROLL-CALC

Running the deterministic agent on PAYROLL-CALC produced this output:

```json
{
  "role": "Terminate program execution",   ← 12 of 14 paragraphs
  "business_rules": [
    "sum values from 1 to 30 into TOTAL"   ← hallucinated, appears everywhere
  ]
}
```

**Root cause:** The heuristic parser (at that time) produced empty `operations[]`
for all arithmetic because COMPUTE/ADD/SUBTRACT were not parsed.
The deterministic agent had no signal to reason from, so it defaulted to the
most generic possible output.

### Why LLM Fixes This

The LLM receives:
1. **Parser output** — symbol table, control flow, calls, risk flags
2. **Raw COBOL source** — the actual code for each paragraph

With actual code to read, the LLM can extract real business rules:
- "Overtime rate = 1.5x for hours > 40"
- "Tax bracket 1: gross < 500 → rate 15%"
- "Search terminates early via EXIT PARAGRAPH when EMP-ID found"

---

## 2. Architecture — How the LLM Analysis Fits the Pipeline

The LLM analysis agent does NOT bypass the existing architecture.
It operates WITHIN the segmenter → chunker → aggregator flow.

```
parser_output (hybrid JSON)
       +
expanded COBOL source
       │
       ▼
┌─────────────────────────────────────────────────────┐
│  segment_program()                                   │
│  Groups paragraphs into logical segments             │
│  (unchanged from original architecture)              │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  chunk_segment()                                     │
│  Splits large segments into LLM-safe chunks          │
│  Each chunk = COBOL excerpt + parser JSON slice      │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  For each chunk:                                     │
│  invoke_prompt(COBOL excerpt + parser JSON)          │
│  LLM returns: role, business_rules, risk_flags       │
│                                                      │
│  Deterministic _analyze_segment() scaffold:          │
│  provides: inputs, outputs, structural flags         │
│                                                      │
│  overlay: LLM fields ON TOP OF deterministic base    │
│  Sets: analysis_engine, analysis_revision            │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  Aggregator                                          │
│  Rebuilds final analysis artifact from chunk results │
│  Same output schema as original analysis agent       │
└─────────────────────────────────────────────────────┘
```

---

## 3. Column-Aware Paragraph Source Extraction

### Why It Matters

COBOL has a fixed-format layout. Without column awareness:
- Comment lines (column 7 = *) would be sent to the LLM as code
- Paragraph names in PERFORM statements would be mistaken for paragraph starts
- Continuation lines would be split incorrectly

### COBOL Fixed-Format Layout

```
Column  1-6:  Sequence numbers (ignore)
Column  7:    Indicator
              * = comment line (SKIP)
              / = page eject (SKIP)
              - = continuation (SKIP as paragraph start)
              D = debug line
              (space) = normal code
Columns 8-11: Area A — paragraph names MUST start here
Columns 12-72: Area B — statements
```

### Auto-Enable Rule

When `ANALYSIS_ENGINE=llm`, column-aware extraction is **automatically forced on**
regardless of the `ANALYSIS_USE_COLUMN_PARAGRAPH_SOURCES` flag.

```python
use_column_aware = (
    config.analysis_use_column_paragraph_sources
    or (configured_engine == "llm")
)
```

This prevents the developer from accidentally running LLM analysis with
wrong paragraph slices by forgetting to set a second flag.

---

## 4. The Two Input Requirement

The analysis agent sends BOTH to the LLM:

| Input | Why It Is Required |
|---|---|
| Parser output | Provides symbol table, call graph, operations, risk flags. Prevents the LLM from having to re-discover structure. |
| COBOL source | Prevents hallucination. The LLM reads actual code and extracts real business rules rather than fabricating from prior context. |

**Neither alone is sufficient:**
- Parser output alone → empty operations[] causes hallucination
- COBOL source alone → LLM ignores the rich structural work already done

---

## 5. LLM Integration — Reuses Conversion Agent Client

The analysis agent uses the SAME LLM client and infrastructure as the conversion agent:

```python
class AnalysisAgent:
    def __init__(self, conversion_agent: ConversionAgent):
        self.conversion_agent = conversion_agent

    def _invoke_llm(self, prompt):
        return self.conversion_agent.invoke_prompt(prompt)
```

This means:
- Same API keys
- Same model selection (Google / OpenAI / OpenRouter)
- Same retry/error handling
- Same `can_invoke_llm()` guard (avoids treating sentinel objects as live clients)

---

## 6. Response Contract

Every response from the analysis agent — including early exits and preflight halts —
includes these three fields:

| Field | Type | Values |
|---|---|---|
| `analysis_engine` | string | `"llm"` \| `"deterministic"` \| `"n/a"` |
| `analysis_revision` | int | `2` (LLM) \| `1` (deterministic) \| `0` (halt/abort) |
| `paragraph_source_extraction` | string | `"column_aware"` \| `"heuristic_split"` \| `"n/a"` |

The constants used:
- `ANALYSIS_REVISION_LLM = 2`
- `ANALYSIS_REVISION_DETERMINISTIC = 1`
- `ANALYSIS_REVISION_HALTED = 0`

---

## 7. Configuration

```bash
# Select analysis engine
ANALYSIS_ENGINE=llm           # LLM-based (default, production)
ANALYSIS_ENGINE=deterministic # Deterministic fallback (for tests/CI)

# Force column-aware paragraph extraction
ANALYSIS_USE_COLUMN_PARAGRAPH_SOURCES=true  # explicit opt-in
# Note: always forced on when ANALYSIS_ENGINE=llm
```

---

## 8. Test Strategy

| Test Type | What It Tests | Where |
|---|---|---|
| Unit (deterministic) | Deterministic agent output schema | `tests/test_analysis_agent.py` |
| Unit (LLM mocked) | LLM path schema, overlay logic, payload content | `tests/test_analysis_llm_pipeline.py` |
| Column-aware LLM | Payload contains no comment lines, not empty | `tests/test_analysis_llm_pipeline.py` |
| Contract uniformity | All paths have analysis_engine + analysis_revision | `tests/test_analysis_agent.py` |
| Payroll (autouse) | ANALYSIS_ENGINE=deterministic forced for string assertions | `tests/test_payroll_multiline_statements.py` |

**Critical isolation rule:**
All tests that assert specific string values (roles, business rules)
force `ANALYSIS_ENGINE=deterministic` in setUp so they do not hit the real LLM.
LLM integration tests use a mocked client.

---
*File 3 of 5 — LLM Analysis Agent*
'''

with open("output/G3_llm_analysis_agent.md", "w", encoding="utf-8") as f:
    f.write(f3)
print(f"G3: {len(f3):,} chars")
