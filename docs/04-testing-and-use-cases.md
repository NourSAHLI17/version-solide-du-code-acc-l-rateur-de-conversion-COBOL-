# Testing reference — Use Case 3, PAYROLL-CALC, three outputs, pytest

## 4.1 How to run the suite

From `cobol-modernization-service`:

```bash
python -m pytest -q
```

Focused integration tests:

```bash
python -m pytest tests/test_usecase3_pipeline.py tests/test_payroll_multiline_statements.py -v
```

---

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

### Why tests patch `COPY_LIBRARY_CONFIG`

| Reality | Test workaround |
|---------|-----------------|
| JCL `SYSLIB` = MVS dataset, not a disk path | Prepend absolute `.../usecase3/copybooks/` to resolver defaults |
| Resolver cache | `clear_cache()` in fixture teardown |

### `test_usecase3_pipeline.py`

All tests use **`PipelineService().run_full_pipeline(cobol, jcl_text)`** with **`ACMEPOST.jcl`**.

| Test | Program | Highlights |
|------|---------|------------|
| `test_custmgr_full_pipeline_enriched_binding` | `CUSTMGR.cbl` | `preflight_errors == []`, symbols, COMPUTE, **`data_mappings["CUSTOMER-FILE"]["physical_dataset"] == "ACME.CUSTOMER.MASTER"`**, PERFORM targets, copybooks |
| `test_stmtrpt_parses_with_fillers_and_rptcopy` | `STMTRPT.cbl` | No preflight errors; `RPTHDCPY`; ≥1 `FILLER` in symbol table |
| `test_txnpost_parses_with_fillers` | `TXNPOST.cbl` | Operations non-empty; `RPTHDCPY` + `TXNCOPY` |

---

## 4.3 PAYROLL-CALC — regression pack (`test_payroll_multiline_statements.py`)

| Fixture | `tests/fixtures/payroll/PAYROLL-CALC.cbl` |
|---------|-------------------------------------------|
| Entry point | **`ParserLayer().parse(source)`** for structural asserts |
| Full analysis | **`AnalysisAgent().analyze(source, parser_output)`** |

**What the tests lock down (high level):**

- **`WS-TAX-RATE`** → `pic_decoded.java_type == BigDecimal`, **`dec_digits == 4`** (`PIC V9(4)` implied decimal).
- **`DISPLAY`** of banner text → **no** spurious **`references`** from English words inside quotes.
- **`DISPLAY "Employee: … EMP-NAME(WS-FOUND-IDX)`** → references include real data names only.
- **`COMPUTE`** rows → multiple **`rounded: true`**, at least one **`rounded: false`** (matches COBOL **`ROUNDED`** keyword usage).
- **Analysis:** `global_purpose` payroll-themed; **no** hallucinated “sum 1..30”; **`8300-DETERMINE-TAX-RATE`** inputs include **`WS-GROSS-PAY`**; roles not bulk-marked “Terminate”; **`analysis_engine`** / **`analysis_revision`** present.
- **Conversion prompt:** **`rounding_contract`** mentions **`WS-NET-PAY`** and **`RoundingMode.DOWN`** vs **`HALF_UP`** where applicable.

**Presenter note:** Detailed COBOL narrative (paragraphs, PIC clauses, tax brackets) lives in **`05-hybrid-approach-quality-fixes-and-file-map.md` §6**.

---

## 4.4 The three outputs — what to show in a demo

| Step | Output | Produced by | What proves value |
|------|--------|-------------|-------------------|
| 1 | **Parser JSON** | `ParserLayer.parse` | `symbol_table`, `operations` (with **`rounded`** on **`COMPUTE`**), `control_flow`, `parser_revision` |
| 2 | **Analysis JSON** | `AnalysisAgent.analyze` | `sections[*].role`, `inputs`, `business_rules`, `global_purpose`, `analysis_engine` |
| 3 | **Java (+ mapping notes)** | `ConversionAgent.convert` (needs LLM keys) | Idiomatic draft + **`rounding_contract`** in prompt inputs |

Stub behavior: without LLM keys, conversion returns a **configuration message**—still demo **outputs 1 and 2**.

---

## 4.5 Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Empty AST + old preflight text | Stale server — restart backend |
| Analysis halted + FILLER message | Stale `parserResult` in browser — reset workspace / re-parse |
| Parser/analyses identical across “releases” | Wrong deployment — verify **`parser_revision`** / **`analysis_revision`** in JSON |

---

*Back to [README](./README.md).*
