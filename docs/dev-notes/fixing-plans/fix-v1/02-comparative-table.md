# Comparative Analysis — Heuristic vs ANTLR-Only vs Hybrid

## Reading this table

Every row is a **specific, measurable technical capability** — not a vague feature
description. For each approach, the cell explains exactly what happens technically,
not just whether it works or not. The verdict column states the winner and why.

---

## Table 1 — Syntactic parsing capabilities

| Capability | Heuristic only (yours) | ANTLR only | Hybrid | Verdict |
|---|---|---|---|---|
| **Division detection** | Regex `^(IDENTIFICATION\|ID\|ENVIRONMENT\|DATA\|PROCEDURE)\s+DIVISION` with `ID→IDENTIFICATION` normalization. One known offset bug when sequence numbers are absent. | Grammar rule `identificationDivision`, `environmentDivision`, etc. Correct by construction. Handles all dialect variants. | ANTLR handles structural detection; your normalization (`ID→IDENTIFICATION`) runs in the adapter. | **Hybrid = ANTLR** for correctness |
| **Fixed/free format detection** | Heuristic: counts lines where cols 1–6 match `[ 0-9]{6}`. Returns fixed if ≥ 1/3 of lines match. Can misclassify programs with unusual formatting. | Lexer grammar has separate `FIXED` and `FREE` modes. Mode switch is explicit, not heuristic. | ANTLR lexer mode selection replaces the heuristic. No misclassification. | **Hybrid = ANTLR** |
| **Continuation line joining** | Indicator col 7 = `-` triggers join. String-literal context preserved by counting quote characters. Edge case: mixed quote styles in same literal. | Lexer handles continuation at token level. All indicator column variants (`-`, `D` debug lines, compiler directives) handled by the grammar. | ANTLR token stream replaces your `_preprocess()` method entirely. | **Hybrid = ANTLR** |
| **Comment line stripping** | Col 7 = `*` or `/` skipped in `_preprocess_fixed_line()`. Free format: lines starting with `*` or `*>` skipped. | Lexer rule `COMMENT_LINE: COL7 '*' ~[\r\n]* -> skip`. Handles all comment variants including `*>` inline comments in free format. | ANTLR handles this at tokenization; your layer never sees comment tokens. | **Hybrid = ANTLR** |
| **Paragraph name detection** | `_is_paragraph_header()`: checks `starts_in_area_a`, non-reserved, ends with `.`, not a scope terminator, not a quoted string, matches `[A-Z0-9][A-Z0-9-]*`. 8 conditions total. Risk of false positive on unusual identifiers. | Grammar rule `paragraph: paragraphName DOT`. Correct by construction — parser knows it is in a context where a paragraph name is valid. No ambiguity. | ANTLR `visitParagraph()` provides paragraph name directly. No heuristic needed. | **Hybrid = ANTLR** |
| **Section detection** | `upper.endswith("SECTION.")` — very simple. Misses sections whose names are not on a standalone line (uncommon but valid). | Grammar rule `section: sectionName SECTION DOT`. Context-aware. | ANTLR `visitSection()`. | **Hybrid = ANTLR** |
| **COMPUTE statement** | **Not parsed.** Detected by `STATEMENT_VERBS` membership and triggers an `INFO` warning. No entry in the `operations` array. Expression is lost. | Grammar rule `computeStatement`: target, optional `ROUNDED`, `=`, arithmetic expression. Full expression tree with operator precedence. | Adapter visits `computeStatement` node, calls `_parse_operand()` on target, emits `{"type":"COMPUTE","expression":…,"rounded":bool}`. | **Hybrid required** — heuristic fails |
| **STRING / UNSTRING** | Not parsed. INFO warning only. Clauses (`DELIMITED SIZE INTO TALLYING`) are completely lost. | Grammar rules `stringStatement` and `unstringStatement` cover all clauses including multiple INTO targets and WITH POINTER. | Adapter visits these nodes and emits structured operation entries. | **Hybrid required** |
| **INSPECT** | Not parsed. INFO warning only. | Grammar rule `inspectStatement` covers TALLYING and REPLACING modes. | Adapter emits INSPECT operation with mode and targets. | **Hybrid required** |
| **MULTIPLY / DIVIDE** | Not parsed. | Grammar rules `multiplyStatement`, `divideStatement` with GIVING and REMAINDER clauses. | Adapter emits structured arithmetic operations. | **Hybrid required** |
| **EXEC SQL blocks** | Detected by `"EXEC SQL" in upper`. INFO flag only. SQL statement content discarded. | Grammar lexer rule captures `EXEC SQL ... END-EXEC` as a token block. SQL text is preserved as a string. | Adapter emits `{"type":"EXEC_SQL","sql_text":"…"}`. Can feed a SQL parser downstream. | **Hybrid significantly better** |
| **Compiler directives** (`>>IF`, `>>DEFINE`) | Not recognized. Lines treated as unknown content or skipped. | Lexer handles `>>` prefix compiler directives. Grammar has rules for conditional compilation. | ANTLR handles; adapter records as metadata. | **Hybrid = ANTLR** |
| **Error recovery** | `_preflight_check()` returns errors and the parse halts — `_build_preflight_failure()` returns empty structures. A program with a missing FD produces no symbol table. | ANTLR generates error nodes using built-in error recovery strategies. Parsing continues after errors. The parse tree is partial but still useful. | ANTLR error nodes trigger warnings in the adapter. Partial JSON output with error markers rather than empty output. | **Hybrid = ANTLR** |

