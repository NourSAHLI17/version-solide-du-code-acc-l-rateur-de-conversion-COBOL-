# cobol-modernization-service — Active Backend

This folder is the **implemented FastAPI backend** for the COBOL Modernizer platform.

## Quick start

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8010 --reload
```

Or from repo root: `start_backend.bat` (launches on port 8010).

## Structure

| Folder | Contents |
|---|---|
| `app/agents/` | `AnalysisAgent`, `ConversionAgent` |
| `app/api/` | REST routes under `/api` |
| `app/converters/` | Constrained generation (F45), Java scaffolding |
| `app/parsers/` | `ParserLayer`, `HybridCobolParser`, JCL, COPY |
| `app/services/` | `PipelineService`, testing, behavioral diff, repairs |
| `app/validation/` | `ValidationService` |
| `tests/` | pytest suite |
| `docs/` | Canonical architecture source (copied to `../docs/architecture/`) |

## Architecture documentation

High-level docs for EY review: `../docs/architecture/`. The `docs/` folder here is the
canonical source; updates should be mirrored to `../docs/architecture/` when changed.

## Related projects

| Folder | Role |
|---|---|
| `../cobol-modernization-dashboard/` | Next.js frontend |
| `../acme-bank-v3/` | COBOL test case (6 programs) |
