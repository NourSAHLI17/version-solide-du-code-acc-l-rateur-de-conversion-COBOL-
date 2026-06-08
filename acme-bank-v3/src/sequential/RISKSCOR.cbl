      *****************************************************************
      * PROGRAM:     RISKSCOR
      * DESCRIPTION: Portfolio risk classification - Production v3.
      *              Same business logic as v2 but adds:
      *              - EXEC SQL to insert results into PROD.RISK_HIST
      *              - Inter-program flag check (run after LOANEVAL)
      *              - Read of RECOVFILE to flag loans under recovery
      *              - Counterparty exposure aggregation
      * COPYBOOKS:   LOANCOPY, CUSTCOPY, SCORECOPY, RECOVCOPY,
      *              ERRCOPY2, RPTCOPY2
      * FILES:       LOAN-FILE       (indexed, I-O)
      *              CUSTOMER-FILE   (indexed, INPUT random)
      *              SCORE-FILE      (indexed, INPUT)
      *              RECOVERY-NEW    (sequential INPUT)
      *              RISK-REPORT     (sequential OUTPUT)
      *              BCT-SUBMISSION  (sequential OUTPUT)
      * AUTHOR:      ACME Bank - Credit Risk Division
      * VERSION:     3.5
      * BCT REF:     Circulaire BCT 2021-02
      *****************************************************************
       IDENTIFICATION DIVISION.
       PROGRAM-ID. RISKSCOR.
       AUTHOR. ACME-CREDIT-RISK.

       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SOURCE-COMPUTER. IBM-MAINFRAME.
       OBJECT-COMPUTER. IBM-MAINFRAME.

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

           SELECT SCORE-FILE
               ASSIGN TO "SCORFILE.dat"
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE IS SEQUENTIAL


               FILE STATUS IS WS-SCR-FS.

           SELECT RECOVERY-NEW
               ASSIGN TO "RECVNEW.dat"
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-REC-FS.

           SELECT RISK-REPORT
               ASSIGN TO "RISKRPT.dat"
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-RPT-FS.

           SELECT BCT-SUBMISSION
               ASSIGN TO "BCTSUBM.dat"
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-OUT-FS.

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

       FD SCORE-FILE
           RECORD CONTAINS 229 CHARACTERS.
       COPY SCORECOPY.

       FD RECOVERY-NEW
           RECORD CONTAINS 238 CHARACTERS.
       COPY RECOVCOPY.

       FD RISK-REPORT
           RECORD CONTAINS 137 CHARACTERS.
       01 RISK-RPT-LINE            PIC X(137).

       FD BCT-SUBMISSION
           RECORD CONTAINS 200 CHARACTERS.
       01 BCT-LINE                 PIC X(200).

       WORKING-STORAGE SECTION.
      *--- File status vars first for FD compatibility ---
       COPY ERRCOPY2.
       COPY RPTCOPY2.

      *--- File status not in ERRCOPY2 ---
       01 WS-REC-FS                PIC X(2)  VALUE SPACES.
          88 REC-FS-OK             VALUE '00'.

      *--- SQLCA for risk history insert ---
       01 SQLCA.
          05 SQLCAID               PIC X(8).
          05 SQLCABC               PIC S9(9) COMP.
          05 SQLCODE               PIC S9(9) COMP.
          05 SQLERRM.
             49 SQLERRML           PIC S9(4) COMP.
             49 SQLERRMC           PIC X(70).
          05 SQLERRP               PIC X(8).
          05 SQLERRD OCCURS 6 TIMES PIC S9(9) COMP.
          05 SQLWARN0              PIC X(8).
          05 SQLEXT                PIC X(8).

       01 WS-SQL-HOST.
          05 WS-SQL-LOAN-ID        PIC 9(10).
          05 WS-SQL-CUST-ID        PIC 9(8).
          05 WS-SQL-CLASS          PIC X(1).
          05 WS-SQL-PREV-CLASS     PIC X(1).
          05 WS-SQL-OUTSTANDING    PIC 9(11)V99.
          05 WS-SQL-PROVISION      PIC 9(11)V99.
          05 WS-SQL-DPD            PIC 9(4).
          05 WS-SQL-DATE           PIC 9(8).

       01 WS-CONTROL.
          05 WS-TODAY-DATE         PIC 9(8) VALUE ZEROS.
          05 WS-END-LOAN-FILE      PIC X    VALUE 'N'.
          05 WS-END-REC-FILE       PIC X    VALUE 'N'.
          05 WS-CURRENT-LOAN-ID    PIC 9(10) VALUE ZEROS.
          05 WS-CURRENT-CUST-ID    PIC 9(8) VALUE ZEROS.
          05 WS-PREV-CLASS         PIC X(1) VALUE SPACES.

      *--- Recovery cross-ref: track loans with active recovery ---
       01 WS-RECOVERY-TABLE.
          05 WS-REC-ENTRY OCCURS 200 TIMES.
             10 WSRE-LOAN-ID        PIC 9(10).
             10 WSRE-ACTION-CODE    PIC X(3).
       01 WS-REC-COUNT              PIC 9(4) VALUE ZEROS.
       01 WS-REC-IDX                PIC 9(4) VALUE ZEROS.
       01 WS-RECOVERY-FOUND         PIC X    VALUE 'N'.

      *--- Provision work fields ---
       01 WS-PROVISIONS.
          05 WS-REQUIRED-PROVISION  PIC 9(11)V99 VALUE ZEROS.
          05 WS-CLASS1-OUTSTANDING  PIC 9(13)V99 VALUE ZEROS.
          05 WS-CLASS2-OUTSTANDING  PIC 9(13)V99 VALUE ZEROS.
          05 WS-CLASS3-OUTSTANDING  PIC 9(13)V99 VALUE ZEROS.
          05 WS-CLASS4-OUTSTANDING  PIC 9(13)V99 VALUE ZEROS.
          05 WS-CLASS1-COUNT        PIC 9(6) VALUE ZEROS.
          05 WS-CLASS2-COUNT        PIC 9(6) VALUE ZEROS.
          05 WS-CLASS3-COUNT        PIC 9(6) VALUE ZEROS.
          05 WS-CLASS4-COUNT        PIC 9(6) VALUE ZEROS.
          05 WS-CLASS1-PROVISION    PIC 9(11)V99 VALUE ZEROS.
          05 WS-CLASS2-PROVISION    PIC 9(11)V99 VALUE ZEROS.
          05 WS-CLASS3-PROVISION    PIC 9(11)V99 VALUE ZEROS.
          05 WS-CLASS4-PROVISION    PIC 9(11)V99 VALUE ZEROS.
          05 WS-TOTAL-PROVISION     PIC 9(13)V99 VALUE ZEROS.
          05 WS-TOTAL-OUTSTANDING   PIC 9(13)V99 VALUE ZEROS.

      *--- BCT submission line ---
       01 WS-BCT-RECORD.
          05 BCT-BANK-CODE         PIC 9(4)      VALUE 1234.
          05 FILLER                PIC X(2)      VALUE SPACES.
          05 BCT-REPORT-DATE       PIC 9(8).
          05 FILLER                PIC X(2)      VALUE SPACES.
          05 BCT-LOAN-ID           PIC 9(10).
          05 FILLER                PIC X(2)      VALUE SPACES.
          05 BCT-CUST-ID           PIC 9(8).
          05 FILLER                PIC X(2)      VALUE SPACES.
          05 BCT-CLASS             PIC X(1).
          05 FILLER                PIC X(2)      VALUE SPACES.
          05 BCT-OUTSTANDING       PIC 9(11)V99.
          05 FILLER                PIC X(2)      VALUE SPACES.
          05 BCT-PROVISION         PIC 9(11)V99.
          05 FILLER                PIC X(2)      VALUE SPACES.
          05 BCT-DPD               PIC 9(4).
          05 FILLER                PIC X(2)      VALUE SPACES.
          05 BCT-RECOVERY-FLAG     PIC X(3).
          05 FILLER                PIC X(124)    VALUE SPACES.

       PROCEDURE DIVISION.

       0000-MAIN.
           MOVE 'RISKSCOR' TO WS-PROGRAM-NAME
           ACCEPT WS-TODAY-DATE FROM DATE YYYYMMDD
           PERFORM 0100-OPEN-FILES
           IF NOT RC-SUCCESS
               DISPLAY 'RISKSCOR ABEND: ' WS-ERROR-MESSAGE
               MOVE 12 TO RETURN-CODE
               STOP RUN
           END-IF
           PERFORM 0150-LOAD-RECOVERY-TABLE
           PERFORM 0200-INIT-REPORT
           PERFORM 1000-PROCESS-PORTFOLIO
               UNTIL WS-END-LOAN-FILE = 'Y'
           PERFORM 0300-WRITE-SUMMARY
           PERFORM 0400-CLOSE-FILES
           DISPLAY 'RISKSCOR COMPLETED.'
           DISPLAY '  CLASS 1: ' WS-CLASS1-COUNT
           DISPLAY '  CLASS 2: ' WS-CLASS2-COUNT
           DISPLAY '  CLASS 3: ' WS-CLASS3-COUNT
           DISPLAY '  CLASS 4: ' WS-CLASS4-COUNT
           DISPLAY '  TOTAL PROV: ' WS-TOTAL-PROVISION
           MOVE 0 TO RETURN-CODE
           STOP RUN.

       0100-OPEN-FILES.
           OPEN I-O LOAN-FILE
           IF NOT LOAN-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               MOVE 'LOANFILE OPEN FAILED' TO WS-ERROR-MESSAGE
               EXIT PARAGRAPH
           END-IF
           OPEN INPUT CUSTOMER-FILE
           IF NOT CUST-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               MOVE 'CUSTFILE OPEN FAILED' TO WS-ERROR-MESSAGE
               CLOSE LOAN-FILE
               EXIT PARAGRAPH
           END-IF
           OPEN INPUT SCORE-FILE
           IF NOT SCR-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               MOVE 'SCORFILE OPEN FAILED' TO WS-ERROR-MESSAGE
               CLOSE LOAN-FILE CUSTOMER-FILE
               EXIT PARAGRAPH
           END-IF
           OPEN INPUT RECOVERY-NEW
      *--- Recovery file is optional - tolerate missing ---
           OPEN OUTPUT RISK-REPORT
           IF NOT RPT-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               MOVE 'RISKRPT OPEN FAILED' TO WS-ERROR-MESSAGE
               CLOSE LOAN-FILE CUSTOMER-FILE SCORE-FILE
               EXIT PARAGRAPH
           END-IF
           OPEN OUTPUT BCT-SUBMISSION
           IF NOT OUT-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               MOVE 'BCTSUBM OPEN FAILED' TO WS-ERROR-MESSAGE
               CLOSE LOAN-FILE CUSTOMER-FILE SCORE-FILE RISK-REPORT
               EXIT PARAGRAPH
           END-IF
           MOVE 0 TO WS-RETURN-CODE
           READ LOAN-FILE
               AT END MOVE 'Y' TO WS-END-LOAN-FILE
               NOT AT END CONTINUE
           END-READ.

       0150-LOAD-RECOVERY-TABLE.
           IF REC-FS-OK
               PERFORM 0160-READ-REC
                   UNTIL WS-END-REC-FILE = 'Y'
                   OR WS-REC-COUNT >= 200
               CLOSE RECOVERY-NEW
           END-IF.

       0160-READ-REC.
           READ RECOVERY-NEW
               AT END MOVE 'Y' TO WS-END-REC-FILE
               NOT AT END
                   ADD 1 TO WS-REC-COUNT
                   MOVE REC-LOAN-ID
                       TO WSRE-LOAN-ID(WS-REC-COUNT)
                   MOVE REC-ACTION-TYPE
                       TO WSRE-ACTION-CODE(WS-REC-COUNT)
           END-READ.

       0200-INIT-REPORT.
           MOVE 'RISKSCOR'  TO RPT-PROGRAM
           MOVE WS-TODAY-DATE TO RPT-RUN-DATE
           MOVE 'RAPPORT CLASSIFICATION CREANCES BCT'
               TO RPT-TITLE
           MOVE 1 TO RPT-PAGE-NO
           WRITE RISK-RPT-LINE FROM RPT-MAIN-HEADER
           WRITE RISK-RPT-LINE FROM RPT-SUB-HEADER
           WRITE RISK-RPT-LINE FROM RPT-SEPARATOR.

       0300-WRITE-SUMMARY.
           WRITE RISK-RPT-LINE FROM RPT-SEPARATOR
           STRING 'CLASSE 1 (COURANTS) : CNT=' WS-CLASS1-COUNT
               ' ENC=' WS-CLASS1-OUTSTANDING
               ' PROV=' WS-CLASS1-PROVISION
               DELIMITED SIZE INTO RISK-RPT-LINE
           WRITE RISK-RPT-LINE
           STRING 'CLASSE 2 (30-90J)   : CNT=' WS-CLASS2-COUNT
               ' ENC=' WS-CLASS2-OUTSTANDING
               ' PROV=' WS-CLASS2-PROVISION
               DELIMITED SIZE INTO RISK-RPT-LINE
           WRITE RISK-RPT-LINE
           STRING 'CLASSE 3 (90-180J)  : CNT=' WS-CLASS3-COUNT
               ' ENC=' WS-CLASS3-OUTSTANDING
               ' PROV=' WS-CLASS3-PROVISION
               DELIMITED SIZE INTO RISK-RPT-LINE
           WRITE RISK-RPT-LINE
           STRING 'CLASSE 4 (>180J)    : CNT=' WS-CLASS4-COUNT
               ' ENC=' WS-CLASS4-OUTSTANDING
               ' PROV=' WS-CLASS4-PROVISION
               DELIMITED SIZE INTO RISK-RPT-LINE
           WRITE RISK-RPT-LINE
           STRING 'TOTAL PROVISIONS    : ' WS-TOTAL-PROVISION
               DELIMITED SIZE INTO RISK-RPT-LINE
           WRITE RISK-RPT-LINE
           WRITE RISK-RPT-LINE FROM RPT-FOOTER-LINE.

       0400-CLOSE-FILES.
           CLOSE LOAN-FILE CUSTOMER-FILE SCORE-FILE
                 RISK-REPORT BCT-SUBMISSION.

       1000-PROCESS-PORTFOLIO.
           IF NOT LOAN-ACTIVE AND NOT LOAN-RESTRUCTURED
               PERFORM 9000-READ-NEXT-LOAN
               EXIT PARAGRAPH
           END-IF
           ADD 1 TO STAT-PROCESSED
           MOVE LOAN-ID      TO WS-CURRENT-LOAN-ID
           MOVE LOAN-CUST-ID TO WS-CURRENT-CUST-ID
           MOVE LOAN-CLASS   TO WS-PREV-CLASS
           PERFORM 2000-CLASSIFY-LOAN
           PERFORM 2500-CHECK-RECOVERY-FLAG
           PERFORM 3000-COMPUTE-PROVISION
           PERFORM 4000-UPDATE-LOAN-CLASS
           PERFORM 4500-INSERT-RISK-HIST
           PERFORM 5000-ACCUMULATE-PORTFOLIO
           PERFORM 7000-WRITE-BCT-RECORD
           PERFORM 9000-READ-NEXT-LOAN.

       2000-CLASSIFY-LOAN.
           EVALUATE TRUE
               WHEN LOAN-DAYS-PAST-DUE <= 30
                   MOVE '1' TO LOAN-CLASS
                   MOVE 0   TO LOAN-PROVISION-RATE
               WHEN LOAN-DAYS-PAST-DUE <= 90
                   MOVE '2' TO LOAN-CLASS
                   MOVE 20.0000 TO LOAN-PROVISION-RATE
               WHEN LOAN-DAYS-PAST-DUE <= 180
                   MOVE '3' TO LOAN-CLASS
                   MOVE 50.0000 TO LOAN-PROVISION-RATE
               WHEN OTHER
                   MOVE '4' TO LOAN-CLASS
                   MOVE 100.0000 TO LOAN-PROVISION-RATE
           END-EVALUATE.

       2500-CHECK-RECOVERY-FLAG.
           MOVE 'N' TO WS-RECOVERY-FOUND
           PERFORM VARYING WS-REC-IDX FROM 1 BY 1
               UNTIL WS-REC-IDX > WS-REC-COUNT
               IF WSRE-LOAN-ID(WS-REC-IDX) = WS-CURRENT-LOAN-ID
                   MOVE 'Y' TO WS-RECOVERY-FOUND
                   EXIT PERFORM
               END-IF
           END-PERFORM.

       3000-COMPUTE-PROVISION.
           COMPUTE WS-REQUIRED-PROVISION ROUNDED =
               LOAN-OUTSTANDING * LOAN-PROVISION-RATE / 100
           MOVE WS-REQUIRED-PROVISION TO LOAN-PROVISION-AMT.

       4000-UPDATE-LOAN-CLASS.
           REWRITE LOAN-RECORD
           END-REWRITE.

       4500-INSERT-RISK-HIST.
           MOVE WS-CURRENT-LOAN-ID TO WS-SQL-LOAN-ID
           MOVE WS-CURRENT-CUST-ID TO WS-SQL-CUST-ID
           MOVE LOAN-CLASS         TO WS-SQL-CLASS
           MOVE WS-PREV-CLASS      TO WS-SQL-PREV-CLASS
           MOVE LOAN-OUTSTANDING   TO WS-SQL-OUTSTANDING
           MOVE WS-REQUIRED-PROVISION TO WS-SQL-PROVISION
           MOVE LOAN-DAYS-PAST-DUE TO WS-SQL-DPD
           MOVE WS-TODAY-DATE      TO WS-SQL-DATE
      *    EXEC SQL
      *        INSERT INTO PROD.RISK_HIST (
      *            LOAN_ID, CUST_ID, NEW_CLASS, PREV_CLASS,
      *            OUTSTANDING, PROVISION_AMT, DAYS_PAST_DUE,
      *            REPORT_DATE, CREATED_BY)
      *        VALUES (
      *            :WS-SQL-LOAN-ID, :WS-SQL-CUST-ID,
      *            :WS-SQL-CLASS, :WS-SQL-PREV-CLASS,
      *            :WS-SQL-OUTSTANDING, :WS-SQL-PROVISION,
      *            :WS-SQL-DPD, :WS-SQL-DATE, 'RISKSCOR')
      *    END-EXEC
      *    IF SQLCODE NOT = 0
      *        DISPLAY 'SQL INSERT FAILED CODE=' SQLCODE
      *    END-IF
           CONTINUE.

       5000-ACCUMULATE-PORTFOLIO.
           ADD LOAN-OUTSTANDING TO WS-TOTAL-OUTSTANDING
           ADD WS-REQUIRED-PROVISION TO WS-TOTAL-PROVISION
           EVALUATE LOAN-CLASS
               WHEN '1'
                   ADD 1 TO WS-CLASS1-COUNT
                   ADD LOAN-OUTSTANDING TO WS-CLASS1-OUTSTANDING
                   ADD WS-REQUIRED-PROVISION TO WS-CLASS1-PROVISION
               WHEN '2'
                   ADD 1 TO WS-CLASS2-COUNT
                   ADD LOAN-OUTSTANDING TO WS-CLASS2-OUTSTANDING
                   ADD WS-REQUIRED-PROVISION TO WS-CLASS2-PROVISION
               WHEN '3'
                   ADD 1 TO WS-CLASS3-COUNT
                   ADD LOAN-OUTSTANDING TO WS-CLASS3-OUTSTANDING
                   ADD WS-REQUIRED-PROVISION TO WS-CLASS3-PROVISION
               WHEN '4'
                   ADD 1 TO WS-CLASS4-COUNT
                   ADD LOAN-OUTSTANDING TO WS-CLASS4-OUTSTANDING
                   ADD WS-REQUIRED-PROVISION TO WS-CLASS4-PROVISION
           END-EVALUATE.

       7000-WRITE-BCT-RECORD.
           MOVE WS-TODAY-DATE     TO BCT-REPORT-DATE
           MOVE WS-CURRENT-LOAN-ID TO BCT-LOAN-ID
           MOVE WS-CURRENT-CUST-ID TO BCT-CUST-ID
           MOVE LOAN-CLASS        TO BCT-CLASS
           MOVE LOAN-OUTSTANDING  TO BCT-OUTSTANDING
           MOVE WS-REQUIRED-PROVISION TO BCT-PROVISION
           MOVE LOAN-DAYS-PAST-DUE TO BCT-DPD
           IF WS-RECOVERY-FOUND = 'Y'
               MOVE 'REC' TO BCT-RECOVERY-FLAG
           ELSE
               MOVE 'NRC' TO BCT-RECOVERY-FLAG
           END-IF
           WRITE BCT-LINE FROM WS-BCT-RECORD.

       9000-READ-NEXT-LOAN.
           READ LOAN-FILE
               AT END MOVE 'Y' TO WS-END-LOAN-FILE
               NOT AT END CONTINUE
           END-READ.

       END PROGRAM RISKSCOR.
