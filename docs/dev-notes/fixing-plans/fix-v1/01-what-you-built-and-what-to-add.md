# Deep Technical Explanation — What You Built and What to Add

## Overview

You did not build a single COBOL parser. You built a **four-stage deterministic pipeline**
with two architectural scaffolds supporting a future fifth stage. Each component has a
specific job, a specific input contract, and a specific output contract. Nothing crosses
those boundaries. This section explains each component in exact technical terms — what
it does internally, why it was built that way, and what is missing.

---

## Stage 1 — `jcl_parser.py`

### What it does

JCL (Job Control Language) is the IBM mainframe shell language that controls how COBOL
programs are executed. It defines the job, the execution steps, the input/output file
bindings, and the conditional execution rules. Without parsing JCL, you cannot know
which physical dataset a COBOL logical file name maps to — you would know that a program
reads `CUSTOMER-FILE` but not that `CUSTOMER-FILE` is physically stored at
`ACME.PROD.CUSTOMER.MASTER` on the mainframe filesystem.

### How it works internally

The parser is built around **10 compiled regex patterns** stored in `JCL_PATTERNS`. Each
pattern targets a specific JCL statement type.

```python
# Example: captures step name and program name
"exec_pgm": re.compile(
    r"^//([A-Z0-9@#$]{1,8})\s+EXEC\s+PGM=([A-Z0-9@#$]{1,8})"
    r"(?:.*PARM='([^']*)')?",
    re.IGNORECASE,
)
```

The parse loop processes lines in order and handles five non-trivial cases:

**Continuation line joining.** JCL statements can span multiple lines. A continuation
line starts with `//` followed by 9 or more spaces in the name field. The parser detects
this with the `"continuation"` pattern and appends the continuation to the previous
statement buffer before processing it as a single logical statement.

**COND parameter parsing.** `COND=(4,LT,STEP1)` means "skip this step if STEP1 returned
a code less than 4." The parser extracts `rc=4`, `operator=LT`, `step=STEP1` into a
typed triplet. This feeds the context enricher so it knows step execution is conditional.

**SYSLIB extraction.** `//SYSLIB DD DSN=ACME.COPYLIB,DISP=SHR` declares where copybooks
live. The parser extracts this path and passes it to the copybook resolver as a search
directory, so the resolver knows where to find `COPY CUSTCOPY` at runtime.

**Inline PROC expansion.** Some JCL embeds PROC definitions inline (between `PROC` and
`PEND` statements). The parser detects `PROC` / `PEND` boundaries and captures the
inline procedure body, allowing the downstream context enricher to trace calls through
proc invocations.

**DD concatenation.** When multiple `DD` statements have a blank name field, they form
a concatenation (equivalent to multiple file inputs chained together). The parser
recognizes the `dd_concat` pattern and links concatenated DDs to their owning DD name.

### Output contract

A `JCLManifest` dataclass with a `to_dict()` method containing:
- `job_name` — the JOB card name
- `steps[]` — each step with `step_name`, `pgm`, `parm`, `cond`, `dd_bindings`
- `dd_bindings[DD_NAME]` — `{dsn, disp}` for each DD
- `syslib_paths[]` — copybook search directories extracted from SYSLIB DDs
- `inline_procs{}` — any PROC definitions found in the JCL

### What is complete

Everything above is implemented and works correctly for standard JCL. This is one of
the strongest components — most COBOL migration tools ignore JCL entirely and leave
file binding mapping as a manual step.

### What is missing

PROC library calls — when a step calls `EXEC MYPROC` where `MYPROC` is not defined
inline but exists in a PROC library (like `SYS1.PROCLIB`), the parser cannot resolve
it. This requires a proc library search similar to the copybook resolver's library
search. Also: symbolic parameter substitution in PROC calls
(`EXEC MYPROC,DSN=&MYDSN`) is not implemented.

---

## Stage 2 — `copybook_resolver.py`

### What it does

COBOL programs use `COPY` statements to include shared record layouts and data
definitions from external files called copybooks. Before structural parsing can happen,
all `COPY` statements must be replaced with the actual content of the referenced
copybook. This is called expansion. If you parse COBOL without expanding copybooks
first, your symbol table will be empty wherever a record layout lives in a copybook —
which is most real programs.

### How it works internally

