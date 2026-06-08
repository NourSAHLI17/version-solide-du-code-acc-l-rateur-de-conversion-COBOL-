# Project Logic and Architecture Guide

This folder documents the **implemented** COBOL modernization platform. All paths refer to
`cobol-modernization-service/` unless noted otherwise.

## How to read these docs

### System logic (start here for EY review)

| File | What it explains |
|---|---|
| `ARCH_00_SYSTEM_LOGIC.md` | Full system picture and responsibilities |
| `ARCH_01_BACKEND_PIPELINE_APPROACHES.md` | Pipeline modes and endpoint approaches |
| `ARCH_02_PARSER_ANALYSIS_CONVERSION_LOGIC.md` | Parser, analysis, and **both conversion modes** |
| `ARCH_03_PROJECT_UPLOAD_AND_BATCH_FLOW.md` | ZIP upload, copybooks, batch processing |
| `ARCH_04_TESTING_VALIDATION_AND_DOWNLOAD_LOGIC.md` | Testing agent, behavioral diff, downloads |
| `ARCH_05_FRONTEND_BACKEND_INTERACTION.md` | Frontend pages and API calls |
| `ARCH_06_APPROACH_DECISIONS_AND_TRADEOFFS.md` | Design decisions and tradeoffs |

### Source contracts (exact schemas and routes)

| File | Contract area |
|---|---|
| `00_project_overview.md` | App entry points, routes, config defaults |
| `01_jcl_and_copy_resolver.md` | JCL parser and COPY resolver |
| `02_cobol_parser.md` | COBOL parser output contract |
| `03_segmenter_aggregator.md` | Segmenter and aggregator |
| `04_testing_agent.md` | Testing agent report contract |
| `05_analysis_conversion_download.md` | Analysis, conversion, project, download APIs |
| `PARSER_LAYER_SPECS.md` | Parser layer specification |
| `SEGMENTER_LAYER_SPECS.md` | Segmenter specification |
| `ANALYSIS_AGENT_SPECS.md` | Analysis agent specification |
| `SCHEMA_CONTRACTS.md` | Cross-cutting schemas |

## Main system idea

The platform modernizes COBOL into Java by preserving **evidence at every step**:

```text
source files
  → deterministic structure (hybrid parser)
  → semantic analysis (LLM or deterministic)
  → mode-aware Java conversion (whole-class or constrained)
  → compile/repair + deterministic testing
  → downloadable artifacts
```

## Active components

| Part | Role | Source |
|---|---|---|
| API routes | Expose each pipeline stage | `app/api/routes/modernization.py`, `testing.py` |
| Pipeline service | Orchestrate stages | `app/services/pipeline_service.py` |
| JCL parser | Job steps, DD bindings | `app/parsers/jcl_parser.py` |
| COPY resolver | Expand COPY dependencies | `app/parsers/copybook_resolver.py` |
| COBOL parser | Structure, symbols, control flow | `app/parsers/cobol_parser.py` (`ParserLayer`) |
| Hybrid parser | ANTLR + heuristic merge (default) | `app/parsers/hybrid_parser.py` |
| Context enricher | JCL-aware file bindings | `app/parsers/context_enricher.py` |
| Segmenter | Paragraph-level slices | `app/services/segmenter.py` |
| Analysis agent | Business rules, risks, guidance | `app/agents/analysis_agent.py` |
| Conversion agent | Java generation (2 modes) | `app/agents/conversion_agent.py` |
| Constrained generation | Scaffold + per-paragraph LLM | `app/converters/constrained_generation.py` |
| Testing agent | Parser/conversion/behavioral checks | `app/services/testing_agent.py` |
| Behavioral diff | GnuCOBOL vs Java stdout compare | `app/services/behavioral_diff_runner.py` |
| Validation service | Expected vs actual output compare | `app/validation/service.py` |

## Parser backends

Selected by `PARSER_BACKEND` (default: **`hybrid`**):

| Value | Implementation | When to use |
|---|---|---|
| `hybrid` | `HybridCobolParser` — heuristic + ANTLR merge | **Default** for production |
| `heuristic` | `ParserLayer` only | Fast, no ANTLR runtime |
| `antlr` | `AntlrCobolParser` | Grammar validation path |

## Conversion modes

| Mode | Trigger | Behavior |
|---|---|---|
| **Whole-class** | Small programs, not in mandatory list | Single LLM call via `ConversionAgent._convert_raw()` |
| **Constrained (F45)** | `LOANEVAL`, `RECOVRY`, `RPTMONTH`, `RISKSCOR`, or >400 non-blank lines | Python builds class scaffold; LLM fills method bodies per paragraph |

Decision function: `should_use_constrained_generation()` in `app/converters/constrained_generation.py`.

## Pipeline approaches

| Approach | Input | Context for conversion |
|---|---|---|
| Raw conversion | COBOL only | Source text |
| Parser-guided | COBOL + parser JSON | Structure, symbols, control flow |
| Analysis-guided | COBOL + analysis JSON | Business rules, risks |
| Full context | COBOL + parser + analysis | **Recommended default** |
| Project batch | ZIP upload | Per-file source + shared copybooks |
| Behavioral verification | Generated Java + COBOL | GnuCOBOL vs Java diff |

## Frontend (`cobol-modernization-dashboard/`)

| Page | Purpose |
|---|---|
| Single File | End-to-end run on one COBOL source |
| Conversion | Mode-based conversion workflow |
| Project Upload | ZIP upload, batch pipeline, project download |
| Testing Agent | Run test report on generated Java |
| Parser / Analysis / Validation | Debug individual stages |
| Shared workspace | Persist artifacts across page navigation |

## Rule for future changes

```text
deterministic evidence first
  → explicit API contract
  → frontend displays real artifact
  → conversion uses only provided context
  → testing or validation reports the result
```
