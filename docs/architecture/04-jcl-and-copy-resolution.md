# 04 — JCL and COPY Resolution

First deterministic stages when job context or copybooks are present.

**Code:** `app/parsers/jcl_parser.py`, `app/parsers/copybook_resolver.py`

---

## Stage 1 — JCL parser

Deterministic. No LLM.

```python
parse_jcl(jcl_source: str) -> JCLManifest
```

`PipelineService.parse_jcl_source()` delegates to `parse_jcl()`.

### JCL manifest contract

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

| Field | Purpose |
|---|---|
| `steps` | Job steps with program names and DD statements |
| `copylib_paths` | SYSLIB / COPY path hints for resolver |
| `dd_bindings` | Dataset name → logical file mapping |
| `execution_order` | Step sequence for multi-program jobs |
| `procs` | Inline or cataloged PROC definitions |

### What JCL provides to downstream stages

- Which copybook directories to search
- File I/O dataset names for context enrichment
- Execution order for multi-program projects

---

## Stage 2 — COPY book resolver

Expands `COPY copybook.` statements before COBOL parsing.

```python
resolve_copybooks(raw_source, jcl_manifest=None, syslib_paths=None)
```

Returns:

| Output | Description |
|---|---|
| `expanded_source` | COBOL with COPY bodies inlined |
| `resolved_copybooks` | Audit list of found copybooks |
| `errors` / `warnings` | Missing copybooks, circular COPY |

### Resolution rules

1. Search paths from JCL `copylib_paths` and explicit `syslib_paths`
2. Match copybook name to `.cpy`, `.copy`, `.cpb` files
3. Recursively expand nested COPY statements
4. Detect circular COPY chains → fatal error
5. Missing copybook → warning (parse continues with placeholder)

### Why before parsing

COPY books contain data division layouts (PIC clauses, OCCURS, REDEFINES). Parsing without
expansion produces incomplete `symbol_table` entries and false preflight errors.

---

## Integration in full pipeline

```text
run_full_pipeline(cobol_source, jcl_source=None)
  1. parse_jcl_source(jcl_source)     → JCLManifest
  2. resolve_copybooks(cobol, manifest)
  3. parser.parse(expanded_source)
  4. context_enricher.enrich(parser_output, manifest)
```

Single-file `/api/parse` skips steps 1–2 unless source is pre-expanded.

---

## API exposure

| Endpoint | JCL/COPY |
|---|---|
| `POST /api/parse` | Raw COBOL only (no automatic COPY) |
| `POST /api/pipeline/run` | Mode-dependent; may use pre-parsed output |
| `POST /api/project/pipeline` | Full ZIP context with copybooks |

Project upload classifies `.jcl`, `.cpy`, `.copy` files separately. See
[10 — Project batch upload](./10-project-batch-upload.md).

---

## Error handling

| Situation | Behavior |
|---|---|
| Invalid JCL syntax | Errors in manifest; pipeline may continue without JCL context |
| Missing COPY | Warning + incomplete symbol table |
| Circular COPY | Fatal; resolution stops |
| No JCL provided | Resolver uses only inline/syslib paths if given |

---

## Related documents

- [05 — COBOL parsing](./05-cobol-parsing.md) — runs on expanded source
- [06 — Context enrichment](./06-context-enrichment-and-segmentation.md) — uses DD bindings