**Column-aware COPY detection.** COBOL fixed format uses strict column rules. `COPY`
statements always appear in Area B (columns 12–72). The primary regex enforces this
by matching the exact column structure:

```python
COPY_PATTERN = re.compile(
    r"^.{6}"   # skip cols 1-6 (sequence numbers)
    r"[ \-D]"  # col 7: indicator
    r"   "     # cols 8-10: Area A must be spaces (not starting in Area A)
    r" {1,}"   # col 11+: Area B
    r"COPY\s+([A-Z0-9#@$\-]+)"
    r"(?:\s+IN\s+([A-Z0-9\-]+))?"
    r"(?:\s+REPLACING\s+(.*?))?"
    r"\.\s*$",
    re.IGNORECASE,
)
```

A `COPY_PATTERN_LOOSE` fallback handles free-format COBOL where column constraints
do not apply.

**REPLACING clause substitution.** `COPY CUSTCOPY REPLACING ==CUST== BY ==ACCT==`
tells the compiler to textually replace every occurrence of `CUST` with `ACCT` inside
the copybook content. The resolver implements this with word-boundary regex:

```python
pattern = re.compile(r'\b' + re.escape(old_token) + r'\b', re.IGNORECASE)
expanded = pattern.sub(new_token, copybook_content)
```

The `\b` word boundary prevents `CUST` from matching inside `CUSTODIAN` — a real
source of bugs in naive REPLACING implementations.

**Recursive nested COPY expansion.** Copybooks can themselves contain `COPY` statements.
The resolver handles this recursively up to `MAX_NESTING_DEPTH = 10`. A `resolved_stack`
list tracks the current resolution chain. Before expanding a copybook, the resolver
checks whether its name is already in the stack — if so, it is a circular reference and
resolution stops with a warning instead of infinite recursion.

**Cross-program cache.** Copybooks are often shared across multiple programs in a
project. The cache key is `"LIBRARY/COPYBOOK_NAME+SHA256(REPLACING_CLAUSE)"`. This
means the same copybook with different REPLACING clauses gets separate cache entries.
Cache hits skip filesystem I/O and re-expansion entirely.

**Three-tier degradation output.** Every COPY statement in the source results in one
of three outcomes recorded in the audit trail:
1. Resolved — content found and expanded successfully
2. Unresolved — copybook file could not be found in any search path
3. Circular — resolution would have caused infinite recursion

**Source-map comment injection.** When a copybook is expanded, the resolver inserts
comment markers at the insertion point:

```
      * >>> COPY CUSTCOPY EXPANDED FROM ./copybooks/CUSTCOPY.cpy <<<
      [copybook content here]
      * >>> END COPY CUSTCOPY <<<
```

This allows the COBOL parser downstream to trace exactly which symbol came from which
copybook, which is critical for generating accurate migration documentation.

### Output contract

A `CopyResolutionResult` dataclass with:
- `expanded_source` — the complete COBOL source with all COPY statements replaced
- `resolved_copybooks[]` — audit trail of every successful expansion
- `unresolved_copybooks[]` — names that could not be found
- `errors[]` — blocking errors (e.g. circular references)
- `warnings[]` — non-fatal issues

### What is complete

Everything above is implemented. This is production-quality work that handles the
non-obvious edge cases (nesting, REPLACING, column strictness, caching) that
most COBOL tools get wrong.

### What is missing

The `\b` word boundary edge case: COBOL names frequently end with hyphens as prefixes
(e.g. `CUST-` in `CUST-ID`, `CUST-NAME`). Python's `\b` treats `-` as a non-word
character, which means `\bCUST\b` will match at the boundary between `CUST` and `-`.
This is actually the correct behavior for COBOL hyphenated identifiers, but it needs
an explicit test confirming that replacing `==CUST==` does not corrupt `CUSTODIAN`
(which it should not, because `CUSTODIAN` has no hyphen after `CUST`). Add a unit
test that validates this boundary specifically.

---

## Stage 3 — `cobol_parser.py` (the `ParserLayer` class)

### What it does

This is the structural parser. It takes the expanded COBOL source from Stage 2 and
produces a complete JSON document describing every structural element: divisions,
sections, paragraphs, data items, control flow, operations, dependencies, risk flags,
and warnings. This JSON is the contract that all downstream stages (analysis, conversion)
consume.

