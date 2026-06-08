# Executive briefing: hybrid modernization, stack, PAYROLL story, and Q&A

Companion to **`05-hybrid-approach-quality-fixes-and-file-map.md`** (full technical depth). Use **05** for architects; use **this file** for directors and steering committees—then drill down on demand.

---

## 1. The argument in 30 seconds

**Legacy risk:** Treating COBOL as “text for GPT” reproduces the worst of shadow IT—no audit trail, wrong decimals, fantasy business rules.

**Our answer:** A **hybrid pipeline**: **deterministic structural parsing** + **deterministic semantic rollup** + **LLM-assisted Java generation constrained by machine-checked JSON**. Parsing is **not** a throwaway step—it **elevates** everything downstream because identifiers, pictures, verbs, and **`ROUNDED`** flags become **typed facts**.

---

## 2. Elevating the parsing layer (why investors / risk officers care)

| Without elevated parsing | With elevated parsing |
|--------------------------|------------------------|
| “The AI said gross pay works like X” | “**Operations** list shows **`COMPUTE`** with **`rounded: true|false`** per COBOL line” |
| PIC guesses | **`pic_decoded`** says **BigDecimal** and **decimal digits** |
| Loop confused with “sum 1..30” | **Branches** and **loops** are separate facts—capacity ≠ summation |
| Same deployment mystery | **`parser_revision`** / **`analysis_revision`** prove **which build** ran |

**Tagline:** *Evidence-first modernization—not prose-first modernization.*

---

## 3. Two strategies, one downstream contract

**Do not confuse these:**

1. **Pipeline hybrid** — deterministic parse + analysis + (optional) LLM Java. **This is how we reduce risk today.**

2. **Parser backend choice** — **`heuristic`** (Python structural parser, **default**) vs **`antlr`** (grammar-generated tree, **scaffold until parity**). **Both target the same JSON contract** so analysis/conversion stay stable when we upgrade the front-end parser.

### Sound bites

| Approach | Strength we acknowledge publicly |
|----------|----------------------------------|
| **Heuristic (ours)** | Fast iteration, **pytest-regressed**, tailored JSON for modernization—not pretending to be a full ISO compiler overnight. |
| **ANTLR / expert grammars** | Industrial-grade **syntax** story; right long-term for dialect breadth **once** adapter + parity tests land. |

**Credibility line:** *We are not betting against ANTLR—we are **sequencing** it after we have a **proven downstream consumption model**.*

---

## 4. PAYROLL-CALC in 60 seconds (for non-COBOL listeners)

- **What it is:** A **sample payroll driver**—in-memory table of **30** employees, menu, hours entry, **pay calculation**, tax brackets, report.
- **Why we use it:** It mixes **`PIC V9(4)`**, **`DISPLAY` literals**, multi-line **`COMPUTE … ROUNDED`**, **`EVALUATE TRUE`** tax tiers, and **`PERFORM`** nesting—the **same patterns** that break naive tooling.
- **What success looks like:** Parser sees **`WS-TAX-RATE`** as numeric decimal; **`DISPLAY "…CALCULATOR"`** has **no false variables**; tax paragraph lists **`WS-GROSS-PAY`** as an input; Java respects **HALF_UP vs DOWN** per **`COMPUTE`**.

*Deep COBOL narrative:* full walkthrough is in **§6 of doc 05**.

---

## 5. The three outputs (what you demo)

| # | Output | One-line value |
|---|--------|----------------|
| **1** | **Parser JSON** | “Ground truth from source—symbols, verbs, control flow, **`rounded`**.” |
| **2** | **Analysis JSON** | “Paragraph roles and rules **grounded** in parser facts—repeatable.” |
| **3** | **Java + notes (+ rounding contract)** | “Target language under **constraints**—not a blind rewrite.” |

If LLM keys are off, **Output 3** may be a stub—still show **1** and **2** to prove **deterministic** value.

---

## 6. Technology inventory (for slides)

| Layer | Technology | Why mention it |
|-------|------------|----------------|
| API | **FastAPI**, **Uvicorn** | Standard, OpenAPI-friendly integration. |
| Runtime | **Python 3** | Parser, pipeline, tests in one stack. |
| LLM glue | **LangChain**, **LangChain Core** | Portable prompts across providers. |
| Providers | **Google GenAI**, **OpenAI**, **OpenRouter** (via **httpx**) | Procurement flexibility. |
| Config | **python-dotenv** | Secrets and **`PARSER_BACKEND`** outside source. |
| Quality | **Ruff**, **pytest** | **200+** tests; PAYROLL regression pack. |
| Future parser | **ANTLR** (grammar folder + scaffold) | **Roadmap**, not “done” until parity—honesty builds trust. |
| Optional UI | Next.js dashboard *(if in scope)* | Separate concern from parsing truth. |

---

## 7. Benefits (business language)

1. **Auditability** — Three artifacts instead of one chat response.
2. **Financial hygiene** — **`ROUNDED`** ≠ cosmetic; reflected in contracts.
3. **Regression** — Same fixture → same structural invariants in CI.
4. **Cost discipline** — LLM calls concentrated where prose/code generation helps.
5. **Technical debt containment** — ANTLR plugs in **without** rewriting analysis/conversion.

---

## 8. Anticipated questions (sharp answers)

**Q: Why didn’t we start with ANTLR?**  
**A:** Grammar + adapter + parity is **multi-quarter**. Heuristic parser **unblocked** downstream design and **tests** that ANTLR must eventually satisfy.

**Q: Is the LLM analyzing COBOL?**  
**A:** **Production** analysis is **deterministic Python** for repeatability. Prompt markdown exists for **governance** and a possible future LLM path—not today’s runtime.

**Q: Can we ship generated Java to prod?**  
**A:** Treat as **accelerated draft**: human review + optional behavioral diff (GnuCOBOL vs JVM) for programs that warrant it.

**Q: How do we know production matches dev?**  
**A:** Parse/analyze JSON carry **`parser_revision`** and **`analysis_revision`** / **`analysis_engine`** fields—operators can verify alignment.

---

## 9. Closing line (optional)

> **Hybrid modernization means the machine proves what the COBOL actually contains before we ask any model to write Java—and that proof becomes our regression suite.**
