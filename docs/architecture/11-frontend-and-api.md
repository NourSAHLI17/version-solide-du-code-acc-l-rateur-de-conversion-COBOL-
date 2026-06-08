# 11 — Frontend and API Integration

How the Next.js dashboard interacts with the FastAPI backend.

**Frontend:** `cobol-modernization-dashboard/`  
**Backend routes:** `app/api/routes/modernization.py`, `testing.py`

---

## Division of responsibility

| Frontend | Backend |
|---|---|
| Collect user input | Execute pipeline stages |
| Call real API endpoints | Own all transformation logic |
| Display backend artifacts | Generate Java, test reports, ZIPs |
| Persist workspace state | Return typed JSON contracts |
| Trigger downloads | Stream file responses |

The frontend **never** invents parser, analysis, Java, or test results.

---

## API base URL

```env
# cobol-modernization-dashboard/.env.local
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8010/api
```

Default in code (`src/lib/api.ts`): `http://127.0.0.1:8010/api` if unset.

---

## Shared workspace

Browser `localStorage` workspace (`src/lib/workspace.ts`) persists:

| Key | Content |
|---|---|
| `sourceCode` | Current COBOL source |
| `parserResult` | Last parser JSON |
| `analysisResult` | Last analysis JSON |
| `javaCode` | Generated Java |
| `projectResults` | Batch pipeline results |
| `jclManifest` | JCL parse output |
| `validationResult` | Validation compare result |
| `backendStatus` | `/api/status` snapshot |
| `lastError` | Last API error message |

**Hydration guard:** Next.js SSR must not overwrite saved workspace before client
hydration completes.

---

## Pages and API calls

| Page | Primary endpoint | Purpose |
|---|---|---|
| Single File | `POST /api/pipeline/run` | End-to-end with mode selector |
| Conversion | `POST /api/convert` | Conversion with context modes |
| Project Upload | `POST /api/project/upload` + `/api/project/pipeline` | Batch |
| Parser | `POST /api/parse` | Parser JSON only |
| Analysis | `POST /api/analyze` | Analysis only |
| Validation | `POST /api/validate` | Expected vs actual |
| Testing | `POST /api/test` | Full test report |
| Cockpit | Multiple stage endpoints | Manual step control |

On load, pages call `GET /api/status` to show LLM and toolchain availability.

---

## Single file workflow

```text
User pastes COBOL
  → POST /api/pipeline/run { mode: "full", cobol_source }
  → Response: parser_output, analysis_output, java_source
  → Workspace updated
  → User navigates to Testing page with javaCode preserved
```

---

## Project upload workflow

```text
User uploads ZIP
  → POST /api/project/upload
  → File tree displayed
  → POST /api/project/pipeline { files, mode: "full" }
  → Per-file results in projectResults
  → POST /api/download/project for ZIP
```

---

## Error display

API errors surface in workspace `lastError` and page-level error banners. HTTP 500
responses show `detail` from FastAPI `HTTPException`.

---

## CORS

Backend enables permissive CORS in `app.main` for local development (dashboard on 3000,
API on 8010).

---

## Related documents

- [reference/api-reference.md](./reference/api-reference.md) — full endpoint list
- [02 — Pipeline and data flow](./02-pipeline-and-data-flow.md) — what each endpoint orchestrates
- [EXECUTION_GUIDE.md](../../EXECUTION_GUIDE.md) — how to start both services
