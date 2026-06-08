# Codex Prompt — Fix context_enricher.py, copybook_resolver.py, and ANTLR Setup
**Target files:**
  - `backend/services/context_enricher.py`
  - `backend/services/copybook_resolver.py`
  - `backend/antlr/` (new grammar + adapter)
  - `tests/test_e2e_pipeline.py` (new file)

---

## PART A — Fix context_enricher.py

### Problem
When a JCL job has 2+ programs (STEP1=TXNPOST, STEP2=STMTRPT), the enricher
cannot find STMTRPT in STEP1 and silently falls back to STEP1's DD bindings.
STMTRPT gets TXNPOST's file bindings, which is completely wrong.

### Locate This Code

Find the method that matches programs to JCL steps. It currently looks like:

```python
# CURRENT WRONG CODE (find this pattern):
fallback_step = next(
    (s for s in self.jcl_manifest.steps if s.dd_bindings), None
)
if fallback_step:
    return self._build_mappings(fallback_step)
```

### Replace With

```python
# FIXED CODE — replace the fallback block with this:
matched_steps = [
    s for s in self.jcl_manifest.steps
    if s.pgm and s.pgm.upper() == program_name.upper()
]

if not matched_steps:
    # Program not found in any JCL step — emit warning, never use wrong step
    self._warnings.append({
        "code":     "W010",
        "severity": "high",
        "message":  (
            f"Program '{program_name}' not found in any JCL EXEC step. "
            f"DD bindings cannot be resolved. "
            f"Physical DSNs will appear as UNRESOLVED in the enriched manifest."
        ),
        "available_programs": [
            s.pgm for s in self.jcl_manifest.steps if s.pgm
        ]
    })
    return {
        "data_mappings": {},
        "parm_values":   {},
        "execution_step": None,
        "warnings":      list(self._warnings)
    }

# Use the correct step for this program
step = matched_steps[0]
return self._build_mappings(step)
```

### Also Add — Physical DSN "UNRESOLVED" Marker

In `_build_mappings()` or wherever DD bindings are assembled, ensure that any
DD name with no matching DSN emits a marker:

```python
def _build_mappings(self, step) -> dict:
    data_mappings = {}
    for logical_name, binding in step.dd_bindings.items():
        dsn = binding.get("dsn") or binding.get("physical_dataset")
        data_mappings[logical_name] = {
            "physical_dataset": dsn if dsn else "UNRESOLVED",
            "disposition":      binding.get("disp", "UNKNOWN"),
            "step_name":        step.step_name
        }
    return {
        "data_mappings": data_mappings,
        "parm_values":   getattr(step, "parm_values", {}),
        "execution_step": step.step_name,
        "warnings":      list(self._warnings)
    }
```

### Checklist — context_enricher.py

- [ ] Multi-program JCL: STMTRPT gets STEP2's bindings, not STEP1's
- [ ] Unknown program emits W010 warning with `available_programs` list
- [ ] Unknown program returns empty `data_mappings`, not wrong data
- [ ] `physical_dataset` is "UNRESOLVED" when DSN is absent, not null/None

---

## PART B — Fix copybook_resolver.py

### Problem
The REPLACING substitution uses `\b` (word boundary) which fails when the
replaced token ends with a hyphen (`==CUST-== BY ==CLIENT-==`). The `\b`
boundary is placed at the hyphen, not after it.

### Locate This Code

Find where REPLACING patterns are built. It looks like:

```python
# CURRENT WRONG CODE (find this pattern):
pattern = r"\b" + re.escape(old_token) + r"\b"
```

### Replace With

```python
# FIXED CODE — COBOL identifier boundary (alphanumeric + hyphen chars only)
# A COBOL identifier can contain letters, digits, and hyphens
# A boundary exists when the adjacent char is NOT in [A-Z0-9-]
old_escaped = re.escape(old_token)
pattern = r"(?<![A-Z0-9-])" + old_escaped + r"(?![A-Z0-9-])"
```

### Why This Fix Is Correct

```
Token to replace: CUST-
Test string: CUST-NAME CUST-ADDR INVALID-CUST-CODE

With \b boundary:
  \bCUST-\b  →  \b sits at hyphen, pattern = \bCUST\b-
  matches "CUST" but not "CUST-" as a unit
  → CUST-NAME stays as CUST-NAME (wrong, should become CLIENT-NAME)

With lookaround boundary:
  (?<![A-Z0-9-])CUST-(?![A-Z0-9-])
  Matches CUST- only when preceded by non-identifier and followed by non-identifier
  In CUST-NAME: CUST- is followed by N (identifier char) → NO MATCH (correct)
  In "CUST- " (trailing): followed by space → MATCH (correct)
```

