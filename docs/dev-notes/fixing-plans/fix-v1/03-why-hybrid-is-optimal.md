# Why the Hybrid Approach Is Optimal

## The core argument in one paragraph

Your heuristic parser does semantic enrichment that ANTLR cannot do. ANTLR does syntactic
parsing that your heuristic cannot do reliably. The two capabilities do not overlap —
they are complementary. The hybrid approach runs them in sequence on the same input and
produces output that neither could produce alone. It is not a compromise between two
approaches. It is the combination of two tools each doing only what it is good at.

---

## What goes wrong with heuristic-only

### Problem 1 — COMPUTE is silently lost

In your current code, `_parse_operation()` has no branch for COMPUTE. When a COBOL
program contains:

```cobol
COMPUTE WS-TOTAL ROUNDED = WS-QTY * WS-PRICE.
COMPUTE WS-TAX = WS-TOTAL * 0.20.
COMPUTE WS-BALANCE = WS-BALANCE + TXN-AMOUNT - WS-FEES.
```

None of these statements appear in the `operations` array. The converter layer
receives JSON with no record that these calculations exist. The generated Java code
will have methods that read `WS-TOTAL`, `WS-TAX`, and `WS-BALANCE` as if they were
filled by magic. The generated code is wrong and the error is silent — no exception
is thrown, no warning is surfaced.

COMPUTE is not an edge case. It is the primary arithmetic verb in COBOL. Every program
that does financial calculations — which is the majority of real mainframe COBOL — uses
it extensively.

### Problem 2 — Dialect-specific constructs silently misparse

IBM Enterprise COBOL has constructs your regex patterns were not designed for:
- `POINTER` usage clause: `05 WS-PTR USAGE IS POINTER.` — parsed as unknown, kind set
  to `"group"` incorrectly
- `COMP-5` (native binary): not distinguished from `COMP` — wrong java_type inference
- Level-66 `RENAMES` clause: `66 CUST-FULL-NAME RENAMES CUST-FIRST THRU CUST-LAST.` —
  the regex for level numbers catches this, but `RENAMES` is not in the match group,
  so `rest` parsing fails silently
- `ADDRESS OF` special register: `MOVE ADDRESS OF WS-STRUCT TO WS-PTR.` — parsed as a
  MOVE from `ADDRESS` to `WS-PTR`, losing the pointer semantics entirely

None of these produce errors. They produce incorrect JSON. The converter layer acts on
incorrect data.

### Problem 3 — Minor source issues halt the entire parse

Your preflight check is a gate: if it finds a duplicate data name or a missing FD entry,
it returns `_build_preflight_failure()` which sets `symbol_table: []`, `operations: []`,
and `control_flow: {branches:[], loops:[], calls:[], gotos:[]}`. The entire program
becomes invisible to the converter.

Real-world mainframe COBOL frequently has minor issues — a COPY book that was removed
from the library but the COPY statement was never cleaned up, an FD that was added late
in development and is technically redundant, a data name that was copied from a template
and never renamed. These are not blocking errors. They are cosmetic issues in programs
that have been running in production for 30 years. The heuristic parser treats them as
fatal.

### Problem 4 — Performance degrades on large programs

Your preprocessor makes multiple full linear passes over the lines array:
- `_extract_divisions()`: full pass
- `_extract_sections()`: full pass
- `_extract_paragraph_index()`: full pass
- `_extract_symbol_table()`: full pass
- `_extract_control_flow()`: full pass (calls `_extract_paragraph_index()` again inside)
- `_extract_operations()`: full pass

For a 50,000-line mainframe COBOL program (not unusual — some programs are 200,000 lines),
this is 7+ full Python list iterations over 50,000 dict objects, with regex compilation
and matching on every line in every pass. This will be slow. Python loops with regex are
not the right tool for this scale.

---

## What goes wrong with ANTLR-only

### Problem 1 — COPY expansion must happen before parsing

The ANTLR COBOL85 grammar expects to receive source code with no COPY statements. When
a program says `COPY CUSTCOPY`, the grammar either has a rule that matches the COPY
token and leaves it as a reference node (it does not expand the file) or it fails to
parse the data items that should have been in that position.

Your `copybook_resolver.py` runs before the parser and produces source that ANTLR can
handle. Without it, ANTLR parses a structurally incomplete program and its symbol table
is full of holes wherever COPY was used — which is most of the DATA DIVISION in most
real programs.

An ANTLR-only approach would need to either build its own COPY resolver (rebuilding what
you already have) or require the user to pre-expand copybooks manually. Neither is
acceptable.

### Problem 2 — JCL is completely outside ANTLR's scope

The ANTLR COBOL85 grammar covers the COBOL language. It says nothing about JCL. There
is no ANTLR grammar for JCL that is maintained and production-ready. Even if you found
one, the integration work to connect JCL parsing → file binding → COBOL context would
be exactly the work your `jcl_parser.py` and `context_enricher.py` already do.

