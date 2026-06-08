# Hybrid modernization architecture: technical rationale, parser elevation, heuristic vs ANTLR, PAYROLL-CALC, and the three outputs

This document is written so you—the COBOL literate owner of the explanation—can brief audiences who are **not** fluent in COBOL but **are** technical (architects, engineering managers, security). It ties **architecture**, **implementation choices**, **what was fixed**, and **how PAYROLL-CALC** exercises the stack end-to-end.

---

## 1. Thesis: why “hybrid” elevates the parsing layer

**Parsing is not an isolated preprocessing step.** In a naive “AI rewrite” pipeline, *everything* downstream depends on whatever the model *believes* about identifiers, pictures, verbs, and control flow—errors compound into analysis and Java.

In this project, **the parsing layer is elevated** because:

1. **Contract-first JSON** — `ParserLayer.parse()` returns a **stable, versioned structure** (`symbol_table`, `operations`, `control_flow`, …). Downstream stages **consume facts**, not prose.

2. **Semantic extraction becomes mechanical** — PIC clauses decode to `pic_decoded` (Java type hints, digit counts). Each `COMPUTE` becomes an operation with **`rounded: true|false`**. `DISPLAY` emits **`references`** only for **unquoted** data names. That lets analysis and conversion **reason over symbols**, not regex over raw lines.

3. **LLMs are pushed into a narrower job** — Given **parser JSON + analysis JSON + rounding_contract**, the conversion model generates Java **under constraints**. It is no longer asked to *discover* that `PIC V9(4)` is an implied decimal fraction or that `WHEN WS-GROSS-PAY < 500` reads gross pay.

4. **Regression is possible** — `pytest` asserts invariants on PAYROLL (PIC, DISPLAY, COMPUTE flags, tax paragraph inputs). That is impossible if “parse” is implicit inside an LLM.

**Bottom line for stakeholders:** *Hybrid means “machine-checked structure first, language generation second.”* That is how risk drops from “prompt engineering” to “software engineering.”

---

## 2. Two orthogonal axes (do not conflate them)

| Axis | Options | What it changes |
|------|---------|-----------------|
| **A. Parser backend** | **`heuristic`** (`ParserLayer`) vs **`antlr`** (`AntlrCobolParser` scaffold) | **How** source becomes JSON |
| **B. Pipeline style** | **Deterministic** analysis vs **LLM** conversion | **Who** produces semantics vs Java |

**Hybrid pipeline** refers primarily to axis **B**: deterministic parse + deterministic analysis + optional LLM conversion.

Axis **A** is a **swap-in parser**: same factory (`create_parser`), same env (`PARSER_BACKEND`), same downstream contract **once** the ANTLR adapter emits equivalent JSON.

---

## 3. Heuristic parser (the approach you implemented): strengths and limits

**What it is:** A staged, regex- and rule-driven **structural** parser in Python (`app/parsers/cobol_parser.py`). It deliberately targets **verbs and shapes** needed for modernization (symbols, MOVE/COMPUTE/DISPLAY/PERFORM, control_flow branches/calls/loops, dependencies), not a full ISO COBOL semantic compiler.

### Strengths (why we kept it as default)

| Strength | Technical meaning |
|----------|-------------------|
| **Controlled surface area** | Each verb family can be tested in isolation; gaps are explicit (`warnings`, unsupported verb notices). |
| **Fast iteration** | No grammar generation pipeline, no JVM step in the inner loop of feature work. |
| **Deterministic output** | Same input → same JSON → CI gates. |
| **Operational simplicity** | Pure Python + FastAPI; fits typical enterprise deployment. |
| **Tailored to modernization JSON** | Output is already **our** schema (`operations`, `pic_decoded`), not a raw AST dump that still needs a massive adapter. |

### Limits (honest)

| Limit | Implication |
|-------|-------------|
| Not a complete grammar | Corner dialects / rare constructs may require incremental parser work. |
| Heuristic PIC | Complex edited pictures need careful `_decode_pic` rules (we hardened `V9(4)`, display edited `Z…`). |
| Structural, not full semantics | Data division semantics (full alignment, group moves) are approximated where needed for pipeline value. |

**When to praise it in a meeting:** *“We traded theoretical completeness for **predictable, testable extraction** aligned with modernization artifacts—not building a general-purpose COBOL compiler.”*

---

## 4. ANTLR path (grammar-based, expert-maintained ecosystem): strengths and current status

**What it is:** Industry-standard **lexer/parser generator**. COBOL grammars exist in the wild (maintained by specialists); generated Python targets give **token-accurate** parse trees.

### Strengths

| Strength | Technical meaning |
|----------|-------------------|
| **Syntax-centric correctness** | Recognition follows grammar rules, not ad-hoc regex growth. |
| **Ecosystem** | ANTLR tooling, debuggers, grammar reuse, incremental upgrades. |
| **Parse tree** | Visitor/listener patterns for transformation—natural fit for “tree → our JSON.” |

