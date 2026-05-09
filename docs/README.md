# COBOL modernization — documentation index

This folder explains **what was implemented**, **why**, and **how it was tested**. Read in order for a full picture, or jump to a chapter.

| # | Document | What it covers |
|---|----------|----------------|
| 1 | [01-architecture-and-pipeline.md](./01-architecture-and-pipeline.md) | End-to-end stages (JCL → COPY → parse → enrich), diagrams, main JSON shapes |
| 2 | [02-parser-layer-and-fixes.md](./02-parser-layer-and-fixes.md) | `ParserLayer`: FILLER, preflight, multi-line statements, copybook metadata |
| 3 | [03-api-and-dashboard-behavior.md](./03-api-and-dashboard-behavior.md) | `/api/pipeline/run` analysis handling, localStorage, when to restart the server |
| 4 | [04-testing-and-use-cases.md](./04-testing-and-use-cases.md) | Use Case 3 integration tests, PAYROLL-CALC multiline tests, how to run `pytest` |

**Code locations (quick reference)**

| Area | Path |
|------|------|
| Heuristic parser | `cobol-modernization-service/app/parsers/cobol_parser.py` |
| COPY resolution | `cobol-modernization-service/app/parsers/copybook_resolver.py` |
| Pipeline orchestration | `cobol-modernization-service/app/services/pipeline_service.py` |
| JCL + data mapping | `cobol-modernization-service/app/parsers/context_enricher.py` |
| API routes | `cobol-modernization-service/app/api/routes/modernization.py` |
| Dashboard | `cobol-modernization-dashboard/src/` |
| Use Case 3 fixtures | `cobol-modernization-service/tests/fixtures/usecase3/` |
| Integration test | `cobol-modernization-service/tests/test_usecase3_pipeline.py` |
| PAYROLL fixture + tests | `tests/fixtures/payroll/`, `tests/test_payroll_multiline_statements.py` |
