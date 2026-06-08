# ACME Bank v3 — Production-Scale Credit Risk & Recovery Pipeline

A realistic Tunisian banking COBOL use case designed to stress-test the
COBOL → Java modernization pipeline. Significantly more complex than
v1 and v2: real data scale (1,900+ records), advanced COBOL constructs
(EXEC SQL, CALL, INSPECT, REDEFINES, internal SORT, OCCURS with INDEXED),
multi-program JCL chain, and inter-program file dependencies.

---

## What's new vs v2

| Aspect | v2 | v3 |
|---|---|---|
| Programs | 3 (~1,600 lines) | 5 (~2,700 lines) |
| Data records | ~26 across 3 files | 1,951 across 5 files |
| Data size | ~5 KB | ~525 KB |
| Copybooks | 6 | 8 (+ GUARCOPY, RECOVCOPY) |
| EXEC SQL | none | 4 SQL blocks across 2 programs (DB2 stubs) |
| CALL sub-programs | none | 2 (CHKAML, CALCFEE) |
| INSPECT verbs | none | REPLACING, CONVERTING, TALLYING |
| REDEFINES | none | yes (income parsing) |
| Internal SORT | external only | INPUT PROCEDURE / OUTPUT PROCEDURE |
| OCCURS w/ INDEXED BY | no | yes (sector matrix) |
| Reference modification | no | yes (sub-string lookup) |
| DECIMAL-POINT IS COMMA | no | yes (European format) |
| ALTERNATE RECORD KEY | 1 | 4 |
| Simultaneous open files | 5 | 8 in LOANEVAL |
| JCL steps | 3 | 4 with multi-LOADLIB |
| French dunning letters | no | yes |

---

## GnuCOBOL baseline testing (flat `.dat` files)

Production sources use `ORGANIZATION IS INDEXED`, but committed `.dat` fixtures are **flat
fixed-width** files. GnuCOBOL treats INDEXED as Berkeley DB; generated Java reads the flat
layout directly. For behavioral baseline runs, use **SEQUENTIAL** variants under
`src/sequential/` (see [docs/GNUCOBOL_FILE_ORGANIZATION.md](docs/GNUCOBOL_FILE_ORGANIZATION.md)).

```bash
cd cobol-modernization-service
python scripts/create_sequential_variants.py
export BEHAVIORAL_BASELINE_TEST_MODE=1   # API behavioral diff
```

---

## Repository layout

```
acme-bank-v3/
├── src/                    # 5 COBOL programs
│   ├── LOANEVAL.cbl       # ~850 lines - main scoring + EXEC SQL + CALL
│   ├── sequential/        # SEQUENTIAL variants for GnuCOBOL baseline (generated)
│   ├── RISKSCOR.cbl       # ~430 lines - BCT classification + SQL INSERT
│   ├── RECOVRY.cbl        # ~700 lines - collections + dunning letters
│   ├── RPTMONTH.cbl       # ~500 lines - executive report w/ top-10 sort
│   ├── CHKAML.cbl         # ~280 lines - AML sub-program (LINKAGE)
│   └── CALCFEE.cbl        # ~190 lines - Fee calc sub-program (LINKAGE)
├── copybooks/             # 8 copybooks
│   ├── CUSTCOPY.cpy       # 55+ fields, PEP/AML/KYC flags
│   ├── LOANCOPY.cpy       # 40+ fields, BCT classification
│   ├── COLLATCOPY.cpy     # Physical + financial collateral
│   ├── GUARCOPY.cpy       # NEW - Guarantor records
│   ├── SCORECOPY.cpy      # Scoring params + 5-component results
│   ├── RECOVCOPY.cpy      # NEW - 11 recovery action types
│   ├── ERRCOPY2.cpy       # Errors + file statuses + statistics
│   └── RPTCOPY2.cpy       # Report headers/footers with FILLER
├── jcl/
│   └── ACMEMNT.jcl        # 4-step monthly batch
├── data/                  # 5 fixed-width data files
│   ├── CUSTFILE.dat       # 500 customers (212 KB)
│   ├── LOANFILE.dat       # 800 loans (187 KB)
│   ├── COLFILE.dat        # 400 collateral records (79 KB)
│   ├── GUARFILE.dat       # 200 guarantees (26 KB)
│   └── SANCFILE.dat       # 51 sanctions/PEP entries (10 KB)
├── scripts/
│   ├── generate_data.py   # Reproducible data generator
│   └── generate_sanctions.py
└── README.md              # This file
```

