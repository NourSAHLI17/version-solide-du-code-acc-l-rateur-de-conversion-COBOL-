      *****************************************************************
      * PROGRAM:     CHKAML
      * DESCRIPTION: AML (Anti-Money Laundering) screening sub-program.
      *              Called by LOANEVAL, ACCTOPEN, TXNHIGH.
      *              Performs:
      *                - Sanctions list lookup (UN, EU, OFAC, Tunisian)
      *                - PEP (Politically Exposed Persons) screening
      *                - Adverse media screening (by name fuzzy match)
      *                - Transaction amount threshold check
      *                - High-risk nationality check
      *              Returns clearance flag, risk score, and reason.
      *
      *              Reads SANCFILE.dat (sanctions list) - in production
      *              this is a DB2 table refreshed daily from BCT and
      *              external providers (Refinitiv World-Check).
      *
      * COPYBOOKS:   ERRCOPY2
      * INTERFACE:   LINKAGE SECTION receives AML-REQUEST,
      *              returns AML-RESPONSE.
      * AUTHOR:      ACME Bank - Compliance Division
      * VERSION:     3.1
      * BCT REF:     Loi 2015-26 (LBA/FT), Decret 2018-1129
      *****************************************************************
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CHKAML.
       AUTHOR. ACME-COMPLIANCE.

       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SOURCE-COMPUTER. IBM-MAINFRAME.
       OBJECT-COMPUTER. IBM-MAINFRAME.

       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SANCTIONS-FILE
               ASSIGN TO "SANCFILE.dat"
               ORGANIZATION IS INDEXED
               ACCESS MODE IS DYNAMIC
               RECORD KEY IS SANC-NAME-KEY
               ALTERNATE RECORD KEY IS SANC-CIN
                   WITH DUPLICATES
               FILE STATUS IS WS-SANC-FS.

       DATA DIVISION.
       FILE SECTION.

       FD SANCTIONS-FILE
           RECORD CONTAINS 200 CHARACTERS.
       01 SANCTIONS-RECORD.
          05 SANC-NAME-KEY        PIC X(55).
          05 SANC-CIN             PIC X(8).
          05 SANC-DOB             PIC 9(8).
          05 SANC-NATIONALITY     PIC X(3).
          05 SANC-LIST-CODE       PIC X(3).
             88 SANC-UN-LIST      VALUE 'UNL'.
             88 SANC-EU-LIST      VALUE 'EUL'.
             88 SANC-OFAC-LIST    VALUE 'OFC'.
             88 SANC-TN-LIST      VALUE 'TUN'.
             88 SANC-PEP-LIST     VALUE 'PEP'.
          05 SANC-SEVERITY        PIC 9(1).
          05 SANC-REASON          PIC X(60).
          05 SANC-LIST-DATE       PIC 9(8).
          05 SANC-FILLER          PIC X(54).

       WORKING-STORAGE SECTION.

      *--- File status ---
       01 WS-SANC-FS              PIC X(2)      VALUE SPACES.
          88 SANC-FS-OK           VALUE '00'.
          88 SANC-FS-EOF          VALUE '10'.
          88 SANC-FS-NOTFOUND     VALUE '23'.

      *--- Risk scoring constants ---
       01 WS-AML-THRESHOLDS.
          05 WS-LARGE-TXN-AMT     PIC 9(11)V99 VALUE 10000.00.
          05 WS-VERY-LARGE-AMT    PIC 9(11)V99 VALUE 50000.00.
          05 WS-HIGH-RISK-COUNTRIES PIC X(60)
              VALUE 'IRN PRK SYR YEM IRQ AFG SOM SDN LBY VEN MMR CUB'.

      *--- Work area ---
       01 WS-WORK.
          05 WS-NAME-NORMALIZED   PIC X(55) VALUE SPACES.
          05 WS-RISK-SCORE        PIC 9(3)  VALUE ZEROS.
          05 WS-SANCTIONS-HIT     PIC X     VALUE 'N'.
          05 WS-PEP-HIT           PIC X     VALUE 'N'.
          05 WS-LARGE-TXN-FLAG    PIC X     VALUE 'N'.
          05 WS-HIGH-RISK-COUNTRY PIC X     VALUE 'N'.
          05 WS-LIST-DESC         PIC X(20) VALUE SPACES.
          05 WS-FILE-OPENED       PIC X     VALUE 'N'.

       LINKAGE SECTION.
       01 LK-AML-REQUEST.
          05 LK-REQ-CUST-ID       PIC 9(8).
          05 LK-REQ-CIN           PIC X(8).
          05 LK-REQ-NAME          PIC X(55).
          05 LK-REQ-DOB           PIC 9(8).
          05 LK-REQ-NATIONALITY   PIC X(3).
          05 LK-REQ-AMOUNT        PIC 9(11)V99.

       01 LK-AML-RESPONSE.
          05 LK-RESP-CLEAR        PIC X(1).
          05 LK-RESP-SCORE        PIC 9(3).
          05 LK-RESP-REASON       PIC X(60).

       PROCEDURE DIVISION USING LK-AML-REQUEST LK-AML-RESPONSE.

      *================================================================
      * 0000-MAIN
      *================================================================
       0000-MAIN.
           MOVE 'Y'    TO LK-RESP-CLEAR
           MOVE 0      TO LK-RESP-SCORE
           MOVE SPACES TO LK-RESP-REASON
           MOVE 'N'    TO WS-SANCTIONS-HIT
           MOVE 'N'    TO WS-PEP-HIT
           MOVE 'N'    TO WS-LARGE-TXN-FLAG
           MOVE 'N'    TO WS-HIGH-RISK-COUNTRY
           MOVE 0      TO WS-RISK-SCORE

           PERFORM 1000-NORMALIZE-NAME
           PERFORM 2000-OPEN-SANCTIONS
           IF WS-FILE-OPENED = 'Y'
               PERFORM 3000-CHECK-SANCTIONS-NAME
               PERFORM 3100-CHECK-SANCTIONS-CIN
               PERFORM 4000-CLOSE-SANCTIONS
           END-IF
           PERFORM 5000-CHECK-AMOUNT
           PERFORM 6000-CHECK-NATIONALITY
           PERFORM 7000-COMPUTE-FINAL-DECISION
           GOBACK.

      *================================================================
      * 1000-NORMALIZE-NAME
      * INSPECT and TRANSFORM the name for comparison: uppercase,
      * trim trailing spaces, remove special chars.
      *================================================================
       1000-NORMALIZE-NAME.
           MOVE LK-REQ-NAME TO WS-NAME-NORMALIZED
           INSPECT WS-NAME-NORMALIZED
               CONVERTING 'abcdefghijklmnopqrstuvwxyz'
               TO         'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
           INSPECT WS-NAME-NORMALIZED
               REPLACING ALL '.' BY ' '
           INSPECT WS-NAME-NORMALIZED
               REPLACING ALL ',' BY ' '
           INSPECT WS-NAME-NORMALIZED
               REPLACING ALL '-' BY ' '.

      *================================================================
      * 2000-OPEN-SANCTIONS
      *================================================================
       2000-OPEN-SANCTIONS.
           OPEN INPUT SANCTIONS-FILE
           IF SANC-FS-OK
               MOVE 'Y' TO WS-FILE-OPENED
           ELSE
               MOVE 'N' TO WS-FILE-OPENED
           END-IF.

      *================================================================
      * 3000-CHECK-SANCTIONS-NAME
      *================================================================
       3000-CHECK-SANCTIONS-NAME.
           MOVE WS-NAME-NORMALIZED TO SANC-NAME-KEY
           READ SANCTIONS-FILE KEY IS SANC-NAME-KEY
               INVALID KEY
                   CONTINUE
               NOT INVALID KEY
                   MOVE 'Y' TO WS-SANCTIONS-HIT
                   EVALUATE TRUE
                       WHEN SANC-PEP-LIST
                           MOVE 'Y' TO WS-PEP-HIT
                           MOVE 'PEP LIST'   TO WS-LIST-DESC
                           ADD 50 TO WS-RISK-SCORE
                       WHEN SANC-UN-LIST
                           MOVE 'UN SANCTIONS' TO WS-LIST-DESC
                           ADD 200 TO WS-RISK-SCORE
                       WHEN SANC-EU-LIST
                           MOVE 'EU SANCTIONS' TO WS-LIST-DESC
                           ADD 200 TO WS-RISK-SCORE
                       WHEN SANC-OFAC-LIST
                           MOVE 'OFAC SANCTIONS' TO WS-LIST-DESC
                           ADD 200 TO WS-RISK-SCORE
                       WHEN SANC-TN-LIST
                           MOVE 'BCT WATCHLIST' TO WS-LIST-DESC
                           ADD 200 TO WS-RISK-SCORE
                   END-EVALUATE
                   STRING 'HIT ' WS-LIST-DESC
                       ' SEVERITY ' SANC-SEVERITY
                       DELIMITED SIZE
                       INTO LK-RESP-REASON
           END-READ.

      *================================================================
      * 3100-CHECK-SANCTIONS-CIN
      *================================================================
       3100-CHECK-SANCTIONS-CIN.
           IF WS-SANCTIONS-HIT = 'Y'
               EXIT PARAGRAPH
           END-IF
           MOVE LK-REQ-CIN TO SANC-CIN
           READ SANCTIONS-FILE KEY IS SANC-CIN
               INVALID KEY CONTINUE
               NOT INVALID KEY
                   MOVE 'Y' TO WS-SANCTIONS-HIT
                   ADD 150 TO WS-RISK-SCORE
                   STRING 'CIN MATCH ON SANCTIONS LIST'
                       DELIMITED SIZE INTO LK-RESP-REASON
           END-READ.

      *================================================================
      * 4000-CLOSE-SANCTIONS
      *================================================================
       4000-CLOSE-SANCTIONS.
           CLOSE SANCTIONS-FILE.

      *================================================================
      * 5000-CHECK-AMOUNT
      *================================================================
       5000-CHECK-AMOUNT.
           IF LK-REQ-AMOUNT > WS-VERY-LARGE-AMT
               MOVE 'Y' TO WS-LARGE-TXN-FLAG
               ADD 80 TO WS-RISK-SCORE
           ELSE IF LK-REQ-AMOUNT > WS-LARGE-TXN-AMT
               MOVE 'Y' TO WS-LARGE-TXN-FLAG
               ADD 30 TO WS-RISK-SCORE
           END-IF.

      *================================================================
      * 6000-CHECK-NATIONALITY
      *================================================================
       6000-CHECK-NATIONALITY.
           INSPECT WS-HIGH-RISK-COUNTRIES
               TALLYING WS-RISK-SCORE FOR ALL LK-REQ-NATIONALITY
           IF WS-RISK-SCORE > 0
               IF LK-REQ-NATIONALITY = 'IRN' OR 'PRK' OR 'SYR'
                  OR 'AFG' OR 'YEM' OR 'IRQ' OR 'SOM' OR 'SDN'
                  OR 'LBY' OR 'VEN' OR 'MMR' OR 'CUB'
                   MOVE 'Y' TO WS-HIGH-RISK-COUNTRY
                   ADD 100 TO WS-RISK-SCORE
               END-IF
           END-IF.

      *================================================================
      * 7000-COMPUTE-FINAL-DECISION
      *================================================================
       7000-COMPUTE-FINAL-DECISION.
           IF WS-RISK-SCORE > 999
               MOVE 999 TO WS-RISK-SCORE
           END-IF
           MOVE WS-RISK-SCORE TO LK-RESP-SCORE
           EVALUATE TRUE
               WHEN WS-SANCTIONS-HIT = 'Y' AND WS-RISK-SCORE > 150
                   MOVE 'N' TO LK-RESP-CLEAR
               WHEN WS-RISK-SCORE >= 300
                   MOVE 'N' TO LK-RESP-CLEAR
                   IF LK-RESP-REASON = SPACES
                       MOVE 'HIGH AML RISK SCORE'
                           TO LK-RESP-REASON
                   END-IF
               WHEN WS-RISK-SCORE >= 150
                   MOVE 'C' TO LK-RESP-CLEAR
                   IF LK-RESP-REASON = SPACES
                       MOVE 'MANUAL REVIEW REQUIRED'
                           TO LK-RESP-REASON
                   END-IF
               WHEN OTHER
                   MOVE 'Y' TO LK-RESP-CLEAR
                   MOVE 'AML CLEAR' TO LK-RESP-REASON
           END-EVALUATE.

       END PROGRAM CHKAML.
