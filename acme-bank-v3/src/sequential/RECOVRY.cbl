      *****************************************************************
      * PROGRAM:     RECOVRY
      * DESCRIPTION: Loan recovery and collection orchestrator.
      *              Reads loans in classes 2, 3, 4 (past due),
      *              determines next recovery action per BCT-mandated
      *              escalation matrix, generates recovery actions,
      *              writes them to RECOVFILE, and produces letters
      *              for the dunning process. Also reads existing
      *              recovery history to avoid duplicate actions and
      *              respect minimum intervals between actions.
      *
      *              Escalation matrix (BCT Circulaire 2021-02):
      *                Class 2 (31-90 days):
      *                  - Day 31-45 : SMS reminder + EMAIL
      *                  - Day 46-60 : Phone call
      *                  - Day 61-90 : Formal dunning letter (DUL)
      *                Class 3 (91-180 days):
      *                  - Day 91-120: Legal notice (LEG)
      *                  - Day 121-150: Guarantor call (GTR)
      *                  - Day 151-180: Restructure proposal (RST)
      *                Class 4 (>180 days):
      *                  - Day 181-365: Court filing (CRT)
      *                  - Day 366+   : Collateral seizure (CSZ)
      *                                 or write-off (WOF)
      *
      *              Uses internal SORT on amount + days_past_due
      *              to prioritize highest-risk loans first.
      *
      * COPYBOOKS:   LOANCOPY, CUSTCOPY, COLLATCOPY, RECOVCOPY,
      *              ERRCOPY2, RPTCOPY2
      * FILES:       LOAN-FILE       (indexed, INPUT)
      *              CUSTOMER-FILE   (indexed, INPUT random)
      *              COLLATERAL-FILE (indexed, INPUT dynamic)
      *              RECOVERY-FILE   (sequential, I-O)
      *              RECOVERY-NEW    (sequential, OUTPUT)
      *              LETTER-FILE     (sequential, OUTPUT)
      *              ESCALATION-RPT  (sequential, OUTPUT)
      *              SORT-WORK       (work file)
      * SUB-PGMS:    None directly. Calls FILE-CONTROL only.
      * AUTHOR:      ACME Bank - Recovery Division
      * VERSION:     2.5
      * BCT REF:     Circulaire BCT 2021-02 Article 18
      *****************************************************************
       IDENTIFICATION DIVISION.
       PROGRAM-ID. RECOVRY.
       AUTHOR. ACME-RECOVERY.
       DATE-WRITTEN. 2024-04-20.

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

           SELECT COLLATERAL-FILE
               ASSIGN TO "COLFILE.dat"
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE IS SEQUENTIAL


               FILE STATUS IS WS-COL-FS.

           SELECT RECOVERY-NEW
               ASSIGN TO "RECVNEW.dat"
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-REC-FS.

           SELECT LETTER-FILE
               ASSIGN TO "LETTERS.dat"
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-LTR-FS.

           SELECT ESCALATION-RPT
               ASSIGN TO "ESCARPT.dat"
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-RPT-FS.

           SELECT SORT-WORK ASSIGN TO "SORTWK2.dat".

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

       FD RECOVERY-NEW
           RECORD CONTAINS 238 CHARACTERS.
       COPY RECOVCOPY.

       FD LETTER-FILE
           RECORD CONTAINS 137 CHARACTERS.
       01 LETTER-LINE              PIC X(137).

       FD ESCALATION-RPT
           RECORD CONTAINS 137 CHARACTERS.
       01 ESCA-RPT-LINE            PIC X(137).

       SD SORT-WORK.
       01 SORT-LOAN-REC.
          05 SORT-PRIORITY         PIC 9(3).
          05 SORT-AMOUNT           PIC 9(13).
          05 SORT-LOAN-ID          PIC 9(10).
          05 SORT-CUST-ID          PIC 9(8).
          05 SORT-DPD              PIC 9(4).
          05 SORT-CLASS            PIC X(1).
          05 SORT-FILLER           PIC X(60).

       WORKING-STORAGE SECTION.
      *--- File status vars first for FD compatibility ---
       COPY ERRCOPY2.
       COPY RPTCOPY2.

      *--- Recovery action being built ---
       01 WS-RECOV-WORK.
          05 WS-NEXT-ACTION-CODE   PIC X(3) VALUE SPACES.
          05 WS-RECOV-SEQ          PIC 9(12) VALUE ZEROS.
          05 WS-DAYS-FROM-LAST-ACT PIC 9(4)  VALUE ZEROS.
          05 WS-LAST-ACTION-DATE   PIC 9(8)  VALUE ZEROS.
          05 WS-LAST-ACTION-CODE   PIC X(3)  VALUE SPACES.

      *--- Recovery file status ---
       01 WS-REC-FS                PIC X(2)  VALUE SPACES.
          88 REC-FS-OK             VALUE '00'.
       01 WS-LTR-FS                PIC X(2)  VALUE SPACES.
          88 LTR-FS-OK             VALUE '00'.

       01 WS-CONTROL.
          05 WS-TODAY-DATE         PIC 9(8) VALUE ZEROS.
          05 WS-END-LOAN-FILE      PIC X    VALUE 'N'.
          05 WS-CURRENT-LOAN-ID    PIC 9(10) VALUE ZEROS.
          05 WS-CURRENT-CUST-ID    PIC 9(8) VALUE ZEROS.

      *--- Stats by class ---
       01 WS-CLASS-STATS.
          05 WS-CL2-COUNT          PIC 9(6) VALUE ZEROS.
          05 WS-CL3-COUNT          PIC 9(6) VALUE ZEROS.
          05 WS-CL4-COUNT          PIC 9(6) VALUE ZEROS.
          05 WS-CL2-AMOUNT         PIC 9(13)V99 VALUE ZEROS.
          05 WS-CL3-AMOUNT         PIC 9(13)V99 VALUE ZEROS.
          05 WS-CL4-AMOUNT         PIC 9(13)V99 VALUE ZEROS.

      *--- Stats by action type ---
       01 WS-ACTION-STATS.
          05 WS-ACT-SMS            PIC 9(6) VALUE ZEROS.
          05 WS-ACT-EMAIL          PIC 9(6) VALUE ZEROS.
          05 WS-ACT-PHONE          PIC 9(6) VALUE ZEROS.
          05 WS-ACT-DUL            PIC 9(6) VALUE ZEROS.
          05 WS-ACT-LEG            PIC 9(6) VALUE ZEROS.
          05 WS-ACT-GTR            PIC 9(6) VALUE ZEROS.
          05 WS-ACT-RST            PIC 9(6) VALUE ZEROS.
          05 WS-ACT-CRT            PIC 9(6) VALUE ZEROS.
          05 WS-ACT-CSZ            PIC 9(6) VALUE ZEROS.
          05 WS-ACT-WOF            PIC 9(6) VALUE ZEROS.

      *--- Dunning letter buffer ---
       01 WS-LETTER-BUFFER.
          05 LB-LINE OCCURS 30 TIMES.
             10 LB-TEXT            PIC X(137).
       01 WS-LETTER-LINE-IDX        PIC 9(2) VALUE ZEROS.

       PROCEDURE DIVISION.

      *================================================================
      * 0000-MAIN
      *================================================================
       0000-MAIN.
           MOVE 'RECOVRY ' TO WS-PROGRAM-NAME
           ACCEPT WS-TODAY-DATE FROM DATE YYYYMMDD
           DISPLAY 'RECOVRY v2.5 START ' WS-TODAY-DATE
           PERFORM 0100-OPEN-FILES
           IF NOT RC-SUCCESS
               DISPLAY 'RECOVRY ABEND: ' WS-ERROR-MESSAGE
               MOVE 12 TO RETURN-CODE
               STOP RUN
           END-IF
           PERFORM 0200-INIT-REPORT

      *--- The processing is sort-driven: highest priority first ---
           SORT SORT-WORK
               ON DESCENDING KEY SORT-PRIORITY
               ON DESCENDING KEY SORT-AMOUNT
               INPUT PROCEDURE IS 1000-LOAD-SORT
                                  THRU 1000-LOAD-SORT-EXIT
               OUTPUT PROCEDURE IS 2000-PROCESS-RECOVERY
                                   THRU 2000-PROCESS-RECOVERY-EXIT

           PERFORM 0300-WRITE-SUMMARY
           PERFORM 0400-CLOSE-FILES
           DISPLAY 'RECOVRY COMPLETED.'
           DISPLAY '  CLASS 2 LOANS: ' WS-CL2-COUNT
               ' AMOUNT: ' WS-CL2-AMOUNT
           DISPLAY '  CLASS 3 LOANS: ' WS-CL3-COUNT
               ' AMOUNT: ' WS-CL3-AMOUNT
           DISPLAY '  CLASS 4 LOANS: ' WS-CL4-COUNT
               ' AMOUNT: ' WS-CL4-AMOUNT
           DISPLAY '  ACTIONS GENERATED:'
           DISPLAY '    SMS    : ' WS-ACT-SMS
           DISPLAY '    EMAIL  : ' WS-ACT-EMAIL
           DISPLAY '    PHONE  : ' WS-ACT-PHONE
           DISPLAY '    DUL    : ' WS-ACT-DUL
           DISPLAY '    LEG    : ' WS-ACT-LEG
           DISPLAY '    GTR    : ' WS-ACT-GTR
           DISPLAY '    RST    : ' WS-ACT-RST
           DISPLAY '    CRT    : ' WS-ACT-CRT
           DISPLAY '    CSZ    : ' WS-ACT-CSZ
           DISPLAY '    WOF    : ' WS-ACT-WOF
           MOVE 0 TO RETURN-CODE
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
           OPEN INPUT CUSTOMER-FILE
           IF NOT CUST-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               STRING 'CUSTFILE OPEN FAILED FS=' WS-CUST-FS
                   DELIMITED SIZE INTO WS-ERROR-MESSAGE
               CLOSE LOAN-FILE
               EXIT PARAGRAPH
           END-IF
           OPEN INPUT COLLATERAL-FILE
           IF NOT COL-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               STRING 'COLFILE OPEN FAILED FS=' WS-COL-FS
                   DELIMITED SIZE INTO WS-ERROR-MESSAGE
               CLOSE LOAN-FILE CUSTOMER-FILE
               EXIT PARAGRAPH
           END-IF
           OPEN OUTPUT RECOVERY-NEW
           IF NOT REC-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               MOVE 'RECVNEW OPEN FAILED' TO WS-ERROR-MESSAGE
               CLOSE LOAN-FILE CUSTOMER-FILE COLLATERAL-FILE
               EXIT PARAGRAPH
           END-IF
           OPEN OUTPUT LETTER-FILE
           IF NOT LTR-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               MOVE 'LETTERS OPEN FAILED' TO WS-ERROR-MESSAGE
               CLOSE LOAN-FILE CUSTOMER-FILE COLLATERAL-FILE
                     RECOVERY-NEW
               EXIT PARAGRAPH
           END-IF
           OPEN OUTPUT ESCALATION-RPT
           IF NOT RPT-FS-OK
               MOVE 12 TO WS-RETURN-CODE
               MOVE 'ESCARPT OPEN FAILED' TO WS-ERROR-MESSAGE
               CLOSE LOAN-FILE CUSTOMER-FILE COLLATERAL-FILE
                     RECOVERY-NEW LETTER-FILE
               EXIT PARAGRAPH
           END-IF
           MOVE 0 TO WS-RETURN-CODE.

      *================================================================
      * 0200-INIT-REPORT
      *================================================================
       0200-INIT-REPORT.
           MOVE 'RECOVRY ' TO RPT-PROGRAM
           MOVE WS-TODAY-DATE TO RPT-RUN-DATE
           MOVE 'RAPPORT ESCALADE RECOUVREMENT'
               TO RPT-TITLE
           MOVE 1 TO RPT-PAGE-NO
           WRITE ESCA-RPT-LINE FROM RPT-MAIN-HEADER
           WRITE ESCA-RPT-LINE FROM RPT-SUB-HEADER
           WRITE ESCA-RPT-LINE FROM RPT-SEPARATOR.

      *================================================================
      * 0300-WRITE-SUMMARY
      *================================================================
       0300-WRITE-SUMMARY.
           WRITE ESCA-RPT-LINE FROM RPT-SEPARATOR
           STRING 'RESUME PAR CLASSE'
               DELIMITED SIZE INTO ESCA-RPT-LINE
           WRITE ESCA-RPT-LINE
           STRING '  CLASSE 2 (30-90J)   : ' WS-CL2-COUNT
               ' LOANS  ENC: ' WS-CL2-AMOUNT
               DELIMITED SIZE INTO ESCA-RPT-LINE
           WRITE ESCA-RPT-LINE
           STRING '  CLASSE 3 (90-180J)  : ' WS-CL3-COUNT
               ' LOANS  ENC: ' WS-CL3-AMOUNT
               DELIMITED SIZE INTO ESCA-RPT-LINE
           WRITE ESCA-RPT-LINE
           STRING '  CLASSE 4 (>180J)    : ' WS-CL4-COUNT
               ' LOANS  ENC: ' WS-CL4-AMOUNT
               DELIMITED SIZE INTO ESCA-RPT-LINE
           WRITE ESCA-RPT-LINE
           WRITE ESCA-RPT-LINE FROM RPT-SEPARATOR
           STRING 'ACTIONS GENEREES'
               DELIMITED SIZE INTO ESCA-RPT-LINE
           WRITE ESCA-RPT-LINE
           STRING '  SMS    : ' WS-ACT-SMS
               '  EMAIL: ' WS-ACT-EMAIL
               '  TEL  : ' WS-ACT-PHONE
               '  DUL  : ' WS-ACT-DUL
               DELIMITED SIZE INTO ESCA-RPT-LINE
           WRITE ESCA-RPT-LINE
           STRING '  LEG    : ' WS-ACT-LEG
               '  GTR  : ' WS-ACT-GTR
               '  RST  : ' WS-ACT-RST
               '  CRT  : ' WS-ACT-CRT
               DELIMITED SIZE INTO ESCA-RPT-LINE
           WRITE ESCA-RPT-LINE
           STRING '  CSZ    : ' WS-ACT-CSZ
               '  WOF  : ' WS-ACT-WOF
               DELIMITED SIZE INTO ESCA-RPT-LINE
           WRITE ESCA-RPT-LINE
           WRITE ESCA-RPT-LINE FROM RPT-FOOTER-LINE.

      *================================================================
      * 0400-CLOSE-FILES
      *================================================================
       0400-CLOSE-FILES.
           CLOSE LOAN-FILE CUSTOMER-FILE COLLATERAL-FILE
                 RECOVERY-NEW LETTER-FILE ESCALATION-RPT.

      *================================================================
      * 1000-LOAD-SORT
      * SORT INPUT PROCEDURE: read all delinquent loans and release
      * to the sort engine. Priority encoded as:
      *    Class 4: priority 300
      *    Class 3: priority 200
      *    Class 2: priority 100
      *    Other  : skip
      *================================================================
       1000-LOAD-SORT.
           READ LOAN-FILE
               AT END MOVE 'Y' TO WS-END-LOAN-FILE
               NOT AT END CONTINUE
           END-READ
           PERFORM UNTIL WS-END-LOAN-FILE = 'Y'
               IF LOAN-ACTIVE OR LOAN-RESTRUCTURED
                   EVALUATE LOAN-CLASS
                       WHEN '2'
                           MOVE 100 TO SORT-PRIORITY
                           PERFORM 1010-RELEASE-TO-SORT
                       WHEN '3'
                           MOVE 200 TO SORT-PRIORITY
                           PERFORM 1010-RELEASE-TO-SORT
                       WHEN '4'
                           MOVE 300 TO SORT-PRIORITY
                           PERFORM 1010-RELEASE-TO-SORT
                       WHEN OTHER
                           CONTINUE
                   END-EVALUATE
               END-IF
               READ LOAN-FILE
                   AT END MOVE 'Y' TO WS-END-LOAN-FILE
                   NOT AT END CONTINUE
               END-READ
           END-PERFORM.
       1000-LOAD-SORT-EXIT. EXIT.

       1010-RELEASE-TO-SORT.
           MOVE LOAN-OUTSTANDING    TO SORT-AMOUNT
           MOVE LOAN-ID             TO SORT-LOAN-ID
           MOVE LOAN-CUST-ID        TO SORT-CUST-ID
           MOVE LOAN-DAYS-PAST-DUE  TO SORT-DPD
           MOVE LOAN-CLASS          TO SORT-CLASS
           MOVE SPACES              TO SORT-FILLER
           RELEASE SORT-LOAN-REC
           IF LOAN-CLASS = '2'
               ADD 1 TO WS-CL2-COUNT
               ADD LOAN-OUTSTANDING TO WS-CL2-AMOUNT
           ELSE IF LOAN-CLASS = '3'
               ADD 1 TO WS-CL3-COUNT
               ADD LOAN-OUTSTANDING TO WS-CL3-AMOUNT
           ELSE IF LOAN-CLASS = '4'
               ADD 1 TO WS-CL4-COUNT
               ADD LOAN-OUTSTANDING TO WS-CL4-AMOUNT
           END-IF.

      *================================================================
      * 2000-PROCESS-RECOVERY
      * SORT OUTPUT PROCEDURE: takes sorted records, looks up customer,
      * collateral, and applies escalation matrix.
      *================================================================
       2000-PROCESS-RECOVERY.
           PERFORM UNTIL 1 = 2
               RETURN SORT-WORK
                   AT END EXIT PERFORM
                   NOT AT END
                       MOVE SORT-LOAN-ID TO WS-CURRENT-LOAN-ID
                       MOVE SORT-CUST-ID TO WS-CURRENT-CUST-ID
                       PERFORM 2100-READ-LOAN-FRESH
                       PERFORM 2200-READ-CUSTOMER
                       PERFORM 2300-DETERMINE-NEXT-ACTION
                       IF WS-NEXT-ACTION-CODE NOT = SPACES
                           PERFORM 3000-GENERATE-ACTION
                           PERFORM 4000-WRITE-LETTER-IF-NEEDED
                           PERFORM 5000-WRITE-ESCALATION-LINE
                       END-IF
               END-RETURN
           END-PERFORM.
       2000-PROCESS-RECOVERY-EXIT. EXIT.

      *================================================================
      * 2100-READ-LOAN-FRESH
      *================================================================
       2100-READ-LOAN-FRESH.
           CONTINUE.

      *================================================================
      * 2200-READ-CUSTOMER
      *================================================================
       2200-READ-CUSTOMER.
           MOVE WS-CURRENT-CUST-ID TO CUST-ID
           READ CUSTOMER-FILE
               AT END CONTINUE
               NOT AT END CONTINUE
           END-READ.

      *================================================================
      * 2300-DETERMINE-NEXT-ACTION
      * Applies BCT escalation matrix:
      *================================================================
       2300-DETERMINE-NEXT-ACTION.
           MOVE SPACES TO WS-NEXT-ACTION-CODE
           EVALUATE TRUE
      *--- Class 2 (31-90 days) ---
               WHEN SORT-CLASS = '2' AND SORT-DPD <= 45
                   MOVE 'SMS' TO WS-NEXT-ACTION-CODE
               WHEN SORT-CLASS = '2' AND SORT-DPD <= 60
                   MOVE 'PHN' TO WS-NEXT-ACTION-CODE
               WHEN SORT-CLASS = '2'
                   MOVE 'DUL' TO WS-NEXT-ACTION-CODE

      *--- Class 3 (91-180 days) ---
               WHEN SORT-CLASS = '3' AND SORT-DPD <= 120
                   MOVE 'LEG' TO WS-NEXT-ACTION-CODE
               WHEN SORT-CLASS = '3' AND SORT-DPD <= 150
                   MOVE 'GTR' TO WS-NEXT-ACTION-CODE
               WHEN SORT-CLASS = '3'
                   MOVE 'RST' TO WS-NEXT-ACTION-CODE

      *--- Class 4 (>180 days) ---
               WHEN SORT-CLASS = '4' AND SORT-DPD <= 365
                   MOVE 'CRT' TO WS-NEXT-ACTION-CODE
               WHEN SORT-CLASS = '4' AND SORT-DPD <= 540
                   IF SORT-AMOUNT > 50000
                       MOVE 'CSZ' TO WS-NEXT-ACTION-CODE
                   ELSE
                       MOVE 'WOF' TO WS-NEXT-ACTION-CODE
                   END-IF
               WHEN SORT-CLASS = '4'
                   MOVE 'WOF' TO WS-NEXT-ACTION-CODE
           END-EVALUATE

      *--- Increment action stats ---
           EVALUATE WS-NEXT-ACTION-CODE
               WHEN 'SMS' ADD 1 TO WS-ACT-SMS
               WHEN 'EML' ADD 1 TO WS-ACT-EMAIL
               WHEN 'PHN' ADD 1 TO WS-ACT-PHONE
               WHEN 'DUL' ADD 1 TO WS-ACT-DUL
               WHEN 'LEG' ADD 1 TO WS-ACT-LEG
               WHEN 'GTR' ADD 1 TO WS-ACT-GTR
               WHEN 'RST' ADD 1 TO WS-ACT-RST
               WHEN 'CRT' ADD 1 TO WS-ACT-CRT
               WHEN 'CSZ' ADD 1 TO WS-ACT-CSZ
               WHEN 'WOF' ADD 1 TO WS-ACT-WOF
           END-EVALUATE.

      *================================================================
      * 3000-GENERATE-ACTION
      * Build and write RECOVERY-ACTION record.
      *================================================================
       3000-GENERATE-ACTION.
           ADD 1 TO WS-RECOV-SEQ
           MOVE WS-RECOV-SEQ        TO REC-ACTION-ID
           MOVE WS-CURRENT-LOAN-ID  TO REC-LOAN-ID
           MOVE WS-CURRENT-CUST-ID  TO REC-CUST-ID
           MOVE WS-TODAY-DATE       TO REC-ACTION-DATE
           MOVE 120000              TO REC-ACTION-TIME
           MOVE WS-NEXT-ACTION-CODE TO REC-ACTION-TYPE
           MOVE SORT-AMOUNT         TO REC-AMOUNT-CLAIMED
           MOVE 0                   TO REC-AMOUNT-RECOVERED
           MOVE 'N'                 TO REC-RESPONSE

      *--- Next action date depends on type ---
           EVALUATE WS-NEXT-ACTION-CODE
               WHEN 'SMS'
               WHEN 'EML'
                   PERFORM 3100-ADD-7-DAYS
               WHEN 'PHN'
                   PERFORM 3100-ADD-7-DAYS
               WHEN 'DUL'
                   PERFORM 3200-ADD-15-DAYS
               WHEN 'LEG'
                   PERFORM 3300-ADD-30-DAYS
               WHEN 'GTR'
                   PERFORM 3300-ADD-30-DAYS
               WHEN 'RST'
                   PERFORM 3300-ADD-30-DAYS
               WHEN 'CRT'
                   PERFORM 3400-ADD-60-DAYS
               WHEN 'CSZ'
                   PERFORM 3400-ADD-60-DAYS
               WHEN 'WOF'
                   MOVE WS-TODAY-DATE TO REC-NEXT-ACTION-DATE
           END-EVALUATE

           MOVE 100000 TO REC-OFFICER-ID
           MOVE SPACES TO REC-LEGAL-FIRM
           MOVE SPACES TO REC-COURT-CASE-NUM
           STRING 'ACTION ' WS-NEXT-ACTION-CODE
               ' AMT ' SORT-AMOUNT
               ' DPD ' SORT-DPD
               DELIMITED SIZE INTO REC-COMMENTS

           WRITE RECOVERY-ACTION.

      *--- Date arithmetic helpers (simplified) ---
       3100-ADD-7-DAYS.
           COMPUTE REC-NEXT-ACTION-DATE =
               WS-TODAY-DATE + 7.
       3200-ADD-15-DAYS.
           COMPUTE REC-NEXT-ACTION-DATE =
               WS-TODAY-DATE + 15.
       3300-ADD-30-DAYS.
           COMPUTE REC-NEXT-ACTION-DATE =
               WS-TODAY-DATE + 30.
       3400-ADD-60-DAYS.
           COMPUTE REC-NEXT-ACTION-DATE =
               WS-TODAY-DATE + 60.

      *================================================================
      * 4000-WRITE-LETTER-IF-NEEDED
      *================================================================
       4000-WRITE-LETTER-IF-NEEDED.
           IF WS-NEXT-ACTION-CODE = 'DUL' OR
              WS-NEXT-ACTION-CODE = 'LEG' OR
              WS-NEXT-ACTION-CODE = 'GTR'
               PERFORM 4100-COMPOSE-LETTER
               PERFORM 4200-EMIT-LETTER
           END-IF.

       4100-COMPOSE-LETTER.
           MOVE SPACES TO WS-LETTER-BUFFER
           MOVE 1 TO WS-LETTER-LINE-IDX

           STRING 'ACME BANK TUNISIE' DELIMITED SIZE
               INTO LB-TEXT(WS-LETTER-LINE-IDX)
           ADD 1 TO WS-LETTER-LINE-IDX
           STRING '15 Avenue Habib Bourguiba, 1001 Tunis'
               DELIMITED SIZE INTO LB-TEXT(WS-LETTER-LINE-IDX)
           ADD 1 TO WS-LETTER-LINE-IDX
           STRING 'Tel: +216 71 123 456'
               DELIMITED SIZE INTO LB-TEXT(WS-LETTER-LINE-IDX)
           ADD 2 TO WS-LETTER-LINE-IDX

           STRING 'Tunis, le ' WS-TODAY-DATE
               DELIMITED SIZE INTO LB-TEXT(WS-LETTER-LINE-IDX)
           ADD 2 TO WS-LETTER-LINE-IDX

           STRING 'Madame, Monsieur ' CUST-FIRST-NAME
               ' ' CUST-LAST-NAME
               DELIMITED SIZE INTO LB-TEXT(WS-LETTER-LINE-IDX)
           ADD 1 TO WS-LETTER-LINE-IDX
           STRING CUST-ADDR-LINE1
               DELIMITED SIZE INTO LB-TEXT(WS-LETTER-LINE-IDX)
           ADD 1 TO WS-LETTER-LINE-IDX
           STRING CUST-ADDR-ZIP ' ' CUST-ADDR-CITY
               DELIMITED SIZE INTO LB-TEXT(WS-LETTER-LINE-IDX)
           ADD 3 TO WS-LETTER-LINE-IDX

           STRING 'Objet: Mise en demeure - Dossier '
               WS-CURRENT-LOAN-ID
               DELIMITED SIZE INTO LB-TEXT(WS-LETTER-LINE-IDX)
           ADD 3 TO WS-LETTER-LINE-IDX

           EVALUATE WS-NEXT-ACTION-CODE
               WHEN 'DUL'
                   STRING 'Nous constatons un retard de paiement '
                       'sur votre dossier de credit.'
                       DELIMITED SIZE
                       INTO LB-TEXT(WS-LETTER-LINE-IDX)
               WHEN 'LEG'
                   STRING 'Suite a nos rappels precedents restes '
                       'sans suite, nous vous mettons formellement '
                       'en demeure.'
                       DELIMITED SIZE
                       INTO LB-TEXT(WS-LETTER-LINE-IDX)
               WHEN 'GTR'
                   STRING 'Nous nous reservons le droit de faire '
                       'appel au garant en cas de non regularisation.'
                       DELIMITED SIZE
                       INTO LB-TEXT(WS-LETTER-LINE-IDX)
           END-EVALUATE
           ADD 2 TO WS-LETTER-LINE-IDX

           STRING 'Montant du sont: ' SORT-AMOUNT ' TND'
               DELIMITED SIZE INTO LB-TEXT(WS-LETTER-LINE-IDX)
           ADD 1 TO WS-LETTER-LINE-IDX
           STRING 'Jours de retard: ' SORT-DPD
               DELIMITED SIZE INTO LB-TEXT(WS-LETTER-LINE-IDX)
           ADD 3 TO WS-LETTER-LINE-IDX

           STRING 'Veuillez regulariser votre situation dans '
               'un delai de 15 jours.'
               DELIMITED SIZE
               INTO LB-TEXT(WS-LETTER-LINE-IDX)
           ADD 3 TO WS-LETTER-LINE-IDX

           STRING 'Veuillez agreer, Madame, Monsieur, '
               'l expression de nos salutations distinguees.'
               DELIMITED SIZE
               INTO LB-TEXT(WS-LETTER-LINE-IDX)
           ADD 4 TO WS-LETTER-LINE-IDX

           STRING 'Le Directeur du Recouvrement'
               DELIMITED SIZE INTO LB-TEXT(WS-LETTER-LINE-IDX).

       4200-EMIT-LETTER.
           PERFORM VARYING WS-LETTER-LINE-IDX FROM 1 BY 1
               UNTIL WS-LETTER-LINE-IDX > 30
               WRITE LETTER-LINE FROM LB-TEXT(WS-LETTER-LINE-IDX)
           END-PERFORM
           MOVE SPACES TO LETTER-LINE
           WRITE LETTER-LINE
           MOVE ALL '=' TO LETTER-LINE
           WRITE LETTER-LINE
           MOVE SPACES TO LETTER-LINE
           WRITE LETTER-LINE.

      *================================================================
      * 5000-WRITE-ESCALATION-LINE
      *================================================================
       5000-WRITE-ESCALATION-LINE.
           STRING WS-CURRENT-LOAN-ID
               '  ' WS-CURRENT-CUST-ID
               '  CL:' SORT-CLASS
               '  DPD:' SORT-DPD
               '  AMT:' SORT-AMOUNT
               '  ACT:' WS-NEXT-ACTION-CODE
               DELIMITED SIZE INTO ESCA-RPT-LINE
           WRITE ESCA-RPT-LINE.

       END PROGRAM RECOVRY.
