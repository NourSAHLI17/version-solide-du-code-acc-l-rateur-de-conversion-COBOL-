# 07 — Analysis Agent

Transforms parser structure + source text into semantic context for conversion.

**Code:** `app/agents/analysis_agent.py`, `app/prompts/analysis_agent_system_prompt.md`

---

## Purpose

| Parser tells… | Analysis tells… |
|---|---|
| What exists (symbols, flow) | Why it matters (business rules, risks) |
| Structural facts | Conversion guidance, complexity |

---

## Engine selection

Controlled by `ANALYSIS_ENGINE` (default: **`llm`**).

| Engine | Condition | Output marker |
|---|---|---|
| `llm` | API key configured | `analysis_engine: "llm"`, `analysis_revision: 2` |
| `deterministic` | `ANALYSIS_ENGINE=deterministic` or LLM failure | `analysis_engine: "deterministic"`, `analysis_revision: 3` |
| halted | `preflight_errors` non-empty | `preferred_strategy: "halted"`, `analysis_revision: 0` |

LLM failure falls back to deterministic unless `ANALYSIS_STRICT_LLM=1`.

---

## Analysis output contract

```json
{
  "program_name": null,
  "global_purpose": "",
  "complexity": "low | medium | high",
  "complexity_drivers": [],
  "sections": [],
  "business_rules": [],
  "file_io_paragraphs": [],
  "loop_paragraphs": [],
  "risk_points": [],
  "risk_flags": [],
  "conversion_guidance": [],
  "data_flow_summary": "",
  "warnings": [],
  "analysis_engine": "llm",
  "analysis_revision": 2
}
```

Each `sections[]` entry maps a COBOL paragraph/section to a semantic role (e.g. validation,
calculation, I/O handler).

---

## LLM analysis flow

```text
parser_output + source_code
  → CobolSegmenter.segment()
  → chunk_program() batches paragraphs
  → per-chunk LLM call with system prompt + parser evidence
  → merge chunk results into unified analysis JSON
```

Grounding rules in the system prompt:

- Do not invent symbols not in `symbol_table`
- Business rules must cite paragraph evidence
- Risk flags reference parser `risk_flags` and control flow

---

## API

```http
POST /api/analyze
```

```json
{
  "source_code": "...",
  "parser_output": {}
}
```

Service: `PipelineService.analyze_cobol()` → `ModernizationAgents.analyze()`.

---

## Configuration

| Variable | Default |
|---|---|
| `ANALYSIS_ENGINE` | `llm` |
| `ANALYSIS_STRICT_LLM` | `0` (allow fallback) |
| `ANTHROPIC_MODEL_ANALYSIS` | `claude-sonnet-4-5` |

---

## Why separate from parser

| Reason | Detail |
|---|---|
| Stability | Parser output is deterministic and cacheable |
| Grounding | LLM receives explicit evidence, not raw guessing |
| Debuggability | Bad analysis visible before expensive conversion |
| Optional | `parse_only` mode skips analysis entirely |

---

## Related documents

- [05 — COBOL parsing](./05-cobol-parsing.md) — required input
- [08 — Java conversion](./08-java-conversion.md) — primary consumer
- [reference/schema-contracts.md](./reference/schema-contracts.md) — analysis JSON shape