### Current status in *this* repo

- `PARSER_BACKEND=antlr` instantiates `AntlrCobolParser`.
- Grammar assets live under `app/grammars/`; **production parsing is not switched** until generated lexer/parser + **`parse_tree_adapter`** map to the **same JSON contract** as `ParserLayer` and tests pass.
- **Honest messaging:** ANTLR is the **evolution path**, not a drop-in advantage until parity work completes.

### Complementarity (heuristic **and** ANTLR)

| Phase | Role |
|-------|------|
| **Now** | Heuristic feeds hybrid pipeline; proves downstream value (analysis, conversion contracts). |
| **Next** | ANTLR improves **syntactic fidelity** on complex sources; **same** analysis/conversion consume JSON. |
| **Never wasted** | Tests and schema double as **acceptance criteria** for ANTLR parity. |

---

## 5. What we fixed technically (parser → analysis → conversion chain)

These fixes are **why** “byte-identical bad outputs” disappear once the **deployed** server runs current code.

### 5.1 Parser (`cobol_parser.py`)

- **`PIC V9(4)`** (`WS-TAX-RATE`): implied decimal **without** leading `9`; decoder treats leading `V` as numeric and maps to **BigDecimal** semantics in `pic_decoded`.
- **`DISPLAY`**: strip quoted literals **before** extracting identifiers → banner text does not fabricate references.
- **`COMPUTE`**: emit typed operations with **`rounded`**, **`expression`**, **`references`**; merge continuation lines into one logical statement.
- **`WHEN`**: append branch rows so **`8300-DETERMINE-TAX-RATE`** conditions surface **`WS-GROSS-PAY`** for data-flow.
- **`parser_revision`**: operational proof of build version in JSON.

### 5.2 Segmenter (`segmenter.py`)

- **`paragraph_source_lines`**: analysis sees **only** the paragraph’s lines → no **`STOP RUN`** bleeding from **`0000-MAIN`** into every paragraph’s pseudo–source text.
- Paragraph header matching **case-normalized** so mapping cannot silently empty.

### 5.3 Analysis (`analysis_agent.py`)

- **`_is_pure_termination`**: a paragraph with **`DISPLAY`** work is **not** “terminate only.”
- **Branch inputs**: match hyphenated names in **`WHEN WS-GROSS-PAY < 500`** → **`WS-GROSS-PAY`** ∈ inputs for tax paragraph.
- **OCCURS / capacity**: one **program-level** capacity rule instead of duplicating “30 entries” across many paragraphs.
- **Response contract (top-level):** **`analysis_engine`** (`"llm"` \| `"deterministic"` \| `"n/a"`), **`analysis_revision`** (integer: `2` = LLM path, `1` = deterministic completion, `0` = preflight halt), **`paragraph_source_extraction`** (`"column_aware"` \| `"heuristic_split"` \| `"n/a"`). See §7 Output 2.

### 5.4 Conversion (`conversion_agent.py`)

- **`rounding_contract`**: deterministic line-per-**`COMPUTE`** mapping to **`RoundingMode.HALF_UP`** vs **`DOWN`** fed **above** raw JSON so the LLM cannot “average away” COBOL semantics.

---

## 6. PAYROLL-CALC use case — COBOL walkthrough for your presentation

**Fixture:** `cobol-modernization-service/tests/fixtures/payroll/PAYROLL-CALC.cbl`  
**Purpose:** Medium-complexity interactive payroll **driver program** (console UI), not a batch payroll production system—but **rich enough** to stress parser, analysis, and conversion.

### 6.1 What the program does (business language)

- Keeps up to **30** employees in working storage (`OCCURS 30`).
- Menu: add employee, view, enter hours, run payroll calc, summary report, reset period, exit.
- Pay logic: **regular vs overtime** (40 hours), **progressive tax brackets** on gross, **net = gross − tax**.
- Uses **`COMPUTE … ROUNDED`** vs plain **`COMPUTE`** deliberately so rounding semantics differ per line.

### 6.2 Identification / environment

- **`PROGRAM-ID. PAYROLL-CALC`** — names the compilation unit; appears as `program_name` in parser JSON.

### 6.3 Data division — what to say slide-by-slide

**Control / loop scalars**

| Item | PIC | Meaning for audience |
|------|-----|---------------------|
| `WS-MENU-CHOICE` | `PIC 9` | Single digit menu choice. |
| `WS-CONTINUE-FLAG` | `PIC X` | `'Y'`/`'N'` loop flag—classic COBOL **boolean-as-char**. |
| `WS-IDX`, `WS-FOUND-IDX` | `9(3)` | Indexes into `OCCURS`—loop counters and search results. |

**Pay computation working storage**