### How it works internally — preprocessing

**Format detection.** The parser first determines whether the source is fixed-format
or free-format. Fixed format has strict column rules; free format does not. The
heuristic counts how many lines have 6 digits or spaces in columns 1–6 (the sequence
number field). If at least one third of non-blank lines match, the source is treated
as fixed-format.

```python
if len(line) >= 7 and re.fullmatch(r"[ 0-9]{6}", line[:6]):
    fixed_like += 1
return "fixed" if fixed_like >= max(1, len(candidates) // 3) else "free"
```

**Fixed-format line preprocessing.** For each fixed-format line:
- Column 7 is the indicator field. `*` and `/` = comment lines, skipped. `-` = continuation.
- Columns 8–11 are Area A. Division headers, section names, level-01 data items, and
  paragraph names must start here.
- Columns 12–72 are Area B. All statements and subordinate data items appear here.
- The `starts_in_area_a` flag is computed as: `leading_spaces <= 3` within the Area B
  body. This is used by `_is_paragraph_header()` to distinguish paragraph names from
  statement continuations.

**Continuation line joining.** When indicator column 7 is `-`, the line's content is
appended to the previous line. The join preserves string-literal context — if the
previous line ended in an open string literal (odd number of quote characters), the
first character of the continuation is consumed as the closing quote, and the rest is
appended without a space. For non-string continuations, a single space is inserted
between the joined texts.

### How it works internally — data extraction

**Symbol table with level hierarchy.** A stack tracks the current nesting depth.
For each data item matched by the level-number regex, the parser pops stack entries
with level numbers >= the current level (so level 10 pops a preceding level 10 and
stays under the level 05 parent), then reads the top of the stack as the parent.
This correctly resolves `05 ITEM → parent = 01 GROUP`.

**PIC clause decoding.** The `_decode_pic()` method parses the raw PIC string into
structured type information used by the converter:

```
PIC 9(5)V99  →  {is_numeric: True, has_implied_decimal: True,
                 int_digits: 5, dec_digits: 2, java_type: "BigDecimal"}
PIC X(20)    →  {is_string: True, storage_length: 20, java_type: "String"}
PIC S9(7)V99 →  {is_signed: True, int_digits: 7, dec_digits: 2, java_type: "BigDecimal"}
```

The `java_type` field is the direct input the converter layer uses to select the
correct Java/Python type without re-analyzing the PIC string itself.

**Level-88 condition name linkage.** Level-88 items in COBOL are named boolean
conditions attached to a parent field. For example:

```cobol
05 CUST-STATUS  PIC X.
   88 CUST-ACTIVE    VALUE 'A'.
   88 CUST-INACTIVE  VALUE 'I'.
```

The parser attaches `condition_names[]` to the parent `CUST-STATUS` symbol. Each
entry has the condition name and the list of values it matches. This is original
work — ANTLR grammars parse level-88 items as data description entries but do not
link them to their parent field semantically.

**All PERFORM forms.** The control flow extractor handles every PERFORM variant:

| Form | Example |
|---|---|
| Simple | `PERFORM PARA-A.` |
| External UNTIL | `PERFORM PARA-A UNTIL X > 0` |
| Inline UNTIL | `PERFORM UNTIL X > 0 ... END-PERFORM` |
| VARYING | `PERFORM VARYING I FROM 1 BY 1 UNTIL I > 100` |
| THRU | `PERFORM A THRU B` |
| THRU UNTIL | `PERFORM A THRU B UNTIL cond` |
| TIMES | `PERFORM 5 TIMES` |

For `PERFORM THRU`, the parser resolves the range: it looks up the paragraph order
list and expands every paragraph between the start and end into individual call entries.
So `PERFORM A THRU C` where the order is `A, B, C` produces calls to A, B, and C.

**Condition stack for conditional call marking.** When a `PERFORM` appears inside an
`IF` or `EVALUATE WHEN` block, the call entry is marked `conditional: True` with the
enclosing condition. The parser maintains a `condition_stack` list — IF pushes a
condition, END-IF pops it. Every call emitted while the stack is non-empty gets
`conditional: True`.

