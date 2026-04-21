# Parser Layer

## Purpose

The parser layer is the first technical layer in the COBOL modernization pipeline.

Its role is not to interpret business meaning and not to generate target code.

Its role is to transform raw COBOL input into a deterministic, structured representation that can be safely consumed by downstream AI agents.

The parser layer answers:

- What are the structural components of the code?
- What variables, sections, paragraphs, files, and dependencies exist?
- What control-flow constructs are present?
- What formal representation can be produced before semantic analysis?

## Core Principle

> The parser extracts structure, not meaning.

That means the parser layer should produce:

- repeatable outputs
- grammar-based outputs
- machine-readable outputs
- no business inference unless explicitly rule-based

## Position in the Pipeline

```text
Raw COBOL Input
    ↓
Parser Layer
    ↓
Structured Output (AST + metadata + graphs + JSON)
    ↓
Analysis Agent
    ↓
Conversion Agent
```

## Why the Parser Layer Comes First

If raw COBOL is sent directly to an LLM:

- the model must infer syntax and semantics at the same time
- structural ambiguities may be missed
- hallucinations become more likely
- variable usage and hidden dependencies may be lost

By introducing a parser layer first, the system provides:

- formal structure
- explicit control flow
- dependency extraction
- variable-level traces

This significantly improves the quality of the analysis and conversion stages.

## Inputs

The parser layer may receive:

- COBOL source files (`.cbl`, `.cob`, `.cpy`)
- copybooks
- optional file definitions
- optional program metadata

### Minimal Input

At minimum, the parser layer needs:

- raw COBOL code as text

### Extended Input

In a richer enterprise setting, it may also ingest:

- multiple related COBOL modules
- copybooks
- naming conventions
- file layout descriptors

## Responsibilities of the Parser Layer

### 1. Lexical / Syntactic Parsing

Parse COBOL code according to a formal grammar.

### 2. AST Generation

Build an Abstract Syntax Tree to represent structural logic.

### 3. Data Definition Extraction

Extract data items, variable declarations, levels, PIC clauses, OCCURS, REDEFINES, and related attributes.

### 4. Control Flow Extraction

Identify IF blocks, EVALUATE statements, PERFORM loops, GO TO statements, CALLs, READ/WRITE statements, and related constructs.

### 5. Dependency Extraction

Detect:

- COPYBOOK dependencies
- file references
- DB references where present
- external program calls

### 6. Section and Paragraph Mapping

Map divisions, sections, paragraphs, and execution ordering.

### 7. Usage Mapping

Track variable read/write behavior where possible.

## Outputs of the Parser Layer

The parser layer should produce a bundle of structured artifacts.

### 1. Abstract Syntax Tree (AST)

Example conceptual AST:

```text
IF
├── condition: BALANCE < AMOUNT
├── THEN
│   └── MOVE 'REJECTED' TO STATUS
└── ELSE
    ├── SUBTRACT AMOUNT FROM BALANCE
    └── MOVE 'APPROVED' TO STATUS
```

### 2. Structural JSON

A JSON representation that summarizes the syntax tree in a machine-readable way.

### 3. Symbol Table

Contains:

- variable names
- types
- picture clauses
- hierarchy
- redefinitions
- array-like occurrences

### 4. Control-Flow Summary

Contains:

- branches
- loops
- procedure transitions
- exits

### 5. Dependency Summary

Contains:

- copybooks
- file names
- external program references

### 6. Section / Paragraph Index

Contains:

- division
- section
- paragraph names
- ordering

### 7. Risk Flags (Rule-Based)

Optional parser-generated structural risk markers, such as:

- `REDEFINES` present
- `OCCURS` present
- nested conditionals
- `GO TO` usage
- external file I/O
- SQL blocks

### 8. Warnings

If a construct is detected but not confidently serialized, the parser should emit a warning instead of guessing.

Examples:

- partially supported verbs
- partially classified data definitions
- embedded blocks detected without a dedicated serializer

## Recommended Output Contract

The parser layer should return stable JSON with these top-level fields:

- `program_name`
- `divisions`
- `sections`
- `paragraphs`
- `symbol_table`
- `control_flow`
- `operations`
- `dependencies`
- `risk_flags`
- `warnings`

Example contract:

```json
{
  "program_name": "TXNPROC",
  "divisions": ["DATA DIVISION", "PROCEDURE DIVISION"],
  "sections": ["WORKING-STORAGE SECTION"],
  "paragraphs": [],
  "symbol_table": [
    {
      "name": "BALANCE",
      "level": 1,
      "pic": "9(5)V99",
      "kind": "numeric"
    },
    {
      "name": "AMOUNT",
      "level": 1,
      "pic": "9(5)V99",
      "kind": "numeric"
    },
    {
      "name": "STATUS",
      "level": 1,
      "pic": "X(10)",
      "kind": "string"
    }
  ],
  "control_flow": {
    "branches": [
      {
        "type": "IF",
        "condition": "BALANCE < AMOUNT"
      }
    ],
    "loops": [],
    "calls": []
  },
  "operations": [
    {
      "type": "MOVE",
      "value": "REJECTED",
      "target": "STATUS"
    },
    {
      "type": "SUBTRACT",
      "value": "AMOUNT",
      "target": "BALANCE"
    },
    {
      "type": "MOVE",
      "value": "APPROVED",
      "target": "STATUS"
    }
  ],
  "dependencies": {
    "copybooks": [],
    "files": [],
    "external_calls": []
  },
  "risk_flags": [
    "conditional_logic"
  ],
  "warnings": []
}
```