| Item | PIC | COBOL nuance |
|------|-----|----------------|
| `WS-HOURLY`-style amounts | `9(n)V99`, `9(n)V9` | Implied decimal **binary-coded** storage—maps to **BigDecimal** in Java migration. |
| **`WS-TAX-RATE`** | **`PIC V9(4)`** | **Only fractional part** (0.0000–0.9999 style usage here)—decoder must treat **`V`** as implied decimal **without** leading integer nines. |
| `WS-STANDARD-HOURS` | `9(3)V9` value **40.0** | Overtime threshold. |
| `WS-OVERTIME-MULTIPLIER` | `9V99` value **1.50** | Time-and-a-half. |

**Roster**

- **`WS-EMPLOYEE OCCURS 30`** — table of records; each slot has ID, name, dept, rate, hours, gross/tax/net, **`EMP-ACTIVE`**, **`EMP-PAY-COMPUTED`** flags.

**Display-only edited numerics** (`ZZ9.99`, …)

- These are **report masks**; arithmetic uses **numeric working storage**, not the Z-edit pictures.

### 6.4 Procedure division — control flow narrative

| Paragraph | Behavior |
|-----------|----------|
| **`0000-MAIN`** | Banner → **`PERFORM 1000-SHOW-MENU UNTIL`** exit flag → goodbye → **`STOP RUN`**. Entry + life cycle. |
| **`1000-SHOW-MENU`** | Prints menu, **`ACCEPT WS-MENU-CHOICE`**, **`PERFORM 2000-ROUTE-CHOICE`**. |
| **`2000-ROUTE-CHOICE`** | **`EVALUATE WS-MENU-CHOICE`** — dispatch `WHEN 1 … 6`, exit on `0`. Classic **menu router**. |
| **`3000-ADD-EMPLOYEE`** | Scan **`PERFORM VARYING WS-IDX … UNTIL > 30`** for first inactive slot (`EXIT PERFORM` when found). Duplicate check via **`8000`**. |
| **`3300-RUN-PAYROLL`** | Loop all slots; if active, not yet computed, hours > 0 → **`PERFORM 8200-CALCULATE-PAY`**. |
| **`8200-CALCULATE-PAY`** | Split regular/overtime, **`COMPUTE`** gross, **`PERFORM 8300-DETERMINE-TAX-RATE`**, tax and net. **Mix of ROUNDED and non-ROUNDED `COMPUTE`**. |
| **`8300-DETERMINE-TAX-RATE`** | **`EVALUATE TRUE`** with **`WHEN WS-GROSS-PAY < …`** — **bracketed progressive tax**. |

**Presenter tip:** The bug class “**sum 1..30**” was **never** valid COBOL semantics here—**`UNTIL WS-IDX > 30`** is an **index bound**, not a summation. The pipeline must **not** infer financial rules from loop syntax alone.

### 6.5 PAYROLL “stress tests” for the toolchain

| COBOL feature | Pipeline stress |
|---------------|----------------|
| `PIC V9(4)` | PIC decoding / Java type |
| Quoted `DISPLAY` | Reference extraction |
| Multi-line `COMPUTE` | Statement merge + `rounded` |
| `EVALUATE TRUE` / `WHEN field op constant` | Branch rows + **inputs** for tax paragraph |
| Nested `PERFORM` | `control_flow.calls` for conversion structure |

---

## 7. The three outputs (what you show side-by-side)

Everything below is what you can literally pull from the API / tests after **`ParserLayer().parse`** + **`AnalysisAgent().analyze`** + **`ConversionAgent.convert`** (when LLM configured).

### Output 1 — Parser JSON (structural truth)

**Producer:** `ParserLayer` (`cobol_parser.py`).  
**Role:** Single source of structural truth for tools and LLMs.

**Representative top-level keys:**

| Key | Audience explanation |
|-----|---------------------|
| `program_name` | From `PROGRAM-ID`. |
| `parser_revision` | Build id — proves deployed code. |
| `symbol_table[]` | Each data item: `name`, `pic`, **`pic_decoded`** (`java_type`, `dec_digits`, …), `occurs`, parent group. |
| `operations[]` | Verbs: `MOVE`, `COMPUTE`, `DISPLAY`, `ACCEPT`, … with `paragraph`, **`rounded`** on `COMPUTE`, **`references`**. |
| `control_flow` | `branches` (IF, EVALUATE, **WHEN**), `loops`, **`calls`** (PERFORM graph), `gotos`. |
| `paragraphs[]` | Ordered paragraph names. |
| `warnings` / `risk_flags` | Preflight and quality hints. |

**Why it matters:** Without this, “analysis” and “Java” are guesses.

### Output 2 — Analysis JSON (semantic rollup)

