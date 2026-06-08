# COBOL Modernization Pipeline — Complete Project Documentation
## Overview, Architecture, Decisions, Problems & Solutions

**Date:** 2026-05-10
**Version:** Production-ready foundation (v1.0)
**Overall Score:** 8.5 / 10

---

## 1. What This Project Is

A **COBOL-to-Java modernization pipeline** that takes legacy COBOL source code
(with JCL job control, copybook dependencies, multi-file projects) and produces:

1. A structured semantic analysis of the COBOL program
2. Functionally equivalent Java code
3. Test reports validating the conversion

The pipeline is designed for **real enterprise COBOL** — not toy programs.
It handles OCCURS arrays, EVALUATE TRUE tax tables, PERFORM VARYING loops,
nested copybooks with REPLACING, multi-step JCL jobs, and BigDecimal arithmetic.

---

## 2. Pipeline Stages (In Order)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    INPUT                                            │
│  COBOL source files + JCL files + Copybook libraries                │
└─────────────────────────┬───────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 1 — JCL Parser                                               │
│  Parses job control: EXEC PGM=, DD statements, DISP, DSN            │
│  Output: jcl_manifest (steps, DD bindings, program names)           │
└─────────────────────────┬───────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 2 — Copybook Resolver                                        │
│  Resolves COPY statements across library paths                      │
│  Handles REPLACING with COBOL identifier boundary matching          │
│  Detects circular references                                        │
│  Output: expanded COBOL source (copy-resolved)                      │
└─────────────────────────┬───────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 3 — Hybrid Parser (NEW — replaces heuristic-only)            │
│  Runs TWO parsers simultaneously and merges their output:           │
│                                                                     │
│  Heuristic (cobol_parser.py)    ANTLR (expert grammar)             │
│  ─────────────────────────────  ──────────────────────────────      │
│  symbol_table ✓                 COMPUTE / ADD / SUBTRACT ✓          │
│  paragraphs order ✓             MULTIPLY / DIVIDE ✓                 │
│  MOVE / DISPLAY / ACCEPT ✓      EVALUATE WHEN dispatch ✓            │
│  PERFORM VARYING details ✓      Formal branch detection ✓           │
│  Source line references ✓       Syntax error list ✓                 │
│                                                                     │
│  HybridMerger combines both → one enriched JSON                     │
│  Output: parser_output JSON (symbol_table, operations,              │
│          control_flow, risk_flags, antlr_syntax_ok)                 │
└─────────────────────────┬───────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 4 — Segmenter                                                │
│  Groups paragraphs into logical segments                            │
│  Uses call graph and data flow to determine boundaries              │
│  Output: segment list with paragraph groups                         │
└─────────────────────────┬───────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 5 — Chunker                                                  │
│  Splits large segments into LLM-safe chunks                         │
│  Preserves context boundaries                                       │
│  Output: chunk list with COBOL excerpt + parser JSON slice          │
└─────────────────────────┬───────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 6 — LLM Analysis Agent (NEW — replaces deterministic)        │
│  Sends each chunk to LLM with:                                      │
│    - COBOL source excerpt (column-aware paragraph extraction)       │
│    - Filtered parser JSON for that chunk                            │
│  LLM returns: role, business_rules, risk_flags narrative            │
│  Deterministic layer provides: inputs, outputs, structural flags    │
│  Aggregator rebuilds final analysis artifact                        │
│  Output: analysis JSON (sections, global_purpose, risk_points, ...) │
└─────────────────────────┬───────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 7 — Conversion Agent                                         │
│  Receives parser output + analysis output + COBOL source            │
│  Produces Java class(es) using LLM                                  │
│  Handles BigDecimal, 1-based arrays, EVALUATE TRUE tables           │
│  Output: Java source files                                          │
└─────────────────────────┬───────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 8 — Testing Agent                                            │
│  Generates JUnit tests from analysis                                │
│  Runs behavioral diff (COBOL stdout vs Java stdout)                 │
│  Output: test reports, is_pipeline_green flag                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Key Design Decisions

### 3.1 Why a Hybrid Parser Instead of ANTLR-Only

**The problem with ANTLR-only:**
Building a complete ANTLR visitor from scratch that reliably extracts symbol table
hierarchy (parent/child groups, OCCURS nesting, PIC decoding) would take weeks.
The heuristic parser already does this correctly.

**The problem with heuristic-only:**
The heuristic parser has a critical blind spot: it cannot parse arithmetic verbs
(COMPUTE, ADD, SUBTRACT, MULTIPLY, DIVIDE). For a payroll program with 6 COMPUTE
statements, the heuristic operations[] is completely empty for arithmetic.

**The hybrid solution:**
Take the best of each parser. The heuristic is authoritative for structure.
The ANTLR expert grammar is authoritative for arithmetic and formal control flow.
The HybridMerger combines them with explicit ownership rules and deduplication.

### 3.2 Why LLM for Analysis Instead of Deterministic

**The problem with deterministic analysis:**
The deterministic analysis agent produced garbage output on PAYROLL-CALC:
- 12 of 14 paragraphs got role = "Terminate program execution"
- Business rules were hallucinated ("sum values from 1 to 30 into TOTAL")
- Global purpose was completely wrong

**Root cause:**
The deterministic agent received only parser AST. When operations[] was sparse
(missing COMPUTE), the LLM had nothing to reason from and fabricated from prior context.

**The LLM solution:**
The LLM analysis agent receives BOTH parser output AND raw COBOL source per chunk.
The LLM reads actual code → accurate roles and business rules.
The deterministic layer provides structural facts (inputs, outputs, flags).
The two are overlaid to produce the final analysis.

### 3.3 Why Per-Chunk LLM Calls Instead of One Giant Prompt

One prompt for an entire 14-paragraph program caused the model to mix paragraph
contexts together. Per-chunk calls mean each LLM call only sees the code it is
analyzing, which eliminates cross-paragraph hallucination.

### 3.4 Why Column-Aware Paragraph Source Extraction

COBOL has a fixed-format layout:
- Columns 1-6: sequence numbers
- Column 7: indicator (* = comment, - = continuation, D = debug)
- Columns 8-11: Area A (paragraph names MUST start here)
- Columns 12-72: Area B (statements)

A naive string search for paragraph names would match:
- Comment lines (col 7 = *)
- PERFORM statements referencing the paragraph name
- Continuation lines

Column-aware extraction only matches paragraph names in Area A and skips comment
lines entirely, ensuring the LLM receives clean paragraph source.

---

## 4. The ANTLR Grammar Source

The COBOL85 grammar used in this project was developed by the COBOL language
community and is part of the `antlr/grammars-v4` repository on GitHub.

**Local path in project:** `grammars_v4_master/cobol85/Cobol85.g4`

This grammar covers the full COBOL85 standard including:
- All arithmetic verbs (COMPUTE, ADD, SUBTRACT, MULTIPLY, DIVIDE)
- All control flow (IF, EVALUATE, PERFORM, GO TO)
- All data description entries (PIC clauses, OCCURS, REDEFINES)
- String manipulation (STRING, UNSTRING, INSPECT)
- File I/O verbs (READ, WRITE, OPEN, CLOSE)

The generated Python artifacts (Cobol85Lexer.py, Cobol85Parser.py,
Cobol85Visitor.py, Cobol85Listener.py) were generated from this grammar
at 2026-05-10 03:04 and live in `app/parsers/generated/`.

To regenerate: `./scripts/regenerate_antlr.sh`

---
*File 1 of 5 — Project Overview*
