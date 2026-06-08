# COBOL Modernization Pipeline — Hybrid Parser Architecture
## Complete Technical Reference

---

## 1. Architecture Diagram

```
COBOL Source (expanded, copybooks resolved)
        │
        ├─────────────────────────────────┐
        ▼                                 ▼
HeuristicParser                     ANTLRTreeWalker
app/services/cobol_parser.py        app/parsers/cobol_tree_adapter.py
                                    Uses: grammars_v4_master/cobol85/Cobol85.g4
                                    Via:  app/parsers/generated/

AUTHORITATIVE FOR:                  AUTHORITATIVE FOR:
✓ symbol_table                      ✓ COMPUTE (with expression + rounded)
✓ paragraphs (source order)         ✓ ADD / SUBTRACT / MULTIPLY / DIVIDE
✓ MOVE operations                   ✓ EVALUATE WHEN dispatch → calls[]
✓ DISPLAY / ACCEPT                  ✓ EVALUATE TRUE WHEN condition reads
✓ PERFORM VARYING details           ✓ Formal IF/EVALUATE branch detection
✓ Source line references            ✓ STRING / UNSTRING / INSPECT
✓ Reads/writes tracking             ✓ GO TO detection
✓ PIC decoding + java_type          ✓ antlr_syntax_ok flag
✓ OCCURS hierarchy                  ✓ antlr_errors list
        │                                 │
        └──────────────┬──────────────────┘
                       ▼
             HybridMerger.merge()
             app/parsers/hybrid_merger.py

             Ownership rules:
             ─────────────────────────────────────────
             symbol_table   → heuristic wins
             paragraphs     → heuristic wins (order)
             operations     → heuristic: MOVE, DISPLAY, ACCEPT, STOP-RUN, EXIT-*
                              ANTLR:     COMPUTE, ADD, SUBTRACT, MULTIPLY, DIVIDE,
                                         STRING, UNSTRING, INSPECT
                              fallback:  heuristic for any type ANTLR did not produce
             calls[]        → union, dedup by (from, to, condition)
             branches[]     → union, dedup by (type, condition, paragraph)
             loops[]        → heuristic (richer), fallback ANTLR if heuristic empty
             gotos[]        → union
             risk_flags     → set union of both
             warnings       → both, tagged source: "heuristic" | "antlr"
             ─────────────────────────────────────────
             Added fields:
             antlr_syntax_ok   → bool
             antlr_errors      → list of {line, column, msg}
             parser_mode       → "hybrid" | "hybrid_degraded" | "heuristic" | "antlr_validated"
             grammar_metadata  → documents grammar source paths
                       │
                       ▼
             Final enriched JSON
             (same schema as original ParserLayer.parse()
              plus the 4 new fields above)
```

---

## 2. Parser Backends

Three backends available via `PARSER_BACKEND` env var:

| Backend | What it does | When to use |
|---|---|---|
| `heuristic` | ParserLayer only, fast, always available | Testing, CI without ANTLR artifacts |
| `antlr` | ANTLR syntax check + heuristic output (no op merge) | Syntax validation only |
| `hybrid` *(default)* | Both parsers run, output merged | Production — best output |

### Graceful Degradation

If ANTLR artifacts are missing or the ANTLR pass crashes:
- `parser_mode` = `"hybrid_degraded"`
- `antlr_syntax_ok` = `false`
- `antlr_errors` = `[{"msg": "ANTLR artifacts unavailable — heuristic only"}]`
- All other output comes from heuristic parser, unchanged

The pipeline **never crashes** due to ANTLR failure.

---

## 3. File Map

```
app/
├── parsers/
│   ├── factory.py                    ← create_parser(backend) entry point
│   ├── hybrid_parser.py              ← HybridCobolParser class
│   ├── hybrid_merger.py              ← HybridMerger.merge() + dedup logic
│   ├── cobol_tree_adapter.py         ← CobolTreeAdapter(Cobol85Visitor), 16 hooks
│   ├── column_aware_paragraphs.py    ← Fixed-format paragraph source extraction
│   ├── antlr_parser.py               ← parse_and_validate() wrapper
│   └── generated/
│       ├── parse_tree_adapter.py     ← run_antlr_pass() + parse_with_hybrid()
│       ├── Cobol85Lexer.py           ← generated from grammars_v4_master
│       ├── Cobol85Parser.py          ← generated from grammars_v4_master
│       ├── Cobol85Visitor.py         ← generated (extended by CobolTreeAdapter)
│       └── Cobol85Listener.py        ← generated
├── services/
│   └── cobol_parser.py               ← heuristic ParserLayer (original)
└── core/
    └── config.py                     ← PARSER_BACKEND, ANALYSIS_ENGINE env vars

grammars_v4_master/
└── cobol85/
    └── Cobol85.g4                    ← AUTHORITATIVE expert grammar (~7300 lines)

antlr4/                               ← ANTLR toolchain (jar resolution)

scripts/
└── regenerate_antlr.sh               ← Regeneration script with --verify flag
```