---

## Table 2 — Semantic enrichment capabilities

| Capability | Heuristic only (yours) | ANTLR only | Hybrid | Verdict |
|---|---|---|---|---|
| **PIC clause → java_type** | `_decode_pic()`: `9(5)V99 → BigDecimal`, `X(20) → String`, `S9(7) → int with signed flag`. Produces `int_digits`, `dec_digits`, `storage_length`, `java_type`. | ANTLR gives the raw PIC token string. No type inference. The grammar knows a PIC clause exists, not what it means for Java. | ANTLR gives the PIC token; `_decode_pic()` runs on it. Identical output to heuristic path, but the input is a verified token from a correct parse. | **Hybrid = your code on ANTLR's verified input** |
| **Level-88 condition name linkage** | `_extract_88_values()` parses the VALUE clause. `condition_names[]` attached to parent symbol with list of matching values. | ANTLR parses level-88 as `dataDescriptionEntry`. It gives you the level number, name, and VALUE clause text. It does not link the 88-level to its parent field. | Adapter: when it encounters a level-88 node, it calls your `_extract_88_values()` and attaches the result to the previously visited parent symbol. | **Hybrid = your code fills ANTLR gap** |
| **PERFORM THRU range expansion** | `_extract_control_flow()`: given `PERFORM A THRU C`, looks up paragraph order list, expands to individual calls to A, B, C. | ANTLR gives `performThru(A, C)` node. It does not expand the range — it has no concept of paragraph order. | Adapter: on THRU node, look up paragraph order (built during visitor traversal) and expand. Same logic as heuristic, on verified node. | **Hybrid = your logic fills ANTLR gap** |
| **Conditional call marking** | Condition stack tracks IF/WHEN context. Every PERFORM inside an IF gets `conditional: True` with the condition string. | ANTLR parse tree shows that a `performStatement` is a child of an `ifStatement`. Nesting relationship is clear from tree structure. | Adapter: check whether the PERFORM node's ancestors include an IF or EVALUATE node. More accurate than stack-based tracking — no risk of stack corruption. | **Hybrid = ANTLR tree is more reliable** |
| **Risk flags** | Computed from completed symbol table + control flow JSON. `goto_present`, `occurs_present`, `redefines_present`, etc. | Not provided. ANTLR produces a parse tree, not semantic analysis. | Adapter calls `_extract_risk_flags()` after building the JSON structures. Identical output, but based on a more complete and correct data set (all statements captured, not just the ones the heuristic handles). | **Hybrid = your code, better input** |
| **W-warnings (W001–W006)** | `_extract_warnings()` runs over operations + symbol table + control flow. W001 unused variable, W002 write-only, W004 dead paragraph, W006 GO TO. | Not provided. | Adapter calls `_extract_warnings()` at the end. Because the operations array is now complete (COMPUTE, STRING, etc. are included), W001 and W002 are more accurate — variables used only in COMPUTE were previously invisible to the warning generator. | **Hybrid = your code, more accurate results** |
| **Symbol kind inference** | `_infer_symbol_kind()`: group/array/numeric/string/redefines/condition based on presence of pic, occurs, redefines keys in the symbol dict. | ANTLR provides the grammatical classification (it knows `OCCURS` is present, `REDEFINES` is present) but does not produce the migration-oriented kind label. | Adapter calls `_infer_symbol_kind()` on the enriched symbol dict built from ANTLR fields. | **Hybrid = your code fills ANTLR gap** |

