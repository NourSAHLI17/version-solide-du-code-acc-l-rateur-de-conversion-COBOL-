# API Reference

FastAPI backend endpoints under `/api`. Source: `app/api/routes/modernization.py`,
`app/api/routes/testing.py`, `app/api/schemas/requests.py`.

Default port: **8010** (`start_backend.bat`, `EXECUTION_GUIDE.md`).

---

## Configuration (`load_config()`)

| Setting | Environment variable | Default |
|---|---|---|
| Host | `HOST` | `0.0.0.0` |
| Port | `PORT` | `8000` in code — use **8010** for handoff |
| LLM provider | `LLM_PROVIDER` | `auto` |
| Parser backend | `PARSER_BACKEND` | `hybrid` |
| Analysis engine | `ANALYSIS_ENGINE` | `llm` |
| Java profile | `JAVA_PROJECT_PROFILE` | `plain_java` |

API keys: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `GOOGLE_API_KEY`.

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/status` | Runtime health, LLM status |
| POST | `/api/parse` | COBOL → parser JSON |
| POST | `/api/analyze` | Source + parser → analysis JSON |
| POST | `/api/convert` | Source + context → Java |
| POST | `/api/validate` | Expected vs actual output |
| POST | `/api/segment` | Parser → paragraph segments |
| POST | `/api/aggregate` | Segments → assembled Java |
| POST | `/api/test` | Testing agent report |
| POST | `/api/smart-convert` | Auto parse/analyze + convert |
| POST | `/api/pipeline/run` | Mode-based pipeline |
| POST | `/api/project/upload` | ZIP → file tree |
| POST | `/api/project/pipeline` | Batch conversion |
| POST | `/api/download/java` | Single Java file download |
| POST | `/api/download/project` | Project ZIP download |
| POST | `/api/testing/behavioral-diff` | GnuCOBOL vs Java diff |
| GET | `/api/testing/toolchain-status` | `cobc` / `javac` availability |

Swagger UI: http://127.0.0.1:8010/docs

---

## Request schemas

| Model | Fields |
|---|---|
| `CobolRequest` | `source_code: str` |
| `AnalyzeRequest` | `source_code: str`, `parser_output: dict` |
| `ConvertRequest` | `source_code: str`, `parser_output: dict`, `analysis_output: str` |
| `ValidateRequest` | `expected_output: str`, `actual_output: str` |
| `SegmentRequest` | `parser_output: dict`, `analysis_output: dict = {}` |
| `AggregateRequest` | `converted_segments: list`, `parser_output: dict`, `segment_manifest: dict = {}` |
| `TestRequest` | `parser_output`, `analysis_output`, `java_source`, `cobol_source` |
| `SmartConvertRequest` | `source_code`, optional `parser_output`, `analysis_output` |
| `PipelineModeRequest` | `cobol_source`, `mode`, optional `parser_output`, `analysis_output` |
| `ProjectPipelineRequest` | `files: list[dict]`, `mode: str` |
| `DownloadJavaRequest` | `java_source: str`, `class_name: str = "Output"` |
| `DownloadProjectRequest` | `results: list[dict]` |

---

## Pipeline modes (`run_pipeline_mode`)

| Mode | Parser in conversion | Analysis in conversion |
|---|---|---|
| `full` | yes | yes |
| `parse_only` | yes | no |
| `parse_analyse` | yes | yes |
| `analyse_only` | no | yes |
| `convert_only` | if provided | if provided |
| `no_parse` | no | no |

---

## Status response (`GET /api/status`)

```json
{
  "api_healthy": true,
  "parser_backend": "HybridCobolParser",
  "analysis_available": true,
  "validation_available": true,
  "llm_configured": false,
  "conversion_available": false,
  "llm_model": "string",
  "prompt_template_available": true
}
```

Exact values depend on runtime configuration.

---

## Error handling

Route handlers return `HTTPException(500, detail=...)` on unexpected failures.
`/api/aggregate` returns HTTP 422 when aggregation produces `errors`.
