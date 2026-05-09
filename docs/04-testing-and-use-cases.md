# Testing reference — Use Case 3, PAYROLL, running pytest

## 4.1 How to run the suite

From `cobol-modernization-service`:

```bash
python -m pytest -q
```

Focused integration tests:

```bash
python -m pytest tests/test_usecase3_pipeline.py tests/test_payroll_multiline_statements.py -v
```

## 4.2 Use Case 3 — fixture layout

```
tests/fixtures/usecase3/
  jcl/ACMEPOST.jcl
  copybooks/   (CUSTCOPY, ERRORCOPY, TXNCOPY, RPTHDCPY — many FILLER in RPTHDCPY)
  src/
    CUSTMGR.cbl
    STMTRPT.cbl
    TXNPOST.cbl
```

## 4.3 Why tests patch `COPY_LIBRARY_CONFIG`

| Reality | Test workaround |
|---------|-----------------|
| JCL `SYSLIB` = MVS dataset, not a disk path | Prepend absolute `.../usecase3/copybooks/` to resolver defaults |
| Resolver cache | `clear_cache()` in fixture teardown |

## 4.4 `test_usecase3_pipeline.py`

All tests use **`PipelineService().run_full_pipeline(cobol, jcl_text)`** with **`ACMEPOST.jcl`**.

| Test | Program | Highlights |
|------|---------|------------|
| `test_custmgr_full_pipeline_enriched_binding` | `CUSTMGR.cbl` | `preflight_errors == []`, symbols, COMPUTE, **`data_mappings["CUSTOMER-FILE"]["physical_dataset"] == "ACME.CUSTOMER.MASTER"`**, PERFORM targets, copybooks |
| `test_stmtrpt_parses_with_fillers_and_rptcopy` | `STMTRPT.cbl` | No preflight errors; `RPTHDCPY`; ≥1 `FILLER` in symbol table |
| `test_txnpost_parses_with_fillers` | `TXNPOST.cbl` | Operations non-empty; `RPTHDCPY` + `TXNCOPY` |

## 4.5 PAYROLL-CALC — `test_payroll_multiline_statements.py`

| Fixture | `tests/fixtures/payroll/PAYROLL-CALC.cbl` |
|---------|-------------------------------------------|
| API | **`ParserLayer().parse(source)`** only |

Asserts 6 `COMPUTE` targets, no false W002 on listed vars, `arithmetic_expression` risk flag, control-flow expectations.

## 4.6 Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| Empty AST + old preflight text | Stale server — restart backend |
| Analysis halted + FILLER message | Stale `parserResult` in browser — reset workspace / re-parse |

---

*Back to [README](./README.md).*