## Boundary of Responsibility

### The Parser Layer SHOULD:

- identify syntax
- identify structures
- identify variables
- identify formal dependencies
- produce deterministic outputs

### The Parser Layer SHOULD NOT:

- guess business intent
- summarize program purpose in natural language
- infer hidden business rules
- decide complexity semantically
- generate Java or pseudo-code

Those tasks belong to the analysis agent and conversion agent.

## Relationship to the Analysis Agent

The analysis agent consumes parser outputs and enriches them with semantic understanding.

### Parser Layer Output

- structural truth

### Analysis Agent Output

- semantic truth

Example distinction:

- Parser says: `IF BALANCE < AMOUNT`
- Analysis agent says: `reject transaction when insufficient funds`

This separation is essential.

## Recommended Technical Strategy

### Option A — Deterministic Parser + JSON Export

Best for enterprise reliability.

### Option B — Deterministic Parser + Lightweight Rule Engine

Useful for adding risk flags and structural warnings.

### Option C — Parser + Graph Generation

Useful for dependency visualization and chunking.

## Suggested Internal Modules

- `lexer`
- `grammar_parser`
- `ast_builder`
- `symbol_table_builder`
- `dependency_extractor`
- `control_flow_extractor`
- `json_serializer`

## Testing Strategy

The parser layer should be tested independently of the LLM stack.

### Test Dimensions

- syntactic correctness
- AST completeness
- symbol extraction accuracy
- dependency extraction accuracy
- handling of nested logic
- handling of COBOL-specific constructs

## Test Cases

### Test Case 1 — Simple Conditional

#### Input

```cobol
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 BALANCE PIC 9(5)V99 VALUE 1000.
       01 AMOUNT  PIC 9(5)V99 VALUE 200.
       01 STATUS  PIC X(10).

       PROCEDURE DIVISION.
           IF BALANCE < AMOUNT
               MOVE 'REJECTED' TO STATUS
           ELSE
               SUBTRACT AMOUNT FROM BALANCE
               MOVE 'APPROVED' TO STATUS
           END-IF.
```

#### Expected Output (essential fields)

```json
{
  "symbol_table": [
    {"name": "BALANCE", "kind": "numeric"},
    {"name": "AMOUNT", "kind": "numeric"},
    {"name": "STATUS", "kind": "string"}
  ],
  "control_flow": {
    "branches": [
      {"type": "IF", "condition": "BALANCE < AMOUNT"}
    ]
  },
  "operations": [
    {"type": "MOVE", "target": "STATUS"},
    {"type": "SUBTRACT", "target": "BALANCE"},
    {"type": "MOVE", "target": "STATUS"}
  ]
}
```

### Test Case 2 — PERFORM Loop

#### Input

```cobol
       PROCEDURE DIVISION.
           PERFORM VARYING I FROM 1 BY 1 UNTIL I > 10
               ADD I TO TOTAL
           END-PERFORM.
```

#### Expected Output (essential fields)

```json
{
  "control_flow": {
    "loops": [
      {
        "type": "PERFORM_VARYING",
        "iterator": "I",
        "start": "1",
        "step": "1",
        "until": "I > 10"
      }
    ]
  },
  "operations": [
    {"type": "ADD", "value": "I", "target": "TOTAL"}
  ]
}
```

### Test Case 3 — Copybook Detection

#### Input

```cobol
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY CUSTOMER-REC.
```

#### Expected Output

```json
{
  "dependencies": {
    "copybooks": ["CUSTOMER-REC"]
  }
}
```

### Test Case 4 — REDEFINES and OCCURS

#### Input

```cobol
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 CUSTOMER-DATA.
          05 CUSTOMER-ID      PIC 9(5).
          05 CUSTOMER-NAME    PIC X(20).
       01 RAW-DATA REDEFINES CUSTOMER-DATA PIC X(25).
       01 ITEMS.
          05 ITEM-CODE PIC X(3) OCCURS 10 TIMES.
```

#### Expected Output

```json
{
  "symbol_table": [
    {"name": "CUSTOMER-DATA", "kind": "group"},
    {"name": "CUSTOMER-ID", "kind": "numeric"},
    {"name": "CUSTOMER-NAME", "kind": "string"},
    {"name": "RAW-DATA", "kind": "redefines"},
    {"name": "ITEM-CODE", "kind": "array", "occurs": 10}
  ],
  "risk_flags": [
    "redefines_present",
    "occurs_present"
  ]
}
```

## Acceptance Criteria

A parser-layer implementation is acceptable if:

- it produces deterministic outputs
- it captures the main structural artifacts
- it serializes them into a stable JSON contract
- it improves downstream analysis quality
- it handles at least simple and medium COBOL constructs reliably

## Final Summary

The parser layer is a non-LLM structural preprocessing component.

Its mission is to convert raw COBOL into a stable intermediate representation that can later be interpreted semantically by the analysis agent.

> The parser layer makes the rest of the pipeline more reliable by reducing ambiguity before any LLM reasoning begins.
