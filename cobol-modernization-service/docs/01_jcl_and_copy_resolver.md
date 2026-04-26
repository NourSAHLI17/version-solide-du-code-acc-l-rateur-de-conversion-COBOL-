# 01 - JCL Parser and COPY Resolver

Source read before writing this document:

- `app/parsers/jcl_parser.py`
- `app/parsers/copybook_resolver.py`
- `app/services/pipeline_service.py`
- `app/api/routes/modernization.py`

## Stage 1: JCL Parser

The JCL parser is deterministic and implemented in `app/parsers/jcl_parser.py`. It does not call an LLM.

The entry point is:

```python
parse_jcl(jcl_source: str) -> JCLManifest
```

`PipelineService.parse_jcl_source()` delegates directly to `parse_jcl()`.

## JCL Manifest Contract

`JCLManifest.to_dict()` returns:

```json
{
  "job_name": "",
  "steps": [],
  "copylib_paths": [],
  "dd_bindings": {},
  "execution_order": [],
  "procs": {},
  "errors": [],
  "warnings": []
}
```

The dataclass fields are:

- `job_name: str`
- `steps: list[dict]`
- `copylib_paths: list[str]`
- `dd_bindings: dict`
- `execution_order: list[str]`
- `procs: dict`
- `errors: list[str]`
- `warnings: list[str]`

## JCL Extraction Rules

The parser recognizes:

- JOB statements
- `EXEC PGM=...`
- `EXEC PROCNAME`
- named DD statements
- DD concatenation
- inline DD data blocks using `DD *` and `/*`
- `DSN=...`
- `DISP=...`
- `COND=(rc,operator,step)`
- inline `PROC` / `PEND`
- continuation lines
- comment lines beginning with `//*`

## JCL Example

Input:

```jcl
//INVJOB JOB
//STEP1 EXEC PGM=INVMGMT,PARM='BATCH'
//SYSLIB DD DSN=PROD.COPYLIB,DISP=SHR
//INVFILE DD DSN=PROD.INV.MASTER,DISP=SHR
```

Representative output fields:

```json
{
  "job_name": "INVJOB",
  "execution_order": ["INVMGMT"],
  "copylib_paths": ["PROD.COPYLIB"],
  "dd_bindings": {
    "STEP1": {
      "SYSLIB": {"dsn": "PROD.COPYLIB", "disp": "SHR"},
      "INVFILE": {"dsn": "PROD.INV.MASTER", "disp": "SHR"}
    }
  }
}
```

The field names above come from `parse_jcl()` and `JCLManifest.to_dict()`.

## Stage 2: COPY Resolver

The COPY resolver is deterministic and implemented in `app/parsers/copybook_resolver.py`.

The entry point is:

```python
resolve_copy_books(source_lines: list[str]) -> CopyResolutionResult
```

`PipelineService.resolve_copybooks()` injects `jcl_manifest["copylib_paths"]` into `COPY_LIBRARY_CONFIG["default"]` before calling `resolve_copy_books()`.

## COPY Resolver Contract

`CopyResolutionResult` contains:

- `expanded_source: str`
- `resolved_copybooks: list[dict]`
- `unresolved_copybooks: list[str]`
- `errors: list[str]`
- `warnings: list[str]`

Resolved audit entries contain:

```json
{
  "name": "INVDATA",
  "path": "absolute/path/to/copybook",
  "library": "DEFAULT",
  "line_in_source": 1,
  "replacing": [],
  "nested_copies": []
}
```

## COPY Behavior

Implemented behavior includes:

- column-aware COPY detection for fixed-format COBOL
- loose fallback COPY detection for free-form or loosely formatted source
- `COPY NAME.`
- `COPY NAME IN LIBRARY.`
- `COPY NAME REPLACING ==OLD== BY ==NEW==.`
- nested COPY resolution up to `MAX_NESTING_DEPTH = 10`
- source-map comments around expanded copybook content
- graceful unresolved-copy degradation
- circular COPY detection
- cross-program cache keyed by library, copy name, and replacing hash

## Resolver Configuration

`COPY_LIBRARY_CONFIG` currently contains:

```python
{
    "default": ["./copybooks/", "./copybooks/common/"],
    "MYLIB": ["./copybooks/mylib/"],
    "SYSLIB": ["./copybooks/system/"],
}
```

`COPY_EXTENSIONS` currently contains:

```python
[".cpy", ".CPY", ".cbl", ".CBL", ".copy", ""]
```

## Pipeline Integration

`PipelineService.run_pipeline()` performs:

1. COPY resolution via `resolve_copybooks()`.
2. Hard failure on circular COPY references.
3. Soft warning on unresolved copybooks.
4. COBOL parse of `resolution.expanded_source`.
5. Attachment of:
   - `resolved_copybooks`
   - `unresolved_copybooks`
   - `copy_resolution_errors`
   - `copy_resolution_warnings`

`PipelineService.run_full_pipeline()` optionally parses JCL first, then runs COPY resolution, COBOL parsing, context enrichment, and attaches `jcl_manifest`.

## Self-Validation Checklist

- [x] JCL manifest fields match `JCLManifest.to_dict()`.
- [x] COPY result fields match `CopyResolutionResult`.
- [x] Resolver configuration values match source.
- [x] Pipeline integration matches `PipelineService`.
- [x] Examples use field names from real code.
- [x] No unsupported JCL or COPY feature was documented.
