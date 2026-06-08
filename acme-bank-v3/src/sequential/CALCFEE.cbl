      *****************************************************************
      * PROGRAM:     CALCFEE
      * DESCRIPTION: Fee and tax calculation sub-program.
      *              Called by LOANEVAL and TXNHIGH.
      *              Computes:
      *                - File opening fee (frais de dossier)
      *                - Insurance premium (ADI - assurance
      *                - deces invalidite)
      *                - Stamp tax (timbre fiscal)
      *                - Total upfront cost
      *              All amounts in millimes (TND has 3 decimal places).
      *
      * COPYBOOKS:   None (self-contained)
      * INTERFACE:   LINKAGE SECTION takes loan type, amount, rate.
      *              Returns 4 amounts: file fee, tax, insurance, total.
      * AUTHOR:      ACME Bank - Pricing Division
      * VERSION:     2.0
      *****************************************************************
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALCFEE.
       AUTHOR. ACME-PRICING.

       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SOURCE-COMPUTER. IBM-MAINFRAME.
       OBJECT-COMPUTER. IBM-MAINFRAME.
       SPECIAL-NAMES.
           DECIMAL-POINT IS COMMA.

       DATA DIVISION.
       WORKING-STORAGE SECTION.

       01 WS-FEE-PARAMS.
          05 WS-FILE-FEE-RATE-CON  PIC 9(2)V9(4) VALUE 1,5000.
          05 WS-FILE-FEE-RATE-IMM  PIC 9(2)V9(4) VALUE 1,0000.
          05 WS-FILE-FEE-RATE-AUT  PIC 9(2)V9(4) VALUE 2,0000.
          05 WS-FILE-FEE-RATE-PRO  PIC 9(2)V9(4) VALUE 0,7500.
          05 WS-FILE-FEE-RATE-REV  PIC 9(2)V9(4) VALUE 2,5000.
          05 WS-FILE-FEE-MIN       PIC 9(7)V99   VALUE 50,000.
          05 WS-FILE-FEE-MAX       PIC 9(7)V99   VALUE 5000,000.
          05 WS-INSURANCE-RATE     PIC 9(2)V9(4) VALUE 0,4500.
          05 WS-TVA-RATE           PIC 9(2)V99   VALUE 19,00.
          05 WS-TIMBRE-FIXED       PIC 9(5)V99   VALUE 5,000.

       01 WS-WORK.
          05 WS-FEE-RATE           PIC 9(2)V9(4) VALUE ZEROS.
          05 WS-FEE-GROSS          PIC 9(7)V99   VALUE ZEROS.
          05 WS-FEE-TVA            PIC 9(7)V99   VALUE ZEROS.

       LINKAGE SECTION.
       01 LK-FEE-REQUEST.
          05 LK-REQ-LOAN-TYPE      PIC X(3).
          05 LK-REQ-AMOUNT         PIC 9(11)V99.
          05 LK-REQ-RATE           PIC 9(2)V9(4).

       01 LK-FEE-RESPONSE.
          05 LK-RESP-FILE-FEE      PIC 9(7)V99.
          05 LK-RESP-TAX           PIC 9(7)V99.
          05 LK-RESP-INSURANCE     PIC 9(7)V99.
          05 LK-RESP-TOTAL         PIC 9(9)V99.

       PROCEDURE DIVISION USING LK-FEE-REQUEST LK-FEE-RESPONSE.

       0000-MAIN.
           MOVE ZEROS TO LK-RESP-FILE-FEE LK-RESP-TAX
                        LK-RESP-INSURANCE LK-RESP-TOTAL

           PERFORM 1000-SELECT-FEE-RATE
           PERFORM 2000-COMPUTE-FILE-FEE
           PERFORM 3000-COMPUTE-INSURANCE
           PERFORM 4000-COMPUTE-TAX
           PERFORM 5000-COMPUTE-TOTAL
           GOBACK.

       1000-SELECT-FEE-RATE.
           EVALUATE LK-REQ-LOAN-TYPE
               WHEN 'CON' MOVE WS-FILE-FEE-RATE-CON TO WS-FEE-RATE
               WHEN 'IMM' MOVE WS-FILE-FEE-RATE-IMM TO WS-FEE-RATE
               WHEN 'AUT' MOVE WS-FILE-FEE-RATE-AUT TO WS-FEE-RATE
               WHEN 'PRO' MOVE WS-FILE-FEE-RATE-PRO TO WS-FEE-RATE
               WHEN 'REV' MOVE WS-FILE-FEE-RATE-REV TO WS-FEE-RATE
               WHEN OTHER MOVE WS-FILE-FEE-RATE-CON TO WS-FEE-RATE
           END-EVALUATE.

       2000-COMPUTE-FILE-FEE.
           COMPUTE WS-FEE-GROSS ROUNDED =
               LK-REQ-AMOUNT * WS-FEE-RATE / 100
           IF WS-FEE-GROSS < WS-FILE-FEE-MIN
               MOVE WS-FILE-FEE-MIN TO WS-FEE-GROSS
           END-IF
           IF WS-FEE-GROSS > WS-FILE-FEE-MAX
               MOVE WS-FILE-FEE-MAX TO WS-FEE-GROSS
           END-IF
           MOVE WS-FEE-GROSS TO LK-RESP-FILE-FEE.

       3000-COMPUTE-INSURANCE.
           IF LK-REQ-LOAN-TYPE = 'IMM' OR
              LK-REQ-LOAN-TYPE = 'AUT' OR
              LK-REQ-LOAN-TYPE = 'CON'
               COMPUTE LK-RESP-INSURANCE ROUNDED =
                   LK-REQ-AMOUNT * WS-INSURANCE-RATE / 100
           ELSE
               MOVE 0 TO LK-RESP-INSURANCE
           END-IF.

       4000-COMPUTE-TAX.
           COMPUTE WS-FEE-TVA ROUNDED =
               LK-RESP-FILE-FEE * WS-TVA-RATE / 100
           COMPUTE LK-RESP-TAX =
               WS-FEE-TVA + WS-TIMBRE-FIXED.

       5000-COMPUTE-TOTAL.
           COMPUTE LK-RESP-TOTAL =
               LK-RESP-FILE-FEE +
               LK-RESP-INSURANCE +
               LK-RESP-TAX.

       END PROGRAM CALCFEE.
