# Schema Contracts

JSON shapes exchanged between pipeline stages. All paths refer to `cobol-modernization-service/`.

---

## 1. Parser output (structural AST)

Produced by `ParserLayer` / `HybridCobolParser` (`app/parsers/cobol_parser.py`).

```json
{
  "program_name": "string",
  "source_format": "fixed | free",
  "parser_backend": "hybrid | heuristic | antlr | hybrid_degraded",
  "divisions": ["string"],
  "sections": ["string"],
  "paragraphs": ["string"],
  "symbol_table": [
    {
      "name": "string",
      "level": "number",
      "pic": "string",
      "kind": "numeric | string | group | redefines | array",
      "redefines": "optional string",
      "occurs": "optional number",
      "unreferenceable": "optional boolean"
    }
  ],
  "control_flow": {
    "branches": [{ "type": "IF | EVALUATE", "condition": "string", "paragraph": "string" }],
    "loops": [{ "type": "PERFORM_VARYING | PERFORM_UNTIL", "inline": "boolean", "target_paragraph": "string" }],
    "calls": [{ "type": "PERFORM | CALL", "from": "string", "to": "string", "conditional": "boolean" }],
    "gotos": [{ "from_paragraph": "string", "to_paragraph": "string", "conditional": "boolean" }]
  },
  "operations": [
    { "type": "MOVE | COMPUTE | ADD | DISPLAY", "target": "string", "value": "string | object", "paragraph": "string", "rounded": "optional boolean" }
  ],
  "dependencies": { "files": [], "copybooks": [], "external_calls": [] },
  "risk_flags": [],
  "warnings": [{ "code": "string", "severity": "string", "message": "string" }],
  "preflight_errors": []
}
```

---

## 2. Analysis output (semantic profile)

Produced by `AnalysisAgent` (`app/agents/analysis_agent.py`).

```json
{
  "program_name": "string",
  "global_purpose": "string",
  "complexity": "low | medium | high",
  "complexity_drivers": ["string"],
  "analysis_engine": "llm | deterministic",
  "analysis_revision": "number",
  "sections": [
    {
      "name": "string",
      "role": "string",
      "inputs": ["string"],
      "outputs": ["string"],
      "business_rules": ["string"],
      "called_by": ["string"],
      "calls": ["string"],
      "has_early_exit": "boolean",
      "is_dead_code": "boolean"
    }
  ],
  "business_rules": ["string"],
  "file_io_paragraphs": ["string"],
  "loop_paragraphs": ["string"],
  "risk_flags": ["string"],
  "risk_points": [],
  "data_flow_summary": "string | object",
  "conversion_guidance": [],
  "warnings": []
}
```

---

## 3. JCL manifest

Produced by `parse_jcl()` (`app/parsers/jcl_parser.py`).

```json
{
  "job_name": "string",
  "steps": [],
  "copylib_paths": [],
  "dd_bindings": {},
  "execution_order": [],
  "procs": {},
  "errors": [],
  "warnings": []
}
```

---

## 4. Test report

Produced by testing agent (`app/services/testing_agent.py`).

```json
{
  "parser_tests": [{ "name": "string", "passed": "boolean", "message": "string" }],
  "conversion_tests": [],
  "behavioral_tests": [],
  "summary": { "passed": 0, "failed": 0, "skipped": 0 }
}
```

---

## 5. Mapping conventions

| Convention | Rule |
|---|---|
| Variable names | Preserved in parser/analysis; CamelCase only in final Java |
| Role descriptions | Behavioral ("process inventory") not syntactic ("has a loop") |
| Condition context | Carries nearest IF/WHEN for control-flow precision |
| Symbol table gate | Conversion must not invent names outside `symbol_table` |
