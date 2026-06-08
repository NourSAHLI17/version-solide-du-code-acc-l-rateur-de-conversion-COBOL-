# COBOL modernization — documentation index

## Architecture (EY review)

**Start here:** [`architecture/README.md`](./architecture/README.md)

### Global view

| # | Document |
|---|---|
| 01 | [System overview](./architecture/01-system-overview.md) |
| 02 | [Pipeline and data flow](./architecture/02-pipeline-and-data-flow.md) |
| 03 | [Design decisions](./architecture/03-design-decisions.md) |

### Pipeline components (execution order)

| # | Document |
|---|---|
| 04 | [JCL and COPY resolution](./architecture/04-jcl-and-copy-resolution.md) |
| 05 | [COBOL parsing](./architecture/05-cobol-parsing.md) |
| 06 | [Context enrichment and segmentation](./architecture/06-context-enrichment-and-segmentation.md) |
| 07 | [Analysis agent](./architecture/07-analysis-agent.md) |
| 08 | [Java conversion](./architecture/08-java-conversion.md) |
| 09 | [Testing, validation, and download](./architecture/09-testing-validation-and-download.md) |
| 10 | [Project batch upload](./architecture/10-project-batch-upload.md) |
| 11 | [Frontend and API](./architecture/11-frontend-and-api.md) |

### Reference

| Document | Purpose |
|---|---|
| [API reference](./architecture/reference/api-reference.md) | Endpoints and request schemas |
| [Schema contracts](./architecture/reference/schema-contracts.md) | JSON between stages |
| [Developer guide](./architecture/reference/developer-guide.md) | Extending the engine |

## How to run

See [`../EXECUTION_GUIDE.md`](../EXECUTION_GUIDE.md) at the repository root.

## Code locations

| Area | Path |
|---|---|
| Backend | `cobol-modernization-service/app/` |
| Hybrid parser | `app/parsers/hybrid_parser.py` |
| Pipeline | `app/services/pipeline_service.py` |
| Frontend | `cobol-modernization-dashboard/src/` |
| Test case | `acme-bank-v3/` |
