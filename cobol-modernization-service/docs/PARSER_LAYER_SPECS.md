# Parser Layer: Structural Extraction Specification

## 1. Purpose

The Parser Layer is the first technical filter in the pipeline. Its mission is to transform raw, noisy COBOL text into a **deterministic, structured JSON representation** of the program's skeleton.

## 2. Lexical & Syntactic Processing

### Preprocessing
COBOL comes in two primary formats which require different handling:
- **Fixed Format**: Area A (Cols 8-11), Area B (Cols 12-72), and Line Numbers (Cols 1-6). The parser identifies these and trims appropriately to avoid syntax corruption.
- **Normalization**: Standardizes headers (e.g., `ID DIVISION` becomes `IDENTIFICATION DIVISION`) and handles continuation characters (`-` in column 7).

### Extraction Engines
1. **Division & Section Mapping**: Identifies the core boundaries of the program.
2. **Symbol Table Builder**: 
   - Tracks variable levels (01, 05, etc.), labels, and `PIC` clauses.
   - Detects `REDEFINES` and `OCCURS` (arrays).
   - Classifies data as `numeric`, `string`, `group`, or `redefines`.
3. **Control Flow Extractor**:
   - Uses high-fidelity regex to capture `PERFORM`, `CALL`, and `GO TO`.
   - **Context Awareness**: Tracks what paragraph a call originates from and whether it is conditional (inside an `IF` or `WHEN`).
4. **Operations Parser**:
   - Extracts literal operations like `MOVE`, `ADD`, `SUBTRACT`, `OPEN`, `CLOSE`.
   - Special handling for subscripted targets (e.g., `MOVE X TO TABLE-ITEM(I)`).

## 3. The "Deterministic First" Rationale

We avoid using LLMs for the initial parsing stage for several reasons:
- **Accuracy**: Regex/Grammar parsers don't hallucinate. If a `PERFORM` is there, it's captured. 
- **Consistency**: Repeated parses of the same file yield identical JSON.
- **Cost/Speed**: Local parsing is near-instant and free, regardless of source size.

## 4. Structural JSON Contract (Key Fields)

```json
{
  "program_name": "...",
  "symbol_table": [
    { "name": "AMT", "pic": "9(5)V99", "kind": "numeric" }
  ],
  "control_flow": {
    "calls": [{ "from": "PARA-A", "to": "PARA-B", "conditional": true }],
    "loops": [{ "type": "PERFORM_UNTIL", "until": "I > 10" }]
  },
  "operations": [
    { "type": "MOVE", "target": "X", "value": "Y" }
  ],
  "warnings": [
    { "code": "W001", "message": "Unused variable detected" }
  ]
}
```

## 5. Error Handling: Preflight Validation

The parser includes a **Preflight Check** that halts the pipeline if the COBOL source is structurally invalid or contains patterns that would break downstream analysis (e.g., duplicate data names in the same scope).