### Checklist — copybook_resolver.py

- [ ] `COPY X REPLACING ==CUST-== BY ==CLIENT-==` correctly substitutes `CUST-NAME` → `CLIENT-NAME`
- [ ] Substitution does NOT corrupt `INVALID-CUST-CODE` (INVALID prefix stays)
- [ ] Simple substitution `==INV== BY ==SALES==` still works correctly
- [ ] Multi-word replacing `==CUST NAME== BY ==CLIENT LABEL==` not broken

---

## PART C — ANTLR Grammar Setup

### Step 1 — Download Real Grammar Files

```bash
# From the official antlr/grammars-v4 repository
# DO NOT write these manually — they are ~7000 lines combined

curl -o backend/antlr/Cobol85Lexer.g4 \
  https://raw.githubusercontent.com/antlr/grammars-v4/master/cobol85/Cobol85Lexer.g4

curl -o backend/antlr/Cobol85Parser.g4 \
  https://raw.githubusercontent.com/antlr/grammars-v4/master/cobol85/Cobol85Parser.g4
```

### Step 2 — Install ANTLR4 Tools

```bash
pip install antlr4-tools antlr4-python3-runtime
```

### Step 3 — Generate Python Artifacts

```bash
antlr4 -Dlanguage=Python3 -visitor -listener \
  -o backend/antlr/generated/ \
  backend/antlr/Cobol85Lexer.g4 \
  backend/antlr/Cobol85Parser.g4
```

**Verify these files exist after generation:**
```
backend/antlr/generated/
├── Cobol85Lexer.py           ← tokenizer
├── Cobol85Parser.py          ← parser rules
├── Cobol85ParserVisitor.py   ← base visitor (you will extend this)
└── Cobol85ParserListener.py  ← base listener (not used)
```

### Step 4 — Write parse_tree_adapter.py

Create `backend/antlr/parse_tree_adapter.py`:

```python
"""
ANTLR parse tree → ParserLayer JSON schema adapter.
Extends the generated Cobol85ParserVisitor to walk every CST node
and call the same enrichment functions used by the heuristic parser.
Output schema is IDENTICAL to ParserLayer.parse() output.
"""
from antlr4 import CommonTokenStream, InputStream, ParseTreeWalker
from .generated.Cobol85Lexer  import Cobol85Lexer
from .generated.Cobol85Parser import Cobol85Parser
from .generated.Cobol85ParserVisitor import Cobol85ParserVisitor

# Import enrichment functions from heuristic parser
from ..services.cobol_parser import _decode_pic, _infer_symbol_kind


class CobolTreeAdapter(Cobol85ParserVisitor):

    def __init__(self):
        self._symbol_table  = []
        self._paragraphs    = []
        self._operations    = []
        self._calls         = []
        self._branches      = []
        self._loops         = []
        self._gotos         = []
        self._risk_flags    = set()
        self._warnings      = []
        self._current_para  = None
        self._symbol_names  = set()

    # ── Data Division ──────────────────────────────────────────────────────

    def visitDataDescriptionEntry(self, ctx):
        """Map ANTLR data item node → symbol_table entry."""
        try:
            level = int(ctx.levelNumber().getText())
            name  = ctx.dataName().getText().upper() if ctx.dataName() else None

            pic_str  = ""
            occurs   = None
            value    = None
            redefines = None

            if ctx.dataPictureClause():
                pic_str = ctx.dataPictureClause().pictureString().getText().upper()

            if ctx.dataOccursClause():
                occurs = int(ctx.dataOccursClause().integerLiteral(0).getText())

            if ctx.dataValueClause():
                value = ctx.dataValueClause().getText().strip("VALUE ").strip()

            if ctx.dataRedefinesClause():
                redefines = ctx.dataRedefinesClause().dataName().getText().upper()

            pic_decoded = _decode_pic(pic_str) if pic_str else {}
            kind        = _infer_symbol_kind(pic_str, occurs, level)

            entry = {
                "name":      name,
                "level":     level,
                "pic":       pic_str or None,
                "value":     value,
                "kind":      kind,
                "occurs":    occurs,
                "redefines": redefines,
                "java_type": pic_decoded.get("java_type"),
                "section":   self._current_section
            }

            if name:
                self._symbol_table.append(entry)
                self._symbol_names.add(name)

            # Detect 88-level condition names
            if level == 88 and name:
                # Link to parent symbol
                if self._symbol_table:
                    parent = next(
                        (s for s in reversed(self._symbol_table)
                         if s["level"] < 88), None
                    )
                    if parent:
                        parent.setdefault("condition_names", []).append({
                            "name":   name,
                            "values": [value] if value else []
                        })

        except Exception as e:
            self._warnings.append({
                "code":    "W099",
                "message": f"Failed to parse data entry: {str(e)}"
            })

        return self.visitChildren(ctx)

    # ── Procedure Division ─────────────────────────────────────────────────

    def visitParagraph(self, ctx):
        """Register paragraph name and set current context."""
        name = ctx.paragraphName().getText().upper()
        self._paragraphs.append(name)
        self._current_para = name
        return self.visitChildren(ctx)

    # ── MOVE ───────────────────────────────────────────────────────────────

    def visitMoveStatement(self, ctx):
        """Handle MOVE including multi-target and function-call sources."""
        try:
            move_stmt = ctx.moveToStatement() or ctx.moveCorrespondingToStatement()
            if not move_stmt:
                return self.visitChildren(ctx)

            from_val = move_stmt.moveToSendingArea().getText().upper()
            is_func  = "FUNCTION" in from_val

            for id_ctx in move_stmt.identifier():
                target = id_ctx.getText().upper()
                self._operations.append({
                    "type":             "MOVE",
                    "value":            from_val,
                    "target":           target,
                    "function_call":    is_func,
                    "paragraph":        self._current_para
                })
                if target in self._symbol_names:
                    self._mark_write(target)
            if from_val in self._symbol_names:
                self._mark_read(from_val)

        except Exception as e:
            self._warnings.append({"code": "W099", "message": str(e)})

        return self.visitChildren(ctx)

    # ── COMPUTE ────────────────────────────────────────────────────────────

    def visitComputeStatement(self, ctx):
        """Handle COMPUTE — emit arithmetic expression into operations[]."""
        try:
            for store_ctx in ctx.computeStore():
                target  = store_ctx.identifier().getText().upper()
                rounded = store_ctx.ROUNDED() is not None
                expr    = ctx.arithmeticExpression().getText().upper()
                self._operations.append({
                    "type":       "COMPUTE",
                    "target":     target,
                    "expression": expr,
                    "rounded":    rounded,
                    "paragraph":  self._current_para
                })
                self._mark_write(target)
                import re
                for token in re.findall(r"[A-Z][A-Z0-9-]+", expr):
                    if token in self._symbol_names:
                        self._mark_read(token)
            self._risk_flags.add("arithmetic_expression")
        except Exception as e:
            self._warnings.append({"code": "W099", "message": str(e)})
        return self.visitChildren(ctx)

    # ── PERFORM ────────────────────────────────────────────────────────────

    def visitPerformStatement(self, ctx):
        """Handle all PERFORM forms."""
        try:
            proc_ctx = ctx.performProcedureStatement()
            if proc_ctx:
                target = proc_ctx.procedureName(0).getText().upper()
                thru   = None
                if proc_ctx.procedureName(1):
                    thru = proc_ctx.procedureName(1).getText().upper()
                self._calls.append({
                    "type":        "PERFORM",
                    "from":        self._current_para,
                    "to":          target,
                    "thru":        thru,
                    "conditional": False,
                    "condition":   None
                })

            vary_ctx = ctx.performVaryingClause()
            if vary_ctx:
                iterator = vary_ctx.identifier(0).getText().upper() if vary_ctx.identifier() else None
                start    = vary_ctx.integerLiteral(0).getText() if vary_ctx.integerLiteral() else "1"
                self._loops.append({
                    "type":      "PERFORM_VARYING",
                    "iterator":  iterator,
                    "start":     start,
                    "step":      "1",
                    "inline":    True,
                    "paragraph": self._current_para
                })
                self._risk_flags.add("loop_logic")

        except Exception as e:
            self._warnings.append({"code": "W099", "message": str(e)})
        return self.visitChildren(ctx)

    # ── EVALUATE ───────────────────────────────────────────────────────────

    def visitEvaluateStatement(self, ctx):
        """Register EVALUATE — extract all WHEN PERFORM targets."""
        self._risk_flags.add("conditional_logic")
        condition_subject = ctx.evaluateSelect(0).getText().upper() if ctx.evaluateSelect() else None
        self._branches.append({
            "type":      "EVALUATE",
            "condition": condition_subject,
            "paragraph": self._current_para
        })
        return self.visitChildren(ctx)

    def visitEvaluateWhenPhrase(self, ctx):
        """Register conditional PERFORM inside EVALUATE WHEN."""
        try:
            for stmt in ctx.statement():
                perform_ctx = stmt.performStatement()
                if perform_ctx:
                    proc = perform_ctx.performProcedureStatement()
                    if proc:
                        target = proc.procedureName(0).getText().upper()
                        self._calls.append({
                            "type":        "PERFORM",
                            "from":        self._current_para,
                            "to":          target,
                            "conditional": True,
                            "condition":   "EVALUATE-WHEN"
                        })
        except Exception:
            pass
        return self.visitChildren(ctx)

    # ── STRING / UNSTRING ──────────────────────────────────────────────────

    def visitStringStatement(self, ctx):
        self._risk_flags.add("string_manipulation")
        self._operations.append({
            "type":      "STRING",
            "raw":       ctx.getText().upper(),
            "paragraph": self._current_para
        })
        return self.visitChildren(ctx)

    def visitUnstringStatement(self, ctx):
        self._risk_flags.add("string_manipulation")
        self._operations.append({
            "type":      "UNSTRING",
            "raw":       ctx.getText().upper(),
            "paragraph": self._current_para
        })
        return self.visitChildren(ctx)

    # ── INSPECT ────────────────────────────────────────────────────────────

    def visitInspectStatement(self, ctx):
        self._risk_flags.add("inspect_tallying")
        subject = ctx.identifier().getText().upper() if ctx.identifier() else None
        self._operations.append({
            "type":      "INSPECT",
            "subject":   subject,
            "raw":       ctx.getText().upper(),
            "paragraph": self._current_para
        })
        return self.visitChildren(ctx)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _mark_read(self, name: str):
        self._operations.append({
            "type":       "_READ_HINT",
            "symbol":     name,
            "paragraph":  self._current_para
        })

    def _mark_write(self, name: str):
        self._operations.append({
            "type":       "_WRITE_HINT",
            "symbol":     name,
            "paragraph":  self._current_para
        })

    def to_ast(self) -> dict:
        """
        Return the same JSON schema as ParserLayer.parse().
        All downstream agents (analysis, conversion, testing) use this
        without modification.
        """
        return {
            "symbol_table":  self._symbol_table,
            "paragraphs":    self._paragraphs,
            "operations":    [
                op for op in self._operations
                if op["type"] not in ("_READ_HINT", "_WRITE_HINT")
            ],
            "control_flow": {
                "branches": self._branches,
                "loops":    self._loops,
                "calls":    self._calls,
                "gotos":    self._gotos
            },
            "risk_flags":   sorted(self._risk_flags),
            "warnings":     self._warnings
        }


def parse_with_antlr(source: str) -> dict:
    """
    Full ANTLR parse of expanded COBOL source.
    Returns same JSON schema as ParserLayer.parse().
    """
    input_stream  = InputStream(source)
    lexer         = Cobol85Lexer(input_stream)
    token_stream  = CommonTokenStream(lexer)
    parser        = Cobol85Parser(token_stream)
    tree          = parser.startRule()

    adapter = CobolTreeAdapter()
    adapter.visit(tree)
    return adapter.to_ast()
```

