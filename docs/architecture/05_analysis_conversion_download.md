# 05 - Analysis, Conversion, Validation, Project Upload, and Downloads

Source read before writing this document:

- `app/agents/analysis_agent.py`
- `app/agents/conversion_agent.py`
- `app/agents/facade.py`
- `app/validation/service.py`
- `app/services/pipeline_service.py`
- `app/api/routes/modernization.py`
- `app/api/schemas/requests.py`

## Analysis API

Route:

```http
POST /api/analyze
```

Request schema:

```json
{
  "source_code": "PROCEDURE DIVISION.",
  "parser_output": {}
}
```

The route calls:

```python
service.analyze_cobol(request.source_code, request.parser_output)
```

`PipelineService.analyze_cobol()` delegates to:

```python
ModernizationAgents.analyze(source_code, parser_output)
```

## Analysis Output Contract

`AnalysisAgent.analyze()` returns a dictionary with:

```json
{
  "program_name": null,
  "global_purpose": "",
  "complexity": "low",
  "complexity_drivers": [],
  "sections": [],
  "business_rules": [],
  "file_io_paragraphs": [],
  "loop_paragraphs": [],
  "all_business_rules": [],
  "dependencies": {
    "copybooks": [],
    "files": [],
    "external_calls": []
  },
  "risk_points": [],
  "risk_flags": [],
  "conversion_guidance": {
    "preferred_strategy": "section-by-section conversion",
    "chunking_required": false,
    "notes": []
  },
  "data_flow_summary": {
    "global_inputs": [],
    "global_outputs": [],
    "shared_state": []
  },
  "assumptions": [],
  "warnings": []
}
```

When `parser_output["preflight_errors"]` is nonempty, analysis returns a halted response with:

- `conversion_guidance.preferred_strategy = "halted"`
- `conversion_guidance.notes = ["resolve preflight_errors before analysis or conversion"]`
- `warnings` containing parser warnings plus preflight errors

## Conversion API

Route:

```http
POST /api/convert
```

Request schema:

```json
{
  "source_code": "PROCEDURE DIVISION.",
  "parser_output": {},
  "analysis_output": "{}"
}
```

Response:

```json
{
  "java_code": "// Conversion agent is not configured.\n// Provide GOOGLE_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY to enable Java generation.\n"
}
```

If an LLM provider is configured, `java_code` contains generated Java source plus mapping notes according to the conversion prompt.

## Conversion Agent Providers

`ConversionAgent` supports:

- Google via `ChatGoogleGenerativeAI`
- OpenAI chat completions
- OpenRouter chat completions
- stub mode when no provider is configured

Provider selection uses `LLM_PROVIDER` with default `auto`.

Runtime status fields from `ConversionAgent.get_runtime_status()`:

```json
{
  "llm_configured": false,
  "provider": "stub",
  "model_name": "gemini-2.0-flash",
  "prompt_template_available": true
}
```

## Conversion Prompt Inputs

`build_conversion_prompt_input()` renders:

- raw COBOL source
- context mode
- parser output JSON
- analysis output JSON
- conversion configuration JSON

Context mode is one of:

- `COBOL source + parser output + analysis output`
- `COBOL source + parser output only`
- `COBOL source + analysis output only`
- `COBOL source only`

Conversion configuration fields:

```json
{
  "target_language": "java",
  "java_version": "17",
  "framework": "none",
  "package_name": "com.modernized.modernized",
  "naming_style": "camelCase",
  "decimal_strategy": "bigdecimal",
  "preferred_decimal_java_type": "BigDecimal",
  "io_strategy": "in-memory",
  "generate_tests": true,
  "complexity_hint": "simple"
}
```

`framework` depends on `JAVA_PROJECT_PROFILE` (default `plain_java` → `"none"`). When the profile
is `spring_boot`, `framework` is `"spring-boot"`. `io_strategy` becomes `buffered` when parser
dependencies include files, otherwise `in-memory`.

## Conversion Modes

`ConversionAgent.convert_with_metadata()` selects the generation strategy:

| Mode | Function | When used |
|---|---|---|
| Whole-class | `_convert_raw()` | Small programs not in the mandatory constrained list |
| Constrained (F45) | `_convert_constrained()` → `run_constrained_generation()` | `LOANEVAL`, `RECOVRY`, `RPTMONTH`, `RISKSCOR`, or source > 400 non-blank lines |

Constrained mode builds Java class scaffolding in Python (`java_class_builder.py`), then calls
the LLM once per paragraph for method bodies only. Whole-class mode sends a single prompt for
the entire Java source.

Post-conversion steps (both modes): `java_pre_write_validator`, `java_compile_repair`,
`java_post_processor`, `scoring_service.score_conversion()`.

## Unified Pipeline Mode API

Route:

```http
POST /api/pipeline/run
```

Request schema:

```json
{
  "cobol_source": "PROCEDURE DIVISION.",
  "mode": "full",
  "parser_output": null,
  "analysis_output": null
}
```

Supported modes:

- `full`
- `parse_only`
- `parse_analyse`
- `analyse_only`
- `convert_only`
- `no_parse`

Every supported mode currently returns `java_source`. Modes control whether parser output and/or analysis output are generated and sent into conversion.

## Smart Convert API

Route:

```http
POST /api/smart-convert
```

Request schema:

```json
{
  "source_code": "PROCEDURE DIVISION.",
  "parser_output": null,
  "analysis_output": null
}
```

Response fields from `PipelineService.smart_modernize()`:

```json
{
  "java_code": "",
  "parser_output": {},
  "analysis_output": "{}"
}
```

## Validation API

Route:

```http
POST /api/validate
```

Request schema:

```json
{
  "expected_output": "A\nB",
  "actual_output": "A\nC"
}
```

`ValidationService.validate_outputs()` can return:

- `comparison_mode = "json_structure"`
- `comparison_mode = "normalized_text"`
- `comparison_mode = "line_diff"`

Response shape:

```json
{
  "is_equivalent": false,
  "comparison_mode": "line_diff",
  "differences": ["- B", "+ C"],
  "warnings": []
}
```

Warnings are added when expected or actual output is empty.

## Project Upload API

Route:

```http
POST /api/project/upload
```

Request:

- multipart form field `file`
- file must have a `.zip` filename

Response:

```json
{
  "files": [
    {
      "path": "src/PROGRAM.cbl",
      "type": "cobol",
      "size": 1234,
      "content": "..."
    }
  ],
  "total": 1
}
```

File type detection:

- `.cbl`, `.cob`, `.cobol` -> `cobol`
- `.jcl`, `.proc` -> `jcl`
- `.cpy`, `.copy`, `.cpb` -> `copybook`
- anything else -> `other`

## Project Pipeline API

Route:

```http
POST /api/project/pipeline
```

Request schema:

```json
{
  "files": [],
  "mode": "full"
}
```

Response:

```json
{
  "results": [
    {
      "file": "src/PROGRAM.cbl",
      "errors": [],
      "parser_output": {},
      "analysis_output": {},
      "java_source": "",
      "test_report": {}
    }
  ],
  "total_files": 1
}
```

`test_report` is attached only when mode is `full` and `java_source` exists.

The project pipeline always computes parser and analysis output for COBOL files before conversion. Conversion context then varies by mode.

## Download APIs

Single Java download:

```http
POST /api/download/java
```

Request:

```json
{
  "java_source": "public class Output {}",
  "class_name": "Output"
}
```

Response is `text/plain` with:

```http
Content-Disposition: attachment; filename="Output.java"
```

Project ZIP download:

```http
POST /api/download/project
```

Request:

```json
{
  "results": []
}
```

The ZIP includes:

- `src/main/java/{file_stem}.java` for each result with `java_source`
- `reports/{file_stem}_test_report.json` for each result with `test_report`

## Self-Validation Checklist

- [x] Analysis response fields match `AnalysisAgent`.
- [x] Conversion request and response fields match source.
- [x] Pipeline modes match `PipelineModeRequest` and `PipelineService`.
- [x] Project upload file types match route code.
- [x] Download paths and headers match route code.
- [x] Validation modes match `ValidationService`.