---

## Business scenario

End-of-month batch run at ACME Bank Tunisia. Four programs run in sequence:

1. **LOANEVAL** scores every loan application using a 5-component model
   (income / payment history / DSCR / collateral / tenure), calls external
   AML (CHKAML) and pricing (CALCFEE) modules, and writes scored decisions.

2. **RISKSCOR** reads the scored decisions, applies BCT Circulaire 2021-02
   classification (Class 1-4 based on days past due), computes required
   provisions, updates the loan master, and produces the BCT regulatory
   submission file.

3. **RECOVRY** reads loans in classes 2, 3, and 4, prioritizes them via
   internal SORT by class+amount, applies the BCT escalation matrix
   (SMS → Phone → Letter → Legal notice → Court → Seizure / Write-off),
   and generates French dunning letters.

4. **RPTMONTH** produces the executive monthly report: portfolio summary
   by class, top-10 exposures (insertion sort), segment breakdown, type
   breakdown, NPL ratios.

---

## Advanced COBOL constructs (what makes this challenging for the parser)

### 1. EXEC SQL with SQLCA
Both LOANEVAL and RISKSCOR define SQLCA and embed SQL blocks (DB2
syntax). The pipeline parser must recognize `EXEC SQL ... END-EXEC`
blocks and host variables (`:WS-XXX`).

```cobol
EXEC SQL
    SELECT BUREAU_SCORE, BUREAU_CLASS
    INTO :WS-SQL-BUREAU-SCORE, :WS-SQL-BUREAU-CLASS
    FROM CREDITBUREAU.SCORES
    WHERE CUST_ID = :WS-SQL-CUST-ID
END-EXEC
```

In RISKSCOR: `INSERT INTO PROD.RISK_HIST` audit log.
The SQL is commented out so the program runs standalone, but the parser
should detect both the active and commented variants.

### 2. Sub-program CALL with LINKAGE SECTION
LOANEVAL calls CHKAML and CALCFEE. Both sub-programs use `LINKAGE
SECTION` with two parameters (request + response). The pipeline must
trace the data flow across modules.

```cobol
CALL 'CHKAML' USING WS-AML-REQUEST WS-AML-RESPONSE
```

CHKAML.cbl:
```cobol
LINKAGE SECTION.
01 LK-AML-REQUEST. ...
01 LK-AML-RESPONSE. ...
PROCEDURE DIVISION USING LK-AML-REQUEST LK-AML-RESPONSE.
```

### 3. INSPECT (3 forms)
- `INSPECT WS-INCOME-RAW REPLACING ALL SPACES BY ZEROS` (LOANEVAL)
- `INSPECT WS-NAME-NORMALIZED CONVERTING 'abc...xyz' TO 'ABC...XYZ'` (CHKAML)
- `INSPECT WS-HIGH-RISK-COUNTRIES TALLYING WS-RISK-SCORE FOR ALL LK-REQ-NATIONALITY` (CHKAML)

### 4. REDEFINES
Customer income field is read raw, then REDEFINES split into whole
and cents parts after INSPECT normalization:
```cobol
01 WS-INCOME-RAW             PIC X(9).
01 WS-INCOME-PARSED REDEFINES WS-INCOME-RAW.
   05 WS-INCOME-WHOLE        PIC 9(7).
   05 WS-INCOME-CENTS        PIC 9(2).
```

### 5. Internal SORT — INPUT PROCEDURE / OUTPUT PROCEDURE
LOANEVAL ranks the 5 scoring components by score:
```cobol
SORT SORT-WORK-FILE
    ON DESCENDING KEY SORT-COMPONENT-SCORE
    INPUT PROCEDURE IS 4910-LOAD-SORT THRU 4910-EXIT
    OUTPUT PROCEDURE IS 4920-RANK-OUTPUT THRU 4920-EXIT.
```
RECOVRY uses the same pattern with two-key sort
(`ON DESCENDING KEY SORT-PRIORITY ON DESCENDING KEY SORT-AMOUNT`).

