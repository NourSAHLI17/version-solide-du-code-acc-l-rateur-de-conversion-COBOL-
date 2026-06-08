# 06 — Context Enrichment and Segmentation

Bridges raw parser output to paragraph-focused analysis and conversion.

**Code:** `app/parsers/context_enricher.py`, `app/services/segmenter.py`,
`app/services/pipeline_segmenter.py`, `app/services/chunker.py`

---

## Context enricher

Attaches JCL-aware execution metadata to parser JSON.

```python
ContextEnricher.enrich(parser_output, jcl_manifest=None)
```

| Addition | Source |
|---|---|
| File binding hints | JCL `dd_bindings` |
| Dataset → logical file map | DD statements |
| I/O paragraph markers | SELECT/FD cross-reference |

**Why:** Conversion needs to know which paragraphs perform file I/O and which dataset names
map to which COBOL files — information not always visible from COBOL alone.

Runs inside `run_full_pipeline()` after parse, before analysis.

---

## Segmenter

`CobolSegmenter` (`app/services/segmenter.py`) splits a program into paragraph-level slices
for analysis and constrained conversion.

### Segment API

```http
POST /api/segment
```

```json
{
  "parser_output": {},
  "analysis_output": {}
}
```

Returns:

```json
{
  "program_name": "PROGRAM-NAME",
  "segments": [],
  "shared_state": [],
  "total_segments": 1
}
```

### Per-segment content

| Field | Purpose |
|---|---|
| `paragraph_name` | COBOL paragraph identifier |
| `source_lines` | Exact source for this paragraph |
| `symbol_reads` / `symbol_writes` | Data items touched |
| `has_file_io` | File operations present |
| `has_loops` | PERFORM UNTIL / VARYING |
| `has_branches` | IF / EVALUATE |
| `has_goto` | GO TO present |

---

## Chunker

`chunk_program()` batches segments for LLM analysis calls — avoids one giant prompt for
large programs. Used by `AnalysisAgent` when `ANALYSIS_ENGINE=llm`.

---

## Aggregator

`POST /api/aggregate` merges per-segment conversion results back into a single Java class
when using segment-based conversion paths.

```json
{
  "converted_segments": [],
  "parser_output": {},
  "segment_manifest": {}
}
```

Returns assembled Java or `errors` (HTTP 422 on failure).

---

## Role in the pipeline

```text
parser_output
  → context_enricher.enrich()        [JCL bindings]
  → segmenter.segment()              [paragraph slices]
  → analysis_agent (per chunk)       [semantic profile]
  → constrained_generation (per method) [F45 mode]
```

Whole-class conversion may skip explicit segment API calls but still uses paragraph
structure from parser JSON internally.

---

## Related documents

- [05 — COBOL parsing](./05-cobol-parsing.md) — upstream contract
- [07 — Analysis agent](./07-analysis-agent.md) — consumes segments
- [08 — Java conversion](./08-java-conversion.md) — F45 uses per-paragraph calls
