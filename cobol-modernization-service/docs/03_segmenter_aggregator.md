# 03 - Segmenter and Aggregator

Source read before writing this document:

- `app/services/pipeline_segmenter.py`
- `app/services/segmenter.py`
- `app/services/chunker.py`
- `app/services/aggregator.py`
- `app/api/routes/modernization.py`
- `app/api/schemas/requests.py`

## Segment API

Route:

```http
POST /api/segment
```

Request schema from `SegmentRequest`:

```json
{
  "parser_output": {},
  "analysis_output": {}
}
```

The route calls:

```python
segment_program(request.parser_output, request.analysis_output)
```

## Graph Segmenter Output

`segment_program()` returns:

```json
{
  "program_name": "PROGRAM-NAME",
  "segments": [],
  "shared_state": [],
  "total_segments": 1
}
```

Each segment dictionary contains:

```json
{
  "id": "SEG_DATA",
  "paragraphs": [],
  "reads": [],
  "writes": [],
  "calls": [],
  "called_by": [],
  "business_rules": [],
  "complexity": "low",
  "requires_chunking": false
}
```

The first segment is always `SEG_DATA` with the business rule text `Data Division - symbol declarations` in source, represented in code as the data division segment.

## Segmenting Algorithm

`pipeline_segmenter.py` uses:

- `build_call_graph(calls)`
- `build_reverse_graph(calls)`
- `score_complexity(paragraphs, parser_output)`
- `extract_symbol_io(paragraphs, operations, symbol_table)`

Complexity scoring:

- loops add `3`
- branches add `2`
- operations add `0.5`
- score `< 5`: `low`
- score `< 15`: `medium`
- otherwise: `high`

`requires_chunking` is `True` only when complexity is `high`.

Shared state is computed from symbols written/read across more than one segment.

## Paragraph Segmenter

`CobolSegmenter.segment(source_code, parser_output)` returns:

```json
{
  "segments": [
    {
      "paragraph_name": "MAIN",
      "cluster_paragraphs": ["MAIN"],
      "source_lines": [],
      "symbol_reads": [],
      "symbol_writes": [],
      "cluster_reads": [],
      "cluster_writes": [],
      "has_file_io": false,
      "has_loop": false,
      "has_branch": false,
      "has_goto": false
    }
  ]
}
```

This class is used by `AnalysisAgent` to produce paragraph-scoped analysis.

## Chunking

`chunk_segment(segment, parser_output)` returns a list of `Chunk` dataclass instances.

Chunk fields:

- `id`
- `segment_id`
- `paragraphs`
- `reads`
- `writes`
- `shared_with_chunks`

If `segment.requires_chunking` is false, a single chunk is returned with id:

```text
{segment.id}_CHUNK_0
```

For complex segments, the chunker uses a target paragraph cutoff of `5` and avoids cutting at paragraph names involved in loops or branches.

## Aggregate API

Route:

```http
POST /api/aggregate
```

Request schema from `AggregateRequest`:

```json
{
  "converted_segments": [],
  "parser_output": {},
  "segment_manifest": {}
}
```

The route calls:

```python
aggregate_segments(
    request.converted_segments,
    request.parser_output,
    request.segment_manifest
)
```

If the result contains `errors`, the route raises HTTP 422 with:

```json
{
  "aggregation_errors": []
}
```

## Aggregator Input Segment Fields

`aggregate_segments()` expects converted segment dictionaries with fields such as:

- `id`
- `method_name`
- `java_method_body`
- `declared_fields`
- `reads`
- `writes`
- `outbound_calls`
- `imports`

## Aggregator Output Contract

Successful output:

```json
{
  "java_source": "package com.modernized...",
  "class_name": "ModernizedProgram",
  "package": "com.modernized.unknown",
  "instance_fields": [],
  "errors": [],
  "warnings": []
}
```

Error output:

```json
{
  "java_source": null,
  "errors": ["Segment SEG_1 calls 'missingMethod' - no matching method"],
  "warnings": []
}
```

The actual source message uses an encoded dash in the string; the semantic content is the missing outbound method error.

## Type Reconciliation

Field type precedence in `TYPE_PRIORITY`:

| Java type | Priority |
|---|---:|
| `BigDecimal` | 4 |
| `String` | 3 |
| `int` | 2 |
| `long` | 1 |
| `double` | 0 |

The higher-priority type wins when duplicate fields are reconciled.

## Java Class Assembly

`aggregate_segments()` derives:

- class name from `program_name` using `to_java_class_name()`
- package as `com.modernized.{program_name_lower_without_dashes}`
- instance fields from shared state or all fields when no shared state exists
- imports from converted segments
- BigDecimal import when needed
- constructor initialization from symbol values and field types
- `main()` invoking `mainParagraph()`

## Self-Validation Checklist

- [x] Segment API request fields match `SegmentRequest`.
- [x] Segment output fields match `segment_program()`.
- [x] Chunk fields match `Chunk.to_dict()`.
- [x] Aggregate request fields match `AggregateRequest`.
- [x] Aggregator output fields match source.
- [x] No segmentation or aggregation field was invented.