An ANTLR-only approach would produce a COBOL AST with logical file names
(`CUSTOMER-FILE`, `TRANSACTION-FILE`) and no knowledge of what physical datasets those
map to. The converter layer would generate Java code that reads from `"CUSTOMER-FILE"`
as a literal string, which means nothing in a Java application. File binding resolution
would become a manual step, defeating the purpose of automation.

### Problem 3 — Semantic enrichment is not what grammars do

ANTLR's COBOL85 grammar is a syntactic specification. It tells you that `05 CUST-ID PIC 9(7).`
is a `dataDescriptionEntry` with `levelNumber=05`, `dataName=CUST-ID`,
`pictureClause=PIC 9(7)`. It does not tell you:
- That `PIC 9(7)` should become `int` in Java (not `long`, not `BigDecimal`, not `String`)
- That `PIC 9(5)V99` should become `BigDecimal` with `scale=2`
- That a level-88 item attached to `CUST-STATUS` means it is a named boolean
  condition on the parent field
- That this variable is used in 3 paragraphs, written in 1 and read in 2 (data flow)
- That it is a dead variable never referenced (W001 warning)
- That writing it as the target of a COMPUTE while also being the source of a READ
  is a potential data flow hazard

All of this semantic knowledge is in your code. It took you significant effort to build.
An ANTLR-only approach provides none of it. You would have to add all of it yourself —
which is exactly what the `parse_tree_adapter.py` does. The hybrid is not "add ANTLR
to your code." It is "have ANTLR do the syntax, have your code do the semantics."

### Problem 4 — Raw parse tree is not your API contract

Your downstream analysis layer and converter layer consume a specific JSON schema:
`symbol_table`, `control_flow`, `operations`, `dependencies`, `risk_flags`, `warnings`.
ANTLR produces a `ParseTree` object — a nested tree of context objects with methods like
`ctx.dataDescriptionEntry()`, `ctx.performStatement()`, etc.

These are completely different data structures. Switching to ANTLR-only means rewriting
every downstream stage to consume a parse tree instead of JSON. That is a larger
change than writing the adapter, and it eliminates the clean API boundary you have
between pipeline stages.

---

## Why hybrid is optimal — the precise argument

The hybrid approach preserves the API contract. Downstream stages receive the same JSON
schema whether the heuristic or the ANTLR backend ran. The `factory.py` selection is
the only thing that changes. This means:

**You can switch backends without touching any downstream code.** Set
`PARSER_BACKEND=antlr` in config and the analysis layer, converter layer, and every
prompt that injects the JSON schema receives a more complete, more accurate JSON
document — but from their perspective, nothing changed.

**You can test both backends against the same expected output.** The same Use Case 3
test (CUSTMGR.cbl + ACMEPOST.jcl + 4 copybooks) runs against both backends and both
must produce the same JSON schema. Differences reveal parser gaps, not downstream
incompatibilities.

**The hybrid reuses rather than rebuilds.** `_decode_pic()`, `_infer_symbol_kind()`,
`_extract_88_values()`, `_extract_risk_flags()`, `_extract_warnings()` — all of these
move unchanged into the adapter. The work you did building these is not discarded. It
becomes more accurate because it now operates on ANTLR's verified parse tree instead
of heuristic-matched lines.

**Each tool does only what it is good at:**
- ANTLR: tokenize correctly, parse all statements, recover from errors, handle dialects
- Your code: decode types, link condition names, map JCL files, detect risks, generate warnings

Neither tool doing the other's job would be as good. A grammar that tries to infer
Java types would be unmaintainable. A regex parser that tries to match every COBOL
dialect would be a 10,000-line string of patterns.

---

## The decision tree

If you pick **heuristic only**, you will permanently not parse COMPUTE, STRING, UNSTRING,
INSPECT, MULTIPLY, DIVIDE, EXEC SQL, or dialect-specific constructs. Every program
that uses these generates wrong or incomplete JSON. You will spend ongoing engineering
time adding regex branches for new constructs as you encounter them, and each new branch
adds fragility to existing patterns.

If you pick **ANTLR only**, you lose JCL parsing, COPY expansion, PIC type inference,
level-88 linkage, risk flags, and all W-warnings unless you rebuild all of that on top
of the raw parse tree — which is exactly the adapter work, meaning you end up at the
hybrid anyway but with a worse API contract.

If you pick **hybrid**, you get a correct syntactic foundation from ANTLR and a correct
semantic enrichment layer from your code. The adapter is the implementation cost. The
architecture is already right — `factory.py`, `base.py`, and `antlr_parser.py` exist
and are correct. The remaining work is filling the grammar files and writing the adapter.

The hybrid is not the most complex option. It is the most complete option with the
lowest long-term maintenance burden.