**Producer:** `AnalysisAgent` (`analysis_agent.py`), with optional **LLM overlay** when `ANALYSIS_ENGINE=llm` and credentials are available (deterministic scaffolding still fills IO flags and aggregates).  
**Role:** Paragraph-level and program-level **meaning** for converters and humans—**grounded** in parser facts plus raw COBOL slices on the LLM path.

**Contract fields (always present on every analysis response path):**

| Key | Allowed values | Meaning |
|-----|----------------|---------|
| `analysis_engine` | `"llm"` \| `"deterministic"` \| `"n/a"` | Which engine produced the rollup: **`llm`** (primary path), **`deterministic`** (explicit config or LLM unavailable), **`n/a`** (preflight halted before analysis). |
| `analysis_revision` | **`int`** | **`2`** = completed analysis via LLM path; **`1`** = completed deterministic path; **`0`** = preflight halt (`analysis_engine` is `"n/a"`). |
| `paragraph_source_extraction` | `"column_aware"` \| `"heuristic_split"` \| `"n/a"` | How paragraph bodies fed into analysis were derived: **`column_aware`** respects fixed-format column 7 (required automatically when **`ANALYSIS_ENGINE=llm`**); **`heuristic_split`** uses segmenter line mapping unless opt-in **`ANALYSIS_USE_COLUMN_PARAGRAPH_SOURCES`**; **`n/a`** when analysis did not run. |

**Representative keys (beyond the contract):**

| Key | Audience explanation |
|-----|---------------------|
| `global_purpose` | One-sentence program intent. |
| `sections[]` | Per paragraph: **`role`**, **`inputs`**, **`outputs`**, **`business_rules`**, **`calls`**, **`called_by`**. |
| `business_rules` / `all_business_rules` | Rules **traceable** to constructs—not free-form essay. |
| `data_flow_summary` | High-level I/O story. |
| `complexity`, `conversion_guidance` | Hints for chunking and risk. |

**Why it matters:** Converts “what does this paragraph do?” into **structured** answers anchored to **`ParserLayer` JSON**, and (on the LLM path) to **column-aware paragraph source** so the model does not invent control flow from empty slices.

### Output 3 — Java + mapping notes (+ rounding discipline)

**Producer:** `ConversionAgent` + LLM when API keys present; stub otherwise.  
**Role:** **Target language artifact** + traceability.

**What you get:**

| Artifact | Audience explanation |
|----------|---------------------|
| Java source | Methods, `BigDecimal`, control structures informed by **parser + analysis**. |
| `## MAPPING NOTES` | Paragraph ↔ method, assumptions (per prompt contract). |
| Prompt internals | **`rounding_contract`** listing each **`COMPUTE`** → HALF_UP vs DOWN — **COBOL `ROUNDED` keyword is not cosmetic**. |

**Why it matters:** This is the **only** stage that should “sound like Java”—but it must **not** invent PICs or rounding.

---

## 8. Paradigm comparison (slide-ready)

| Dimension | Raw LLM “compile” | Heuristic + hybrid (current) | Grammar-first ANTLR (target) |
|-----------|---------------------|------------------------------|------------------------------|
| Syntax fidelity | Low | **Medium–high (chosen subset)** | **High (grammar-complete)** |
| Time to value | Days | **Weeks–months continuous** | **Quarters (grammar+adapter)** |
| Testability | Weak | **Strong (pytest + fixtures)** | **Strong (same JSON contract)** |
| Cost model | High token burn | **LLM mostly on conversion** | Same downstream |

---

## 9. File map (where truth lives)

| Concern | Path |
|---------|------|
| Heuristic parser | `cobol-modernization-service/app/parsers/cobol_parser.py` |
| Parser factory | `app/parsers/factory.py` |
| ANTLR scaffold | `app/parsers/antlr_parser.py`, `app/grammars/**` |
| Config `PARSER_BACKEND`, `ANALYSIS_ENGINE`, `ANALYSIS_USE_COLUMN_PARAGRAPH_SOURCES` | `app/core/config.py` |
| Segmenter | `app/services/segmenter.py`, `app/services/pipeline_segmenter.py` |
| Analysis | `app/agents/analysis_agent.py`, `app/prompts/analysis_agent_system_prompt.md` |
| Conversion | `app/agents/conversion_agent.py` |
| PAYROLL tests | `tests/test_payroll_multiline_statements.py` |
| PAYROLL source | `tests/fixtures/payroll/PAYROLL-CALC.cbl` |

---

## 10. One closing argument for leadership

> **The parsing layer is elevated because it stops being “text” and becomes typed, versioned evidence.** Hybrid modernization uses that evidence everywhere—inputs to analysis, contracts to Java—so we modernize **systems**, not **prompts**.

---

*Revision note: align **`parser_revision`** (parser build id, string in parser JSON) and **`analysis_revision`** (integer analysis contract: 0 halt / 1 deterministic / 2 LLM) with your deployed branch when presenting.*
