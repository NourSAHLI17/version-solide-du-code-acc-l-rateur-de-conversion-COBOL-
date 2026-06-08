# 04 - Testing Agent

Source read before writing this document:

- `app/services/testing_agent.py`
- `app/api/routes/modernization.py`
- `app/api/schemas/requests.py`

## Test API

Route:

```http
POST /api/test
```

Request schema from `TestRequest`:

```json
{
  "parser_output": {},
  "analysis_output": {},
  "java_source": "",
  "cobol_source": ""
}
```

The route calls:

```python
run_testing_agent(
    request.parser_output,
    request.analysis_output,
    request.java_source,
    request.cobol_source
)
```

## Orchestrator Output

`run_testing_agent()` returns:

```json
{
  "parser_tests": [],
  "conversion_tests": [],
  "behavioral_tests": [],
  "summary": {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "critical_failures": 0,
    "high_failures": 0
  },
  "is_pipeline_green": true
}
```

`is_pipeline_green` is `true` only when there are no failed tests with severity `critical`.

## Parser Structural Tests

Function:

```python
run_parser_tests(parser_output: dict) -> list[dict]
```

Generated checks include:

- symbol table entries have `pic` or `kind`
- call graph targets exist as known paragraphs
- paragraphs are not COBOL reserved words
- `PERFORM_VARYING` loops include iterator, start, step, and until
- conditional calls are registered as live conditional calls

Parser test result fields:

```json
{
  "id": "SYM_FIELD-NAME",
  "description": "Symbol 'FIELD-NAME' has pic and kind defined",
  "passed": true,
  "severity": "critical"
}
```

## Conversion Static Tests

Function:

```python
run_conversion_tests(java_source: str, parser_output: dict) -> list[dict]
```

If `java_source` is empty, it returns an empty list.

Generated checks include:

- `NO_DO_WHILE`
- `NO_FLOAT_DOUBLE`
- one `BIGDECIMAL_{symbol}` check per decimal symbol
- one `ARRAY_SIZE_{symbol}` check per OCCURS symbol
- `STRING_COMPARE_STRIP`
- `EMPTY_CHECK_ISBLANK`

Example result shape:

```json
{
  "id": "NO_DO_WHILE",
  "description": "No do-while loops (PERFORM UNTIL must be while)",
  "passed": true,
  "severity": "high",
  "detail": "Found 0 do-while occurrences"
}
```

## Behavioral Diff API (primary verification path)

Route:

```http
POST /api/testing/behavioral-diff
```

Handler: `app/api/routes/testing.py` → `run_behavioral_diff()` in
`app/services/behavioral_diff_runner.py`.

This is the production behavioral verification used for ACME Bank and single-file runs. It:

- stages COBOL data files and COPY books
- compiles COBOL with GnuCOBOL and Java with `javac`
- runs both executables and compares stdout
- returns layered scoring via `behavioral_layer_scoring_service.py`

Related: `GET /api/testing/toolchain-status` reports GnuCOBOL/Java availability.

## Behavioral Tests (testing agent)

Function:

```python
run_behavioral_tests(java_source: str, cobol_source: str) -> list[dict]
```

If `java_source` is empty, it returns an empty list.

The agent checks for local tools:

- `cobc --version`
- `javac -version`

It uses a temporary directory, writes Java source to `{class_name}.java`, compiles with `javac`, optionally compiles COBOL with `cobc`, then runs fixed scenarios.

Configured scenarios:

- `ADD_THEN_REPORT`
- `UPDATE_NOT_FOUND`
- `DELETE_THEN_REPORT`
- `INVALID_CHOICE`
- `EMPTY_REPORT`

Behavioral result fields:

```json
{
  "id": "ADD_THEN_REPORT",
  "description": "Add 1 item then generate report",
  "passed": false,
  "java_compiled": false,
  "java_compile_error": "javac not available on this system",
  "cobol_available": false,
  "stdout_diff": [],
  "assertion_failures": [],
  "java_stdout": "",
  "severity": "critical"
}
```

The exact values depend on compiler availability and generated Java behavior.

## Summary Computation

The summary is computed over:

```python
all_tests = parser_tests + conversion_tests + behavioral_tests
```

Counts:

- `total`: total tests
- `passed`: tests where `passed` is true
- `failed`: tests where `passed` is false
- `critical_failures`: failed tests where `severity == "critical"`
- `high_failures`: failed tests where `severity == "high"`

## Important Runtime Notes

- The current testing agent is regex/subprocess based.
- It does not require `javalang`.
- Behavioral tests require `javac` to compile Java.
- COBOL-vs-Java stdout diff requires `cobc`; otherwise COBOL comparison output is unavailable.
- Empty Java source means no conversion or behavioral tests are produced.

## Self-Validation Checklist

- [x] Request body matches `TestRequest`.
- [x] Response fields match `run_testing_agent()`.
- [x] Test IDs come from `testing_agent.py`.
- [x] Behavioral scenario IDs come from source.
- [x] Compiler requirements come from `_check_gnucobol()` and `_check_javac()`.
- [x] No test suite or result field was invented.