---

## Table 3 — Pipeline capabilities (unique to your architecture)

| Capability | Heuristic only (yours) | ANTLR only | Hybrid | Verdict |
|---|---|---|---|---|
| **JCL parsing** | `jcl_parser.py`: job steps, EXEC PGM, DD bindings, SYSLIB, COND, inline PROC. Complete. | No ANTLR COBOL grammar covers JCL. JCL is a completely different language. | `jcl_parser.py` is unchanged and runs as Stage 1. Unique to your pipeline. | **Both paths = your code exclusively** |
| **COPY expansion** | `copybook_resolver.py`: REPLACING, recursive nesting, circular detection, cache, source maps. Complete. | Standard ANTLR usage requires pre-expanded source. The grammar treats COPY as a reference, not a statement to expand. | `copybook_resolver.py` runs as Stage 2, feeds expanded source to ANTLR. Critical prerequisite. | **Both paths = your code exclusively** |
| **Logical → physical file mapping** | `context_enricher.py`: maps COBOL file names to JCL DD names to physical DSNs. Happy path complete; fallback buggy. | Not applicable — ANTLR knows nothing about runtime file bindings. | `context_enricher.py` is unchanged and runs as Stage 4 consuming the enriched AST. | **Both paths = your code exclusively** |
| **Multi-program project support** | Supported via the copybook cache and context enricher's per-program step matching. | Not applicable. | Same as heuristic path — your stages are program-agnostic. | **Both paths = your code exclusively** |

---

## Table 4 — Operational characteristics

| Characteristic | Heuristic only | ANTLR only | Hybrid |
|---|---|---|---|
| **Performance on 50k-line programs** | Unknown. Multiple full passes over the lines array. Python regex at scale may be slow (seconds per file). | Single-pass LL(*) tokenization + parsing. Sub-second on large files. ANTLR is a compiled parser generator, not a Python loop. | ANTLR parse pass is fast. Your adapter is a single tree-walk — O(n) where n is node count, not line count. Total ≈ ANTLR cost. |
| **Dialect variance handling** | One implicit dialect assumed. IBM-specific extensions (COMP-3, POINTER, level-66 renames, address-of) silently missed or misclassified. | The Cobol85 grammar covers the widest common subset. IBM, MicroFocus, and GnuCOBOL variants have grammar extensions available. | ANTLR grammar selected per dialect. Your enrichment logic is dialect-agnostic — it runs on whatever the grammar produces. |
| **Maintainability** | Every new COBOL construct requires a new regex branch in `_parse_operation()`. Regex brittleness increases with complexity. | Grammar rules are modular. Adding a new verb means adding one grammar rule. | Grammar handles new constructs. Adapter adds one visitor method. Your enrichment methods remain unchanged. Lowest maintenance burden long-term. |
| **Testability** | Unit-testable at regex level. Hard to test edge cases without actual COBOL source. | Grammar can be tested with ANTLR's test framework. Parse tree structure is deterministic. | Both layers independently testable. Adapter can be tested with mock parse trees. |

---

## Summary verdict

The hybrid approach wins every category where either individual approach has a weakness:

- Where ANTLR is better (syntactic correctness, error recovery, COMPUTE/STRING/INSPECT,
  performance, dialect handling) → ANTLR runs and your adapter processes its output.
- Where your code is better (PIC decoding, level-88 linkage, JCL parsing, COPY expansion,
  file binding, risk flags, W-warnings) → your methods run unchanged on ANTLR's verified
  input, producing more accurate results than on heuristic input.
- Where only your code can do something (JCL, COPY, file binding) → those stages are
  completely outside the ANTLR path and remain unchanged in both approaches.

The one thing the heuristic-only approach gets entirely right that ANTLR cannot touch
is Stages 1, 2, and 4. These are your unique contributions and they stay in the hybrid.
