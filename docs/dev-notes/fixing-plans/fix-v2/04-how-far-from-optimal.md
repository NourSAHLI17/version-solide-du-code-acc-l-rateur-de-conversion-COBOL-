# How Far You Are from the Optimal Approach

## Measuring completeness

Optimal is defined as: hybrid pipeline fully wired, all COBOL statements serialized
into the operations array, context enricher producing correct mappings for multi-program
JCL, and the full pipeline covered by an integration test. Each component is scored
independently below.

---

## Component-by-component proximity

### `jcl_parser.py` — 95% complete

What is done: job parsing, EXEC PGM/PROC, DD named + concatenation, SYSLIB extraction,
COND operator parsing, inline PROC with PEND boundary detection, DD disposition, inline
data block detection, continuation line joining, typed `JCLManifest` output.

What is missing (5%): symbolic parameter substitution in PROC calls
(`EXEC MYPROC,DSN=&MYDSN` where `&MYDSN` is a symbolic parameter). This affects JCL
jobs that use parameterized PROCs — common in enterprise shops. Also: PROC library
search (resolving `EXEC MYPROC` when `MYPROC` is in `SYS1.PROCLIB`, not inline).

**Effort to complete: 1–2 days.**

---

### `copybook_resolver.py` — 92% complete

What is done: column-aware COPY detection with Area B enforcement, fallback loose
pattern for free format, REPLACING clause with word-boundary substitution, recursive
nesting to depth 10, circular reference detection, cross-program cache with REPLACING
hash key, three-tier degradation (resolved/unresolved/circular), source-map comment
injection, `CopyResolutionResult` dataclass output.

What is missing (8%): the word-boundary edge case test (confirm `\b` handles
`==CUST==` → `==ACCT==` without affecting `CUSTODIAN`). Multi-library search order
is currently hardcoded in `COPY_LIBRARY_CONFIG` — it should be driven by the SYSLIB
paths extracted from the JCL manifest. Right now the JCL parser extracts SYSLIB paths
but they are not plumbed into the copybook resolver's search list. This is a wiring
gap, not an implementation gap.

**Effort to complete: 4 hours (wiring SYSLIB paths + edge case test).**

---

### `cobol_parser.py` heuristic path — 74% complete

What is done: format detection, preprocessing (Area A/B, indicator col 7, continuation),
program name extraction, division/section/paragraph extraction with `_is_paragraph_header()`
guards, full symbol table with level hierarchy, PIC decoding, USAGE clause, VALUE,
REDEFINES, OCCURS, level-88 linkage, all PERFORM forms (simple/UNTIL/VARYING/THRU/TIMES),
PERFORM THRU range expansion, condition stack, GO TO extraction, OPEN/CLOSE, READ with
INTO, WRITE/REWRITE/DELETE/DELETE_FILE, ACCEPT, DISPLAY with reference extraction,
MOVE with subscript and multi-target support, ADD/SUBTRACT, preflight validation
(4 checks), W001–W006 warnings.

What is missing (26%):
- COMPUTE: not in operations (most critical gap)
- STRING / UNSTRING: not in operations
- INSPECT: not in operations
- MULTIPLY / DIVIDE: not in operations
- EXEC SQL: boundary detected, content discarded
- SET statement: not parsed
- SEARCH / SEARCH ALL: not parsed
- Error recovery: preflight halt instead of partial output

**Effort to complete heuristic path: 2–3 days (add all missing verbs).**
**Effort to reach optimal via hybrid: 3–5 days for the adapter + 2 hours for grammar setup.**

---

### `context_enricher.py` — 60% complete

What is done: `_extract_execution_context()` correctly finds the step matching the
program name and extracts step name, PARM string, and COND. `_map_files()` correctly
maps logical file names to physical DSNs when the program name matches a JCL step.
`EnrichedManifest` structure is correct.

What is missing (40%): the fallback in `_map_files()` silently uses wrong step data
for multi-program JCL. Missing: UNRESOLVED marker when program name has no matching
step, warning entry in the manifest for unresolved files, and wiring of SYSLIB paths
from `jcl_manifest.syslib_paths` to `copybook_resolver`'s search configuration.

**Effort to complete: 3–4 hours.**

---

### `antlr_parser.py` + grammar + adapter — 15% complete

What is done: the `AntlrCobolParser` class scaffold with `missing_requirements()`
diagnostics, the correct check sequence for antlr4 runtime + grammar files + generated
artifacts, the `parse()` method with the right error message, the `CobolParser` Protocol
in `base.py`, and the `create_parser()` factory in `factory.py`.

What is missing (85%): the real grammar files (currently 12-line stubs), the generated
Python artifacts (directory does not exist), and most critically `parse_tree_adapter.py`
which does not exist at all. This file is the entire implementation of the hybrid path —
it is the visitor class that converts ANTLR parse tree nodes into your JSON schema.

**Effort to complete: 2 hours for grammar setup + artifact generation, 3–5 days for the adapter.**

---

### `factory.py` + `base.py` — 100% complete

