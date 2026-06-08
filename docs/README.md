# COBOL modernization — documentation index

## Architecture reference (EY review)

Start with [`architecture/ARCHITECTURE_README.md`](./architecture/ARCHITECTURE_README.md) — it is the canonical index for all architecture docs.

### System logic (`ARCH_*.md`)

| Document | What it covers |
|---|---|
| [architecture/ARCH_00_SYSTEM_LOGIC.md](./architecture/ARCH_00_SYSTEM_LOGIC.md) | Full system picture |
| [architecture/ARCH_01_BACKEND_PIPELINE_APPROACHES.md](./architecture/ARCH_01_BACKEND_PIPELINE_APPROACHES.md) | Pipeline modes and endpoint approaches |
| [architecture/ARCH_02_PARSER_ANALYSIS_CONVERSION_LOGIC.md](./architecture/ARCH_02_PARSER_ANALYSIS_CONVERSION_LOGIC.md) | Parser, analysis, both conversion modes |
| [architecture/ARCH_03_PROJECT_UPLOAD_AND_BATCH_FLOW.md](./architecture/ARCH_03_PROJECT_UPLOAD_AND_BATCH_FLOW.md) | ZIP upload, copybooks, batch processing |
| [architecture/ARCH_04_TESTING_VALIDATION_AND_DOWNLOAD_LOGIC.md](./architecture/ARCH_04_TESTING_VALIDATION_AND_DOWNLOAD_LOGIC.md) | Testing, behavioral diff, validation |
| [architecture/ARCH_05_FRONTEND_BACKEND_INTERACTION.md](./architecture/ARCH_05_FRONTEND_BACKEND_INTERACTION.md) | Frontend pages and API calls |
| [architecture/ARCH_06_APPROACH_DECISIONS_AND_TRADEOFFS.md](./architecture/ARCH_06_APPROACH_DECISIONS_AND_TRADEOFFS.md) | Design decisions and tradeoffs |

### Source contracts and specs

| Document | What it covers |
|---|---|
| [architecture/00_project_overview.md](./architecture/00_project_overview.md) | Routes, config defaults, orchestration |
| [architecture/01_jcl_and_copy_resolver.md](./architecture/01_jcl_and_copy_resolver.md) | JCL parser and COPY resolver |
| [architecture/02_cobol_parser.md](./architecture/02_cobol_parser.md) | COBOL parser output contract |
| [architecture/03_segmenter_aggregator.md](./architecture/03_segmenter_aggregator.md) | Segmenter and aggregator |
| [architecture/04_testing_agent.md](./architecture/04_testing_agent.md) | Testing agent report contract |
| [architecture/05_analysis_conversion_download.md](./architecture/05_analysis_conversion_download.md) | Analysis, conversion, project, download APIs |
| [architecture/PARSER_LAYER_SPECS.md](./architecture/PARSER_LAYER_SPECS.md) | Parser layer specification |
| [architecture/SEGMENTER_LAYER_SPECS.md](./architecture/SEGMENTER_LAYER_SPECS.md) | Segmenter specification |
| [architecture/ANALYSIS_AGENT_SPECS.md](./architecture/ANALYSIS_AGENT_SPECS.md) | Analysis agent specification |
| [architecture/SCHEMA_CONTRACTS.md](./architecture/SCHEMA_CONTRACTS.md) | Cross-cutting schemas |
| [architecture/DEVELOPER_GUIDE.md](./architecture/DEVELOPER_GUIDE.md) | Developer onboarding |

## Code locations

| Area | Path |
|---|---|
| Backend (active) | `cobol-modernization-service/app/` |
| Hybrid parser | `cobol-modernization-service/app/parsers/hybrid_parser.py` |
| Heuristic parser | `cobol-modernization-service/app/parsers/cobol_parser.py` |
| Pipeline | `cobol-modernization-service/app/services/pipeline_service.py` |
| Conversion modes | `cobol-modernization-service/app/agents/conversion_agent.py` |
| Behavioral diff | `cobol-modernization-service/app/services/behavioral_diff_runner.py` |
| Frontend | `cobol-modernization-dashboard/src/` |
| ACME test case | `acme-bank-v3/` |