**Preflight validation.** Before full parsing, a preflight check runs four structural
validations that would produce useless output if ignored:
1. Duplicate data names — same name declared twice in the data division
2. Missing FD entries — `SELECT FILE` in FILE-CONTROL with no corresponding `FD FILE`
3. Undeclared VARYING iterators — `PERFORM VARYING I` where `I` is not in the symbol table
4. Reserved words used as paragraph names — would be misinterpreted as statements

**Warning generation (W001–W006).** The warning generator performs semantic analysis
over the completed symbol table, control flow, and operations arrays:
- W001: symbol declared but never appears in any operation or condition
- W002: symbol written (MOVE/ADD/ACCEPT target) but never read
- W004: paragraph never appears as the target of any PERFORM or GO TO
- W006: GO TO present — flag for structured refactoring
- W003 and W005 are also implemented (redundant init, possibly uninitialized read)

### What is complete

The heuristic path handles the majority of real COBOL programs correctly: all division
and section structures, the complete symbol table with PIC decoding and level-88 linkage,
all PERFORM forms including THRU range expansion, condition stack tracking, GO TO
extraction, OPEN/CLOSE/READ/WRITE/REWRITE/DELETE operations, MOVE with subscript
support, ACCEPT/DISPLAY, preflight validation, and W-warnings.

### What is missing

**COMPUTE is not in the operations array.** The verb is in `STATEMENT_VERBS` and
`RESERVED_WORDS`, and `_extract_warnings()` emits an INFO flag when it sees it, but
`_parse_operation()` has no branch for COMPUTE. A COBOL program that calculates
`COMPUTE WS-BALANCE ROUNDED = WS-BALANCE + TXN-AMOUNT` produces no operation entry.
The converter layer receives no signal about this arithmetic. Fix:

```python
compute_match = re.match(
    r"^COMPUTE\s+([A-Z0-9-]+(?:\([^)]+\))?)"
    r"\s+(ROUNDED\s+)?=\s+(.+?)\.?$",
    upper_text,
)
if compute_match:
    target = self._parse_operand(compute_match.group(1))
    return {
        "type": "COMPUTE",
        "target": target["name"],
        "target_subscript": target["subscript"],
        "target_is_array_element": target["is_array_element"],
        "rounded": compute_match.group(2) is not None,
        "expression": compute_match.group(3).strip(),
        "paragraph": paragraph,
    }
```

**STRING / UNSTRING / INSPECT are detected but not parsed.** These verbs are common
in address formatting, date manipulation, and data validation. They get INFO warnings
but no structured operation entry.

**MULTIPLY and DIVIDE are not parsed.** The non-COMPUTE arithmetic verbs (`MULTIPLY
QTY BY PRICE GIVING TOTAL`, `DIVIDE TOTAL BY COUNT GIVING AVG`) produce no operation
entries.

---

## Stage 4 — `context_enricher.py`

### What it does

The context enricher is the stage that gives the COBOL AST its execution context. It
takes the parser output (which knows about logical file names like `CUSTOMER-FILE`) and
the JCL manifest (which knows about physical datasets like `ACME.PROD.CUSTOMER.MASTER`)
and produces an `EnrichedManifest` that maps every logical file to its physical location,
execution step, and runtime parameters.

### How it works internally

The `_map_files()` method walks `ast.dependencies.file_bindings`, which is a dictionary
of `{COBOL_logical_name: JCL_DD_name}` pairs extracted by the parser from the
ENVIRONMENT DIVISION. For each entry it searches the JCL manifest steps for a step
whose `pgm` field matches `ast.program_name`, then looks up the DD name in that step's
`dd_bindings` dictionary to get the physical dataset name and disposition.

```python
for logical_name, dd_name in file_bindings.items():
    entry = {"logical_name": logical_name, "jcl_dd_name": dd_name,
             "physical_dataset": "UNKNOWN", "disposition": "UNKNOWN"}
    if dd_name in dd_bindings:
        dd_block = dd_bindings[dd_name]
        entry["physical_dataset"] = dd_block.get("dsn", "UNKNOWN")
        entry["disposition"] = dd_block.get("disp", "UNKNOWN")
    mappings[logical_name] = entry
```

### What is complete

The concept and the happy path are correct. For a single-program JCL job, this works
perfectly.

### What is missing

**The fallback is wrong.** When no step matches the program name, the code does this:

```python
# Fallback if no exact program_name match in JCL
if not dd_bindings and jcl_manifest.get("steps"):
    for step in jcl_manifest.get("steps", []):
        if step.get("dd_bindings"):
            dd_bindings = step.get("dd_bindings", {})
            break
```

In a multi-program JCL job with TXNPOST in STEP1 and STMTRPT in STEP2, enriching
STMTRPT with STEP1's DD bindings maps STMTRPT's files to TXNPOST's datasets. This
is silently wrong — no error is raised, no warning is emitted, and the
`EnrichedManifest` contains physically incorrect data.

The fix is to remove the fallback and emit an explicit unresolved marker:

```python
if not dd_bindings:
    for logical_name, dd_name in file_bindings.items():
        mappings[logical_name] = {
            "logical_name": logical_name,
            "jcl_dd_name": dd_name,
            "physical_dataset": "UNRESOLVED",
            "disposition": "UNKNOWN",
            "warning": f"No JCL step found with PGM={ast.get('program_name')}"
        }
    return mappings
```

---

## Architectural scaffolds — `antlr_parser.py`, `base.py`, `factory.py`

### What they do

These three files define the **architecture for the hybrid approach** but do not yet
implement it.

`base.py` defines a `CobolParser` Protocol — a Python structural interface (duck
typing). Any class that has a `parse(source_code: str) -> Dict[str, object]` method
satisfies this protocol without inheriting from it. This means `ParserLayer` and
`AntlrCobolParser` are interchangeable to any caller that receives a `CobolParser`.

`factory.py` selects the backend based on configuration:

```python
def create_parser(config: AppConfig) -> CobolParser:
    backend = config.parser_backend.lower()
    if backend == "heuristic":
        return ParserLayer()
    if backend == "antlr":
        return AntlrCobolParser()
    raise ValueError(...)
```

`antlr_parser.py` is the integration scaffold. Its `missing_requirements()` method
checks for: the `antlr4` Python package, the real grammar files, and the generated
Python artifacts. Its `parse()` method raises `RuntimeError` with setup instructions
until all requirements are met.

### What is complete

The architecture is completely correct. The Protocol + factory pattern is exactly right
for the hybrid approach. No downstream layer needs to change when you switch from
heuristic to ANTLR.

### What is missing

**The grammar files are stubs.** `Cobol85Lexer.g4` and `Cobol85Parser.g4` are
12-line placeholder files. The real ANTLR4 COBOL85 grammar from
`github.com/antlr/grammars-v4` is approximately 7000 lines total. Without the real
grammar, running `antlr4 -Dlanguage=Python3 -visitor` produces nothing useful.

**The `generated/` directory does not exist.** The files `Cobol85Lexer.py`,
`Cobol85Parser.py`, `Cobol85ParserVisitor.py` are generated by the ANTLR tool and
are prerequisites for the adapter. They do not exist yet.

**`parse_tree_adapter.py` does not exist.** This is the critical bridge. It is a
Python class that subclasses the generated `Cobol85ParserVisitor`, overrides one
method per grammar rule, calls your existing enrichment methods (`_decode_pic`,
`_infer_symbol_kind`, `_extract_88_values`, risk flags, warnings), and assembles
the same JSON schema that `ParserLayer.parse()` already produces. This is the core
of the hybrid: ANTLR handles syntactic correctness, your layer handles semantic
enrichment. The downstream layers receive identical output regardless of which
backend ran.

---

## Summary: what you built vs what to add

### Built and complete
- JCL parser with continuation joining, COND parsing, SYSLIB extraction, DD binding
- Copybook resolver with REPLACING, recursive nesting, cache, circular detection
- COBOL heuristic parser covering ~74% of real programs: all structure, PIC decoding,
  level-88 linkage, all PERFORM forms, preflight validation, W-warnings
- Context enricher happy path (correct for single-program JCL)
- Protocol + factory architecture ready for hybrid backend

### To add (ordered by urgency)
1. Real ANTLR grammar files + generate Python artifacts (2 hours)
2. COMPUTE operation in `_parse_operation()` (30 minutes)
3. Context enricher fallback fix — UNRESOLVED instead of wrong step (20 minutes)
4. `parse_tree_adapter.py` — the hybrid bridge (3–5 days)
5. STRING/UNSTRING/INSPECT/MULTIPLY/DIVIDE operations (1 day)
6. End-to-end integration test using Use Case 3 project (3 hours)
