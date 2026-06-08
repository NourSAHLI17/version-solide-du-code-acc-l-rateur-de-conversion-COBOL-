# 03 — Design Decisions and Tradeoffs

Decision guide for reviewers and future developers. Each decision states the approach, why it
exists, and the tradeoff accepted.

---

## 1. Staged pipeline instead of one big prompt

**Approach:** `COPY/JCL → parser → analysis → conversion → testing → validation`

| Why | Tradeoff |
|---|---|
| COBOL behavior depends on declarations, file bindings, COPY books, paragraph flow | More code and endpoints |
| Each stage output is inspectable in the UI | Users must understand stages |
| Failures localize to one stage | Benefit: traceability and safer conversion |

---

## 2. Deterministic components before LLM

**Approach:** Parser, COPY resolver, segmenter, testing, and validation are deterministic.
LLM is used for analysis (default) and Java generation only.

| Why | Tradeoff |
|---|---|
| Parser output must be stable; tests run without API keys | Heuristic parser less complete than commercial COBOL compilers |
| COPY expansion must not invent source | Benefit: predictable, debuggable behavior |

---

## 3. Raw COBOL always in conversion prompt

**Approach:** Every conversion includes the original source. Parser and analysis are optional
context layers.

| Why | Tradeoff |
|---|---|
| Parser/analysis may omit formatting or line-level detail | Longer prompts |
| Source remains ground truth | Benefit: fewer missing-source mistakes |

---

## 4. Multiple pipeline modes

**Approach:** `full`, `parse_only`, `parse_analyse`, `analyse_only`, `convert_only`, `no_parse`

| Why | Tradeoff |
|---|---|
| Isolate effect of parser vs analysis context on conversion | Mode names must stay documented |
| One endpoint drives frontend selector | Benefit: controlled experimentation |

---

## 5. Hybrid parser as default

**Approach:** `PARSER_BACKEND=hybrid` merges heuristic `ParserLayer` with ANTLR Cobol85 visitor.

| Why | Tradeoff |
|---|---|
| Heuristic handles project-specific edge cases (FILLER, multi-line) | Two parsers to maintain |
| ANTLR improves syntactic fidelity on complex sources | Degrades to heuristic if ANTLR unavailable |
| Same JSON contract regardless of backend | Benefit: one downstream contract |

---

## 6. Two conversion modes (whole-class vs constrained F45)

**Approach:** Small programs → single LLM call. Large / ACME programs → Python scaffold +
per-paragraph LLM.

| Why | Tradeoff |
|---|---|
| One prompt on 14 paragraphs mixes contexts | More LLM calls in F45 mode |
| Scaffold enforces class structure, imports, method signatures | Benefit: better structure on large programs |

Trigger: `should_use_constrained_generation()` in `app/converters/constrained_generation.py`.

---

## 7. In-memory project upload (no database)

**Approach:** ZIP read → file tree JSON → pipeline receives files back in request body.

| Why | Tradeoff |
|---|---|
| Self-contained projects; no persistent storage | Very large ZIPs may need streaming later |
| Copybooks in ZIP available during parse | Benefit: simple local dev and clear API |

---

## 8. Parser + analysis per file in project results

**Approach:** Project pipeline returns `parser_output` and `analysis_output` per `.cbl` file.

| Why | Tradeoff |
|---|---|
| Inspect every file; Testing Agent reuses artifacts | Larger response payloads |
| One failed file does not hide others | Benefit: batch diagnosability |

---

## 9. Shared frontend workspace

**Approach:** `localStorage` workspace shares source, parser, analysis, Java, project results
across pages.

| Why | Tradeoff |
|---|---|
| Generate on Conversion page, test on Testing page | Hydration/sync complexity |
| Navigation does not clear artifacts | Benefit: multi-page workflow |

---

## 10. Backend as source of truth

**Approach:** Frontend displays real API responses; no mock pipeline data.

| Why | Tradeoff |
|---|---|
| Trustworthy modernization output | UI empty when backend has no data |
| Tests match what users see | Benefit: honest debugging |

---

## 11. Static testing before behavioral diff

**Approach:** Parser + Java static checks first; GnuCOBOL vs Java runtime only when toolchain
available.

| Why | Tradeoff |
|---|---|
| Not every machine has `cobc` installed | Static checks cannot prove full equivalence |
| Fast feedback on common issues | Benefit: useful report in more environments |

---

## 12. Backend-generated downloads

**Approach:** `POST /api/download/java` and `/api/download/project` stream from backend.

| Why | Tradeoff |
|---|---|
| Consistent naming and ZIP assembly | Archives built in memory |
| Frontend only handles blob response | Benefit: simpler frontend |

---

## Extension checklist

When adding a new component:

1. Classify: deterministic or LLM-driven?
2. Implement service first, then typed API route
3. Return a displayable artifact for the frontend
4. Add to shared workspace if another page needs it
5. Add pytest for service or route contract
6. Update architecture docs (this folder)

**Rule:** If a feature cannot explain its input, output, and reason for existing, it likely
belongs in an earlier pipeline stage — not buried inside conversion.
