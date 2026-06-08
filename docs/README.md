# COBOL modernization — documentation index

## Architecture reference (EY review)

Start with `architecture/ARCHITECTURE_README.md`, then read the `ARCH_*.md` series.

| Document | What it covers |
|---|---|
| [architecture/ARCH_00_SYSTEM_LOGIC.md](./architecture/ARCH_00_SYSTEM_LOGIC.md) | Full system picture |
| [architecture/ARCH_02_PARSER_ANALYSIS_CONVERSION_LOGIC.md](./architecture/ARCH_02_PARSER_ANALYSIS_CONVERSION_LOGIC.md) | Parser, analysis, both conversion modes |
| [architecture/ARCH_04_TESTING_VALIDATION_AND_DOWNLOAD_LOGIC.md](./architecture/ARCH_04_TESTING_VALIDATION_AND_DOWNLOAD_LOGIC.md) | Testing, behavioral diff, validation |
| [architecture/00_project_overview.md](./architecture/00_project_overview.md) | Routes, config defaults, orchestration |
| [architecture/01-architecture-and-pipeline.md](./architecture/01-architecture-and-pipeline.md) | End-to-end pipeline stages and JSON shapes |
| [architecture/02-parser-layer-and-fixes.md](./architecture/02-parser-layer-and-fixes.md) | ParserLayer + hybrid backend details |
| [architecture/03-api-and-dashboard-behavior.md](./architecture/03-api-and-dashboard-behavior.md) | API and dashboard integration |
| [architecture/04-testing-and-use-cases.md](./architecture/04-testing-and-use-cases.md) | pytest, Use Case 3, PAYROLL regression |
| [architecture/PARSER_LAYER_SPECS.md](./architecture/PARSER_LAYER_SPECS.md) | Parser specification |
| [architecture/ANALYSIS_AGENT_SPECS.md](./architecture/ANALYSIS_AGENT_SPECS.md) | Analysis agent specification |
| [architecture/SCHEMA_CONTRACTS.md](./architecture/SCHEMA_CONTRACTS.md) | Cross-cutting schemas |

## Internal dev notes

Iteration notes, fix plans, and prompts: `dev-notes/` (not required for architecture review).

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
