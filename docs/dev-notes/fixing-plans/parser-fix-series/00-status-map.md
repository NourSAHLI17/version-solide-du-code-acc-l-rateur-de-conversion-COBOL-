# Status Map — What's Fixed vs What Still Needs Work

## Already fixed (confirmed by your docs and tests)

| Issue | Fix | Evidence |
|---|---|---|
| FILLER duplicate halt | `UNREFERENCEABLE_NAMES`, preflight split into (errors, warnings) | Doc 02 §2.1, STMTRPT/TXNPOST now parse |
| Multi-line COMPUTE | `_combine_logical_statements()` joins lines until period | Doc 02 §2.3, 6 COMPUTE targets in PAYROLL test |
| Preflight too aggressive | Split into fatal errors + non-fatal warnings | Doc 02 §2.2 |
| Copybook metadata lost after expansion | `parse(source, copybook_metadata)` merges resolver audit | Doc 02 §2.4 |
| Context enricher wiring | `run_full_pipeline` passes JCL through to enricher | Doc 01 §1.2, CUSTMGR data_mappings test |
| Escaped JSON in API | `_coerce_analysis_to_dict` unwraps nested strings | Doc 03 §3.2 |
| Hybrid backend scaffold | factory.py supports heuristic/hybrid/antlr | Doc 02 §2.5 |

## Still needs fixing for 10/10

| # | Stage | Issue | Impact | File to create |
|---|---|---|---|---|
| 1 | Parser | `V9(4)` PIC decode returns `java_type: "String"` instead of `"BigDecimal"` | Wrong type mapping for pure-decimal fields | `01-fix-pic-v-prefix.md` |
| 2 | Parser | DISPLAY reference extraction picks up words from string literals | False variable references in operations | `02-fix-display-references.md` |
| 3 | Analysis | 12/14 paragraphs labeled "Terminate program execution" | Useless role information for converter | `03-fix-paragraph-roles.md` |
| 4 | Analysis | "sum values from 1 to 30 into TOTAL" hallucinated in 13 paragraphs | Invented business rules contaminate output | `04-fix-business-rules.md` |
| 5 | Analysis | `8300-DETERMINE-TAX-RATE` inputs empty (misses EVALUATE WHEN vars) | Incomplete data flow | `05-fix-dataflow-evaluate.md` |
| 6 | Analysis | `global_purpose` is generic ("compute an accumulated total") | Meaningless program description | `06-fix-global-purpose.md` |
| 7 | Converter | `rounded: false` still uses `RoundingMode.HALF_UP` instead of `DOWN` | Wrong financial arithmetic | `07-fix-rounded-flag.md` |
| 8 | Converter | `isActive()` returns String (violates JavaBeans) | Java convention violation | `08-fix-flag-naming.md` |
| 9 | Converter | Call graph flattened (`showMenu` and `routeChoice` called as siblings) | Structural deviation from COBOL | `09-fix-call-graph.md` |
| 10 | All | Master Cursor prompt covering all 9 fixes | Single injection point | `10-cursor-master-prompt.md` |
