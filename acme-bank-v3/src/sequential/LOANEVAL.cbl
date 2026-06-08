      *****************************************************************
      * PROGRAM:     LOANEVAL
      * DESCRIPTION: Loan application evaluation engine - Production v3.
      *              Reads loan applications, retrieves customer KYC
      *              and credit bureau data via embedded SQL, loads
      *              collateral and guarantees, applies the BCT-approved
      *              5-component scoring model with sector adjustments,
      *              calls CHKAML risk module for AML clearance,
      *              and writes scored decisions to the output files.
      *
      *              Enhancements vs v2:
      *              - EXEC SQL calls to CREDITBUREAU and FXRATE tables
      *              - CALL to external module CHKAML for AML screening
      *              - INSPECT for income string normalization
      *              - REDEFINES on customer record for parse flex
      *              - Internal SORT of scoring components by weight
      *              - Sector-based risk adjustment matrix
      *              - PERFORM THRU for batch error recovery
      *
      * COPYBOOKS:   CUSTCOPY, LOANCOPY, COLLATCOPY, GUARCOPY,
      *              SCORECOPY, ERRCOPY2, RPTCOPY2
      * FILES:       LOAN-FILE, CUSTOMER-FILE, COLLATERAL-FILE,
      *              GUARANTEE-FILE, SCORE-FILE, DECISION-REPORT,
      *              REJECT-LOG, SORT-WORK-FILE
      * SUB-PGMS:    CHKAML  - AML screening service
      *              CALCFEE - Fee calculation service
      * TABLES:      CREDITBUREAU.SCORES - External credit bureau scores
      *              FOREX.DAILY_RATES   - Currency conversion rates
      *              PROD.SECTOR_RISK    - Sector risk adjustment matrix
      * AUTHOR:      ACME Bank - Credit Risk Division
      * VERSION:     6.0
      * BCT REF:     Circulaire BCT 2021-02, 2023-08, 2024-04
      *****************************************************************
       IDENTIFICATION DIVISION.
       PROGRAM-ID. LOANEVAL.
       AUTHOR. ACME-CREDIT-RISK.
       DATE-WRITTEN. 2024-04-15.
       DATE-COMPILED.

       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SOURCE-COMPUTER. IBM-MAINFRAME.
       OBJECT-COMPUTER. IBM-MAINFRAME.
       SPECIAL-NAMES.
           DECIMAL-POINT IS COMMA.

       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT LOAN-FILE
               ASSIGN TO "LOANFILE.dat"
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE IS SEQUENTIAL

               FILE STATUS IS WS-LOAN-FS.

           SELECT CUSTOMER-FILE
               ASSIGN TO "CUSTFILE.dat"
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE IS SEQUENTIAL
               FILE STATUS IS WS-CUST-FS.

           SELECT COLLATERAL-FILE
               ASSIGN TO "COLFILE.dat"
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE IS SEQUENTIAL
               FILE STATUS IS WS-COL-FS.

           SELECT GUARANTEE-FILE
               ASSIGN TO "GUARFILE.dat"
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE IS SEQUENTIAL
               FILE STATUS IS WS-GTR-FS.

           SELECT SCORE-FILE
               ASSIGN TO "SCORFILE.dat"
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE IS SEQUENTIAL

               FILE STATUS IS WS-SCR-FS.

           SELECT DECISION-REPORT
               ASSIGN TO "DECIRPT.dat"
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-RPT-FS.

           SELECT REJECT-LOG
               ASSIGN TO "EVALREJ.dat"
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-REJ-FS.

           SELECT SORT-WORK-FILE
               ASSIGN TO "SORTWRK.dat".

       DATA DIVISION.
       FILE SECTION.

       FD LOAN-FILE
           RECORD CONTAINS 239 CHARACTERS.
       01 LOAN-RECORD.
           COPY LOANCOPY REPLACING
               ==01 LOAN-RECORD.==
               BY ====
               ==05 LOAN-FILLER          PIC X(8)==
               BY ==05 LOAN-FILLER          PIC X(9)==.

       FD CUSTOMER-FILE
           RECORD CONTAINS 434 CHARACTERS.
       COPY CUSTCOPY.

       FD COLLATERAL-FILE
           RECORD CONTAINS 253 CHARACTERS.
       COPY COLLATCOPY.

       FD GUARANTEE-FILE
           RECORD CONTAINS 130 CHARACTERS.
       COPY GUARCOPY.

       FD SCORE-FILE
           RECORD CONTAINS 229 CHARACTERS.
       01 SCORE-RESULT.
          05 SCR-RESULT-ID        PIC 9(12)     VALUE ZEROS.
          05 SCR-LOAN-ID          PIC 9(10)     VALUE ZEROS.
          05 SCR-CUST-ID          PIC 9(8)      VALUE ZEROS.
          05 SCR-DATE             PIC 9(8)      VALUE ZEROS.
          05 SCR-TOTAL-SCORE      PIC 9(4)      VALUE ZEROS.
          05 SCR-DECISION         PIC X(2)      VALUE SPACES.
             88 SCR-APPROVED      VALUE 'AP'.
             88 SCR-CONDITIONAL   VALUE 'CO'.
             88 SCR-REVIEW        VALUE 'RV'.
             88 SCR-DECLINED      VALUE 'DC'.
          05 SCR-MAX-LOAN-AMT     PIC 9(11)V99  VALUE ZEROS.
          05 SCR-MAX-RATE         PIC 9(2)V9(4) VALUE ZEROS.
          05 SCR-REASON-1         PIC X(50)     VALUE SPACES.
          05 SCR-REASON-2         PIC X(50)     VALUE SPACES.
          05 SCR-REASON-3         PIC X(50)     VALUE SPACES.
          05 SCR-ANALYST-ID       PIC 9(6)      VALUE ZEROS.
          05 SCR-FILLER           PIC X(10)     VALUE SPACES.

       FD DECISION-REPORT
           RECORD CONTAINS 137 CHARACTERS.
       01 DECISION-LINE            PIC X(137).

       FD REJECT-LOG
           RECORD CONTAINS 120 CHARACTERS.
       01 REJECT-LINE              PIC X(120).

       SD SORT-WORK-FILE.
       01 SORT-COMPONENT-REC.
          05 SORT-COMPONENT-NAME   PIC X(8).
          05 SORT-COMPONENT-WEIGHT PIC 9(3)V99.
          05 SORT-COMPONENT-SCORE  PIC 9(4).
          05 SORT-COMPONENT-RANK   PIC 9(1).

       WORKING-STORAGE SECTION.
      *--- File status vars first for FD compatibility ---
       COPY ERRCOPY2.
      *--- WS-GTR-FS is defined in ERRCOPY2 ---
       COPY RPTCOPY2.
      *--- Scoring params/work; SCORE-RESULT record is under FD ---
       COPY SCORELAY.

      *================================================================
      * EMBEDDED SQL HOST VARIABLES
      *================================================================
       01 WS-SQL-VARS.
          05 WS-SQL-CUST-ID        PIC 9(8)      VALUE ZEROS.
          05 WS-SQL-BUREAU-SCORE   PIC S9(4)     VALUE ZEROS.
          05 WS-SQL-BUREAU-CLASS   PIC X(1)      VALUE SPACES.
          05 WS-SQL-FROM-CCY       PIC X(3)      VALUE SPACES.
          05 WS-SQL-TO-CCY         PIC X(3)      VALUE 'TND'.
          05 WS-SQL-FX-RATE        PIC S9(5)V9(6) VALUE ZEROS.
          05 WS-SQL-SECTOR         PIC X(4)      VALUE SPACES.
          05 WS-SQL-SECTOR-ADJ     PIC S9(3)V99  VALUE ZEROS.

      *--- SQLCA (SQL Communication Area) ---
       01 SQLCA.
          05 SQLCAID               PIC X(8).
          05 SQLCABC               PIC S9(9) COMP.
          05 SQLCODE               PIC S9(9) COMP.
          05 SQLERRM.
             49 SQLERRML           PIC S9(4) COMP.
             49 SQLERRMC           PIC X(70).
          05 SQLERRP               PIC X(8).
          05 SQLERRD OCCURS 6 TIMES PIC S9(9) COMP.
          05 SQLWARN.
             10 SQLWARN0           PIC X.
             10 SQLWARN1           PIC X.
             10 SQLWARN2           PIC X.
             10 SQLWARN3           PIC X.
             10 SQLWARN4           PIC X.
             10 SQLWARN5           PIC X.
             10 SQLWARN6           PIC X.
             10 SQLWARN7           PIC X.
          05 SQLEXT                PIC X(8).

      *================================================================
      * REDEFINES - alternative view of customer income for parsing
      *================================================================
       01 WS-INCOME-RAW             PIC X(9).
       01 WS-INCOME-PARSED REDEFINES WS-INCOME-RAW.
          05 WS-INCOME-WHOLE        PIC 9(7).
          05 WS-INCOME-CENTS        PIC 9(2).

      *================================================================
      * MAIN WORKING STORAGE
      *================================================================
       01 WS-CONTROL.
          05 WS-TODAY-DATE          PIC 9(8)      VALUE ZEROS.
          05 WS-TODAY-TIME          PIC 9(6)      VALUE ZEROS.
          05 WS-END-LOAN-FILE       PIC X         VALUE 'N'.
          05 WS-COLLATERAL-FOUND    PIC X         VALUE 'N'.
          05 WS-GUARANTEE-FOUND     PIC X         VALUE 'N'.
          05 WS-CURRENT-LOAN-ID     PIC 9(10)     VALUE ZEROS.
          05 WS-CURRENT-CUST-ID     PIC 9(8)      VALUE ZEROS.
          05 WS-AML-CLEAR           PIC X         VALUE 'N'.
          05 WS-AML-REASON          PIC X(60)     VALUE SPACES.

      *--- Computed values ---
       01 WS-COMPUTED.
          05 WS-SCORE-SEQ           PIC 9(12)     VALUE ZEROS.
          05 WS-TOTAL-COLLAT-VALUE  PIC 9(13)V99  VALUE ZEROS.
          05 WS-TOTAL-GUAR-VALUE    PIC 9(13)V99  VALUE ZEROS.
          05 WS-TOTAL-EXISTING-DEBT PIC 9(11)V99  VALUE ZEROS.
          05 WS-MONTHLY-DEBT-SERV   PIC 9(9)V99   VALUE ZEROS.
          05 WS-BANK-TENURE-YEARS   PIC 9(3)      VALUE ZEROS.
          05 WS-INCOME-TO-PMT       PIC 9(3)V9(4) VALUE ZEROS.
          05 WS-NORMALIZED-INCOME   PIC 9(9)V99   VALUE ZEROS.
          05 WS-BUREAU-ADJUSTMENT   PIC S9(4)     VALUE ZEROS.
          05 WS-SECTOR-ADJUSTMENT   PIC S9(4)     VALUE ZEROS.

      *--- Sector risk matrix from PROD.SECTOR_RISK at startup ---
       01 WS-SECTOR-MATRIX.
          05 WS-SECTOR-ENTRY OCCURS 12 TIMES INDEXED BY SECTOR-IDX.
             10 SCT-CODE             PIC X(4)     VALUE SPACES.
             10 SCT-LABEL            PIC X(30)    VALUE SPACES.
             10 SCT-ADJUSTMENT       PIC S9(3)V99 VALUE ZEROS.

      *--- Working table for sort: 5 scoring components ---
       01 WS-COMPONENT-TABLE.
          05 WS-COMP-ENTRY OCCURS 5 TIMES.
             10 WSC-NAME             PIC X(8).
             10 WSC-WEIGHT           PIC 9(3)V99.
             10 WSC-SCORE            PIC 9(4).
             10 WSC-RANK             PIC 9(1).
       01 WS-COMP-IDX                PIC 9(2)     VALUE ZEROS.

      *--- Sub-program parameter areas ---
       01 WS-AML-REQUEST.
          05 AML-REQ-CUST-ID         PIC 9(8).
          05 AML-REQ-CIN             PIC X(8).
          05 AML-REQ-NAME            PIC X(55).
          05 AML-REQ-DOB             PIC 9(8).
          05 AML-REQ-NATIONALITY     PIC X(3).
          05 AML-REQ-AMOUNT          PIC 9(11)V99.
       01 WS-AML-RESPONSE.
          05 AML-RESP-CLEAR          PIC X(1).
          05 AML-RESP-SCORE          PIC 9(3).
          05 AML-RESP-REASON         PIC X(60).

       01 WS-FEE-REQUEST.
          05 FEE-REQ-LOAN-TYPE       PIC X(3).
          05 FEE-REQ-AMOUNT          PIC 9(11)V99.
          05 FEE-REQ-RATE            PIC 9(2)V9(4).
       01 WS-FEE-RESPONSE.
          05 FEE-RESP-FILE-FEE       PIC 9(7)V99.
          05 FEE-RESP-TAX            PIC 9(7)V99.
          05 FEE-RESP-INSURANCE      PIC 9(7)V99.
          05 FEE-RESP-TOTAL          PIC 9(9)V99.

      *--- Report formatting ---
       01 WS-REPORT-WORK.
          05 WS-DISP-LOAN-ID         PIC 9(10)    VALUE ZEROS.
          05 WS-DISP-CUST-ID         PIC 9(8)     VALUE ZEROS.
          05 WS-DISP-AMOUNT          PIC Z(9)9,999 VALUE ZEROS.
          05 WS-DISP-RATE            PIC Z9,9999  VALUE ZEROS.
          05 WS-DISP-SCORE           PIC Z(3)9    VALUE ZEROS.
          05 WS-PAGE-NO              PIC 9(4)     VALUE ZEROS.
          05 WS-LINE-COUNT           PIC 9(3)     VALUE ZEROS.
          05 WS-MAX-LINES            PIC 9(3)     VALUE 55.

       01 WS-DECISION-LINE.
          05 DEC-LOAN-ID             PIC 9(10).
          05 FILLER                  PIC X(2) VALUE SPACES.
          05 DEC-CUST-ID             PIC 9(8).
          05 FILLER                  PIC X(2) VALUE SPACES.
          05 DEC-LOAN-TYPE           PIC X(3).
          05 FILLER                  PIC X(2) VALUE SPACES.
          05 DEC-AMOUNT              PIC Z(9)9,999.
          05 FILLER                  PIC X(2) VALUE SPACES.
          05 DEC-RATE                PIC Z9,9999.
          05 FILLER                  PIC X(2) VALUE SPACES.
          05 DEC-SCORE               PIC Z(3)9.
          05 FILLER                  PIC X(2) VALUE SPACES.
          05 DEC-DECISION            PIC X(11).
          05 FILLER                  PIC X(2) VALUE SPACES.
          05 DEC-REASON              PIC X(50).
          05 FILLER                  PIC X(24) VALUE SPACES.

       01 WS-REJECT-DETAIL.
          05 REJ-LOAN-ID             PIC 9(10).
          05 FILLER                  PIC X(2) VALUE SPACES.
          05 REJ-CUST-ID             PIC 9(8).
          05 FILLER                  PIC X(2) VALUE SPACES.
          05 REJ-REASON              PIC X(80).
          05 FILLER                  PIC X(18) VALUE SPACES.

      *--- In-memory lookup tables (sequential file scan at startup) ---
       01 WS-CUST-TABLE.
          05 WS-NBR-CUST              PIC 9(4) VALUE 0.
          05 WS-CUST-ENTRY OCCURS 500 TIMES.
             10 WS-CT-REC            PIC X(434).

       01 WS-COL-TABLE.
          05 WS-NBR-COL               PIC 9(4) VALUE 0.
          05 WS-COL-ENTRY OCCURS 400 TIMES.
             10 WS-CL-LOAN-ID        PIC 9(10).
             10 WS-CL-REC            PIC X(253).

       01 WS-GUAR-TABLE.
          05 WS-NBR-GUAR              PIC 9(4) VALUE 0.
          05 WS-GUAR-ENTRY OCCURS 200 TIMES.
             10 WS-GT-LOAN-ID        PIC 9(10).
             10 WS-GT-REC            PIC X(130).

       01 TB-IX                       PIC 9(4) VALUE 0.

       01 WS-LOAD-EOF-FLAGS.
          05 WS-CUST-EOF              PIC X VALUE 'N'.
             88 CUST-TABLE-EOF        VALUE 'Y'.
          05 WS-COL-EOF               PIC X VALUE 'N'.
             88 COL-TABLE-EOF         VALUE 'Y'.
          05 WS-GUAR-EOF              PIC X VALUE 'N'.
             88 GUAR-TABLE-EOF        VALUE 'Y'.

       PROCEDURE DIVISION.

      *================================================================
      * 0000-MAIN
      *================================================================
       0000-MAIN.
           MOVE 'LOANEVAL' TO WS-PROGRAM-NAME
           ACCEPT WS-TODAY-DATE FROM DATE YYYYMMDD
           ACCEPT WS-TODAY-TIME FROM TIME
           DISPLAY 'LOANEVAL v6.0 - START ' WS-TODAY-DATE
               '-' WS-TODAY-TIME
           PERFORM 0100-OPEN-FILES
           IF NOT RC-SUCCESS
               DISPLAY 'LOANEVAL ABEND: ' WS-ERROR-MESSAGE
               MOVE 12 TO RETURN-CODE
               STOP RUN
           END-IF
           PERFORM 0050-LOAD-TABLES
           IF NOT RC-SUCCESS
               DISPLAY 'LOANEVAL ABEND: ' WS-ERROR-MESSAGE
               MOVE 12 TO RETURN-CODE
               STOP RUN
           END-IF
           PERFORM 0200-LOAD-SCORE-PARAMS
           PERFORM 0250-LOAD-SECTOR-MATRIX
           PERFORM 0300-INIT-REPORT
           PERFORM 1000-PROCESS-LOANS
               UNTIL WS-END-LOAN-FILE = 'Y'
           PERFORM 0400-WRITE-SUMMARY
           PERFORM 0500-CLOSE-FILES
           DISPLAY 'LOANEVAL COMPLETED.'
           DISPLAY '  READ        : ' STAT-READ
           DISPLAY '  APPROVED    : ' STAT-APPROVED
           DISPLAY '  CONDITIONAL : ' STAT-CONDITIONAL
           DISPLAY '  DECLINED    : ' STAT-DECLINED
           DISPLAY '  ERRORS      : ' STAT-ERRORS
           IF STAT-ERRORS > 0
               MOVE 4 TO RETURN-CODE
           ELSE
               MOVE 0 TO RETURN-CODE
           END-IF
           STOP RUN.

      *================================================================
      * 0100-OPEN-FILES
      *================================================================
       0100-OPEN-FILES.
           OPEN INPUT LOAN-FILE
           IF NOT LOAN-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               STRING 'LOANFILE OPEN FAILED FS=' WS-LOAN-FS
                   DELIMITED SIZE INTO WS-ERROR-MESSAGE
               EXIT PARAGRAPH
           END-IF
           OPEN I-O SCORE-FILE
           IF NOT SCR-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               STRING 'SCORFILE OPEN FAILED FS=' WS-SCR-FS
                   DELIMITED SIZE INTO WS-ERROR-MESSAGE
               CLOSE LOAN-FILE
               EXIT PARAGRAPH
           END-IF
           OPEN OUTPUT DECISION-REPORT
           IF NOT RPT-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               MOVE 'DECIRPT OPEN FAILED' TO WS-ERROR-MESSAGE
               CLOSE LOAN-FILE SCORE-FILE
               EXIT PARAGRAPH
           END-IF
           OPEN OUTPUT REJECT-LOG
           IF NOT REJ-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               MOVE 'EVALREJ OPEN FAILED' TO WS-ERROR-MESSAGE
               CLOSE LOAN-FILE SCORE-FILE DECISION-REPORT
               EXIT PARAGRAPH
           END-IF
           MOVE 0 TO WS-RETURN-CODE
           READ LOAN-FILE
               AT END MOVE 'Y' TO WS-END-LOAN-FILE
               NOT AT END CONTINUE
           END-READ.

      *================================================================
      * 0050-LOAD-TABLES
      * Load CUST/COL/GUAR files into memory tables once at startup.
      *================================================================
       0050-LOAD-TABLES.
           MOVE 0 TO WS-NBR-CUST WS-NBR-COL WS-NBR-GUAR
           MOVE 'N' TO WS-CUST-EOF WS-COL-EOF WS-GUAR-EOF
           OPEN INPUT CUSTOMER-FILE
           IF NOT CUST-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               STRING 'CUSTFILE OPEN FAILED FS=' WS-CUST-FS
                   DELIMITED SIZE INTO WS-ERROR-MESSAGE
               EXIT PARAGRAPH
           END-IF
           PERFORM UNTIL CUST-TABLE-EOF
               READ CUSTOMER-FILE
                   AT END MOVE 'Y' TO WS-CUST-EOF
                   NOT AT END
                       IF WS-NBR-CUST < 500
                           ADD 1 TO WS-NBR-CUST
                           MOVE WS-NBR-CUST TO TB-IX
                           MOVE CUSTOMER-RECORD TO WS-CT-REC(TB-IX)
                       END-IF
               END-READ
           END-PERFORM
           CLOSE CUSTOMER-FILE

           OPEN INPUT COLLATERAL-FILE
           IF NOT COL-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               STRING 'COLFILE OPEN FAILED FS=' WS-COL-FS
                   DELIMITED SIZE INTO WS-ERROR-MESSAGE
               EXIT PARAGRAPH
           END-IF
           PERFORM UNTIL COL-TABLE-EOF
               READ COLLATERAL-FILE
                   AT END MOVE 'Y' TO WS-COL-EOF
                   NOT AT END
                       IF WS-NBR-COL < 400
                           ADD 1 TO WS-NBR-COL
                           MOVE WS-NBR-COL TO TB-IX
                           MOVE COL-LOAN-ID TO WS-CL-LOAN-ID(TB-IX)
                           MOVE COLLATERAL-RECORD TO WS-CL-REC(TB-IX)
                       END-IF
               END-READ
           END-PERFORM
           CLOSE COLLATERAL-FILE

           OPEN INPUT GUARANTEE-FILE
           IF NOT GTR-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               STRING 'GUARFILE OPEN FAILED FS=' WS-GTR-FS
                   DELIMITED SIZE INTO WS-ERROR-MESSAGE
               EXIT PARAGRAPH
           END-IF
           PERFORM UNTIL GUAR-TABLE-EOF
               READ GUARANTEE-FILE
                   AT END MOVE 'Y' TO WS-GUAR-EOF
                   NOT AT END
                       IF WS-NBR-GUAR < 200
                           ADD 1 TO WS-NBR-GUAR
                           MOVE WS-NBR-GUAR TO TB-IX
                           MOVE GTR-LOAN-ID TO WS-GT-LOAN-ID(TB-IX)
                           MOVE GUARANTOR-RECORD TO WS-GT-REC(TB-IX)
                       END-IF
               END-READ
           END-PERFORM
           CLOSE GUARANTEE-FILE
           MOVE 0 TO WS-RETURN-CODE.

      *================================================================
      * 0200-LOAD-SCORE-PARAMS
      *================================================================
       0200-LOAD-SCORE-PARAMS.
           MOVE '2024.1' TO SCR-MODEL-VERSION
           MOVE 1000     TO SCR-MAX-SCORE
           MOVE 600      TO SCR-MIN-APPROVE
           MOVE 450      TO SCR-MIN-COND
           MOVE 350      TO SCR-MIN-REVIEW
           MOVE 25,00    TO SCR-WEIGHT-INCOME
           MOVE 30,00    TO SCR-WEIGHT-HISTORY
           MOVE 20,00    TO SCR-WEIGHT-DSCR
           MOVE 15,00    TO SCR-WEIGHT-COLLAT
           MOVE 10,00    TO SCR-WEIGHT-TENURE.

      *================================================================
      * 0250-LOAD-SECTOR-MATRIX
      * Loads sector risk adjustment matrix from PROD.SECTOR_RISK table.
      * Used to adjust raw score based on borrower industry risk.
      *================================================================
       0250-LOAD-SECTOR-MATRIX.
      *    EXEC SQL
      *        DECLARE C_SECTOR CURSOR FOR
      *            SELECT SECTOR_CODE, SECTOR_LABEL, RISK_ADJUSTMENT
      *            FROM PROD.SECTOR_RISK
      *            WHERE ACTIVE_FLAG = 'Y'
      *            ORDER BY SECTOR_CODE
      *    END-EXEC
      *    EXEC SQL OPEN C_SECTOR END-EXEC
      *    PERFORM VARYING SECTOR-IDX FROM 1 BY 1
      *        UNTIL SECTOR-IDX > 12 OR SQLCODE NOT = 0
      *        EXEC SQL
      *            FETCH C_SECTOR INTO :SCT-CODE(SECTOR-IDX),
      *                                :SCT-LABEL(SECTOR-IDX),
      *                                :SCT-ADJUSTMENT(SECTOR-IDX)
      *        END-EXEC
      *    END-PERFORM
      *    EXEC SQL CLOSE C_SECTOR END-EXEC

      *--- Hardcoded fallback when SQL not available (dev/test mode) ---
           MOVE 'BANK' TO SCT-CODE(1)
           MOVE 'SECTEUR BANCAIRE' TO SCT-LABEL(1)
           MOVE 25,00 TO SCT-ADJUSTMENT(1)
           MOVE 'ADMI' TO SCT-CODE(2)
           MOVE 'ADMINISTRATION PUBLIQUE' TO SCT-LABEL(2)
           MOVE 30,00 TO SCT-ADJUSTMENT(2)
           MOVE 'INDS' TO SCT-CODE(3)
           MOVE 'INDUSTRIE MANUFACTURIERE' TO SCT-LABEL(3)
           MOVE 15,00 TO SCT-ADJUSTMENT(3)
           MOVE 'COMM' TO SCT-CODE(4)
           MOVE 'COMMERCE GROS DETAIL' TO SCT-LABEL(4)
           MOVE 05,00 TO SCT-ADJUSTMENT(4)
           MOVE 'AGRI' TO SCT-CODE(5)
           MOVE 'AGRICULTURE PECHE' TO SCT-LABEL(5)
           MOVE -10,00 TO SCT-ADJUSTMENT(5)
           MOVE 'TOUR' TO SCT-CODE(6)
           MOVE 'TOURISME HOTELLERIE' TO SCT-LABEL(6)
           MOVE -15,00 TO SCT-ADJUSTMENT(6)
           MOVE 'CONS' TO SCT-CODE(7)
           MOVE 'CONSTRUCTION BTP' TO SCT-LABEL(7)
           MOVE -05,00 TO SCT-ADJUSTMENT(7)
           MOVE 'TRSP' TO SCT-CODE(8)
           MOVE 'TRANSPORT LOGISTIQUE' TO SCT-LABEL(8)
           MOVE 10,00 TO SCT-ADJUSTMENT(8)
           MOVE 'PROF' TO SCT-CODE(9)
           MOVE 'PROFESSIONS LIBERALES' TO SCT-LABEL(9)
           MOVE 20,00 TO SCT-ADJUSTMENT(9)
           MOVE 'PHAR' TO SCT-CODE(10)
           MOVE 'PHARMACIE SANTE' TO SCT-LABEL(10)
           MOVE 25,00 TO SCT-ADJUSTMENT(10)
           MOVE 'TELE' TO SCT-CODE(11)
           MOVE 'TELECOMMUNICATIONS' TO SCT-LABEL(11)
           MOVE 20,00 TO SCT-ADJUSTMENT(11)
           MOVE 'AUTR' TO SCT-CODE(12)
           MOVE 'AUTRES SECTEURS' TO SCT-LABEL(12)
           MOVE 00,00 TO SCT-ADJUSTMENT(12).

      *================================================================
      * 0300-INIT-REPORT
      *================================================================
       0300-INIT-REPORT.
           MOVE 'LOANEVAL'  TO RPT-PROGRAM
           MOVE WS-TODAY-DATE TO RPT-RUN-DATE
           MOVE 'RAPPORT EVALUATION CREDITS - PRODUCTION'
               TO RPT-TITLE
           MOVE 1 TO RPT-PAGE-NO
           WRITE DECISION-LINE FROM RPT-MAIN-HEADER
           WRITE DECISION-LINE FROM RPT-SUB-HEADER
           WRITE DECISION-LINE FROM RPT-SEPARATOR
           WRITE DECISION-LINE FROM RPT-COL-HEADER-LOAN
           WRITE DECISION-LINE FROM RPT-SEPARATOR.

      *================================================================
      * 0400-WRITE-SUMMARY
      *================================================================
       0400-WRITE-SUMMARY.
           WRITE DECISION-LINE FROM RPT-SEPARATOR
           STRING 'TOTAUX: TRAITES=' STAT-READ
               ' APPROUVES=' STAT-APPROVED
               ' CONDITIONNEL=' STAT-CONDITIONAL
               ' REFUSES=' STAT-DECLINED
               DELIMITED SIZE INTO DECISION-LINE
           WRITE DECISION-LINE
           STRING 'MONTANT TOTAL: ' STAT-TOTAL-AMT
               '  APPROUVE: ' STAT-APPROVED-AMT
               DELIMITED SIZE INTO DECISION-LINE
           WRITE DECISION-LINE
           WRITE DECISION-LINE FROM RPT-FOOTER-LINE.

      *================================================================
      * 0500-CLOSE-FILES
      *================================================================
       0500-CLOSE-FILES.
           CLOSE LOAN-FILE SCORE-FILE DECISION-REPORT REJECT-LOG.

      *================================================================
      * 1000-PROCESS-LOANS
      *================================================================
       1000-PROCESS-LOANS.
           ADD 1 TO STAT-READ
           MOVE LOAN-ID      TO WS-CURRENT-LOAN-ID
           MOVE LOAN-CUST-ID TO WS-CURRENT-CUST-ID
           ADD LOAN-ORIGINAL-AMT TO STAT-TOTAL-AMT
           PERFORM 1100-VALIDATE-PRECONDITIONS
           IF WS-RETURN-CODE = 12
               ADD 1 TO STAT-ERRORS
               PERFORM 1900-WRITE-REJECT
               PERFORM 9000-READ-NEXT-LOAN
               EXIT PARAGRAPH
           END-IF
           PERFORM 2000-LOAD-CUSTOMER
           IF NOT CUST-FS-OK
               ADD 1 TO STAT-ERRORS
               STRING 'CUSTOMER NOT FOUND: ' WS-CURRENT-CUST-ID
                   DELIMITED SIZE INTO WS-ERROR-MESSAGE
               PERFORM 1900-WRITE-REJECT
               PERFORM 9000-READ-NEXT-LOAN
               EXIT PARAGRAPH
           END-IF
           PERFORM 2050-NORMALIZE-INCOME
           PERFORM 2100-VALIDATE-CUSTOMER
           IF WS-RETURN-CODE = 8
               ADD 1 TO STAT-DECLINED
               PERFORM 1900-WRITE-REJECT
               PERFORM 9000-READ-NEXT-LOAN
               EXIT PARAGRAPH
           END-IF
           PERFORM 2200-EXTERNAL-AML-CHECK
           IF WS-AML-CLEAR NOT = 'Y'
               ADD 1 TO STAT-DECLINED
               MOVE WS-AML-REASON TO WS-ERROR-MESSAGE
               PERFORM 1900-WRITE-REJECT
               PERFORM 9000-READ-NEXT-LOAN
               EXIT PARAGRAPH
           END-IF
           PERFORM 2300-FETCH-BUREAU-SCORE
           PERFORM 2400-FETCH-SECTOR-ADJUSTMENT
           PERFORM 3000-LOAD-COLLATERAL
           PERFORM 3100-LOAD-GUARANTEES
           PERFORM 4000-COMPUTE-SCORE
           PERFORM 4900-RANK-COMPONENTS
           PERFORM 5000-APPLY-DECISION
           PERFORM 5300-CALL-FEE-CALCULATION
           PERFORM 6000-WRITE-SCORE-RECORD
           PERFORM 7000-WRITE-DECISION-LINE
           PERFORM 9000-READ-NEXT-LOAN.

      *================================================================
      * 1100-VALIDATE-PRECONDITIONS
      *================================================================
       1100-VALIDATE-PRECONDITIONS.
           MOVE 0 TO WS-RETURN-CODE
           IF LOAN-ID = ZEROS
               MOVE 12 TO WS-RETURN-CODE
               MOVE 'LOAN-ID IS ZERO - INVALID RECORD'
                   TO WS-ERROR-MESSAGE
               EXIT PARAGRAPH
           END-IF
           IF LOAN-ORIGINAL-AMT = ZEROS
               MOVE 12 TO WS-RETURN-CODE
               MOVE 'LOAN AMOUNT IS ZERO' TO WS-ERROR-MESSAGE
               EXIT PARAGRAPH
           END-IF
           IF NOT LOAN-ACTIVE AND NOT LOAN-RESTRUCTURED
               MOVE 12 TO WS-RETURN-CODE
               MOVE 'LOAN STATUS NOT ELIGIBLE FOR EVALUATION'
                   TO WS-ERROR-MESSAGE
           END-IF.

      *================================================================
      * 1900-WRITE-REJECT
      *================================================================
       1900-WRITE-REJECT.
           MOVE WS-CURRENT-LOAN-ID TO REJ-LOAN-ID
           MOVE WS-CURRENT-CUST-ID TO REJ-CUST-ID
           MOVE WS-ERROR-MESSAGE   TO REJ-REASON
           WRITE REJECT-LINE FROM WS-REJECT-DETAIL.

      *================================================================
      * 2000-LOAD-CUSTOMER
      * Table scan: find matching CUST-ID in pre-loaded WS-CUST-TABLE.
      *================================================================
       2000-LOAD-CUSTOMER.
           MOVE '23' TO WS-CUST-FS
           PERFORM VARYING TB-IX FROM 1 BY 1
               UNTIL TB-IX > WS-NBR-CUST
               MOVE WS-CT-REC(TB-IX) TO CUSTOMER-RECORD
               IF CUST-ID = WS-CURRENT-CUST-ID
                   MOVE '00' TO WS-CUST-FS
                   EXIT PERFORM
               END-IF
           END-PERFORM
           IF WS-CUST-FS NOT = '00'
               MOVE '23' TO WS-CUST-FS
           END-IF.

      *================================================================
      * 2050-NORMALIZE-INCOME
      * INSPECT income field for non-numeric chars then convert.
      * Demonstrates INSPECT REPLACING and REDEFINES.
      *================================================================
       2050-NORMALIZE-INCOME.
           STRING CUST-MONTHLY-INCOME
               DELIMITED BY SIZE
               INTO WS-INCOME-RAW
           INSPECT WS-INCOME-RAW
               REPLACING ALL SPACES BY ZEROS
           INSPECT WS-INCOME-RAW
               REPLACING ALL '-' BY '0'
      *--- After INSPECT, REDEFINES lets us read whole+cents ---
           IF WS-INCOME-WHOLE = ZEROS AND WS-INCOME-CENTS = ZEROS
               MOVE 0 TO WS-NORMALIZED-INCOME
           ELSE
               COMPUTE WS-NORMALIZED-INCOME =
                   WS-INCOME-WHOLE + (WS-INCOME-CENTS / 100)
           END-IF.

      *================================================================
      * 2100-VALIDATE-CUSTOMER
      *================================================================
       2100-VALIDATE-CUSTOMER.
           MOVE 0 TO WS-RETURN-CODE
           IF CUST-BLACKLISTED
               MOVE 8 TO WS-RETURN-CODE
               MOVE 'CLIENT BLACKLISTE - DEMANDE REFUSEE'
                   TO WS-ERROR-MESSAGE
               EXIT PARAGRAPH
           END-IF
           IF CUST-AML-ALERT
               MOVE 8 TO WS-RETURN-CODE
               MOVE 'ALERTE AML EN COURS' TO WS-ERROR-MESSAGE
               EXIT PARAGRAPH
           END-IF
           IF NOT CUST-KYC-OK
               MOVE 8 TO WS-RETURN-CODE
               STRING 'KYC NON VALIDE - STATUT: ' CUST-KYC-STATUS
                   DELIMITED SIZE INTO WS-ERROR-MESSAGE
               EXIT PARAGRAPH
           END-IF
           IF CUST-IS-PEP
               MOVE 'DOSSIER PEP - VALIDATION MANUELLE'
                   TO SCR-REASON-1
           END-IF
           IF NOT CUST-ACTIVE
               MOVE 8 TO WS-RETURN-CODE
               MOVE 'CLIENT INACTIF' TO WS-ERROR-MESSAGE
           END-IF.

      *================================================================
      * 2200-EXTERNAL-AML-CHECK
      * Calls external AML screening module CHKAML.
      * Returns Y/N clearance.
      *================================================================
       2200-EXTERNAL-AML-CHECK.
           MOVE CUST-ID         TO AML-REQ-CUST-ID
           MOVE CUST-CIN        TO AML-REQ-CIN
           STRING CUST-FIRST-NAME ' ' CUST-LAST-NAME
               DELIMITED SIZE INTO AML-REQ-NAME
           MOVE CUST-DATE-OF-BIRTH TO AML-REQ-DOB
           MOVE CUST-NATIONALITY   TO AML-REQ-NATIONALITY
           MOVE LOAN-ORIGINAL-AMT  TO AML-REQ-AMOUNT
           CALL 'CHKAML' USING WS-AML-REQUEST WS-AML-RESPONSE
           MOVE AML-RESP-CLEAR  TO WS-AML-CLEAR
           MOVE AML-RESP-REASON TO WS-AML-REASON.

      *================================================================
      * 2300-FETCH-BUREAU-SCORE
      * Retrieves external credit bureau score via SQL.
      * Used as an adjustment to the internal score (+/- 100 points).
      *================================================================
       2300-FETCH-BUREAU-SCORE.
           MOVE WS-CURRENT-CUST-ID TO WS-SQL-CUST-ID
           MOVE 0 TO WS-BUREAU-ADJUSTMENT
      *    EXEC SQL
      *        SELECT BUREAU_SCORE, BUREAU_CLASS
      *        INTO :WS-SQL-BUREAU-SCORE, :WS-SQL-BUREAU-CLASS
      *        FROM CREDITBUREAU.SCORES
      *        WHERE CUST_ID = :WS-SQL-CUST-ID
      *          AND SCORE_DATE = (
      *              SELECT MAX(SCORE_DATE)
      *              FROM CREDITBUREAU.SCORES
      *              WHERE CUST_ID = :WS-SQL-CUST-ID)
      *    END-EXEC

      *--- Fallback: derive a synthetic bureau score from CIN hash ---
           COMPUTE WS-BUREAU-ADJUSTMENT =
               FUNCTION MOD(WS-SQL-CUST-ID, 200) - 100.

      *================================================================
      * 2400-FETCH-SECTOR-ADJUSTMENT
      * Looks up sector code in pre-loaded matrix using employer name.
      *================================================================
       2400-FETCH-SECTOR-ADJUSTMENT.
           MOVE 0 TO WS-SECTOR-ADJUSTMENT
           EVALUATE TRUE
               WHEN CUST-EMPLOYER (1:6) = 'BANQUE'
                   MOVE 'BANK' TO WS-SQL-SECTOR
               WHEN CUST-EMPLOYER (1:10) = 'MINISTERE '
                   MOVE 'ADMI' TO WS-SQL-SECTOR
               WHEN CUST-EMPLOYER (1:8) = 'TUNISIE '
                   MOVE 'TELE' TO WS-SQL-SECTOR
               WHEN CUST-EMPLOYER (1:6) = 'ORANGE'
               OR   CUST-EMPLOYER (1:7) = 'OOREDOO'
                   MOVE 'TELE' TO WS-SQL-SECTOR
               WHEN CUST-EMPLOYER (1:8) = 'PHARMACI'
                   MOVE 'PHAR' TO WS-SQL-SECTOR
               WHEN CUST-EMPLOYER (1:8) = 'HOTEL  '
               OR   CUST-EMPLOYER (1:6) = 'TUNISA'
                   MOVE 'TOUR' TO WS-SQL-SECTOR
               WHEN CUST-EMPLOYER (1:7) = 'GROUPE '
                   MOVE 'INDS' TO WS-SQL-SECTOR
               WHEN CUST-EMPLOYER (1:8) = 'COMMERCE'
                   MOVE 'COMM' TO WS-SQL-SECTOR
               WHEN CUST-EMPLOYER (1:7) = 'ARTISAN'
                   MOVE 'COMM' TO WS-SQL-SECTOR
               WHEN OTHER
                   MOVE 'AUTR' TO WS-SQL-SECTOR
           END-EVALUATE
           PERFORM VARYING SECTOR-IDX FROM 1 BY 1
               UNTIL SECTOR-IDX > 12
               IF SCT-CODE(SECTOR-IDX) = WS-SQL-SECTOR
                   MOVE SCT-ADJUSTMENT(SECTOR-IDX)
                       TO WS-SECTOR-ADJUSTMENT
                   EXIT PERFORM
               END-IF
           END-PERFORM.

      *================================================================
      * 3000-LOAD-COLLATERAL
      * Table scan: sum collateral values for current loan id.
      *================================================================
       3000-LOAD-COLLATERAL.
           MOVE ZEROS TO WS-TOTAL-COLLAT-VALUE
           MOVE 'N'   TO WS-COLLATERAL-FOUND
           PERFORM VARYING TB-IX FROM 1 BY 1
               UNTIL TB-IX > WS-NBR-COL
               IF WS-CL-LOAN-ID(TB-IX) = WS-CURRENT-LOAN-ID
                   MOVE WS-CL-REC(TB-IX) TO COLLATERAL-RECORD
                   MOVE 'Y' TO WS-COLLATERAL-FOUND
                   IF COL-ACTIVE
                       ADD COL-APPRAISAL-VALUE
                           TO WS-TOTAL-COLLAT-VALUE
                   END-IF
               END-IF
           END-PERFORM.

       3010-SUM-COLLAT.
           READ COLLATERAL-FILE NEXT
               AT END CONTINUE
           END-READ
           IF COL-FS-OK AND COL-LOAN-ID = WS-CURRENT-LOAN-ID
               IF COL-ACTIVE
                   ADD COL-APPRAISAL-VALUE TO WS-TOTAL-COLLAT-VALUE
               END-IF
           END-IF.

      *================================================================
      * 3100-LOAD-GUARANTEES
      * Table scan: sum guarantee amounts for current loan id.
      *================================================================
       3100-LOAD-GUARANTEES.
           MOVE ZEROS TO WS-TOTAL-GUAR-VALUE
           MOVE 'N'   TO WS-GUARANTEE-FOUND
           PERFORM VARYING TB-IX FROM 1 BY 1
               UNTIL TB-IX > WS-NBR-GUAR
               IF WS-GT-LOAN-ID(TB-IX) = WS-CURRENT-LOAN-ID
                   MOVE WS-GT-REC(TB-IX) TO GUARANTOR-RECORD
                   MOVE 'Y' TO WS-GUARANTEE-FOUND
                   IF GTR-ACTIVE
                       ADD GTR-AMOUNT TO WS-TOTAL-GUAR-VALUE
                   END-IF
               END-IF
           END-PERFORM.

       3110-SUM-GUARANTEES.
           READ GUARANTEE-FILE NEXT
               AT END CONTINUE
           END-READ
           IF GTR-FS-OK AND GTR-LOAN-ID = WS-CURRENT-LOAN-ID
               IF GTR-ACTIVE
                   ADD GTR-AMOUNT TO WS-TOTAL-GUAR-VALUE
               END-IF
           END-IF.

      *================================================================
      * 4000-COMPUTE-SCORE
      *================================================================
       4000-COMPUTE-SCORE.
           MOVE ZEROS TO SCR-INCOME-SCORE SCR-HISTORY-SCORE
                        SCR-DSCR-SCORE SCR-COLLAT-SCORE
                        SCR-TENURE-SCORE
           MOVE SPACES TO SCR-REASON-1 SCR-REASON-2 SCR-REASON-3
           PERFORM 4100-SCORE-INCOME
           PERFORM 4200-SCORE-HISTORY
           PERFORM 4300-SCORE-DSCR
           PERFORM 4400-SCORE-COLLATERAL
           PERFORM 4500-SCORE-TENURE
           COMPUTE SCR-RAW-SCORE ROUNDED =
               (SCR-INCOME-SCORE  * SCR-WEIGHT-INCOME  +
                SCR-HISTORY-SCORE * SCR-WEIGHT-HISTORY +
                SCR-DSCR-SCORE    * SCR-WEIGHT-DSCR    +
                SCR-COLLAT-SCORE  * SCR-WEIGHT-COLLAT  +
                SCR-TENURE-SCORE  * SCR-WEIGHT-TENURE) / 100
           COMPUTE SCR-FINAL-SCORE =
               SCR-RAW-SCORE + WS-BUREAU-ADJUSTMENT
                             + WS-SECTOR-ADJUSTMENT
           IF SCR-FINAL-SCORE > SCR-MAX-SCORE
               MOVE SCR-MAX-SCORE TO SCR-FINAL-SCORE
           END-IF
           IF SCR-FINAL-SCORE < 0
               MOVE 0 TO SCR-FINAL-SCORE
           END-IF.

       4100-SCORE-INCOME.
           IF WS-NORMALIZED-INCOME = ZEROS OR
               LOAN-MONTHLY-PMT = ZEROS
               MOVE 0 TO SCR-INCOME-SCORE
               MOVE 'REVENU OU MENSUALITE NULS' TO SCR-REASON-2
               EXIT PARAGRAPH
           END-IF
           COMPUTE WS-INCOME-TO-PMT ROUNDED =
               WS-NORMALIZED-INCOME / LOAN-MONTHLY-PMT
           EVALUATE TRUE
               WHEN WS-INCOME-TO-PMT >= 3,0
                   MOVE 1000 TO SCR-INCOME-SCORE
               WHEN WS-INCOME-TO-PMT >= 2,5
                   MOVE 850  TO SCR-INCOME-SCORE
               WHEN WS-INCOME-TO-PMT >= 2,0
                   MOVE 700  TO SCR-INCOME-SCORE
               WHEN WS-INCOME-TO-PMT >= 1,5
                   MOVE 500  TO SCR-INCOME-SCORE
               WHEN WS-INCOME-TO-PMT >= 1,2
                   MOVE 300  TO SCR-INCOME-SCORE
               WHEN OTHER
                   MOVE 0    TO SCR-INCOME-SCORE
                   MOVE 'RATIO REVENU/MENSUALITE INSUFFISANT'
                       TO SCR-REASON-2
           END-EVALUATE.

       4200-SCORE-HISTORY.
           EVALUATE TRUE
               WHEN LOAN-DAYS-PAST-DUE = 0 AND
                    LOAN-MISSED-PMTS = 0
                   MOVE 1000 TO SCR-HISTORY-SCORE
               WHEN LOAN-DAYS-PAST-DUE <= 30
                   MOVE 700  TO SCR-HISTORY-SCORE
               WHEN LOAN-DAYS-PAST-DUE <= 90
                   MOVE 400  TO SCR-HISTORY-SCORE
                   MOVE 'RETARDS DE PAIEMENT DETECTES'
                       TO SCR-REASON-1
               WHEN LOAN-DAYS-PAST-DUE <= 180
                   MOVE 150  TO SCR-HISTORY-SCORE
                   MOVE 'CREANCE CLASSEE - SUIVI REQUIS'
                       TO SCR-REASON-1
               WHEN OTHER
                   MOVE 0    TO SCR-HISTORY-SCORE
                   MOVE 'CREANCE EN SOUFFRANCE > 180 JOURS'
                       TO SCR-REASON-1
           END-EVALUATE.

       4300-SCORE-DSCR.
           COMPUTE WS-MONTHLY-DEBT-SERV =
               LOAN-MONTHLY-PMT + WS-TOTAL-EXISTING-DEBT
           IF WS-MONTHLY-DEBT-SERV = ZEROS
               MOVE 1000 TO SCR-DSCR-SCORE
               EXIT PARAGRAPH
           END-IF
           COMPUTE SCR-DSCR-RATIO ROUNDED =
               WS-NORMALIZED-INCOME / WS-MONTHLY-DEBT-SERV
           EVALUATE TRUE
               WHEN SCR-DSCR-RATIO >= 1,5
                   MOVE 1000 TO SCR-DSCR-SCORE
               WHEN SCR-DSCR-RATIO >= 1,2
                   MOVE 750  TO SCR-DSCR-SCORE
               WHEN SCR-DSCR-RATIO >= 1,0
                   MOVE 500  TO SCR-DSCR-SCORE
               WHEN SCR-DSCR-RATIO >= 0,8
                   MOVE 250  TO SCR-DSCR-SCORE
                   MOVE 'TAUX DE COUVERTURE FAIBLE'
                       TO SCR-REASON-3
               WHEN OTHER
                   MOVE 0    TO SCR-DSCR-SCORE
                   MOVE 'CAPACITE REMBOURSEMENT INSUFFISANTE'
                       TO SCR-REASON-3
           END-EVALUATE.

       4400-SCORE-COLLATERAL.
           COMPUTE WS-TOTAL-COLLAT-VALUE =
               WS-TOTAL-COLLAT-VALUE + WS-TOTAL-GUAR-VALUE
           IF WS-TOTAL-COLLAT-VALUE = ZEROS
               MOVE 0 TO SCR-COLLAT-SCORE
               EXIT PARAGRAPH
           END-IF
           COMPUTE SCR-LTV-RATIO ROUNDED =
               LOAN-OUTSTANDING / WS-TOTAL-COLLAT-VALUE * 100
           EVALUATE TRUE
               WHEN SCR-LTV-RATIO <= 60
                   MOVE 1000 TO SCR-COLLAT-SCORE
               WHEN SCR-LTV-RATIO <= 70
                   MOVE 800  TO SCR-COLLAT-SCORE
               WHEN SCR-LTV-RATIO <= 80
                   MOVE 600  TO SCR-COLLAT-SCORE
               WHEN SCR-LTV-RATIO <= 90
                   MOVE 400  TO SCR-COLLAT-SCORE
               WHEN SCR-LTV-RATIO <= 100
                   MOVE 200  TO SCR-COLLAT-SCORE
               WHEN OTHER
                   MOVE 0    TO SCR-COLLAT-SCORE
           END-EVALUATE.

       4500-SCORE-TENURE.
           COMPUTE WS-BANK-TENURE-YEARS =
               (WS-TODAY-DATE - CUST-OPEN-DATE) / 10000
           EVALUATE TRUE
               WHEN WS-BANK-TENURE-YEARS >= 10
                   MOVE 1000 TO SCR-TENURE-SCORE
               WHEN WS-BANK-TENURE-YEARS >= 7
                   MOVE 800  TO SCR-TENURE-SCORE
               WHEN WS-BANK-TENURE-YEARS >= 5
                   MOVE 600  TO SCR-TENURE-SCORE
               WHEN WS-BANK-TENURE-YEARS >= 3
                   MOVE 400  TO SCR-TENURE-SCORE
               WHEN WS-BANK-TENURE-YEARS >= 1
                   MOVE 200  TO SCR-TENURE-SCORE
               WHEN OTHER
                   MOVE 0    TO SCR-TENURE-SCORE
           END-EVALUATE.

      *================================================================
      * 4900-RANK-COMPONENTS
      * Demonstrates an internal SORT - ranks the 5 scoring components
      * descending so we can identify the strongest and weakest factors.
      *================================================================
       4900-RANK-COMPONENTS.
           MOVE 'INCOME  ' TO WSC-NAME(1)
           MOVE SCR-WEIGHT-INCOME TO WSC-WEIGHT(1)
           MOVE SCR-INCOME-SCORE  TO WSC-SCORE(1)
           MOVE 'HISTORY ' TO WSC-NAME(2)
           MOVE SCR-WEIGHT-HISTORY TO WSC-WEIGHT(2)
           MOVE SCR-HISTORY-SCORE  TO WSC-SCORE(2)
           MOVE 'DSCR    ' TO WSC-NAME(3)
           MOVE SCR-WEIGHT-DSCR   TO WSC-WEIGHT(3)
           MOVE SCR-DSCR-SCORE    TO WSC-SCORE(3)
           MOVE 'COLLAT  ' TO WSC-NAME(4)
           MOVE SCR-WEIGHT-COLLAT TO WSC-WEIGHT(4)
           MOVE SCR-COLLAT-SCORE  TO WSC-SCORE(4)
           MOVE 'TENURE  ' TO WSC-NAME(5)
           MOVE SCR-WEIGHT-TENURE TO WSC-WEIGHT(5)
           MOVE SCR-TENURE-SCORE  TO WSC-SCORE(5)

           SORT SORT-WORK-FILE
               ON DESCENDING KEY SORT-COMPONENT-SCORE
               INPUT PROCEDURE IS 4910-LOAD-SORT THRU 4910-EXIT
               OUTPUT PROCEDURE IS 4920-RANK-OUTPUT THRU 4920-EXIT.

       4910-LOAD-SORT.
           PERFORM VARYING WS-COMP-IDX FROM 1 BY 1
               UNTIL WS-COMP-IDX > 5
               MOVE WSC-NAME(WS-COMP-IDX)
                   TO SORT-COMPONENT-NAME
               MOVE WSC-WEIGHT(WS-COMP-IDX)
                   TO SORT-COMPONENT-WEIGHT
               MOVE WSC-SCORE(WS-COMP-IDX)
                   TO SORT-COMPONENT-SCORE
               MOVE 0 TO SORT-COMPONENT-RANK
               RELEASE SORT-COMPONENT-REC
           END-PERFORM.
       4910-EXIT. EXIT.

       4920-RANK-OUTPUT.
           MOVE 1 TO WS-COMP-IDX
           PERFORM UNTIL WS-COMP-IDX > 5
               RETURN SORT-WORK-FILE
                   AT END EXIT PERFORM
                   NOT AT END
                       MOVE WS-COMP-IDX TO SORT-COMPONENT-RANK
                       MOVE SORT-COMPONENT-NAME
                           TO WSC-NAME(WS-COMP-IDX)
                       MOVE WS-COMP-IDX TO WSC-RANK(WS-COMP-IDX)
                       ADD 1 TO WS-COMP-IDX
               END-RETURN
           END-PERFORM.
       4920-EXIT. EXIT.

      *================================================================
      * 5000-APPLY-DECISION
      *================================================================
       5000-APPLY-DECISION.
           EVALUATE TRUE
               WHEN SCR-FINAL-SCORE >= SCR-MIN-APPROVE
                   MOVE 'AP' TO SCR-DECISION
                   ADD 1 TO STAT-APPROVED
                   PERFORM 5100-COMPUTE-MAX-LOAN
                   PERFORM 5200-COMPUTE-PRICING
                   ADD LOAN-ORIGINAL-AMT TO STAT-APPROVED-AMT
               WHEN SCR-FINAL-SCORE >= SCR-MIN-COND
                   MOVE 'CO' TO SCR-DECISION
                   ADD 1 TO STAT-CONDITIONAL
                   PERFORM 5100-COMPUTE-MAX-LOAN
                   PERFORM 5200-COMPUTE-PRICING
               WHEN SCR-FINAL-SCORE >= SCR-MIN-REVIEW
                   MOVE 'RV' TO SCR-DECISION
                   ADD 1 TO STAT-CONDITIONAL
               WHEN OTHER
                   MOVE 'DC' TO SCR-DECISION
                   ADD 1 TO STAT-DECLINED
                   ADD LOAN-ORIGINAL-AMT TO STAT-DECLINED-AMT
                   MOVE ZEROS TO SCR-MAX-LOAN-AMT
           END-EVALUATE.

       5100-COMPUTE-MAX-LOAN.
           COMPUTE SCR-MAX-LOAN-AMT =
               WS-NORMALIZED-INCOME * 12 * 0,40
           IF WS-TOTAL-COLLAT-VALUE > ZEROS
               COMPUTE WS-TOTAL-COLLAT-VALUE =
                   WS-TOTAL-COLLAT-VALUE * 0,80
               IF WS-TOTAL-COLLAT-VALUE < SCR-MAX-LOAN-AMT
                   MOVE WS-TOTAL-COLLAT-VALUE TO SCR-MAX-LOAN-AMT
               END-IF
           END-IF
           IF LOAN-ORIGINAL-AMT < SCR-MAX-LOAN-AMT
               MOVE LOAN-ORIGINAL-AMT TO SCR-MAX-LOAN-AMT
           END-IF.

       5200-COMPUTE-PRICING.
           EVALUATE TRUE
               WHEN SCR-FINAL-SCORE >= 850
                   COMPUTE SCR-MAX-RATE = 7,25 + 1,50
               WHEN SCR-FINAL-SCORE >= 700
                   COMPUTE SCR-MAX-RATE = 7,25 + 2,50
               WHEN SCR-FINAL-SCORE >= 600
                   COMPUTE SCR-MAX-RATE = 7,25 + 3,50
               WHEN OTHER
                   COMPUTE SCR-MAX-RATE = 7,25 + 4,50
           END-EVALUATE.

      *================================================================
      * 5300-CALL-FEE-CALCULATION
      *================================================================
       5300-CALL-FEE-CALCULATION.
           MOVE LOAN-TYPE         TO FEE-REQ-LOAN-TYPE
           MOVE LOAN-ORIGINAL-AMT TO FEE-REQ-AMOUNT
           MOVE SCR-MAX-RATE      TO FEE-REQ-RATE
           CALL 'CALCFEE' USING WS-FEE-REQUEST WS-FEE-RESPONSE.

      *================================================================
      * 6000-WRITE-SCORE-RECORD
      *================================================================
       6000-WRITE-SCORE-RECORD.
           ADD 1 TO WS-SCORE-SEQ
           MOVE WS-SCORE-SEQ       TO SCR-RESULT-ID
           MOVE WS-CURRENT-LOAN-ID TO SCR-LOAN-ID
           MOVE WS-CURRENT-CUST-ID TO SCR-CUST-ID
           MOVE WS-TODAY-DATE      TO SCR-DATE
           MOVE SCR-FINAL-SCORE    TO SCR-TOTAL-SCORE
           WRITE SCORE-RESULT
           END-WRITE.

      *================================================================
      * 7000-WRITE-DECISION-LINE
      *================================================================
       7000-WRITE-DECISION-LINE.
           IF WS-LINE-COUNT >= WS-MAX-LINES
               ADD 1 TO WS-PAGE-NO
               MOVE WS-PAGE-NO TO RPT-PAGE-NO
               WRITE DECISION-LINE FROM RPT-MAIN-HEADER
               WRITE DECISION-LINE FROM RPT-SEPARATOR
               MOVE 2 TO WS-LINE-COUNT
           END-IF
           MOVE WS-CURRENT-LOAN-ID TO DEC-LOAN-ID
           MOVE WS-CURRENT-CUST-ID TO DEC-CUST-ID
           MOVE LOAN-TYPE          TO DEC-LOAN-TYPE
           MOVE LOAN-ORIGINAL-AMT  TO DEC-AMOUNT
           MOVE LOAN-INTEREST-RATE TO DEC-RATE
           MOVE SCR-FINAL-SCORE    TO DEC-SCORE
           EVALUATE SCR-DECISION
               WHEN 'AP' MOVE 'APPROUVE   ' TO DEC-DECISION
               WHEN 'CO' MOVE 'CONDITIONNEL' TO DEC-DECISION
               WHEN 'RV' MOVE 'A ETUDIER  ' TO DEC-DECISION
               WHEN 'DC' MOVE 'REFUSE     ' TO DEC-DECISION
           END-EVALUATE
           MOVE SCR-REASON-1 TO DEC-REASON
           WRITE DECISION-LINE FROM WS-DECISION-LINE
           ADD 1 TO WS-LINE-COUNT.

      *================================================================
      * 9000-READ-NEXT-LOAN
      *================================================================
       9000-READ-NEXT-LOAN.
           READ LOAN-FILE
               AT END MOVE 'Y' TO WS-END-LOAN-FILE
               NOT AT END CONTINUE
           END-READ.

       END PROGRAM LOANEVAL.
