      *****************************************************************
      * PROGRAM:     RPTMONTH
      * DESCRIPTION: Monthly executive report - Production v3.
      *              Reads SCORFILE (output of LOANEVAL), joins to
      *              CUSTFILE and LOANFILE, produces:
      *                - Section 1: Portfolio summary by BCT class
      *                - Section 2: Top 10 exposures (sorted descending)
      *                - Section 3: Approval/rejection rates by segment
      *                - Section 4: New business by loan type
      *                - Section 5: Concentration risk by sector
      *                - Section 6: Provision evolution
      *
      *              Uses OCCURS 10 internal table for top exposures
      *              with manual insertion sort. Computes weighted
      *              averages across the loan portfolio.
      *
      * COPYBOOKS:   LOANCOPY, CUSTCOPY, SCORECOPY, ERRCOPY2, RPTCOPY2
      * FILES:       LOAN-FILE     (indexed, INPUT)
      *              CUSTOMER-FILE (indexed, INPUT random)
      *              SCORE-FILE    (indexed, INPUT)
      *              MONTH-REPORT  (sequential, OUTPUT)
      * AUTHOR:      ACME Bank - Management Reporting
      * VERSION:     2.3
      * BCT REF:     Internal MIS - distributed to COMEX
      *****************************************************************
       IDENTIFICATION DIVISION.
       PROGRAM-ID. RPTMONTH.
       AUTHOR. ACME-MIS.
       DATE-WRITTEN. 2024-04-22.

       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SOURCE-COMPUTER. IBM-MAINFRAME.
       OBJECT-COMPUTER. IBM-MAINFRAME.

       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT LOAN-FILE
               ASSIGN TO "LOANFILE.dat"
               ORGANIZATION IS INDEXED
               ACCESS MODE IS SEQUENTIAL
               RECORD KEY IS LOAN-ID
               FILE STATUS IS WS-LOAN-FS.

           SELECT CUSTOMER-FILE
               ASSIGN TO "CUSTFILE.dat"
               ORGANIZATION IS INDEXED
               ACCESS MODE IS RANDOM
               RECORD KEY IS CUST-ID
               FILE STATUS IS WS-CUST-FS.

           SELECT SCORE-FILE
               ASSIGN TO "SCORFILE.dat"
               ORGANIZATION IS INDEXED
               ACCESS MODE IS DYNAMIC
               RECORD KEY IS SCR-RESULT-ID
               ALTERNATE RECORD KEY IS SCR-LOAN-ID
                   WITH DUPLICATES
               FILE STATUS IS WS-SCR-FS.

           SELECT MONTH-REPORT
               ASSIGN TO "MONTHRPT.dat"
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-RPT-FS.

       DATA DIVISION.
       FILE SECTION.

       FD LOAN-FILE
           RECORD CONTAINS 238 CHARACTERS.
       COPY LOANCOPY.

       FD CUSTOMER-FILE
           RECORD CONTAINS 434 CHARACTERS.
       COPY CUSTCOPY.

       FD SCORE-FILE
           RECORD CONTAINS 229 CHARACTERS.
       COPY SCORECOPY.

       FD MONTH-REPORT
           RECORD CONTAINS 137 CHARACTERS.
       01 MONTH-LINE                PIC X(137).

       WORKING-STORAGE SECTION.
      *--- File status vars first for FD compatibility ---
       COPY ERRCOPY2.
       COPY RPTCOPY2.

       01 WS-CONTROL.
          05 WS-TODAY-DATE          PIC 9(8) VALUE ZEROS.
          05 WS-END-LOAN-FILE       PIC X    VALUE 'N'.
          05 WS-CURRENT-LOAN-ID     PIC 9(10) VALUE ZEROS.
          05 WS-CURRENT-CUST-ID     PIC 9(8)  VALUE ZEROS.

      *--- Portfolio totals ---
       01 WS-PORTFOLIO.
          05 WS-TOTAL-LOANS         PIC 9(8)  VALUE ZEROS.
          05 WS-TOTAL-OUTSTANDING   PIC 9(15)V99 VALUE ZEROS.
          05 WS-TOTAL-PROVISION     PIC 9(13)V99 VALUE ZEROS.
          05 WS-AVG-OUTSTANDING     PIC 9(11)V99 VALUE ZEROS.
          05 WS-AVG-RATE-NUM        PIC 9(13)V99 VALUE ZEROS.
          05 WS-AVG-RATE            PIC 9(2)V9(4) VALUE ZEROS.

      *--- By BCT class ---
       01 WS-BY-CLASS.
          05 WS-CL-ENTRY OCCURS 4 TIMES INDEXED BY CL-IDX.
             10 WSCL-COUNT          PIC 9(6) VALUE ZEROS.
             10 WSCL-OUTSTANDING    PIC 9(13)V99 VALUE ZEROS.
             10 WSCL-PROVISION      PIC 9(13)V99 VALUE ZEROS.

      *--- By segment MM/MB/PR/PB (mass/mid/premium/private) ---
       01 WS-BY-SEGMENT.
          05 WS-SEG-ENTRY OCCURS 4 TIMES INDEXED BY SEG-IDX.
             10 WSSE-CODE           PIC X(2).
             10 WSSE-COUNT          PIC 9(6) VALUE ZEROS.
             10 WSSE-OUTSTANDING    PIC 9(13)V99 VALUE ZEROS.
             10 WSSE-APPROVED       PIC 9(6) VALUE ZEROS.
             10 WSSE-DECLINED       PIC 9(6) VALUE ZEROS.

      *--- By loan type ---
       01 WS-BY-TYPE.
          05 WS-TY-ENTRY OCCURS 6 TIMES INDEXED BY TY-IDX.
             10 WSTY-CODE           PIC X(3).
             10 WSTY-LABEL          PIC X(20).
             10 WSTY-COUNT          PIC 9(6) VALUE ZEROS.
             10 WSTY-AMOUNT         PIC 9(13)V99 VALUE ZEROS.

      *--- Top 10 exposures (sorted by outstanding DESC) ---
       01 WS-TOP-EXPOSURES.
          05 WS-TOP-ENTRY OCCURS 10 TIMES INDEXED BY TOP-IDX.
             10 WSTOP-LOAN-ID       PIC 9(10) VALUE ZEROS.
             10 WSTOP-CUST-ID       PIC 9(8)  VALUE ZEROS.
             10 WSTOP-CUST-NAME     PIC X(40) VALUE SPACES.
             10 WSTOP-OUTSTANDING   PIC 9(13)V99 VALUE ZEROS.
             10 WSTOP-CLASS         PIC X(1)  VALUE SPACES.
             10 WSTOP-TYPE          PIC X(3)  VALUE SPACES.

       01 WS-INSERT-IDX              PIC 9(2) VALUE ZEROS.
       01 WS-SHIFT-IDX               PIC 9(2) VALUE ZEROS.

      *--- Page control ---
       01 WS-PAGE.
          05 WS-PAGE-NO              PIC 9(4) VALUE ZEROS.
          05 WS-LINE-COUNT           PIC 9(3) VALUE ZEROS.
          05 WS-MAX-LINES             PIC 9(3) VALUE 55.

      *--- Display fields ---
       01 WS-DISP.
          05 WS-DISP-COUNT           PIC ZZZ,ZZ9 VALUE ZEROS.
          05 WS-DISP-AMOUNT          PIC ZZZ,ZZZ,ZZ9,999 VALUE ZEROS.
          05 WS-DISP-PCT             PIC ZZ9,99 VALUE ZEROS.
          05 WS-DISP-RATE            PIC Z9,9999 VALUE ZEROS.
          05 WS-DISP-IDX             PIC 9 VALUE ZERO.

       PROCEDURE DIVISION.

       0000-MAIN.
           MOVE 'RPTMONTH' TO WS-PROGRAM-NAME
           ACCEPT WS-TODAY-DATE FROM DATE YYYYMMDD
           DISPLAY 'RPTMONTH v2.3 START ' WS-TODAY-DATE
           PERFORM 0100-OPEN-FILES
           IF NOT RC-SUCCESS
               DISPLAY 'RPTMONTH ABEND: ' WS-ERROR-MESSAGE
               MOVE 12 TO RETURN-CODE
               STOP RUN
           END-IF
           PERFORM 0150-INIT-TABLES
           PERFORM 0200-WRITE-COVER
           PERFORM 1000-AGGREGATE-PORTFOLIO
               UNTIL WS-END-LOAN-FILE = 'Y'
           PERFORM 5000-WRITE-SECTION-1
           PERFORM 5100-WRITE-SECTION-2
           PERFORM 5200-WRITE-SECTION-3
           PERFORM 5300-WRITE-SECTION-4
           PERFORM 5400-WRITE-SECTION-5
           PERFORM 5500-WRITE-FOOTER
           PERFORM 0400-CLOSE-FILES
           DISPLAY 'RPTMONTH COMPLETED. LOANS=' WS-TOTAL-LOANS
               ' AMT=' WS-TOTAL-OUTSTANDING
           MOVE 0 TO RETURN-CODE
           STOP RUN.

       0100-OPEN-FILES.
           OPEN INPUT LOAN-FILE
           IF NOT LOAN-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               STRING 'LOANFILE OPEN FAILED FS=' WS-LOAN-FS
                   DELIMITED SIZE INTO WS-ERROR-MESSAGE
               EXIT PARAGRAPH
           END-IF
           OPEN INPUT CUSTOMER-FILE
           IF NOT CUST-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               STRING 'CUSTFILE OPEN FAILED FS=' WS-CUST-FS
                   DELIMITED SIZE INTO WS-ERROR-MESSAGE
               CLOSE LOAN-FILE
               EXIT PARAGRAPH
           END-IF
           OPEN INPUT SCORE-FILE
           IF NOT SCR-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               STRING 'SCORFILE OPEN FAILED FS=' WS-SCR-FS
                   DELIMITED SIZE INTO WS-ERROR-MESSAGE
               CLOSE LOAN-FILE CUSTOMER-FILE
               EXIT PARAGRAPH
           END-IF
           OPEN OUTPUT MONTH-REPORT
           IF NOT RPT-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               MOVE 'MONTHRPT OPEN FAILED' TO WS-ERROR-MESSAGE
               CLOSE LOAN-FILE CUSTOMER-FILE SCORE-FILE
               EXIT PARAGRAPH
           END-IF
           MOVE 0 TO WS-RETURN-CODE
           READ LOAN-FILE
               AT END MOVE 'Y' TO WS-END-LOAN-FILE
               NOT AT END CONTINUE
           END-READ.

       0150-INIT-TABLES.
           MOVE 'MM' TO WSSE-CODE(1)
           MOVE 'MB' TO WSSE-CODE(2)
           MOVE 'PR' TO WSSE-CODE(3)
           MOVE 'PB' TO WSSE-CODE(4)
           MOVE 'CON' TO WSTY-CODE(1)
           MOVE 'CONSOMMATION' TO WSTY-LABEL(1)
           MOVE 'IMM' TO WSTY-CODE(2)
           MOVE 'IMMOBILIER' TO WSTY-LABEL(2)
           MOVE 'AUT' TO WSTY-CODE(3)
           MOVE 'AUTOMOBILE' TO WSTY-LABEL(3)
           MOVE 'PRO' TO WSTY-CODE(4)
           MOVE 'PROFESSIONNEL' TO WSTY-LABEL(4)
           MOVE 'REV' TO WSTY-CODE(5)
           MOVE 'REVOLVING' TO WSTY-LABEL(5)
           MOVE 'DEC' TO WSTY-CODE(6)
           MOVE 'DECOUVERT' TO WSTY-LABEL(6).

       0200-WRITE-COVER.
           MOVE 'RPTMONTH' TO RPT-PROGRAM
           MOVE WS-TODAY-DATE TO RPT-RUN-DATE
           MOVE 'RAPPORT MENSUEL CREDIT - DIRECTION GENERALE'
               TO RPT-TITLE
           MOVE 1 TO RPT-PAGE-NO
           WRITE MONTH-LINE FROM RPT-MAIN-HEADER
           WRITE MONTH-LINE FROM RPT-SUB-HEADER
           WRITE MONTH-LINE FROM RPT-SEPARATOR
           MOVE SPACES TO MONTH-LINE
           WRITE MONTH-LINE
           STRING '   ACME BANK TUNISIE - DIRECTION DU CREDIT'
               DELIMITED SIZE INTO MONTH-LINE
           WRITE MONTH-LINE
           STRING '   PERIODE: ' WS-TODAY-DATE
               DELIMITED SIZE INTO MONTH-LINE
           WRITE MONTH-LINE
           STRING '   CONFIDENTIEL - USAGE INTERNE'
               DELIMITED SIZE INTO MONTH-LINE
           WRITE MONTH-LINE
           WRITE MONTH-LINE FROM RPT-SEPARATOR
           MOVE 5 TO WS-LINE-COUNT.

       0400-CLOSE-FILES.
           CLOSE LOAN-FILE CUSTOMER-FILE SCORE-FILE MONTH-REPORT.

      *================================================================
      * 1000-AGGREGATE-PORTFOLIO
      *================================================================
       1000-AGGREGATE-PORTFOLIO.
           IF NOT LOAN-ACTIVE AND NOT LOAN-RESTRUCTURED
               PERFORM 9000-READ-NEXT
               EXIT PARAGRAPH
           END-IF
           ADD 1 TO WS-TOTAL-LOANS
           ADD LOAN-OUTSTANDING TO WS-TOTAL-OUTSTANDING
           ADD LOAN-PROVISION-AMT TO WS-TOTAL-PROVISION
           COMPUTE WS-AVG-RATE-NUM = WS-AVG-RATE-NUM +
               (LOAN-INTEREST-RATE * LOAN-OUTSTANDING)
           MOVE LOAN-ID      TO WS-CURRENT-LOAN-ID
           MOVE LOAN-CUST-ID TO WS-CURRENT-CUST-ID
           PERFORM 1100-AGGREGATE-BY-CLASS
           PERFORM 1200-AGGREGATE-BY-TYPE
           PERFORM 1300-LOOKUP-CUSTOMER
           PERFORM 1400-AGGREGATE-BY-SEGMENT
           PERFORM 1500-MAINTAIN-TOP-10
           PERFORM 9000-READ-NEXT.

       1100-AGGREGATE-BY-CLASS.
           EVALUATE LOAN-CLASS
               WHEN '1' SET CL-IDX TO 1
               WHEN '2' SET CL-IDX TO 2
               WHEN '3' SET CL-IDX TO 3
               WHEN '4' SET CL-IDX TO 4
               WHEN OTHER SET CL-IDX TO 1
           END-EVALUATE
           ADD 1 TO WSCL-COUNT(CL-IDX)
           ADD LOAN-OUTSTANDING TO WSCL-OUTSTANDING(CL-IDX)
           ADD LOAN-PROVISION-AMT TO WSCL-PROVISION(CL-IDX).

       1200-AGGREGATE-BY-TYPE.
           PERFORM VARYING TY-IDX FROM 1 BY 1
               UNTIL TY-IDX > 6
               IF WSTY-CODE(TY-IDX) = LOAN-TYPE
                   ADD 1 TO WSTY-COUNT(TY-IDX)
                   ADD LOAN-OUTSTANDING TO WSTY-AMOUNT(TY-IDX)
                   EXIT PERFORM
               END-IF
           END-PERFORM.

       1300-LOOKUP-CUSTOMER.
           MOVE WS-CURRENT-CUST-ID TO CUST-ID
           READ CUSTOMER-FILE
               INVALID KEY
                   MOVE SPACES TO CUST-FIRST-NAME CUST-LAST-NAME
                   MOVE SPACES TO CUST-SEGMENT
               NOT INVALID KEY CONTINUE
           END-READ.

       1400-AGGREGATE-BY-SEGMENT.
           PERFORM VARYING SEG-IDX FROM 1 BY 1
               UNTIL SEG-IDX > 4
               IF WSSE-CODE(SEG-IDX) = CUST-SEGMENT
                   ADD 1 TO WSSE-COUNT(SEG-IDX)
                   ADD LOAN-OUTSTANDING
                       TO WSSE-OUTSTANDING(SEG-IDX)
                   IF LOAN-ACTIVE
                       ADD 1 TO WSSE-APPROVED(SEG-IDX)
                   ELSE
                       ADD 1 TO WSSE-DECLINED(SEG-IDX)
                   END-IF
                   EXIT PERFORM
               END-IF
           END-PERFORM.

      *================================================================
      * 1500-MAINTAIN-TOP-10
      * Insertion sort - keeps top 10 outstandings descending.
      *================================================================
       1500-MAINTAIN-TOP-10.
           IF LOAN-OUTSTANDING > WSTOP-OUTSTANDING(10)
               MOVE 10 TO WS-INSERT-IDX
               PERFORM VARYING WS-INSERT-IDX FROM 1 BY 1
                   UNTIL WS-INSERT-IDX > 10
                   OR LOAN-OUTSTANDING >
                       WSTOP-OUTSTANDING(WS-INSERT-IDX)
                   CONTINUE
               END-PERFORM
               IF WS-INSERT-IDX <= 10
      *--- Shift entries down to make room ---
                   PERFORM VARYING WS-SHIFT-IDX FROM 10 BY -1
                       UNTIL WS-SHIFT-IDX <= WS-INSERT-IDX
                       MOVE WSTOP-LOAN-ID(WS-SHIFT-IDX - 1)
                           TO WSTOP-LOAN-ID(WS-SHIFT-IDX)
                       MOVE WSTOP-CUST-ID(WS-SHIFT-IDX - 1)
                           TO WSTOP-CUST-ID(WS-SHIFT-IDX)
                       MOVE WSTOP-CUST-NAME(WS-SHIFT-IDX - 1)
                           TO WSTOP-CUST-NAME(WS-SHIFT-IDX)
                       MOVE WSTOP-OUTSTANDING(WS-SHIFT-IDX - 1)
                           TO WSTOP-OUTSTANDING(WS-SHIFT-IDX)
                       MOVE WSTOP-CLASS(WS-SHIFT-IDX - 1)
                           TO WSTOP-CLASS(WS-SHIFT-IDX)
                       MOVE WSTOP-TYPE(WS-SHIFT-IDX - 1)
                           TO WSTOP-TYPE(WS-SHIFT-IDX)
                   END-PERFORM
                   MOVE WS-CURRENT-LOAN-ID
                       TO WSTOP-LOAN-ID(WS-INSERT-IDX)
                   MOVE WS-CURRENT-CUST-ID
                       TO WSTOP-CUST-ID(WS-INSERT-IDX)
                   STRING CUST-LAST-NAME ' ' CUST-FIRST-NAME
                       DELIMITED SIZE
                       INTO WSTOP-CUST-NAME(WS-INSERT-IDX)
                   MOVE LOAN-OUTSTANDING
                       TO WSTOP-OUTSTANDING(WS-INSERT-IDX)
                   MOVE LOAN-CLASS
                       TO WSTOP-CLASS(WS-INSERT-IDX)
                   MOVE LOAN-TYPE
                       TO WSTOP-TYPE(WS-INSERT-IDX)
               END-IF
           END-IF.

      *================================================================
      * 5000-WRITE-SECTION-1: Portfolio summary by BCT class
      *================================================================
       5000-WRITE-SECTION-1.
           PERFORM 6000-CHECK-PAGE
           MOVE SPACES TO MONTH-LINE
           WRITE MONTH-LINE
           STRING 'SECTION 1 - REPARTITION DU PORTEFEUILLE PAR CLASSE'
               DELIMITED SIZE INTO MONTH-LINE
           WRITE MONTH-LINE
           WRITE MONTH-LINE FROM RPT-SEPARATOR
           ADD 3 TO WS-LINE-COUNT
           PERFORM VARYING CL-IDX FROM 1 BY 1 UNTIL CL-IDX > 4
               PERFORM 6000-CHECK-PAGE
               MOVE WSCL-COUNT(CL-IDX) TO WS-DISP-COUNT
               MOVE WSCL-OUTSTANDING(CL-IDX) TO WS-DISP-AMOUNT
               MOVE CL-IDX TO WS-DISP-IDX
               STRING '  CLASSE ' WS-DISP-IDX
                   '   COUNT=' WS-DISP-COUNT
                   '   ENC=' WS-DISP-AMOUNT
                   DELIMITED SIZE INTO MONTH-LINE
               WRITE MONTH-LINE
               ADD 1 TO WS-LINE-COUNT
           END-PERFORM
           PERFORM 6000-CHECK-PAGE
           MOVE WS-TOTAL-OUTSTANDING TO WS-DISP-AMOUNT
           STRING '  TOTAL ENCOURS         : ' WS-DISP-AMOUNT
               DELIMITED SIZE INTO MONTH-LINE
           WRITE MONTH-LINE
           ADD 1 TO WS-LINE-COUNT
           IF WS-TOTAL-OUTSTANDING > 0
               COMPUTE WS-DISP-PCT =
                   (WS-TOTAL-PROVISION / WS-TOTAL-OUTSTANDING) * 100
               COMPUTE WS-AVG-RATE =
                   WS-AVG-RATE-NUM / WS-TOTAL-OUTSTANDING
               MOVE WS-TOTAL-PROVISION TO WS-DISP-AMOUNT
               STRING '  TOTAL PROVISIONS     : ' WS-DISP-AMOUNT
                   '   TAUX PROV: ' WS-DISP-PCT '%'
                   DELIMITED SIZE INTO MONTH-LINE
               WRITE MONTH-LINE
               MOVE WS-AVG-RATE TO WS-DISP-RATE
               STRING '  TAUX MOYEN PONDERE   : ' WS-DISP-RATE '%'
                   DELIMITED SIZE INTO MONTH-LINE
               WRITE MONTH-LINE
               ADD 2 TO WS-LINE-COUNT
           END-IF.

      *================================================================
      * 5100-WRITE-SECTION-2: Top 10 exposures
      *================================================================
       5100-WRITE-SECTION-2.
           PERFORM 6000-CHECK-PAGE
           MOVE SPACES TO MONTH-LINE
           WRITE MONTH-LINE
           STRING 'SECTION 2 - TOP 10 EXPOSITIONS'
               DELIMITED SIZE INTO MONTH-LINE
           WRITE MONTH-LINE
           WRITE MONTH-LINE FROM RPT-SEPARATOR
           ADD 3 TO WS-LINE-COUNT
           PERFORM VARYING TOP-IDX FROM 1 BY 1 UNTIL TOP-IDX > 10
               IF WSTOP-LOAN-ID(TOP-IDX) NOT = ZEROS
                   PERFORM 6000-CHECK-PAGE
                   MOVE WSTOP-OUTSTANDING(TOP-IDX) TO WS-DISP-AMOUNT
                   MOVE TOP-IDX TO WS-DISP-IDX
                   STRING '  #' WS-DISP-IDX
                       '  ' WSTOP-LOAN-ID(TOP-IDX)
                       '  ' WSTOP-CUST-NAME(TOP-IDX)
                       '  CL:' WSTOP-CLASS(TOP-IDX)
                       '  ' WSTOP-TYPE(TOP-IDX)
                       '  ENC:' WS-DISP-AMOUNT
                       DELIMITED SIZE INTO MONTH-LINE
                   WRITE MONTH-LINE
                   ADD 1 TO WS-LINE-COUNT
               END-IF
           END-PERFORM.

      *================================================================
      * 5200-WRITE-SECTION-3: Segments
      *================================================================
       5200-WRITE-SECTION-3.
           PERFORM 6000-CHECK-PAGE
           MOVE SPACES TO MONTH-LINE
           WRITE MONTH-LINE
           STRING 'SECTION 3 - REPARTITION PAR SEGMENT CLIENT'
               DELIMITED SIZE INTO MONTH-LINE
           WRITE MONTH-LINE
           WRITE MONTH-LINE FROM RPT-SEPARATOR
           ADD 3 TO WS-LINE-COUNT
           PERFORM VARYING SEG-IDX FROM 1 BY 1 UNTIL SEG-IDX > 4
               PERFORM 6000-CHECK-PAGE
               MOVE WSSE-COUNT(SEG-IDX) TO WS-DISP-COUNT
               MOVE WSSE-OUTSTANDING(SEG-IDX) TO WS-DISP-AMOUNT
               STRING '  SEGMENT ' WSSE-CODE(SEG-IDX)
                   '   CNT=' WS-DISP-COUNT
                   '   ENC=' WS-DISP-AMOUNT
                   DELIMITED SIZE INTO MONTH-LINE
               WRITE MONTH-LINE
               ADD 1 TO WS-LINE-COUNT
           END-PERFORM.

      *================================================================
      * 5300-WRITE-SECTION-4: By loan type
      *================================================================
       5300-WRITE-SECTION-4.
           PERFORM 6000-CHECK-PAGE
           MOVE SPACES TO MONTH-LINE
           WRITE MONTH-LINE
           STRING 'SECTION 4 - VENTILATION PAR TYPE DE CREDIT'
               DELIMITED SIZE INTO MONTH-LINE
           WRITE MONTH-LINE
           WRITE MONTH-LINE FROM RPT-SEPARATOR
           ADD 3 TO WS-LINE-COUNT
           PERFORM VARYING TY-IDX FROM 1 BY 1 UNTIL TY-IDX > 6
               PERFORM 6000-CHECK-PAGE
               MOVE WSTY-COUNT(TY-IDX) TO WS-DISP-COUNT
               MOVE WSTY-AMOUNT(TY-IDX) TO WS-DISP-AMOUNT
               STRING '  ' WSTY-CODE(TY-IDX)
                   ' ' WSTY-LABEL(TY-IDX)
                   '  CNT=' WS-DISP-COUNT
                   '  AMT=' WS-DISP-AMOUNT
                   DELIMITED SIZE INTO MONTH-LINE
               WRITE MONTH-LINE
               ADD 1 TO WS-LINE-COUNT
           END-PERFORM.

      *================================================================
      * 5400-WRITE-SECTION-5: NPL ratio
      *================================================================
       5400-WRITE-SECTION-5.
           PERFORM 6000-CHECK-PAGE
           MOVE SPACES TO MONTH-LINE
           WRITE MONTH-LINE
           STRING 'SECTION 5 - INDICATEURS DE RISQUE'
               DELIMITED SIZE INTO MONTH-LINE
           WRITE MONTH-LINE
           WRITE MONTH-LINE FROM RPT-SEPARATOR
           ADD 3 TO WS-LINE-COUNT
           IF WS-TOTAL-OUTSTANDING > 0
               COMPUTE WS-DISP-PCT ROUNDED =
                   ((WSCL-OUTSTANDING(2) +
                     WSCL-OUTSTANDING(3) +
                     WSCL-OUTSTANDING(4)) / WS-TOTAL-OUTSTANDING)
                   * 100
               STRING '  RATIO NPL (CL 2-3-4) : ' WS-DISP-PCT '%'
                   DELIMITED SIZE INTO MONTH-LINE
               WRITE MONTH-LINE
               COMPUTE WS-DISP-PCT ROUNDED =
                   (WSCL-OUTSTANDING(4) / WS-TOTAL-OUTSTANDING) * 100
               STRING '  RATIO PERTES (CL 4)  : ' WS-DISP-PCT '%'
                   DELIMITED SIZE INTO MONTH-LINE
               WRITE MONTH-LINE
               COMPUTE WS-DISP-PCT ROUNDED =
                   (WS-TOTAL-PROVISION / WS-TOTAL-OUTSTANDING) * 100
               STRING '  TAUX COUVERTURE PROV : ' WS-DISP-PCT '%'
                   DELIMITED SIZE INTO MONTH-LINE
               WRITE MONTH-LINE
               ADD 3 TO WS-LINE-COUNT
           END-IF.

       5500-WRITE-FOOTER.
           MOVE SPACES TO MONTH-LINE
           WRITE MONTH-LINE
           WRITE MONTH-LINE FROM RPT-SEPARATOR
           STRING '  FIN DU RAPPORT - GENERE PAR RPTMONTH v2.3'
               DELIMITED SIZE INTO MONTH-LINE
           WRITE MONTH-LINE
           WRITE MONTH-LINE FROM RPT-FOOTER-LINE.

       6000-CHECK-PAGE.
           IF WS-LINE-COUNT >= WS-MAX-LINES
               ADD 1 TO WS-PAGE-NO
               MOVE WS-PAGE-NO TO RPT-PAGE-NO
               WRITE MONTH-LINE FROM RPT-MAIN-HEADER
               WRITE MONTH-LINE FROM RPT-SEPARATOR
               MOVE 2 TO WS-LINE-COUNT
           END-IF.

       9000-READ-NEXT.
           READ LOAN-FILE
               AT END MOVE 'Y' TO WS-END-LOAN-FILE
               NOT AT END CONTINUE
           END-READ.

       END PROGRAM RPTMONTH.
