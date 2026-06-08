# Parser layer — what changed and why

This document describes **`ParserLayer`** (`app/parsers/cobol_parser.py`) and related behavior.

## 2.1 FILLER and duplicate names

**Problem:** COBOL uses `FILLER` many times in one record. Treating every `FILLER` as a unique “data name” caused false “duplicate name” preflight failures and stopped parsing.

**Approach:**

| Mechanism | Behavior |
|-----------|----------|
| `UNREFERENCEABLE_NAMES = frozenset({"FILLER"})` | FILLER is not treated like a normal duplicate for fatal checks / W007 duplicate-name warnings |
| Symbol table | FILLER rows can carry `"unreferenceable": True` |

**Why it matters:** Programs that `COPY` layouts such as `RPTHDCPY.cpy` introduce many FILLER lines; blocking on duplicates would empty the entire AST.

## 2.2 Preflight (`_preflight_check`)

Preflight runs **before** full extraction.

| Outcome | Meaning |
|---------|---------|
| `(errors, warnings)` | Fatal `errors` → `_build_preflight_failure` (empty structure); `warnings` merged later |

**Typical fatal error:** undeclared index in `PERFORM VARYING` (iterator not in declared names).

## 2.3 Multi-line statements (`_combine_logical_statements`)

**Problem:** COBOL allows statements to span lines **without** column-7 continuation (`-`). Example:

```cobol
COMPUTE WS-X ROUNDED =
    WS-A + WS-B.
```

Previously, each physical line was parsed alone → **no COMPUTE operation**, and **W002** false positives.

**Approach:** After `_preprocess`, a pass runs **inside PROCEDURE DIVISION** only: merge continuation lines into the previous statement until a `.` or new statement starter (`STATEMENT_STARTERS`: verbs, `END-IF`, `ELSE`, etc.).

**Regression:** `tests/fixtures/payroll/PAYROLL-CALC.cbl` + `test_payroll_multiline_statements.py`.

## 2.4 Copybook metadata in `parse(source, copybook_metadata)`

| Source | Purpose |
|--------|---------|
| Resolver audit (`copybook_metadata`) | Merge names into `dependencies.copybooks` |
| Raw source scan | Patterns like `>>> COPY … EXPANDED FROM` / `BEGIN COPY` |

## 2.5 Parser backend selection (`factory.py`)

Default: **`hybrid`**.

| `PARSER_BACKEND` | Class | Behavior |
|---|---|---|
| `hybrid` | `HybridCobolParser` | `ParserLayer` + ANTLR visitor merge via `HybridMerger` |
| `heuristic` | `ParserLayer` | Heuristic extraction only |
| `antlr` | `AntlrCobolParser` | ANTLR validation without full merge |

Hybrid flow (`app/parsers/generated/parse_tree_adapter.py` → `parse_with_hybrid()`):

1. Run `ParserLayer().parse(source)` (always)
2. If ANTLR unavailable → return heuristic JSON with `parser_backend: "hybrid_degraded"`
3. If ANTLR available → `run_antlr_pass()` + `CobolTreeAdapter` visitor → `HybridMerger.merge()`
4. Set `parser_backend: "hybrid"`, `antlr_syntax_ok`, `antlr_operations_merged`

---

*Next: [03-api-and-dashboard-behavior.md](./03-api-and-dashboard-behavior.md)*
