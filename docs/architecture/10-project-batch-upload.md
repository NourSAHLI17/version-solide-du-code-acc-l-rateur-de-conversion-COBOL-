# 10 — Project Batch Upload

Multi-file COBOL modernization via ZIP upload. Different from single-file conversion.

**Code:** `PipelineService.run_project_pipeline()`, upload handler in `modernization.py`

---

## Goal

Handle real projects with:

- Multiple `.cbl` / `.cob` programs
- Separate COPY books (`.cpy`, `.copy`, `.cpb`)
- JCL job definitions (`.jcl`, `.proc`)
- Supporting data files

---

## Two-step flow

### Step 1 — Upload

```http
POST /api/project/upload
Content-Type: multipart/form-data
```

Returns file tree:

```json
{
  "files": [
    {
      "path": "src/LOANEVAL.cbl",
      "type": "cobol",
      "size": 1234,
      "content": "..."
    }
  ],
  "total": 1
}
```

**In-memory only** — no persistent server storage. Frontend shows IDE-style explorer.

### Step 2 — Pipeline

```http
POST /api/project/pipeline
```

```json
{
  "files": [ /* same file records from upload */ ],
  "mode": "full"
}
```

Processes each COBOL file through parse → analyze → convert.

---

## File type classification

| Extension | Type |
|---|---|
| `.cbl`, `.cob`, `.cobol` | `cobol` |
| `.cpy`, `.copy`, `.cpb` | `copybook` |
| `.jcl`, `.proc` | `jcl` |
| Other | `other` |

Copybooks are available to COPY resolver during COBOL file parsing. JCL files feed
`parse_jcl_source()` when present.

---

## Per-file results

Each COBOL file in the batch returns:

```json
{
  "path": "src/LOANEVAL.cbl",
  "status": "success | error",
  "parser_output": {},
  "analysis_output": {},
  "java_source": "...",
  "error": null
}
```

Parser and analysis artifacts are **always included** when generated — even if conversion
fails for one file.

---

## Parallel processing

Large projects process files concurrently (thread pool in `run_project_pipeline`).
Failures are isolated per file.

---

## Download

After batch conversion, `POST /api/download/project` packages all Java files and test
reports into a ZIP.

---

## Frontend integration

Project Upload page (`/convert/project`):

1. User uploads ZIP
2. File explorer shows tree from upload response
3. User selects mode and runs pipeline
4. Per-file status badges and artifact panels
5. Download project ZIP

Workspace stores `projectResults` for Testing Agent page.

---

## Related documents

- [04 — JCL and COPY](./04-jcl-and-copy-resolution.md) — used during batch parse
- [11 — Frontend and API](./11-frontend-and-api.md) — workspace integration
