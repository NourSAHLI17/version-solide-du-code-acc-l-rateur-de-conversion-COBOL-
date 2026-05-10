# API and dashboard behavior

## 3.1 Main HTTP entry points

| Endpoint | Role |
|----------|------|
| `POST /api/parse` | `PipelineService.parse_cobol` — raw COBOL (no JCL/COPY unless pre-expanded) |
| `POST /api/analyze` | Semantic analysis; requires `parser_output` JSON |
| `POST /api/pipeline/run` | `run_pipeline_mode` — modes (`full`, `parse_only`, `parse_analyse`, …) |

Full **JCL + COPY + enrichment** is exercised via `PipelineService.run_full_pipeline` (tests and any route that uses it).

## 3.2 The “escaped JSON string” bug (`/api/pipeline/run`)

**Symptom:** Analysis showed nested `\"\\\"...` strings.

**Fix (`pipeline_service`):**

| Helper | Role |
|--------|------|
| `_coerce_analysis_to_dict` | Accept `dict` or JSON string; unwrap nested string layers |
| `_analysis_to_str` | Single `json.dumps` for the conversion agent |
| Responses | `analysis_output` returned as **dict** when applicable |

**Schema:** `PipelineModeRequest.analysis_output` may be `dict | str`.

## 3.3 Dashboard: localStorage

Workspace key: `cobol-modernization-workspace-v2` (`src/lib/workspace.ts`).

| Mitigation | Behavior |
|------------|----------|
| Stale parser | Analysis/cockpit **re-parse** before analyze |
| Source edit | Changing COBOL clears cached parser/analysis/java |

**Restart** the Python server after backend code changes (`python main.py` does not auto-reload unless you use `--reload`).

## 3.4 Frontend artifact display

`JsonViewer` uses `JSON.stringify` — the shape comes entirely from the API response.

---

*Next: [04-testing-and-use-cases.md](./04-testing-and-use-cases.md)*
