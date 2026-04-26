# Architecture 01 - Backend Pipeline Approaches

This document explains the backend pipeline approach by approach.

## Approach 1: Core Parse, Analyze, Convert

The most basic pipeline is:

```text
COBOL source
  -> parse_cobol
  -> analyze_cobol
  -> convert_cobol
```

Code path:

- `PipelineService.parse_cobol()`
- `PipelineService.analyze_cobol()`
- `PipelineService.convert_cobol()`

API paths:

- `POST /api/parse`
- `POST /api/analyze`
- `POST /api/convert`

Why we need it:

- parser gives deterministic structure
- analysis gives business meaning and conversion guidance
- conversion creates Java from source and context

Why this approach:

- each layer can be tested independently
- frontend can show parser JSON before analysis
- conversion prompt can include structured evidence instead of raw COBOL only

## Approach 2: Full Internal Pipeline With JCL and COPY

The deeper backend pipeline is:

```text
JCL source
  -> parse_jcl_source
COBOL source
  -> resolve_copybooks
  -> parse expanded source
  -> context enrichment
```

Code path:

- `PipelineService.parse_jcl_source()`
- `PipelineService.resolve_copybooks()`
- `PipelineService.run_pipeline()`
- `PipelineService.run_full_pipeline()`

Why we need it:

- COBOL programs often depend on COPY books
- JCL often defines file bindings and SYSLIB paths
- parser output without COPY expansion can miss data declarations
- conversion needs execution and file context

Why this approach:

- JCL and COPY are handled deterministically before parsing
- unresolved COPY books degrade gracefully unless circular references appear
- resolved copy metadata is attached to parser output

## Approach 3: Mode-Based Pipeline

The mode endpoint is:

```text
POST /api/pipeline/run
```

Supported modes:

- `full`
- `parse_only`
- `parse_analyse`
- `analyse_only`
- `convert_only`
- `no_parse`

Why we need it:

- users need to test conversion with different context levels
- debugging conversion requires isolating parser and analysis influence
- some users may already have parser or analysis output
- sometimes raw fallback conversion is useful

Why this approach:

- one endpoint supports the frontend selector
- every mode still returns `java_source`
- modes control which context enters the conversion prompt

Current context behavior:

| Mode | Parser output generated/used | Analysis output generated/used | Conversion receives |
|---|---|---|---|
| `full` | yes | yes | COBOL + parser + analysis |
| `parse_only` | yes | no | COBOL + parser |
| `parse_analyse` | yes | yes | COBOL + parser + analysis |
| `analyse_only` | yes for analysis generation, then omitted from conversion | yes | COBOL + analysis |
| `convert_only` | yes when provided or generated | yes when provided or generated | COBOL + available context |
| `no_parse` | no | no | COBOL only |

## Approach 4: Smart Convert

Endpoint:

```text
POST /api/smart-convert
```

Code path:

- `PipelineService.smart_modernize()`

Why we need it:

- callers can pass optional precomputed parser or analysis output
- backend fills missing pieces automatically
- simple clients can ask for conversion without managing every stage

Why this approach:

- convenience wrapper for common use cases
- still preserves parser and analysis outputs in response
- avoids duplicating pipeline logic in the frontend

## Approach 5: Validation as a Separate Stage

Endpoint:

```text
POST /api/validate
```

Code path:

- `PipelineService.validate_conversion()`
- `ValidationService.validate_outputs()`

Why we need it:

- conversion quality is not only about Java syntax
- expected and actual outputs need comparison
- JSON outputs need structural comparison
- text outputs need normalized or line-diff comparison

Why this approach:

- validation can be used independently from conversion
- frontend can compare any two outputs
- output equivalence logic stays deterministic

## Approach 6: Runtime Status

Endpoint:

```text
GET /api/status
```

Why we need it:

- frontend needs to know if backend is reachable
- users need to know parser backend and LLM readiness
- conversion may be unavailable when no LLM key is configured

Why this approach:

- cheap endpoint
- no LLM call
- can be polled by UI health components

