# COBOL Modernization Pipeline — Full Architecture & Discussion Reference
**Project:** COBOL → Java Modernization Accelerator  
**Stack:** Python backend · GPT-4.1 (Parser/Analysis/Testing) · Claude Opus (Conversion)  
**Date:** 2026-04-22  

---

## Table of Contents
1. [Pipeline Overview](#1-pipeline-overview)
2. [Full Pipeline Flow Diagram](#2-full-pipeline-flow-diagram)
3. [Stage-by-Stage Reference](#3-stage-by-stage-reference)
4. [COPY Book Resolver](#4-copy-book-resolver)
5. [JCL Parsing Layer](#5-jcl-parsing-layer)
6. [Parser Layer Improvements](#6-parser-layer-improvements)
7. [Segmentation & Chunking](#7-segmentation--chunking)
8. [Analysis Agent](#8-analysis-agent)
9. [Conversion Agent & Codex Prompt](#9-conversion-agent--codex-prompt)
10. [Aggregation Layer](#10-aggregation-layer)
11. [Testing Agent](#11-testing-agent)
12. [Model Allocation Strategy](#12-model-allocation-strategy)
13. [Issues Summary from Audit Rounds](#13-issues-summary-from-audit-rounds)

---

## 1. Pipeline Overview

The pipeline is a **white-box, auditable, multi-agent modernization engine** that converts
COBOL programs to semantically equivalent Java. It is structured as strict sequential stages —
no stage runs until its predecessor completes successfully.

### Core Design Principles
- **Deterministic first**: every decision that can be made with pure logic never touches an LLM
- **Semantic fidelity over idiomatic Java**: COBOL runtime behaviour is the source of truth
- **Auditability**: every transformation produces a structured JSON artifact for inspection
- **Graceful degradation**: unresolvable COPY books or missing JCL are flagged, not silently skipped

---

## 2. Full Pipeline Flow Diagram

```
═══════════════════════════════════════════════════════════════════════
                    COBOL MODERNIZATION PIPELINE
═══════════════════════════════════════════════════════════════════════

INPUT LAYER
───────────────────────────────────────────────────────────────────────
  ┌─────────────────────┐     ┌─────────────────────┐
  │   JCL Source Files  │     │  COBOL Source Files  │
  │   (*.jcl, *.proc)   │     │  (*.cbl, *.cob)      │
  └─────────┬───────────┘     └──────────┬───────────┘
            │                            │
            ▼                            │
STAGE 1 — JCL PARSING                   │
            │                            │
  ┌─────────▼───────────┐               │
  │    JCL PARSER        │               │
  │  • Job steps order   │               │
  │  • EXEC PGM=X        │               │
  │  • DD DSN= bindings  │               │
  │  • PARM= values      │               │
  │  • COND= logic       │               │
  │  • SYSLIB paths ◄────┼───────────────┼─ KEY: tells resolver
  └─────────┬───────────┘               │   where copybooks live
            │ JCL Manifest JSON          │
            │                            │
            └────────────┬───────────────┘
                         │
STAGE 2 — COPY BOOK RESOLUTION
                         │
            ┌────────────▼───────────────┐
            │    COPY BOOK RESOLVER       │
            │  1. Get paths from JCL      │
            │  2. Scan COBOL for COPY     │
            │  3. Locate + read .cpy file │
            │  4. Apply REPLACING clause  │
            │  5. Resolve nested COPYs    │
            │  6. Update cross-prog cache │
            │  7. Flag unresolved books   │
            └────────────┬───────────────┘
                         │ EXPANDED COBOL SOURCE
                         │ (no more COPY statements)
                         │
STAGE 3 — COBOL PARSING
                         │
            ┌────────────▼───────────────┐
            │    PREFLIGHT GATE           │
            │    (deterministic Python)   │
            │  • Column structure valid   │
            │  • No phantom paragraphs    │
            │  • No reserved word abuse   │
            │  • No unresolved COPY refs  │
            └────────────┬───────────────┘
                         │ PASS only
            ┌────────────▼───────────────┐
            │    COBOL PARSER             │
            │    (column-aware)           │
            │  • Symbol table (complete)  │
            │  • Control flow graph       │
            │  • Operations list          │
            │  • 88-level conditions      │
            │  • REDEFINES mappings       │
            │  • FD + SELECT bindings     │
            └────────────┬───────────────┘
                         │
STAGE 4 — CONTEXT ENRICHMENT
                         │
            ┌────────────▼───────────────┐
            │   CONTEXT ENRICHER          │
            │  Merges Parser AST          │
            │      + JCL Manifest         │
            │      + Copy Resolution      │
            │  Produces:                  │
            │  • Logical→Physical files   │
            │  • PARM→COBOL variable map  │
            │  • Program execution order  │
            └────────────┬───────────────┘
                         │ Enriched AST JSON
                         │
STAGE 5 — SEGMENTATION + CHUNKING
                         │
            ┌────────────▼───────────────┐
            │   SEGMENTATION LAYER        │
            │  Groups paragraphs by       │
            │  call graph + shared state  │
            └────────────┬───────────────┘
            ┌────────────▼───────────────┐
            │   CHUNKING LAYER            │
            │  (large segments only)      │
            │  Splits preserving loop/    │
            │  branch boundaries          │
            └────────────┬───────────────┘
                         │
STAGE 6 — ANALYSIS AGENT  (GPT-4.1, per segment)
                         │
            ┌────────────▼───────────────┐
            │   ANALYSIS AGENT            │
            │  • Business rule extraction │
            │  • Risk flag identification │
            │  • Data flow per segment    │
            └────────────┬───────────────┘
                         │
STAGE 7 — CONVERSION AGENT  (Claude Opus, per segment)
                         │
            ┌────────────▼───────────────┐
            │   CONVERSION AGENT          │
            │  • Strict codex prompt      │
            │  • Per-segment Java output  │
            │  • JCL context injected     │
            └────────────┬───────────────┘
                         │
STAGE 8 — AGGREGATION
                         │
            ┌────────────▼───────────────┐
            │   AGGREGATOR                │
            │  • Dedup field declarations │
            │  • Type reconciliation      │
            │  • Cross-ref validation     │
            │  • Assemble final Java class│
            └────────────┬───────────────┘
                         │
STAGE 9 — TESTING AGENT
                         │
            ┌────────────▼───────────────┐
            │   TESTING AGENT             │
            │  ┌──────────┬───────────┐  │
            │  │ Parser   │ JCL       │  │
            │  │ Tests    │ Tests     │  │
            │  ├──────────┼───────────┤  │
            │  │Conversion│Behavioral │  │
            │  │ Tests    │ Tests     │  │
            │  └──────────┴───────────┘  │
            │  Output: test_report.json  │
            └────────────┬───────────────┘
                         │
OUTPUT: Java class + test suite + full audit trail
═══════════════════════════════════════════════════════════════════════
```

---

## 3. Stage-by-Stage Reference

| Stage | Component | Model | Input | Output |
|---|---|---|---|---|
| 1 | JCL Parser | None (deterministic) | Raw JCL files | JCL manifest JSON |
| 2 | COPY Resolver | None (deterministic) | JCL paths + COBOL source | Expanded COBOL source |
| 3a | Preflight Gate | None (deterministic) | Expanded source | PASS/FAIL + error list |
| 3b | COBOL Parser | None (deterministic) | Expanded source | Full AST JSON |
| 4 | Context Enricher | None (deterministic) | AST + JCL manifest | Enriched AST JSON |
| 5 | Segmenter + Chunker | None (deterministic) | Enriched AST | Segment manifest JSON |
| 6 | Analysis Agent | GPT-4.1 | Segments | Business rules + risk flags |
| 7 | Conversion Agent | Claude Opus | Segments + analysis | Java method fragments |
| 8 | Aggregator | None (deterministic) | All Java fragments | Single Java class |
| 9 | Testing Agent | GPT-4.1 (generation) | Everything | test_report.json |

---

## 4. COPY Book Resolver

### What It Is
A COPY book is a shared external file containing reusable COBOL data definitions.
`COPY INVDATA.` is replaced by the full content of `INVDATA.cpy` before compilation.
The resolver performs this substitution before your parser runs.

### Before vs. After Expansion

**Before (raw source — what you receive):**
```cobol
DATA DIVISION.
WORKING-STORAGE SECTION.
01 MENU-CHOICE    PIC X    VALUE SPACE.
COPY INVDATA.
01 FOUND-FLAG     PIC X    VALUE 'N'.
```

**After (expanded source — what your parser receives):**
```cobol
DATA DIVISION.
WORKING-STORAGE SECTION.
01 MENU-CHOICE    PIC X    VALUE SPACE.
* >>>BEGIN COPY INVDATA<<<
01 INVENTORY-TABLE.
   05 INV-ENTRY OCCURS 100 TIMES.
      10 INV-NAME      PIC X(20)   VALUE SPACES.
      10 INV-QUANTITY  PIC 9(5)    VALUE ZEROS.
      10 INV-PRICE     PIC 9(5)V99 VALUE ZEROS.
* >>>END COPY INVDATA<<<
01 FOUND-FLAG     PIC X    VALUE 'N'.
```

### Three COPY Variants to Handle

| Variant | Syntax | Handling |
|---|---|---|
| Simple COPY | `COPY INVDATA.` | Find file, insert content |
| COPY with REPLACING | `COPY INVDATA REPLACING ==INV== BY ==SALES==.` | Apply text substitution before insert |
| COPY with library qualifier | `COPY INVDATA IN MYLIB.` | Search specific library path |

### Why JCL Feeds the Resolver

On z/OS, the JCL compile step declares which PDS libraries to search via `SYSLIB DD`:

```jcl
//COMPILE  EXEC PGM=IGYCRCTL
//SYSLIB   DD DSN=SYS1.COPYLIB,DISP=SHR
//         DD DSN=PROJ.INV.COPYLIB,DISP=SHR
//SYSIN    DD DSN=SOURCE.COBOL(INVMGMT),DISP=SHR
```

The `SYSLIB` entries become the `copylib_paths` in the JCL manifest, which populate
the resolver's search path. Without JCL, the resolver doesn't know where to look.

### Three-Tier Degradation Strategy

| Situation | Action |
|---|---|
| Copy book found, fully resolved | ✅ Full parse — symbol table complete |
| Copy book not found, name known | ⚠️ Insert stub symbols marked `"source": "inferred"` — flag for human review |
| Same copy book seen before (other program) | 🔄 Reuse cross-program symbol cache — check for REPLACING variants |

### Cross-Program Copy Book Cache

```json
{
  "INVDATA": {
    "path": "/copybooks/INVDATA.cpy",
    "symbols": ["INVENTORY-TABLE", "INV-ENTRY", "INV-NAME", "INV-QUANTITY", "INV-PRICE"],
    "used_by": ["INVMGMT", "INVRPT", "INVUPD"],
    "replacing_variants": [
      { "program": "SALESRPT", "replacing": [{"old": "INV", "new": "SALES"}] }
    ]
  }
}
```

### Full Python Implementation

```python
import os, re
from dataclasses import dataclass

COPY_LIBRARY_CONFIG = {
    "default": ["/cobol/copybooks/", "/cobol/copybooks/common/"],
    "MYLIB": "/cobol/copybooks/mylib/",
    "SYSLIB": "/cobol/copybooks/system/"
}
COPY_EXTENSIONS = [".cpy", ".cbl", ".copy", ".CBY", ""]

@dataclass
class CopyResolutionResult:
    expanded_source: str
    resolved_copybooks: list
    unresolved_copybooks: list
    errors: list

def find_copy_book(name, library="default"):
    search_paths = COPY_LIBRARY_CONFIG.get(library, COPY_LIBRARY_CONFIG["default"])
    for base_path in search_paths:
        for ext in COPY_EXTENSIONS:
            for candidate in [name + ext, name.upper() + ext]:
                full = os.path.join(base_path, candidate)
                if os.path.isfile(full):
                    return full
    return None

def parse_replacing_clause(replacing_str):
    pairs = []
    pattern = r'==([^=]+)==\s+BY\s+==([^=]+)=='
    for m in re.finditer(pattern, replacing_str, re.IGNORECASE):
        pairs.append((m.group(1).strip(), m.group(2).strip()))
    return pairs

def apply_replacing(content, replacing_pairs):
    for old, new in replacing_pairs:
        content = re.sub(r'\b' + re.escape(old) + r'\b', new, content, flags=re.IGNORECASE)
    return content

def resolve_copy_books(source_lines, depth=0, resolved_stack=None, result=None):
    if resolved_stack is None: resolved_stack = set()
    if result is None:
        result = CopyResolutionResult("", [], [], [])
    if depth > 10:
        result.errors.append("COPY nesting depth exceeded 10 — possible circular reference")
        return result

    COPY_PATTERN = re.compile(
        r'^\s{11,}COPY\s+([A-Z0-9#@$\-]+)'
        r'(?:\s+IN\s+([A-Z0-9\-]+))?'
        r'(?:\s+REPLACING\s+(.*?))?\.$',
        re.IGNORECASE
    )
    expanded = []
    for lineno, line in enumerate(source_lines, 1):
        if len(line) >= 7 and line[6] in ('*', '/'):
            expanded.append(line)
            continue
        m = COPY_PATTERN.match(line.rstrip())
        if not m:
            expanded.append(line)
            continue
        copy_name = m.group(1).upper()
        library   = (m.group(2) or "default").upper()
        replacing = parse_replacing_clause(m.group(3) or "")
        copy_key  = f"{library}/{copy_name}"
        if copy_key in resolved_stack:
            result.errors.append(f"Line {lineno}: Circular COPY: {copy_key}")
            continue
        path = find_copy_book(copy_name, library)
        if not path:
            result.unresolved_copybooks.append(copy_name)
            result.errors.append(f"Line {lineno}: COPY book not found: {copy_name}")
            expanded.append(f"      * >>>UNRESOLVED COPY: {copy_name}<<<\n")
            continue
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            copy_lines = f.readlines()
        if replacing:
            content = apply_replacing(''.join(copy_lines), replacing)
            copy_lines = content.splitlines(keepends=True)
        resolved_stack.add(copy_key)
        resolve_copy_books(copy_lines, depth+1, resolved_stack, result)
        resolved_stack.discard(copy_key)
        expanded.append(f"      * >>>BEGIN COPY {copy_name} FROM {path}<<<\n")
        expanded.extend(copy_lines)
        expanded.append(f"      * >>>END COPY {copy_name}<<<\n")
        result.resolved_copybooks.append({
            "name": copy_name, "path": path,
            "library": library, "line": lineno, "replacing": replacing
        })
    result.expanded_source = ''.join(expanded)
    return result
```

---

## 5. JCL Parsing Layer

### What JCL Provides to the Pipeline

| JCL Element | What It Tells You | Pipeline Use |
|---|---|---|
| `EXEC PGM=X` | Which COBOL program runs | Links JCL step to COBOL source file |
| `DD DSN=X` | Physical file bound to logical FD name | Resolves COBOL `SELECT` → real data source |
| `PARM='...'` | Runtime parameters passed to program | Maps to COBOL `ACCEPT` from `SYSIN` or `LINKAGE` |
| `COND=(n,op,step)` | Conditional step execution | Models error handling flow |
| `SYSLIB DD` | Copy book library search paths | Feeds COPY resolver |
| `PROC` definitions | Reusable job step templates | Expanded before step-level analysis |

### JCL Manifest JSON Structure

```json
{
  "job_name": "INVJOB01",
  "steps": [
    {
      "step_name": "COMPILE",
      "pgm": "IGYCRCTL",
      "copylib_paths": ["SYS1.COPYLIB", "PROJ.INV.COPYLIB"],
      "source": "SOURCE.COBOL(INVMGMT)"
    },
    {
      "step_name": "RUN",
      "pgm": "INVMGMT",
      "parm": "MODE=BATCH",
      "dd_bindings": {
        "INVFILE": "PROD.INV.MASTER",
        "RPTFILE": "PROD.INV.REPORT",
        "SYSIN":   "*inline*"
      },
      "cond": null
    }
  ],
  "execution_order": ["INVMGMT"],
  "copylib_paths": ["SYS1.COPYLIB", "PROJ.INV.COPYLIB"]
}
```

### JCL Parser — Key Elements to Extract

```python
JCL_PATTERNS = {
    "job":      re.compile(r'^//(\w+)\s+JOB\s+(.*)$'),
    "exec_pgm": re.compile(r'^//(\w+)\s+EXEC\s+PGM=(\w+)(?:,PARM='([^']*)')?'),
    "exec_proc":re.compile(r'^//(\w+)\s+EXEC\s+(?!PGM)(\w+)'),
    "dd_dsn":   re.compile(r'^//(\w+)\s+DD\s+DSN=([^,\s]+)'),
    "dd_concat":re.compile(r'^//\s+DD\s+DSN=([^,\s]+)'),   # DD concatenation
    "syslib":   re.compile(r'^//SYSLIB\s+DD\s+DSN=([^,\s]+)'),
    "cond":     re.compile(r'COND=\((\d+),(\w+)(?:,(\w+))?\)'),
    "comment":  re.compile(r'^//\*'),
    "proc_def": re.compile(r'^//(\w+)\s+PROC\s*(.*)$'),
    "pend":     re.compile(r'^//\s+PEND\s*$'),
}
```

---

## 6. Parser Layer Improvements

### Column Layout (Fixed-Format COBOL)

| Columns | Zone | Purpose |
|---|---|---|
| 1–6 | Sequence area | Line numbers — strip before tokenization |
| 7 | Indicator | `*`=comment, `/`=page eject, `-`=continuation, `D`=debug |
| 8–11 | Area A | Divisions, Sections, Paragraphs, FD, 01/77 level items |
| 12–72 | Area B | Statements, subordinate items (02–49), inline code |
| 73–80 | Identification | Compiler listing only — ignored |

### Paragraph Name Validation Guard

```python
import re

VALID_PARAGRAPH_NAME = re.compile(r'^[A-Z0-9][A-Z0-9\-]{0,29}$')

COBOL_RESERVED_WORDS = {
    'ACCEPT','ADD','ALTER','CALL','CANCEL','CLOSE','COMPUTE','CONTINUE',
    'DELETE','DISPLAY','DIVIDE','ELSE','END','EVALUATE','EXIT','GO','IF',
    'INITIALIZE','INSPECT','MERGE','MOVE','MULTIPLY','OPEN','PERFORM',
    'READ','RELEASE','RETURN','REWRITE','SEARCH','SET','SORT','START',
    'STOP','STRING','SUBTRACT','UNSTRING','WRITE','SECTION','DIVISION',
    'WORKING-STORAGE','PROCEDURE','DATA','ENVIRONMENT','IDENTIFICATION'
}

def is_valid_paragraph_name(name: str, column: int) -> bool:
    if not (8 <= column <= 11):         return False
    if not VALID_PARAGRAPH_NAME.match(name): return False
    if name in COBOL_RESERVED_WORDS:    return False
    return True
```

### 88-Level Condition Names

```cobol
01 FOUND-FLAG    PIC X    VALUE 'N'.
   88 ITEM-FOUND         VALUE 'Y'.
   88 ITEM-NOT-FOUND     VALUE 'N'.
```

Must generate:
```java
private char foundFlag = 'N';
private boolean isItemFound()    { return foundFlag == 'Y'; }
private boolean isItemNotFound() { return foundFlag == 'N'; }
```

### Full Parser Enhancement Checklist

| Enhancement | Priority | Complexity |
|---|---|---|
| Column-aware tokenizer (Area A/B enforcement) | 🔴 Critical | Medium |
| Paragraph name regex guard | 🔴 Critical | Low |
| Section vs. paragraph discriminator | 🔴 Critical | Medium |
| 88-level condition name extraction | 🟡 High | Low |
| PERFORM THRU range resolution | 🟡 High | Medium |
| REDEFINES detection + union-type flag | 🟡 High | Medium |
| Continuation line merging (col 7 = `-`) | 🟡 High | Low |
| Sequence number stripping (cols 1–6) | 🟡 High | Low |
| INITIALIZE verb semantics | 🟢 Medium | Low |
| PIC clause full symbol grammar (Z,*,+,-,.,B,0) | 🟢 Medium | Low |
| SEARCH / SEARCH ALL table handling | 🟢 Medium | Medium |
| Subscripted variable read-detection in DISPLAY | 🟢 Medium | Low |

### Preflight Validation Gate

```python
def preflight_validate(parser_output: dict) -> list[str]:
    errors = []
    symbol_names = {s['name'] for s in parser_output['symbol_table']}
    known_paragraphs = set(parser_output['paragraphs'])

    for para in parser_output['paragraphs']:
        if para in symbol_names:
            errors.append(f"CONFLICT: '{para}' is both a paragraph and a symbol")

    for call in parser_output['control_flow']['calls']:
        if call['to'] not in known_paragraphs:
            errors.append(f"PHANTOM CALL: '{call['to']}' called but not a known paragraph")

    for loop in parser_output['control_flow']['loops']:
        if loop.get('iterator') and loop['iterator'] not in symbol_names:
            errors.append(f"UNKNOWN ITERATOR: '{loop['iterator']}' not in symbol table")

    for para in parser_output['paragraphs']:
        if para in COBOL_RESERVED_WORDS:
            errors.append(f"RESERVED WORD AS PARAGRAPH: '{para}'")

    return errors
```

---

## 7. Segmentation & Chunking

### Segmenter Python Pseudocode

```python
from dataclasses import dataclass, field

@dataclass
class Segment:
    id: str
    paragraphs: list
    reads: set
    writes: set
    calls: list
    called_by: list
    business_rules: list
    complexity: str  # "low" | "medium" | "high"

def score_complexity(paragraphs, parser_output):
    score = 0
    score += len([l for l in parser_output['control_flow']['loops']
                  if l['paragraph'] in paragraphs]) * 3
    score += len([b for b in parser_output['control_flow']['branches']
                  if b['paragraph'] in paragraphs]) * 2
    score += len([o for o in parser_output['operations']
                  if o['paragraph'] in paragraphs]) * 0.5
    if score < 5:  return "low"
    if score < 15: return "medium"
    return "high"  # triggers chunking layer
```

### Chunking Rules
- **Never cut inside a `PERFORM VARYING` block**
- **Never split an `EVALUATE` or `IF/ELSE` across chunks**
- **Each chunk carries its relevant symbol context as a header**
- Chunking only activates when `complexity == "high"`

---

## 8. Analysis Agent

### Input (per segment)
```json
{
  "program_name": "INVENTORY-MANAGEMENT",
  "resolved_call_graph": [...],
  "symbol_table": [...],
  "paragraphs": [...],
  "business_rule_hints": [...]
}
```

### Output Contract
```json
{
  "sections": [
    {
      "name": "ADD-ITEM",
      "role": "...",
      "business_rules": [...],
      "is_dead_code": false,
      "called_by": ["PROCESS-CHOICE"],
      "calls": []
    }
  ],
  "business_rules": [...],
  "warnings": [...]
}
```

### Known False Positive — W002 on Subscripted Variables
`DISPLAY "Item Qty: " INV-QUANTITY(I)` registers `INV-QUANTITY` as written-but-never-read
because the parser does not walk subscripted DISPLAY operands for read-set registration.
**Fix:** walk all DISPLAY operand tokens; any identifier in the symbol table = read operation.

---

## 9. Conversion Agent & Codex Prompt

### 12 Mandatory Rules (inject as SYSTEM prompt)

| Rule | COBOL Construct | Required Java Translation |
|---|---|---|
| 1 | `PERFORM X UNTIL cond` | `while (!cond) { x(); }` — never `do-while` |
| 2 | `PERFORM VARYING I FROM 1 BY 1 UNTIL I > 100` | `for (int i = 0; i < 100; i++)` with 0-based array access |
| 3 | `PIC 9(5)V99` + `ACCEPT` | `readImpliedDecimal(5, 2)` — no explicit decimal point |
| 4 | `EVALUATE WHEN` dispatch | All `PERFORM` inside `WHEN` are live calls — never dead code |
| 5 | `IF name = SPACES` | `name.isBlank()` |
| 6 | `IF X = Y` on PIC X fields | `x.stripTrailing().equals(y.stripTrailing())` |
| 7 | `EXIT PERFORM` | `break` — never `return` |
| 8 | `STOP RUN` | End of `mainParagraph()` — no `System.exit()` |
| 9 | `MOVE SPACES/ZEROS` | `" ".repeat(n)` / `0` / `BigDecimal.ZERO` by PIC type |
| 10 | Any `PIC 9(n)Vdd` field | `BigDecimal` — never `float` or `double` |
| 11 | `VALUE SPACES/ZEROS` in DATA DIV | Initialize all array slots in constructor |
| 12 | Validation requirement | Generate JUnit 5 behavioral tests covering all paths |

### `readImpliedDecimal` Implementation

```java
private BigDecimal readImpliedDecimal(int intDigits, int decDigits) {
    while (true) {
        String raw = scanner.nextLine().trim();
        try {
            String digits = raw.replaceAll("[^0-9]", "");
            int total = intDigits + decDigits;
            while (digits.length() < total) digits = "0" + digits;
            if (digits.length() > total) digits = digits.substring(digits.length() - total);
            String intPart = digits.substring(0, digits.length() - decDigits);
            String decPart = digits.substring(digits.length() - decDigits);
            return new BigDecimal(intPart + (decDigits > 0 ? "." + decPart : ""));
        } catch (Exception e) {
            System.out.print("Invalid input. Enter " + (intDigits + decDigits) + " digits only: ");
        }
    }
}
```

---

## 10. Aggregation Layer

### Responsibilities
1. Deduplicate field declarations (same symbol declared in multiple segments)
2. Type reconciliation — `BigDecimal` always wins over `int`/`double`
3. Promote shared-state variables to instance fields
4. Validate cross-references — every method call has a matching method body
5. Assemble final Java class with package, imports, constructor, `main()`

### Type Reconciliation Rule

```python
TYPE_PRIORITY = {"BigDecimal": 3, "String": 2, "int": 1, "double": 0}

def reconcile_type(type_a, type_b):
    return type_a if TYPE_PRIORITY.get(type_a, 0) >= TYPE_PRIORITY.get(type_b, 0) else type_b
```

### Cross-Reference Validation

```python
def validate_cross_refs(converted_segments):
    all_methods = {seg['method_name'] for seg in converted_segments}
    errors = []
    for seg in converted_segments:
        for call in seg['outbound_calls']:
            if call not in all_methods:
                errors.append(f"{seg['id']} calls '{call}' — no matching method found")
    return errors
```

---

## 11. Testing Agent

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      TESTING AGENT                              │
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐                    │
│  │ PARSER TESTS     │  │ JCL TESTS        │                    │
│  │ (deterministic)  │  │ (deterministic)  │                    │
│  │ • Column parsing │  │ • DD binding     │                    │
│  │ • Symbol table   │  │ • PARM parsing   │                    │
│  │ • Call graph     │  │ • Step ordering  │                    │
│  │ • Preflight gate │  │                  │                    │
│  └──────────────────┘  └──────────────────┘                    │
│  ┌──────────────────┐  ┌──────────────────┐                    │
│  │ CONVERSION TESTS │  │ BEHAVIORAL TESTS │                    │
│  │ (JavaParser AST) │  │ (GnuCOBOL+Java)  │                    │
│  │ • No float/double│  │ • Identical input│                    │
│  │ • No do-while    │  │ • stdout diff    │                    │
│  │ • Array sizes    │  │ • All menu paths │                    │
│  │ • BigDecimal     │  │ • Edge cases     │                    │
│  └──────────────────┘  └──────────────────┘                    │
│                                                                 │
│  OUTPUT: test_report.json                                       │
│  { parser_tests, jcl_tests, conversion_tests, behavioral_tests  │
│    is_pipeline_green: true/false }                              │
└─────────────────────────────────────────────────────────────────┘
```

### Business Rule → Test Case Mapping

| Business Rule | Generated Test |
|---|---|
| Capacity capped at 100 items | Fill 100 items, assert "Inventory is full" on item 101 |
| First empty slot used | Delete index 3, add new item, assert it lands at index 3 |
| Empty = spaces only | Add item with `"   "` name, verify treated as empty slot |
| Only first match updated | Two items same name, update, assert only first changed |
| Deletion clears all fields | Delete item, report, assert absent AND qty/price = 0 |
| Only non-empty slots in report | Empty inventory, run report, assert no item lines |

### JUnit 5 Test Template

```java
@Test
void testAddItem_thenReport() {
    String input = "1\nApple               \n50\n150\n4\n0\n";
    System.setIn(new ByteArrayInputStream(input.getBytes()));
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    System.setOut(new PrintStream(out));
    new InventoryManagement().mainParagraph();
    String output = out.toString();
    assertTrue(output.contains("Item added successfully!"));
    assertTrue(output.contains("Item Name     : Apple"));
}
```

---

## 12. Model Allocation Strategy

| Stage | Component | Model | Reason |
|---|---|---|---|
| 1 | JCL Parser | None | Pure regex/pattern matching |
| 2 | COPY Resolver | None | Deterministic file I/O |
| 3 | Parser + Preflight | None | Deterministic grammar rules |
| 4 | Context Enricher | None | Deterministic JSON merge |
| 5 | Segmenter/Chunker | None | Graph traversal algorithm |
| 6 | Analysis Agent | GPT-4.1 | Pattern recognition from structured JSON |
| 7 | Conversion Agent | Claude Opus | Strict semantic rule following |
| 8 | Aggregator | None | Deterministic type reconciliation |
| 9a | Test Generation | GPT-4.1 | Templating from structured JSON |
| 9b | Test Execution | None | Python/shell scripting |

---

## 13. Issues Summary from Audit Rounds

### Round 1 Issues

| # | Severity | Layer | Issue |
|---|---|---|---|
| 1 | 🔴 HIGH | Parser | EVALUATE-dispatched PERFORM calls not in call graph |
| 2 | 🔴 HIGH | Validator | Structural-only comparison — misses runtime divergence |
| 3 | 🟡 MEDIUM | Conversion | `do-while` for pre-test PERFORM UNTIL |
| 4 | 🟡 MEDIUM | Conversion | Explicit decimal input vs. implied decimal (PIC V) |
| 5 | 🟢 LOW | Analysis | `global_outputs` polluted with DISPLAY literal tokens |
| 6 | 🟢 LOW | Conversion | `trim()` vs `isBlank()` for empty-name check |

### Round 2 Status

| # | Issue | Status |
|---|---|---|
| 1 | EVALUATE dispatch call graph | ✅ Fixed |
| 2 | Validator structural-only | ❌ Still not fixed |
| 3 | `do-while` for PERFORM UNTIL | ❌ Still not fixed |
| 4 | Implied decimal input | ❌ Still not fixed |
| 5 | `global_outputs` pollution | ✅ Fixed |
| 6 | `trim()` vs `isBlank()` | ✅ Fixed (but NPE risk added) |
| **NEW** | `equals()` without `stripTrailing()` in update/delete | ❌ Regression |

---

*Full Architecture Reference — COBOL Modernization Accelerator — 2026-04-22*
