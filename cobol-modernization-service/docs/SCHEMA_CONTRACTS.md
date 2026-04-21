# Technical Schema Contracts

This document specifies the exact JSON contracts between the three layers of the modernization engine.

## 1. Parser Layer Output (The Structural AST)

This JSON is produced by `cobol_parser.py`.

```json
{
  "program_name": "string",
  "source_format": "fixed | free",
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
      "occurs": "optional number"
    }
  ],
  "control_flow": {
    "branches": [{ "type": "IF | EVALUATE", "condition": "string", "paragraph": "string" }],
    "loops": [{ "type": "PERFORM_VARYING | PERFORM_UNTIL", "inline": "boolean", "target_paragraph": "string" }],
    "calls": [{ "type": "PERFORM | CALL", "from": "string", "to": "string", "conditional": "boolean" }],
    "gotos": [{ "from_paragraph": "string", "to_paragraph": "string", "conditional": "boolean" }]
  },
  "operations": [
    { "type": "MOVE | ADD | SUBTRACT", "target": "string", "value": "string | object", "paragraph": "string" }
  ],
  "warnings": [{ "code": "string", "severity": "string", "message": "string" }]
}
```

## 2. Analysis Agent Output (The Semantic Profile)

This JSON is produced by `analysis_agent.py` and used as input for the **Conversion Layer**.

```json
{
  "program_name": "string",
  "global_purpose": "string",
  "complexity": "low | medium | high",
  "complexity_drivers": ["string"],
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
  "data_flow_summary": {
    "global_inputs": ["string"],
    "global_outputs": ["string"],
    "shared_state": ["string"]
  },
  "business_rules": ["string"],
  "risk_flags": ["string"],
  "conversion_guidance": {
    "preferred_strategy": "string",
    "chunking_required": "boolean",
    "notes": ["string"]
  }
}
```

## 3. Mapping Conventions

- **Variable Names**: Kept as-is in Parser/Analysis layers for traceability; converted to CamelCase only in the final Java output.
- **Role Descriptions**: Should be behavioral (e.g., "Iteratively process inventory slots") rather than syntactic (e.g., "Paragraph with a loop").
- **Condition Context**: Always carries the nearest `IF` or `WHEN` condition to ensure control-flow precision.
