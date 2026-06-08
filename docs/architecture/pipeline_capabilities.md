# Pipeline Capabilities

> COBOL Modernization Pipeline — construct support matrix and known limitations.
>
> Last updated: 2026-05-26

---

## Supported Constructs

These COBOL features are fully recognized by the parser, carried through analysis, and correctly converted to Java.

### Data Division

| Construct | Notes |
|---|---|
| `PIC X`, `PIC 9`, `PIC V`, `PIC S` | All standard picture clauses |
| `COMP` / `COMP-1` / `COMP-2` | Binary and floating-point numeric types |
| `COMP-3` (packed decimal) | Converted to `BigDecimal` in Java |
| `FD` and `SD` file descriptions | File and sort descriptions with full record layout |
| `OCCURS` (fixed) | With and without `INDEXED BY` |
| `REDEFINES` | Overlapping field layouts preserved via union-style accessors |
| `COPY` statement | Copybook expansion before parsing |
| `ALTERNATE RECORD KEY WITH DUPLICATES` | Indexed file alternate keys |
| `SPECIAL-NAMES DECIMAL-POINT IS COMMA` | European decimal notation |
| Reference modification (substring) | `field(start:length)` syntax |

### Procedure Division

| Construct | Notes |
|---|---|
| `PERFORM` (simple) | Inline and out-of-line paragraph calls |
| `PERFORM VARYING` | Converted to Java `for` loops |
| `PERFORM UNTIL` | Converted to Java `while` loops |
| `PERFORM THRU` | Range of paragraphs executed sequentially |
| `EVALUATE` / `WHEN` / `WHEN OTHER` | Converted to `switch` or `if-else` chains |
| `IF` / `ELSE` nested up to 5 levels | Deep conditional nesting |
| `COMPUTE` with `ROUNDED` | Arithmetic expressions with rounding mode |
| `MOVE` | Type-aware assignment (alphanumeric, numeric, group) |
| `ADD`, `SUBTRACT`, `MULTIPLY`, `DIVIDE` | Including `GIVING`, `REMAINDER`, `ON SIZE ERROR` |
| `STRING` / `UNSTRING` | Concatenation and splitting with `DELIMITED BY` |
| `INSPECT REPLACING` | Character/substring replacement |
| `INSPECT CONVERTING` | Character transliteration |
| `INSPECT TALLYING` | Character counting |
| `CALL` (sub-program) | External program invocation converted to method/service calls |
| Internal `SORT` | With `INPUT PROCEDURE` / `OUTPUT PROCEDURE` |
| `REWRITE` on indexed files | Field preservation for unmodified fields |

### File I/O

| Construct | Notes |
|---|---|
| Sequential file `READ` / `WRITE` | Line-by-line and record-based |
| Indexed file `READ` / `WRITE` / `REWRITE` / `DELETE` | With `RECORD KEY` and `ALTERNATE RECORD KEY` |
| `FILE STATUS` checking | Two-byte status codes |
| `OPEN INPUT` / `OUTPUT` / `I-O` / `EXTEND` | All open modes |
| `START` with key conditions | Indexed file positioning |

---

## Partially Supported

These constructs are recognized by the parser but may produce incomplete or stubbed Java output.

| Construct | Current Behavior |
|---|---|
| `EXEC SQL` ... `END-EXEC` | Recognized and extracted; stubbed in Java with `// TODO: SQL` marker. Basic `SELECT INTO` may generate JDBC calls depending on analyzer output. |
| `USAGE BINARY` | Converted to `int` or `long` depending on PIC size. Precision edge cases (>18 digits) may need manual review. |
| `OCCURS DEPENDING ON` (basic) | Simple ODO with numeric bounds is supported. Complex nested ODO or ODO with subordinate OCCURS may produce incorrect array sizing. |
| `COPY ... REPLACING` | COPY expansion works; `REPLACING` pseudo-text substitution handles simple token replacement but may miss complex multi-line replacements. |
| `DISPLAY` / `ACCEPT` | `DISPLAY` converted to `System.out.println`. `ACCEPT` converted to `Scanner` input. Interactive prompts may need manual adjustment. |

---

## Not Supported

These constructs are not handled by the current pipeline. Programs using them will either fail to parse or produce Java with missing functionality.

| Construct | Reason |
|---|---|
| CICS commands (`EXEC CICS`) | BMS screen handling, transaction management, and CICS API calls require a runtime middleware layer not present in the Java output. |
| IMS DB calls (`EXEC DLI`) | Hierarchical database access patterns have no direct Java equivalent without an IMS bridge. |
| VSAM file types beyond INDEXED | RRDS (relative record) and ESDS (entry-sequenced) access methods are not modeled. |
| `DECLARE CURSOR` / complex SQL | SQL beyond simple `SELECT INTO` and `INSERT` is stubbed. Cursor-based result set iteration, dynamic SQL, and stored procedure calls require manual conversion. |
| COBOL OO features | `CLASS-ID`, `METHOD-ID`, `INVOKE`, `FACTORY`, and object-oriented COBOL extensions are not recognized by the parser. |
| Report Writer (`RD`, `GENERATE`) | Report Writer feature is parsed but not converted to Java. |
| Communication Section | `CD` entries and `SEND`/`RECEIVE` are not supported. |
| Segmentation (`SECTION` priority numbers) | Overlay segmentation is obsolete and not modeled. |

---

## Known Limitations

### Size and Complexity

- **Programs over 5,000 lines** may exceed the analyzer's LLM context window. The pipeline segments large programs automatically, but business rule extraction quality degrades for very large monolithic programs.
- **Deeply nested copybook chains** (>3 levels of COPY within COPY) may cause expansion timeouts.
- **Programs with >50 paragraphs** receive less granular per-paragraph scoring since structural checks are spread across more units.

### Cross-Program and JCL

- **JCL flow is parsed but not automatically wired.** Multi-step job streams are recognized, but the Java output does not generate orchestration code (e.g., Spring Batch jobs) to chain program executions.
- **Sub-program linkage** via `CALL` is converted to method calls, but the calling conventions (parameter passing by reference vs. by content) may need manual review for complex `USING` clauses.

### Numeric Precision

- **Decimal point in literals** must match the `SPECIAL-NAMES` configuration. If `DECIMAL-POINT IS COMMA` is declared, numeric literals in the source must use commas; the parser does not auto-detect mismatches.
- **COMP-3 byte offsets** depend on correct PIC clause parsing. Incorrect record layouts in copybooks can cascade into wrong field boundaries in the Java output.

### Copybooks and Data Layout

- **All copybook fields must be referenceable from a single 01-level** record. Programs that use multiple 01-levels within a single FD, or that reference fields across different record descriptions without qualification, may produce ambiguous Java field mappings.
- **RENAMES (66-level)** items are recognized but converted to simple aliases. Complex RENAMES spanning non-contiguous fields may not preserve correct byte boundaries.
- **88-level condition names** are converted to boolean helper methods. Compound 88-level conditions with `THRU` ranges work for numeric fields but may be imprecise for alphanumeric ranges.

### Runtime Behavior

- **File I/O assumes flat files** in the working directory. Programs that reference DD names via JCL `ASSIGN` clauses need manual path configuration in the Java output.
- **STOP RUN vs. GOBACK** — both are converted to method returns or `System.exit()`. In sub-program contexts, `GOBACK` should return control to the caller, which may require manual adjustment if the call hierarchy is complex.
- **ON EXCEPTION / NOT ON EXCEPTION** handlers on `CALL` statements are converted to try/catch blocks, but the exception type mapping may not match the original COBOL behavior exactly.
