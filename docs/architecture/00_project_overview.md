# 00 - Project Overview

Source read before writing this document:

- `app/api/routes/modernization.py`
- `app/api/schemas/requests.py`
- `app/services/pipeline_service.py`
- `app/core/config.py`
- `app/agents/facade.py`
- `app/agents/analysis_agent.py`
- `app/agents/conversion_agent.py`
- `app/validation/service.py`

## Runtime Shape

The backend is a FastAPI service mounted from `app.main:app`. The application factory adds permissive CORS and includes the modernization router.

The router is configured as:

```python
router = APIRouter(prefix="/api", tags=["modernization"])
```

All public backend endpoints therefore live under `/api`.

## Configuration

`load_config()` reads runtime values from environment variables and `.env`:

| Setting | Environment variable | Default |
|---|---|---|
| Host | `HOST` | `0.0.0.0` |
| Port | `PORT` | `8000` (repo `start_backend.bat` uses **8010**) |
| Google key | `GOOGLE_API_KEY` | `None` |
| OpenAI key | `OPENAI_API_KEY` | `None` |
| OpenRouter key | `OPENROUTER_API_KEY` | `None` |
| Anthropic key | `ANTHROPIC_API_KEY` | `None` |
| LLM provider | `LLM_PROVIDER` | `auto` (`anthropic`, `openai`, `openrouter`, `google`) |
| Anthropic project default | `DEFAULT_ANTHROPIC_MODEL` in `app/services/llm_config.py` | `claude-sonnet-4-5` |
| Anthropic analysis model | `ANTHROPIC_MODEL_ANALYSIS` / `ANTHROPIC_MODEL` | `claude-sonnet-4-5` |
| Anthropic conversion model | `ANTHROPIC_MODEL_CONVERSION` | same as analysis model |
| OpenAI model | `OPENAI_MODEL` | `gpt-4.1-mini` |
| OpenRouter model | `OPENROUTER_MODEL` | `openai/gpt-4o-mini` |
| Parser backend | `PARSER_BACKEND` | `hybrid` |
| Analysis engine | `ANALYSIS_ENGINE` | `llm` |
| Java profile | `JAVA_PROJECT_PROFILE` | `plain_java` |

## Service Orchestration

`PipelineService` is the central orchestration layer. Its constructor wires:

- `parser`: created by `create_parser(load_config())`
- `agents`: `ModernizationAgents()`
- `validator`: `ValidationService()`
- `context_enricher`: `ContextEnricher()`

The core orchestration methods are:

- `parse_jcl_source(jcl_source)`
- `resolve_copybooks(raw_cobol_source, jcl_manifest=None)`
- `run_pipeline(raw_cobol_source, jcl_manifest=None)`
- `run_full_pipeline(raw_cobol_source, jcl_source=None)`
- `parse_cobol(source_code)`
- `analyze_cobol(source_code, parser_output)`
- `convert_cobol(source_code, parser_output, analysis_output)`
- `validate_conversion(expected_output, actual_output)`
- `smart_modernize(source_code, parser_output=None, analysis_output=None)`
- `run_pipeline_mode(cobol_source, mode, parser_output=None, analysis_output=None)`
- `run_project_pipeline(files, mode="full")`
- `get_runtime_status()`

## Public API Endpoints

The routes currently registered in `app/api/routes/modernization.py` are:

| Method | Path | Handler |
|---|---|---|
| POST | `/api/parse` | `parse_cobol` |
| POST | `/api/analyze` | `analyze_cobol` |
| POST | `/api/convert` | `convert_cobol` |
| POST | `/api/validate` | `validate_conversion` |
| POST | `/api/segment` | `run_segmentation` |
| POST | `/api/aggregate` | `run_aggregation` |
| POST | `/api/test` | `run_tests` |
| POST | `/api/smart-convert` | `smart_convert` |
| POST | `/api/pipeline/run` | `run_pipeline_mode` |
| POST | `/api/project/upload` | `upload_project` |
| POST | `/api/project/pipeline` | `run_project_pipeline` |
| POST | `/api/download/java` | `download_java` |
| POST | `/api/download/project` | `download_project` |
| GET | `/api/status` | `backend_status` |

## Request Schemas

The request models are defined in `app/api/schemas/requests.py`:

- `CobolRequest`: `source_code: str`
- `AnalyzeRequest`: `source_code: str`, `parser_output: dict`
- `ConvertRequest`: `source_code: str`, `parser_output: dict`, `analysis_output: str`
- `ValidateRequest`: `expected_output: str`, `actual_output: str`
- `SegmentRequest`: `parser_output: dict`, `analysis_output: dict = {}`
- `AggregateRequest`: `converted_segments: list[dict]`, `parser_output: dict`, `segment_manifest: dict = {}`
- `TestRequest`: `parser_output: dict = {}`, `analysis_output: dict = {}`, `java_source: str = ""`, `cobol_source: str = ""`
- `SmartConvertRequest`: `source_code: str`, optional `parser_output`, optional `analysis_output`
- `PipelineModeRequest`: `cobol_source: str`, `mode: str`, optional `parser_output`, optional `analysis_output`
- `ProjectPipelineRequest`: `files: list[dict]`, `mode: str`
- `DownloadJavaRequest`: `java_source: str`, `class_name: str = "Output"`
- `DownloadProjectRequest`: `results: list[dict]`

## Pipeline Mode Contract

`run_pipeline_mode()` supports:

- `full`
- `parse_only`
- `parse_analyse`
- `analyse_only`
- `convert_only`
- `no_parse`

All modes return `java_source` because the current implementation performs conversion for every supported mode. Context sent into conversion depends on the mode:

| Mode | Parser context in conversion prompt | Analysis context in conversion prompt |
|---|---|---|
| `full` | yes | yes |
| `parse_only` | yes | no |
| `parse_analyse` | yes | yes |
| `analyse_only` | no | yes |
| `convert_only` | yes when provided/generated | yes when provided/generated |
| `no_parse` | no | no |

## Status Contract

`GET /api/status` returns:

```json
{
  "api_healthy": true,
  "parser_backend": "ParserLayer",
  "analysis_available": true,
  "validation_available": true,
  "llm_configured": false,
  "conversion_available": false,
  "llm_model": "gemini-2.0-flash",
  "prompt_template_available": true
}
```

The exact `parser_backend`, `llm_configured`, `conversion_available`, `llm_model`, and `prompt_template_available` values depend on runtime configuration and installed dependencies.

## Error Handling

Most route handlers wrap service calls in `try/except` and return `HTTPException(status_code=500, detail=str(exc))` for unexpected failures. `/aggregate` returns HTTP 422 when the aggregation result contains `errors`.

## Self-Validation Checklist

- [x] Source files were read before writing this document.
- [x] Endpoint paths come from `app/api/routes/modernization.py`.
- [x] Request fields come from `app/api/schemas/requests.py`.
- [x] Pipeline modes come from `PipelineService.run_pipeline_mode`.
- [x] Status fields come from `PipelineService.get_runtime_status`.
- [x] No fake endpoint was documented.
