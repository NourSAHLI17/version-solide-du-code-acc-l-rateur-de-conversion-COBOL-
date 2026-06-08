# 09 — Testing, Validation, and Download

Quality assurance and artifact delivery after Java generation.

**Code:** `app/services/testing_agent.py`, `behavioral_diff_runner.py`,
`app/validation/service.py`, download handlers in `modernization.py`

---

## Why testing is separate from conversion

Conversion can succeed while behavior is wrong. Testing validates:

| Layer | Checks |
|---|---|
| Parser tests | Structural source quality |
| Conversion tests | Java static rules |
| Behavioral tests | Runtime COBOL vs Java stdout |

---

## Testing agent

```http
POST /api/test
```

```json
{
  "parser_output": {},
  "analysis_output": {},
  "java_source": "",
  "cobol_source": ""
}
```

### Report structure

```json
{
  "parser_tests": [],
  "conversion_tests": [],
  "behavioral_tests": [],
  "summary": { "passed": 0, "failed": 0, "skipped": 0 }
}
```

### Parser tests

- Symbols have `pic` or `kind`
- PERFORM targets exist as paragraphs
- Paragraph names are not reserved words
- Loop metadata complete

### Conversion static tests

- No `do-while` for `PERFORM UNTIL` (should be `while`)
- BigDecimal used for decimal PICs
- Method names align with paragraph mapping
- No invented field names outside symbol table

### Behavioral tests

Attempted when `cobc` and `javac` are on PATH. Compares GnuCOBOL stdout vs Java stdout.

---

## Behavioral diff

```http
POST /api/testing/behavioral-diff
GET  /api/testing/toolchain-status
```

`run_behavioral_diff()` in `behavioral_diff_runner.py`:

1. Compile COBOL with GnuCOBOL
2. Compile Java with `javac`
3. Run both with same input data
4. Diff stdout lines

Toolchain status reports availability of `cobc`, `java`, `javac`.

---

## Validation service

```http
POST /api/validate
```

```json
{
  "expected_output": "...",
  "actual_output": "..."
}
```

`ValidationService` compares expected vs actual text output — used when reference output
is known (regression scenarios).

---

## Downloads

| Endpoint | Output |
|---|---|
| `POST /api/download/java` | Single `.java` file stream |
| `POST /api/download/project` | ZIP with all converted Java + test reports |

Backend owns file naming and ZIP assembly. Frontend receives blob and triggers browser download.

---

## Degradation strategy

| Environment | What works |
|---|---|
| No GnuCOBOL | Parser + conversion static tests only |
| No JDK | No compile or behavioral tests |
| Full toolchain | Complete report with behavioral diff |

Static checks provide immediate value; behavioral diff is the gold standard when available.

---

## Related documents

- [08 — Java conversion](./08-java-conversion.md) — upstream artifact
- [11 — Frontend and API](./11-frontend-and-api.md) — Testing Agent page