---

## 4. CobolTreeAdapter — 16 Visitor Hooks

All method names are verified against `grammars_v4_master/cobol85/Cobol85.g4`
rule names before implementation. Each hook wraps in try/except and appends
to warnings on failure — never raises.

| Visitor Method | Grammar Rule | What It Produces |
|---|---|---|
| `visitProgramIdParagraph` | `programIdParagraph` | program_name_antlr |
| `visitParagraph` | `paragraph` | paragraphs[], sets _current_para |
| `visitDataDescriptionEntryFormat1` | `dataDescriptionEntryFormat1` | symbol_table entries |
| `visitMoveToStatement` | `moveToStatement` | MOVE operations |
| `visitComputeStatement` | `computeStatement` | COMPUTE with expression + rounded |
| `visitAddStatement` | `addStatement` | ADD operations |
| `visitSubtractStatement` | `subtractStatement` | SUBTRACT operations |
| `visitMultiplyStatement` | `multiplyStatement` | MULTIPLY operations |
| `visitDivideStatement` | `divideStatement` | DIVIDE operations |
| `visitPerformStatement` | `performStatement` | calls[] + loops[] |
| `visitEvaluateStatement` | `evaluateStatement` | branches[] + WHEN→calls[] |
| `visitIfStatement` | `ifStatement` | branches[] |
| `visitDisplayStatement` | `displayStatement` | DISPLAY operations |
| `visitAcceptStatement` | `acceptStatement` | ACCEPT operations |
| `visitReadStatement` | `readStatement` | READ operations |
| `visitWriteStatement` | `writeStatement` | WRITE operations |
| `visitStopStatement` | `stopStatement` | STOP RUN detection |
| `visitGoToStatement` | `goToStatement` | gotos[], goto_present risk flag |
| `visitStringStatement` | `stringStatement` | STRING + string_manipulation flag |
| `visitUnstringStatement` | `unstringStatement` | UNSTRING + string_manipulation flag |
| `visitInspectStatement` | `inspectStatement` | INSPECT + inspect_tallying flag |

Risk flags set by ANTLR visitor:
- `arithmetic_expression` — any COMPUTE/ADD/SUBTRACT/MULTIPLY/DIVIDE
- `conditional_logic` — any EVALUATE
- `loop_logic` — any PERFORM VARYING
- `string_manipulation` — any STRING/UNSTRING
- `inspect_tallying` — any INSPECT
- `goto_present` — any GO TO

---

## 5. HybridMerger Logic

### Operation Ownership

```python
_HEURISTIC_OWNS = {"MOVE", "DISPLAY", "ACCEPT", "STOP-RUN", "EXIT-PERFORM",
                   "EXIT-PARAGRAPH", "STOPRUN"}

_ANTLR_OWNS     = {"COMPUTE", "ADD", "SUBTRACT", "MULTIPLY", "DIVIDE",
                   "STRING", "UNSTRING", "INSPECT"}
```

### Merge Steps

1. `kept_h` = heuristic ops where type in `_HEURISTIC_OWNS`
2. `kept_a` = ANTLR ops where type in `_ANTLR_OWNS`
3. `fallback_h` = heuristic ops where ANTLR owns the type but produced nothing
   (protects against ANTLR partial failures)
4. `operations = kept_h + kept_a + fallback_h`

### Deduplication Keys

- calls: `(from, to, condition)`
- branches: `(type, condition, paragraph)`
- operations fingerprint: `(type, target, paragraph)` for COMPUTE;
  `(type, perform_target, paragraph)` for PERFORM

---

## 6. grammar_metadata Field

Attached to all parse results. Documents which grammar files were used:

```json
{
  "grammar_metadata": {
    "grammar_source": "grammars_v4_master/cobol85/Cobol85.g4",
    "generated_target": "app/parsers/generated/",
    "runtime": "antlr4-python3-runtime (pip)",
    "note": "Expert COBOL85 grammar from antlr/grammars-v4 community repository"
  }
}
```

---

## 7. Regeneration

```bash
# Verify artifacts exist
./scripts/regenerate_antlr.sh --verify

# Regenerate from local grammar source
./scripts/regenerate_antlr.sh
```

Jar resolution order:
1. `antlr4/tool/target/antlr4-*-complete.jar`
2. `antlr4/*.jar`
3. System `antlr4` CLI (pip-installed fallback)

---
*File 2 of 5 — Hybrid Parser Architecture*
