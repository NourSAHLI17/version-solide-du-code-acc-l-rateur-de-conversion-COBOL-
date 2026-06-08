# 01 — System Overview

## What this platform is

The COBOL Modernizer is an end-to-end system that converts legacy COBOL batch programs into
**plain Java** (no Spring Boot by default). It combines:

- **Deterministic extraction** — parsing, COPY expansion, JCL context, segmentation
- **LLM-assisted semantics** — business rules, risks, conversion guidance
- **Guided Java generation** — whole-class or constrained per-paragraph mode
- **Verification** — compile/repair, static tests, optional GnuCOBOL vs Java behavioral diff

| Layer | Technology | Folder |
|---|---|---|
| Backend API | Python 3.11+, FastAPI | `cobol-modernization-service/` |
| Frontend UI | Next.js, TypeScript | `cobol-modernization-dashboard/` |
| Sample test case | COBOL + data + JCL | `acme-bank-v3/` |
| Architecture docs | Markdown | `docs/architecture/` |

Default backend port: **8010**. Dashboard: **3000**.

---

## Core architectural idea

Modernization is **not** a single LLM prompt on raw COBOL. The system splits work into stages,
each producing inspectable JSON artifacts:

```text
source files
  → JCL parse + COPY resolve
  → hybrid COBOL parse (structure)
  → context enrichment + segmentation
  → semantic analysis
  → Java conversion (mode-selected)
  → compile/repair + testing
  → download
```

Every stage can run independently for debugging. The frontend shows real backend output — it
does not simulate pipeline results.

---

## Why stages instead of one prompt

COBOL programs depend on details that generic LLMs often miss:

| Concern | Why it matters |
|---|---|
| Fixed-format columns | Statement boundaries, comment lines |
| COPY books | Data layouts live outside the main program |
| JCL DD bindings | File names and paths for I/O |
| Paragraph control flow | PERFORM, GO TO, EVALUATE semantics |
| PIC clauses | Numeric precision, BigDecimal mapping |
| Global working-storage | Shared state across paragraphs |

A staged pipeline gives conversion **structured evidence** (parser JSON, analysis JSON) plus
the original source, reducing hallucination and making failures traceable to a specific stage.

---

## Central orchestration: `PipelineService`

`PipelineService` (`app/services/pipeline_service.py`) is the single orchestration layer.

| Responsibility | Benefit |
|---|---|
| Thin route handlers | Routes delegate to service methods |
| Centralized stage order | One place to change pipeline flow |
| Direct testability | pytest calls service without HTTP |
| Mode-based execution | `run_pipeline_mode()` for partial runs |

Key methods:

- `parse_jcl_source`, `resolve_copybooks`, `run_full_pipeline`
- `parse_cobol`, `analyze_cobol`, `convert_cobol`
- `run_pipeline_mode`, `run_project_pipeline`
- `get_runtime_status`

---

## Deterministic vs LLM components

| Deterministic (no LLM) | LLM-assisted |
|---|---|
| JCL parser, COPY resolver | Analysis agent (default) |
| Hybrid/heuristic COBOL parser | Java conversion (whole-class or F45) |
| Context enricher, segmenter | — |
| Testing agent (static checks) | — |
| Behavioral diff runner | — |
| Validation service | — |

Parser output must be **stable and reproducible**. Tests run without an API key. The LLM is
used only where generation or semantic interpretation is required.

---

## User workflows

| Workflow | When to use |
|---|---|
| **Single file** | One COBOL program, quick parse → analyze → convert |
| **Project upload** | ZIP with multiple `.cbl` files, copybooks, JCL |
| **Stage debug pages** | Parser, Analysis, Validation in isolation |
| **Testing agent** | After Java is generated — static + behavioral checks |
| **Cockpit** | Manual step-by-step backend operation |

---

## Frontend pages (summary)

| Page | Path | Purpose |
|---|---|---|
| Single File | `/convert/single` | End-to-end pipeline on one source |
| Project Upload | `/convert/project` | ZIP batch conversion |
| Conversion | `/conversion` | Mode-based conversion |
| Testing | `/testing/legacy` | Run test report on Java |
| Parser / Analysis / Validation | `/parser`, `/analysis`, `/validation` | Per-stage debug |
| Cockpit | `/cockpit` | Manual pipeline control |

Details: [11 — Frontend and API](./11-frontend-and-api.md).

---

## Repository layout (architecture-relevant)

```text
cobol/
├── cobol-modernization-service/app/   ← backend implementation
├── cobol-modernization-dashboard/     ← frontend
├── docs/architecture/                 ← this documentation set
├── acme-bank-v3/                      ← regression test case (6 programs)
├── grammars_v4_master/                ← ANTLR grammar reference
├── EXECUTION_GUIDE.md                 ← how to run the app
└── start_backend.bat / start_frontend.bat
```

---

## Next documents

- [02 — Pipeline and data flow](./02-pipeline-and-data-flow.md) — how stages connect
- [03 — Design decisions](./03-design-decisions.md) — tradeoffs and rationale