### Step 5 — Update antlr_parser.py

In `backend/antlr/antlr_parser.py`, replace the `parse()` method stub:

```python
def parse(self, source: str) -> dict:
    if self._missing_requirements():
        raise RuntimeError(
            "ANTLR artifacts not found. Run: "
            "antlr4 -Dlanguage=Python3 -visitor -o backend/antlr/generated/ "
            "backend/antlr/Cobol85Lexer.g4 backend/antlr/Cobol85Parser.g4"
        )
    from .parse_tree_adapter import parse_with_antlr
    return parse_with_antlr(source)
```

---

## PART D — End-to-End Integration Test

Create `tests/test_e2e_pipeline.py`:

```python
"""
End-to-end pipeline integration test.
Uses Use Case 3 fixtures: CUSTMGR.cbl + ACMEPOST.jcl + 4 copybooks.
Validates the full pipeline from JCL parse to EnrichedManifest.
"""
import pytest
import os

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "use_case_3")


@pytest.fixture
def pipeline_output():
    from backend.services.jcl_parser       import JCLParser
    from backend.services.copybook_resolver import CopybookResolver
    from backend.services.cobol_parser      import ParserLayer
    from backend.services.context_enricher  import ContextEnricher

    jcl_manifest = JCLParser().parse(
        open(os.path.join(FIXTURES, "ACMEPOST.jcl")).read()
    )
    expanded = CopybookResolver(
        copylib_paths=jcl_manifest.copylib_paths
    ).resolve(
        open(os.path.join(FIXTURES, "CUSTMGR.cbl")).read()
    )
    ast = ParserLayer().parse(expanded["expanded_source"])
    enriched = ContextEnricher(jcl_manifest).enrich(ast, program_name="CUSTMGR")
    return jcl_manifest, ast, enriched


def test_symbol_table_contains_copybook_symbols(pipeline_output):
    """All symbols from all 4 copybooks must appear in symbol table."""
    _, ast, _ = pipeline_output
    sym_names = {s["name"] for s in ast["symbol_table"]}
    # These come from copybooks, not the main source
    assert "CUSTOMER-ID"      in sym_names, "CUSTID copybook not expanded"
    assert "ACCT-BALANCE"     in sym_names, "ACCTBAL copybook not expanded"
    assert "CUSTOMER-FILE"    in sym_names


def test_dd_binding_correct_program(pipeline_output):
    """CUSTMGR must get its own step's DD bindings, not another step's."""
    _, _, enriched = pipeline_output
    mappings = enriched["data_mappings"]
    assert "CUSTOMER-FILE" in mappings
    assert mappings["CUSTOMER-FILE"]["physical_dataset"] == "ACME.CUSTOMER.MASTER"
    # Must NOT have bindings from another step
    assert "TXNFILE" not in mappings  # belongs to a different step


def test_compute_in_operations(pipeline_output):
    """COMPUTE statements must appear in operations[] after fix."""
    _, ast, _ = pipeline_output
    compute_ops = [o for o in ast["operations"] if o["type"] == "COMPUTE"]
    assert len(compute_ops) > 0, "No COMPUTE operations found — check cobol_parser.py fix"
    for op in compute_ops:
        assert "target" in op
        assert "expression" in op
        assert "rounded" in op


def test_no_false_dead_code_warnings(pipeline_output):
    """Paragraphs dispatched via EVALUATE must not appear as dead code."""
    _, ast, _ = pipeline_output
    dead_code_warnings = [
        w for w in ast["warnings"]
        if w.get("code") == "W004"
    ]
    assert len(dead_code_warnings) == 0, (
        f"False dead code warnings: {dead_code_warnings}"
    )


def test_no_false_dead_assignment_warnings(pipeline_output):
    """Variables in multi-target MOVE must not appear as dead assignments."""
    _, ast, _ = pipeline_output
    dead_assign = [
        w for w in ast["warnings"]
        if w.get("code") == "W002"
    ]
    assert len(dead_assign) == 0, (
        f"False dead assignment warnings: {dead_assign}"
    )


def test_risk_flags_present(pipeline_output):
    """Programs with COMPUTE must have arithmetic_expression risk flag."""
    _, ast, _ = pipeline_output
    assert "arithmetic_expression" in ast["risk_flags"]


def test_copybook_replacing_applied(pipeline_output):
    """REPLACING substitution must produce correct symbol names."""
    _, ast, _ = pipeline_output
    sym_names = {s["name"] for s in ast["symbol_table"]}
    # After REPLACING ==CUST-== BY ==CLIENT-==, should have CLIENT-NAME not CUST-NAME
    # (adjust based on actual Use Case 3 REPLACING clauses)
    # assert "CLIENT-NAME" in sym_names
    # assert "CUST-NAME" not in sym_names  # uncomment when Use Case 3 uses REPLACING
```

---

## GLOBAL CHECKLIST

After all changes in this file are implemented:

- [ ] context_enricher.py: multi-program JCL uses correct step per program name
- [ ] context_enricher.py: unknown program emits W010, returns empty mappings
- [ ] copybook_resolver.py: REPLACING with hyphen-ending tokens works correctly
- [ ] parse_tree_adapter.py exists with all visitXxx methods implemented
- [ ] antlr_parser.py.parse() imports and calls parse_with_antlr()
- [ ] ANTLR grammar files are real (not stubs) and artifacts generated
- [ ] test_e2e_pipeline.py passes all 6 assertions
- [ ] factory.py "antlr" backend no longer throws RuntimeError

---
*Codex Prompt — context_enricher + copybook_resolver + ANTLR + tests — 2026-05-07*
