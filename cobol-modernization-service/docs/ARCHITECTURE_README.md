# Project Logic and Architecture Guide

This folder contains two kinds of documentation.

The numbered `00` to `05` files describe real backend contracts, schemas, endpoints, and source-level behavior.

The `ARCH_*` files explain the project logic in human terms: why each part exists, how the pieces connect, and why the pipeline uses this staged approach instead of one large conversion step.

## How To Read These Docs

Start here if you want the project logic:

| File | What It Explains | Best For |
|---|---|---|
| `ARCH_00_SYSTEM_LOGIC.md` | Full system picture and main responsibilities | Understanding the whole platform |
| `ARCH_01_BACKEND_PIPELINE_APPROACHES.md` | Backend pipeline modes and endpoint approaches | Understanding how requests move through backend stages |
| `ARCH_02_PARSER_ANALYSIS_CONVERSION_LOGIC.md` | Parser, analysis, and conversion separation | Understanding why conversion needs structured context |
| `ARCH_03_PROJECT_UPLOAD_AND_BATCH_FLOW.md` | ZIP upload, copybooks, batch processing, per-file results | Understanding project upload workflow |
| `ARCH_04_TESTING_VALIDATION_AND_DOWNLOAD_LOGIC.md` | Testing Agent, validation, and downloads | Understanding quality checks and output artifacts |
| `ARCH_05_FRONTEND_BACKEND_INTERACTION.md` | Frontend pages, shared workspace, API calls | Understanding how UI state connects to backend artifacts |
| `ARCH_06_APPROACH_DECISIONS_AND_TRADEOFFS.md` | Design decisions, tradeoffs, and extension guidance | Understanding why the project uses these approaches |

Use the source-contract docs when you need exact route or schema details:

| File | Source Contract Area |
|---|---|
| `00_project_overview.md` | Application entry points, backend routes, frontend routes |
| `01_jcl_and_copy_resolver.md` | JCL parser and COPY resolver contracts |
| `02_cobol_parser.md` | COBOL parser output contract |
| `03_segmenter_aggregator.md` | Segmenter and aggregator contracts |
| `04_testing_agent.md` | Testing Agent report contract |
| `05_analysis_conversion_download.md` | Analysis, conversion, project, and download contracts |

## Main System Idea

The project modernizes COBOL into Java by preserving evidence at every step.

The platform does not rely on one raw prompt that asks an LLM to understand everything. Instead, it builds context through deterministic stages first, then uses that evidence during Java conversion.

The core idea is:

```text
source files
  -> deterministic structure
  -> semantic analysis
  -> mode-aware Java conversion
  -> deterministic testing and validation
  -> downloadable artifacts
```

## Why The Pipeline Is Staged

COBOL modernization has several hidden risks:

- A small COPY book can change data layout for an entire program.
- JCL can explain file bindings that are not obvious in the COBOL source.
- Paragraph flow can affect behavior more than the visual order of the file.
- Numeric PIC clauses need careful Java type choices.
- A generated Java file can compile but still behave differently.

The staged approach reduces those risks by making each source of evidence visible and testable.

## Main Backend Parts

| Part | Why It Exists | Main Source Files |
|---|---|---|
| API routes | Expose every pipeline stage to the frontend | `app/api/routes/modernization.py` |
| Pipeline service | Orchestrate parse, analysis, conversion, project, testing, and download flows | `app/services/pipeline_service.py` |
| JCL parser | Extract job steps, DD statements, and dataset context | `app/services/jcl_parser.py` |
| COPY resolver | Expand or report COPY book dependencies | `app/services/copy_resolver.py` |
| COBOL parser | Extract program structure, symbols, control flow, dependencies, and warnings | `app/services/cobol_parser.py` |
| Segmenter | Split COBOL into paragraph-level conversion units | `app/services/pipeline_segmenter.py` |
| Aggregator | Reassemble converted segments into coherent Java output | `app/services/aggregator.py` |
| Analysis agent | Convert parser/source evidence into business and risk guidance | `app/agents/analysis_agent.py` |
| Conversion agent | Build Java from COBOL plus selected context | `app/agents/conversion_agent.py` |
| Testing agent | Check parser quality, Java conversion rules, and runtime behavior when tools exist | `app/services/testing_agent.py` |
| Validation service | Compare expected and actual outputs deterministically | `app/services/validation_service.py` |

## Main Frontend Parts

| Part | Why It Exists |
|---|---|
| Single File page | Fast end-to-end run for one COBOL source |
| Conversion page | Focused mode-based conversion workflow |
| Project Upload page | ZIP upload, file explorer, batch pipeline, project download |
| Testing Agent page | Run tests on generated Java from single-file or project output |
| Parser, Analysis, Validation pages | Debug individual backend stages |
| Shared workspace | Preserve generated artifacts across page navigation |
| Health strip | Show backend and model readiness |

## Pipeline Approaches At A Glance

| Approach | Input | Context Used For Conversion | Why Use It |
|---|---|---|---|
| Raw conversion | COBOL only | COBOL source | Fast fallback and provider smoke test |
| Parser-guided conversion | COBOL plus parser output | Source structure, symbols, control flow | Useful when semantic analysis is not needed |
| Analysis-guided conversion | COBOL plus analysis output | Business rules, risks, guidance | Useful when business meaning is more important than strict parser detail |
| Full context conversion | COBOL plus parser plus analysis | Structure and meaning together | Best default for real modernization |
| Project batch conversion | ZIP files | Per-file source plus project copybooks and selected mode context | Required for multi-file COBOL systems |
| Testing and validation | Generated Java plus parser/source/expected output | Static and runtime checks | Required to catch semantic drift |

## Rule For Future Changes

When adding a new feature, keep this pattern:

```text
deterministic evidence first
  -> explicit API contract
  -> frontend displays real artifact
  -> conversion uses only provided context
  -> testing or validation reports the result
```

This keeps the project explainable, debuggable, and safer for real modernization work.