### 6. OCCURS with INDEXED BY
Sector risk matrix (12 entries) loaded once, looked up per loan:
```cobol
05 WS-SECTOR-ENTRY OCCURS 12 TIMES INDEXED BY SECTOR-IDX.
   10 SCT-CODE        PIC X(4).
   10 SCT-LABEL       PIC X(30).
   10 SCT-ADJUSTMENT  PIC S9(3)V99.
```
Lookup uses `PERFORM VARYING SECTOR-IDX` plus `EXIT PERFORM`. Tests
both indexed and subscripted access patterns in the same program.

### 7. SPECIAL-NAMES DECIMAL-POINT IS COMMA
LOANEVAL is European-format COBOL (decimal comma).
All numeric literals: `25,00` not `25.00`. This is how French/Tunisian
COBOL is written. The parser must accept both formats based on
SPECIAL-NAMES.

### 8. Reference modification
Employer name sector inference uses substring:
```cobol
WHEN CUST-EMPLOYER (1:6) = 'BANQUE'
    MOVE 'BANK' TO WS-SQL-SECTOR
WHEN CUST-EMPLOYER (1:10) = 'MINISTERE '
    MOVE 'ADMI' TO WS-SQL-SECTOR
```

### 9. ALTERNATE RECORD KEY WITH DUPLICATES
Four files use this for one-to-many access:
- COLFILE: alternate key on COL-LOAN-ID (multiple collaterals per loan)
- GUARFILE: alternate key on GTR-LOAN-ID (multiple guarantors per loan)
- SCORFILE: alternate key on SCR-LOAN-ID (history of scores)
- SANCFILE: alternate key on SANC-CIN (name and ID lookup)

### 10. Eight simultaneously open files in LOANEVAL
```
INPUT:  LOAN-FILE, CUSTOMER-FILE, COLLATERAL-FILE, GUARANTEE-FILE
I-O:    SCORE-FILE
OUTPUT: DECISION-REPORT, REJECT-LOG
WORK:   SORT-WORK-FILE
```

### 11. Cross-program file dependencies
- LOANEVAL writes SCORFILE → RISKSCOR reads → RPTMONTH reads
- RECOVRY writes RECVNEW → RISKSCOR reads (recovery flag)
- This means STEP02 and STEP04 must come after STEP01 (JCL COND).

### 12. Multi-LOADLIB JCL concatenation
STEP01 needs CHKAML and CALCFEE which live in separate load libraries:
```
//STEPLIB  DD  DSN=ACME.PROD.CREDIT.LOADLIB,DISP=SHR
//         DD  DSN=ACME.PROD.AML.LOADLIB,DISP=SHR
//         DD  DSN=ACME.PROD.PRICING.LOADLIB,DISP=SHR
```

---

## Tunisian banking specifics

Real-world banking content the parser/converter must handle correctly:

| Item | Detail |
|---|---|
| **Decimal format** | Comma decimal (`SPECIAL-NAMES DECIMAL-POINT IS COMMA`) |
| **Currency precision** | TND has 3 decimals (millimes), some fields PIC 9(n)V9(3) |
| **CIN** | 8-digit national ID (`PIC 9(8)`) — primary customer identifier |
| **Governorates** | 24 codes used in addresses |
| **BCT Circulaire 2021-02** | 4-class loan classification (1=current, 2=30-90d, 3=90-180d, 4=>180d) |
| **TMM reference rate** | 7.25% base, +1.50% to +4.50% spread by score in CALCFEE |
| **TVA** | 19% on banking fees |
| **Timbre fiscal** | Fixed stamp tax on loan files (5,000 TND) |
| **PEP screening** | Loi 2015-26 LBA/FT mandate — checked in CHKAML |
| **BCT submission** | Quarterly file produced by RISKSCOR for regulator |
| **Customer segments** | MM (mass market), MB (middle), PR (premium), PB (private banking) |
| **Loan types** | CON, IMM, AUT, PRO, REV, DEC (consumer, mortgage, auto, business, revolving, overdraft) |
| **French dunning letters** | All customer-facing strings in French (per BCT consumer protection) |

---

## How to run (after Java conversion)

The pipeline should detect:

1. **LOANEVAL** as the entry point (referenced first in JCL).
2. **CHKAML and CALCFEE** as sub-programs invoked by LOANEVAL.
3. **The file lineage**:
   - LOANFILE → LOANEVAL → SCORFILE → RISKSCOR → BCTSUBM
   - LOANFILE → RECOVRY → RECVNEW → RISKSCOR (back-reference)
   - All three intermediate files → RPTMONTH
4. **The two SORT blocks** as in-memory operations needing temp work files.
5. **The 4 EXEC SQL blocks** as JDBC/JPA calls needing connection injection.
6. **The 8 indexed files** as either H2 in-memory tables, JPA entities, or
   simple BTreeMap depending on target persistence layer.

---

## Expected pipeline behavior

When run through the COBOL → Java pipeline, this use case should:

- ✅ Parse all 5 programs without error.
- ✅ Detect the 8 copybook resolutions.
- ✅ Identify the 2 sub-program CALL graph edges.
- ✅ Detect the 4 EXEC SQL blocks and flag them for SQL → JPA translation.
- ✅ Handle DECIMAL-POINT IS COMMA properly (parse `25,00` as 25.00).
- ✅ Convert internal SORT to Stream.sorted() with a Comparator or to
  Collections.sort on an ArrayList in the OUTPUT PROCEDURE.
- ✅ Convert OCCURS INDEXED BY to either Java arrays or ArrayList with
  preserved access patterns.
- ✅ Handle ALTERNATE RECORD KEY (multiple secondary indexes per "table").
- ✅ Map LINKAGE SECTION parameters to Java method signatures.
- ✅ Preserve all BCT business rules in the generated Java code.

Things that should **NOT** trip up the pipeline:
- Commented-out EXEC SQL (still seen as SQL by lexer)
- File status 88-level conditions for control flow
- Reference modification syntax `IDENTIFIER(start:length)`
- French strings with accented characters
- Multi-step JCL with COND= chains
- DCB RECFM/LRECL/BLKSIZE specifications

---

## Regulatory references

- **BCT Circulaire 2021-02**: Loan classification and provisioning
- **BCT Circulaire 2018-06**: KYC requirements (Article 24 - guarantors)
- **BCT Circulaire 2023-08**: Updated risk management
- **Loi 2015-26**: LBA/FT (anti-money laundering / counter-terrorism)
- **Décret 2018-1129**: AML implementation decree
- **Loi 2004-63**: Personal data protection (anonymization required)

---

## Demo talking points (for the EY presentation)

1. **Scale is realistic** — 1,900 records, ~500KB. Not toy data.
   A real Tunisian bank batch is 100,000-1,000,000 records, but the
   structure and constructs here are production-equivalent.

2. **Tunisian context is authentic** — real governorate codes, real
   employer types, French dunning letters, BCT regulatory references,
   TMM-based pricing.

3. **Advanced COBOL constructs** — every major construct that trips up
   simple converters is exercised: EXEC SQL, CALL, INSPECT, REDEFINES,
   internal SORT, INDEXED BY, reference modification, alternate keys,
   European decimal format.

4. **Multi-program orchestration** — 5 programs + 4-step JCL is how
   real batches are structured. Not a single monolithic file.

5. **Audit trail** — BCT submission file, dunning letters, recovery
   actions. Regulator-friendly output.

---

## Caveats / known limitations

- SQL blocks are commented out — they're for parser detection but
  don't actually call DB2. The fallback paths (e.g., synthetic bureau
  score via FUNCTION MOD) make programs runnable standalone.
- Letter generation in RECOVRY uses simplified date arithmetic
  (`COMPUTE REC-NEXT-ACTION-DATE = WS-TODAY-DATE + 7`) which produces
  invalid dates near month boundaries. A real program would use a
  date calculation routine (e.g., CEEDATE).
- The synthetic bureau score `FUNCTION MOD(WS-SQL-CUST-ID, 200) - 100`
  is deterministic but not realistic. Real bureau integration would
  be via DB2 or REST.
- The sanctions file is small (51 entries) — a real production
  sanctions list is ~250,000 entries from Refinitiv World-Check.
- Programs are not actually compilable on every COBOL dialect — they
  target IBM Enterprise COBOL conventions but use some constructs
  (like INSPECT CONVERTING) that work on most modern compilers.
- AML and pricing modules are intentionally simplified versions of
  what real production modules look like.