Both files are fully implemented and architecturally correct. No changes needed.

---

## Overall pipeline completeness

| Path | Completeness | Real-world COBOL coverage |
|---|---|---|
| Heuristic path (what runs today) | ~74% | Programs with no COMPUTE/STRING/arithmetic verbs: 95% accurate. Programs with COMPUTE-heavy logic: missing all arithmetic operations from the output. Programs with dialect extensions: silently incorrect. Programs with minor source issues: halt. |
| After quick fixes (items 1–3 below) | ~82% | COMPUTE added, enricher fixed, SYSLIB wired. Better for financial programs. Still no STRING/INSPECT/error recovery. |
| After full hybrid completion | ~97% | All statements, all dialects, error recovery, complete file binding. Remaining 3%: very exotic constructs (SCREEN SECTION, COMMUNICATION SECTION, REPORT WRITER). |

---

## Ordered work items with exact effort

### Item 1 — Fix COMPUTE (30 minutes, high impact)

In `cobol_parser.py`, add to `_parse_operation()` before the final `return None`:

```python
compute_match = re.match(
    r"^COMPUTE\s+([A-Z0-9-]+(?:\([^)]+\))?)"
    r"(?:\s+(ROUNDED))?"
    r"\s*=\s*(.+?)\.?$",
    upper_text,
)
if compute_match:
    target = self._parse_operand(compute_match.group(1))
    operation = {
        "type": "COMPUTE",
        "target": target["name"],
        "rounded": compute_match.group(2) is not None,
        "expression": compute_match.group(3).strip(),
    }
    if target["subscript"]:
        operation["target_subscript"] = target["subscript"]
    if target["is_array_element"]:
        operation["target_is_array_element"] = True
    if paragraph:
        operation["paragraph"] = paragraph
    return operation
```

Also remove the INFO warning for COMPUTE from `_extract_warnings()` — once it is
properly parsed, the INFO flag is redundant.

---

### Item 2 — Fix context enricher fallback (20 minutes, high impact)

In `context_enricher.py`, replace the fallback block in `_map_files()`:

```python
# REMOVE THIS:
if not dd_bindings and jcl_manifest.get("steps"):
    for step in jcl_manifest.get("steps", []):
        if step.get("dd_bindings"):
            dd_bindings = step.get("dd_bindings", {})
            break

# REPLACE WITH:
if not dd_bindings:
    program_name = ast.get("program_name", "UNKNOWN")
    for logical_name, dd_name in file_bindings.items():
        mappings[logical_name] = {
            "logical_name": logical_name,
            "jcl_dd_name": dd_name,
            "physical_dataset": "UNRESOLVED",
            "disposition": "UNKNOWN",
            "resolution_warning": (
                f"No JCL step found with PGM={program_name}. "
                f"File binding for {logical_name} could not be resolved."
            ),
        }
    return mappings
```

---

### Item 3 — Wire SYSLIB paths from JCL to copybook resolver (2 hours)

In the pipeline orchestration layer (wherever `resolve_copy_books()` is called),
pass the SYSLIB paths from the JCL manifest into the resolver's search configuration:

```python
jcl_result = parse_jcl(jcl_source)
# Add SYSLIB paths discovered from JCL to the resolver search config
for path in jcl_result.syslib_paths:
    if path not in COPY_LIBRARY_CONFIG["default"]:
        COPY_LIBRARY_CONFIG["default"].append(path)

copy_result = resolve_copy_books(cobol_source, library_config=COPY_LIBRARY_CONFIG)
```

---

### Item 4 — Real ANTLR grammar setup (2 hours)

```bash
# Download real grammar files
curl -o app/grammars/cobol85/Cobol85Lexer.g4 \
  https://raw.githubusercontent.com/antlr/grammars-v4/master/cobol85/Cobol85Lexer.g4

curl -o app/grammars/cobol85/Cobol85Parser.g4 \
  https://raw.githubusercontent.com/antlr/grammars-v4/master/cobol85/Cobol85Parser.g4

# Generate Python artifacts
cd app/grammars/cobol85
antlr4 -Dlanguage=Python3 -visitor -o ../../parsers/generated \
  Cobol85Lexer.g4 Cobol85Parser.g4

# Install runtime
pip install antlr4-python3-runtime
```

After this, `AntlrCobolParser().missing_requirements()` returns an empty list and the
ANTLR path no longer throws `RuntimeError`. What it still cannot do is produce useful
output — that requires Item 5.

---

### Item 5 — Write `parse_tree_adapter.py` (3–5 days)

This is the core of the hybrid. The file subclasses the generated
`Cobol85ParserVisitor` and overrides one method per grammar rule that maps to a JSON
output entry. The skeleton:

```python
from app.parsers.generated.Cobol85ParserVisitor import Cobol85ParserVisitor
from app.parsers.cobol_parser import ParserLayer

class ParseTreeAdapter(Cobol85ParserVisitor):
    def __init__(self):
        self._enricher = ParserLayer()
        self.symbol_table = []
        self.operations = []
        self.control_flow = {"branches":[], "loops":[], "calls":[], "gotos":[]}
        self._paragraph_order = []
        self._current_paragraph = None
        self._condition_stack = []

    def visitDataDescriptionEntry(self, ctx):
        # Build symbol dict from ctx fields
        level = int(ctx.levelNumber().getText())
        name = ctx.dataName().getText().upper()
        pic_str = ctx.pictureClause().getText() if ctx.pictureClause() else None
        symbol = {"name": name, "level": level, ...}
        if pic_str:
            symbol["pic"] = pic_str
            symbol["pic_decoded"] = self._enricher._decode_pic(pic_str)
        symbol["kind"] = self._enricher._infer_symbol_kind(symbol)
        self.symbol_table.append(symbol)
        return self.visitChildren(ctx)

    def visitComputeStatement(self, ctx):
        target_text = ctx.computeStoreOperand(0).getText().upper()
        target = self._enricher._parse_operand(target_text)
        expression = ctx.arithmeticExpression().getText()
        rounded = ctx.ROUNDED() is not None
        self.operations.append({
            "type": "COMPUTE",
            "target": target["name"],
            "expression": expression,
            "rounded": rounded,
            "paragraph": self._current_paragraph,
        })
        return self.visitChildren(ctx)

    def to_json(self) -> dict:
        risk_flags = self._enricher._extract_risk_flags(
            self.symbol_table, self.control_flow,
            self._dependencies, self._lines_stub
        )
        warnings = self._enricher._extract_warnings(
            self._lines_stub, self.symbol_table,
            self.control_flow, self.operations
        )
        return {
            "program_name": self._program_name,
            "source_format": "fixed",
            "preflight_errors": self._errors,
            "divisions": self._divisions,
            "sections": self._sections,
            "paragraphs": self._paragraph_order,
            "symbol_table": self.symbol_table,
            "control_flow": self.control_flow,
            "operations": self.operations,
            "dependencies": self._dependencies,
            "risk_flags": risk_flags,
            "warnings": warnings,
        }
```

The complete adapter needs visitor methods for approximately 30 grammar rules:
`programIdParagraph`, `dataDescriptionEntry`, `paragraph`, `ifStatement`,
`evaluateStatement`, `performStatement`, `computeStatement`, `moveStatement`,
`addStatement`, `subtractStatement`, `multiplyStatement`, `divideStatement`,
`readStatement`, `writeStatement`, `rewriteStatement`, `deleteStatement`,
`openStatement`, `closeStatement`, `acceptStatement`, `displayStatement`,
`goToStatement`, `callStatement`, `stringStatement`, `unstringStatement`,
`inspectStatement`, `startStatement`, `setStatement`, `searchStatement`,
`stopStatement`, `exitStatement`.

---

### Item 6 — Integration test (3 hours)

Write a test that runs the complete pipeline against Use Case 3:

```python
def test_full_pipeline_use_case_3():
    jcl_source = open("tests/fixtures/usecase3/jcl/ACMEPOST.jcl").read()
    cobol_source = open("tests/fixtures/usecase3/src/CUSTMGR.cbl").read()

    jcl_manifest = parse_jcl(jcl_source)
    copy_result = resolve_copy_books(
        cobol_source,
        copybook_dirs=["tests/fixtures/usecase3/copybooks/"]
    )
    parser = create_parser(AppConfig(parser_backend="heuristic"))
    ast = parser.parse(copy_result.expanded_source)
    enriched = ContextEnricher().enrich(ast, jcl_manifest.to_dict())

    # Structural assertions
    assert ast["program_name"] == "CUSTMGR"
    assert "IDENTIFICATION DIVISION" in ast["divisions"]
    assert "CUSTOMER-RECORD" in [s["name"] for s in ast["symbol_table"]]

    # File binding assertion (the critical cross-stage verification)
    assert enriched["data_mappings"]["CUSTOMER-FILE"]["physical_dataset"] \
        == "ACME.CUSTOMER.MASTER"

    # Control flow
    calls = {c["to"] for c in ast["control_flow"]["calls"]}
    assert "3000-ADD-CUSTOMER" in calls
    assert "9000-DISPLAY-CUSTOMER" in calls

    # No preflight errors
    assert ast["preflight_errors"] == []
```

---

## Distance summary

| Work item | Time | Moves completeness from → to |
|---|---|---|
| Fix COMPUTE in operations | 30 min | 74% → 79% |
| Fix enricher fallback | 20 min | 79% → 81% |
| Wire SYSLIB paths | 2 hours | 81% → 83% |
| Add STRING/UNSTRING/MULTIPLY/DIVIDE | 1 day | 83% → 88% |
| Integration test | 3 hours | 88% → 88% (validates, doesn't add coverage) |
| Real grammar files + artifact generation | 2 hours | Unblocks ANTLR path |
| Write parse_tree_adapter.py | 3–5 days | 88% → 97% |

**Total time to optimal hybrid: approximately 6–8 working days.**
**Time to significantly better heuristic path: 2 days.**
**Time to fix the two most critical bugs: 50 minutes.**
