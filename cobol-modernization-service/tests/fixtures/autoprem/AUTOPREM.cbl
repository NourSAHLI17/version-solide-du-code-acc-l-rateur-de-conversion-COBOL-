*****************************************************************
      * PROGRAM:     AUTOPREM
      * DESCRIPTION: Auto insurance premium calculator for STAR Assurance
      *              (Tunisian insurer). Computes the annual premium for
      *              a personal auto policy using:
      *                - Base rate by vehicle category (5 categories)
      *                - Driver age coefficient (4 brackets)
      *                - Driver experience bonus/malus
      *                - Vehicle power coefficient (CV fiscaux)
      *                - Coverage type (TR / TC / TI)
      *                - Bonus-malus history (CRM coefficient)
      *                - Regional risk factor (governorate)
      *                - Taxes: TVA 19% + parafiscal 5%
      *
      *              Input: hardcoded test cases in WORKING-STORAGE
      *                     (10 sample quotes covering edge cases)
      *              Output: DISPLAY a formatted quote for each case
      *
      *              Self-contained, no files, no sub-programs, no SQL.
      *              Single-program test case for converter validation.
      *
      * BUSINESS REF: Code des Assurances Tunisien, Article 65
      *               Tarif Reference RC Auto 2024 (FTUSA)
      * AUTHOR:      STAR Assurance - Tarification IT
      * VERSION:     1.4
      *****************************************************************
       IDENTIFICATION DIVISION.
       PROGRAM-ID. AUTOPREM.
       AUTHOR. STAR-TARIFICATION.
       DATE-WRITTEN. 2024-03-10.

       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SOURCE-COMPUTER. IBM-MAINFRAME.
       OBJECT-COMPUTER. IBM-MAINFRAME.

       DATA DIVISION.
       WORKING-STORAGE SECTION.

      *================================================================
      * INPUT: Quote requests (10 hardcoded test cases)
      *================================================================
       01 WS-QUOTE-TABLE.
          05 WS-QUOTE OCCURS 10 TIMES INDEXED BY Q-IDX.
             10 QT-QUOTE-ID         PIC 9(8).
             10 QT-CLIENT-NAME      PIC X(40).
             10 QT-DRIVER-AGE       PIC 9(3).
             10 QT-LICENSE-YEARS    PIC 9(2).
             10 QT-VEHICLE-CAT      PIC X(2).
                88 CAT-TOURISME     VALUE 'TR'.
                88 CAT-UTILITAIRE   VALUE 'UT'.
                88 CAT-MOTO         VALUE 'MT'.
                88 CAT-CAMION       VALUE 'CM'.
                88 CAT-LUXE         VALUE 'LX'.
             10 QT-VEHICLE-POWER    PIC 9(2).
             10 QT-VEHICLE-VALUE    PIC 9(8)V99.
             10 QT-COVERAGE         PIC X(2).
                88 COV-RESPONS-CIV  VALUE 'RC'.
                88 COV-TIERS-COLL   VALUE 'TC'.
                88 COV-TOUS-RISQUES VALUE 'TI'.
             10 QT-CRM-COEF         PIC 9(1)V99.
             10 QT-GOVERNORATE      PIC X(3).
             10 QT-ACCIDENTS-3Y     PIC 9(1).

      *================================================================
      * OUTPUT: Computed premium per quote
      *================================================================
       01 WS-PREMIUM-TABLE.
          05 WS-PREMIUM OCCURS 10 TIMES INDEXED BY P-IDX.
             10 PR-QUOTE-ID         PIC 9(8)      VALUE ZEROS.
             10 PR-BASE-PREMIUM     PIC 9(7)V999  VALUE ZEROS.
             10 PR-AGE-COEF         PIC 9(1)V99   VALUE ZEROS.
             10 PR-POWER-COEF       PIC 9(1)V99   VALUE ZEROS.
             10 PR-COVERAGE-COEF    PIC 9(1)V99   VALUE ZEROS.
             10 PR-REGION-COEF      PIC 9(1)V99   VALUE ZEROS.
             10 PR-ACCIDENT-LOAD    PIC 9(1)V99   VALUE ZEROS.
             10 PR-NET-PREMIUM      PIC 9(7)V999  VALUE ZEROS.
             10 PR-TVA              PIC 9(7)V999  VALUE ZEROS.
             10 PR-PARAFISCAL       PIC 9(7)V999  VALUE ZEROS.
             10 PR-TOTAL-PREMIUM    PIC 9(7)V999  VALUE ZEROS.
             10 PR-DECISION         PIC X(10)     VALUE SPACES.
                88 PR-ACCEPTED      VALUE 'ACCEPTE'.
                88 PR-REJECTED      VALUE 'REFUSE'.
                88 PR-MANUAL        VALUE 'MANUEL'.
             10 PR-REJECTION-REASON PIC X(50)     VALUE SPACES.

      *================================================================
      * Base rates by vehicle category (TND per year before coefficients)
      *================================================================
       01 WS-BASE-RATES.
          05 WS-RATE-TOURISME       PIC 9(5)V99 VALUE 480.00.
          05 WS-RATE-UTILITAIRE     PIC 9(5)V99 VALUE 620.00.
          05 WS-RATE-MOTO           PIC 9(5)V99 VALUE 320.00.
          05 WS-RATE-CAMION         PIC 9(5)V99 VALUE 950.00.
          05 WS-RATE-LUXE           PIC 9(5)V99 VALUE 1850.00.

      *================================================================
      * Tax rates and thresholds
      *================================================================
       01 WS-CONSTANTS.
          05 WS-TVA-RATE            PIC 9(2)V99 VALUE 19.00.
          05 WS-PARAFISCAL-RATE     PIC 9(2)V99 VALUE 5.00.
          05 WS-MIN-DRIVER-AGE      PIC 9(2)    VALUE 18.
          05 WS-MAX-DRIVER-AGE      PIC 9(2)    VALUE 80.
          05 WS-HIGH-RISK-LIMIT     PIC 9(1)    VALUE 3.
          05 WS-MIN-PREMIUM-MILL    PIC 9(7)V99 VALUE 250.00.
          05 WS-MAX-PREMIUM-MILL    PIC 9(7)V99 VALUE 25000.00.

      *================================================================
      * Working fields
      *================================================================
       01 WS-WORK.
          05 WS-CURRENT-IDX         PIC 9(2)    VALUE ZEROS.
          05 WS-SUBTOTAL            PIC 9(7)V99 VALUE ZEROS.
          05 WS-TOTAL-NET           PIC 9(9)V99 VALUE ZEROS.
          05 WS-TOTAL-GROSS         PIC 9(9)V99 VALUE ZEROS.
          05 WS-ACCEPTED-COUNT      PIC 9(3)    VALUE ZEROS.
          05 WS-REJECTED-COUNT      PIC 9(3)    VALUE ZEROS.
          05 WS-MANUAL-COUNT        PIC 9(3)    VALUE ZEROS.

      *--- Display fields (numeric edited) ---
       01 WS-DISP.
          05 WS-DISP-QUOTE          PIC 9(8)        VALUE ZEROS.
          05 WS-DISP-AMOUNT         PIC ZZ,ZZZ.999  VALUE ZEROS.
          05 WS-DISP-COEF           PIC Z.99        VALUE ZEROS.
          05 WS-DISP-AGE            PIC ZZ9         VALUE ZEROS.
          05 WS-DISP-POWER          PIC Z9          VALUE ZEROS.
          05 WS-DISP-PCT            PIC Z9.99       VALUE ZEROS.

       PROCEDURE DIVISION.

      *================================================================
      * 0000-MAIN
      *================================================================
       0000-MAIN.
           DISPLAY ' '
           DISPLAY '======================================='
           DISPLAY 'STAR ASSURANCE - CALCUL PRIMES AUTO'
           DISPLAY 'Version 1.4 - Tarif 2024'
           DISPLAY '======================================='
           DISPLAY ' '
           PERFORM 1000-LOAD-TEST-CASES
           PERFORM 2000-PROCESS-ALL-QUOTES
           PERFORM 3000-DISPLAY-SUMMARY
           STOP RUN.

      *================================================================
      * 1000-LOAD-TEST-CASES
      * Load 10 sample quotes covering realistic edge cases.
      *================================================================
       1000-LOAD-TEST-CASES.
      *--- Quote 1: Young driver, basic tourism vehicle, Tunis ---
           MOVE 10000001 TO QT-QUOTE-ID(1)
           MOVE 'BENSALAH AHMED' TO QT-CLIENT-NAME(1)
           MOVE 22  TO QT-DRIVER-AGE(1)
           MOVE 02  TO QT-LICENSE-YEARS(1)
           MOVE 'TR' TO QT-VEHICLE-CAT(1)
           MOVE 06  TO QT-VEHICLE-POWER(1)
           MOVE 25000.00 TO QT-VEHICLE-VALUE(1)
           MOVE 'RC' TO QT-COVERAGE(1)
           MOVE 1.00 TO QT-CRM-COEF(1)
           MOVE 'TUN' TO QT-GOVERNORATE(1)
           MOVE 0 TO QT-ACCIDENTS-3Y(1)

      *--- Quote 2: Experienced driver, family car, Sfax ---
           MOVE 10000002 TO QT-QUOTE-ID(2)
           MOVE 'TRABELSI FATMA' TO QT-CLIENT-NAME(2)
           MOVE 45 TO QT-DRIVER-AGE(2)
           MOVE 22 TO QT-LICENSE-YEARS(2)
           MOVE 'TR' TO QT-VEHICLE-CAT(2)
           MOVE 08 TO QT-VEHICLE-POWER(2)
           MOVE 48000.00 TO QT-VEHICLE-VALUE(2)
           MOVE 'TC' TO QT-COVERAGE(2)
           MOVE 0.50 TO QT-CRM-COEF(2)
           MOVE 'SFX' TO QT-GOVERNORATE(2)
           MOVE 0 TO QT-ACCIDENTS-3Y(2)

      *--- Quote 3: Luxury vehicle full coverage ---
           MOVE 10000003 TO QT-QUOTE-ID(3)
           MOVE 'CHAOUACHI MOEZ' TO QT-CLIENT-NAME(3)
           MOVE 52 TO QT-DRIVER-AGE(3)
           MOVE 30 TO QT-LICENSE-YEARS(3)
           MOVE 'LX' TO QT-VEHICLE-CAT(3)
           MOVE 14 TO QT-VEHICLE-POWER(3)
           MOVE 185000.00 TO QT-VEHICLE-VALUE(3)
           MOVE 'TI' TO QT-COVERAGE(3)
           MOVE 0.55 TO QT-CRM-COEF(3)
           MOVE 'TUN' TO QT-GOVERNORATE(3)
           MOVE 0 TO QT-ACCIDENTS-3Y(3)

      *--- Quote 4: Motorcycle, young rider ---
           MOVE 10000004 TO QT-QUOTE-ID(4)
           MOVE 'GHARBI KARIM' TO QT-CLIENT-NAME(4)
           MOVE 25 TO QT-DRIVER-AGE(4)
           MOVE 05 TO QT-LICENSE-YEARS(4)
           MOVE 'MT' TO QT-VEHICLE-CAT(4)
           MOVE 04 TO QT-VEHICLE-POWER(4)
           MOVE 9500.00 TO QT-VEHICLE-VALUE(4)
           MOVE 'RC' TO QT-COVERAGE(4)
           MOVE 1.00 TO QT-CRM-COEF(4)
           MOVE 'SOU' TO QT-GOVERNORATE(4)
           MOVE 1 TO QT-ACCIDENTS-3Y(4)

      *--- Quote 5: Commercial truck ---
           MOVE 10000005 TO QT-QUOTE-ID(5)
           MOVE 'TRANSPORT BELHAJ SARL' TO QT-CLIENT-NAME(5)
           MOVE 38 TO QT-DRIVER-AGE(5)
           MOVE 15 TO QT-LICENSE-YEARS(5)
           MOVE 'CM' TO QT-VEHICLE-CAT(5)
           MOVE 20 TO QT-VEHICLE-POWER(5)
           MOVE 145000.00 TO QT-VEHICLE-VALUE(5)
           MOVE 'TC' TO QT-COVERAGE(5)
           MOVE 0.85 TO QT-CRM-COEF(5)
           MOVE 'BIZ' TO QT-GOVERNORATE(5)
           MOVE 0 TO QT-ACCIDENTS-3Y(5)

      *--- Quote 6: Under-age driver (REJECTED) ---
           MOVE 10000006 TO QT-QUOTE-ID(6)
           MOVE 'JEBALI MEHDI' TO QT-CLIENT-NAME(6)
           MOVE 17 TO QT-DRIVER-AGE(6)
           MOVE 00 TO QT-LICENSE-YEARS(6)
           MOVE 'TR' TO QT-VEHICLE-CAT(6)
           MOVE 05 TO QT-VEHICLE-POWER(6)
           MOVE 18000.00 TO QT-VEHICLE-VALUE(6)
           MOVE 'RC' TO QT-COVERAGE(6)
           MOVE 1.00 TO QT-CRM-COEF(6)
           MOVE 'TUN' TO QT-GOVERNORATE(6)
           MOVE 0 TO QT-ACCIDENTS-3Y(6)

      *--- Quote 7: High accident history (MANUAL REVIEW) ---
           MOVE 10000007 TO QT-QUOTE-ID(7)
           MOVE 'BOUAZIZ NESRINE' TO QT-CLIENT-NAME(7)
           MOVE 28 TO QT-DRIVER-AGE(7)
           MOVE 08 TO QT-LICENSE-YEARS(7)
           MOVE 'TR' TO QT-VEHICLE-CAT(7)
           MOVE 07 TO QT-VEHICLE-POWER(7)
           MOVE 32000.00 TO QT-VEHICLE-VALUE(7)
           MOVE 'TC' TO QT-COVERAGE(7)
           MOVE 2.50 TO QT-CRM-COEF(7)
           MOVE 'NAB' TO QT-GOVERNORATE(7)
           MOVE 4 TO QT-ACCIDENTS-3Y(7)

      *--- Quote 8: Senior driver, modest car ---
           MOVE 10000008 TO QT-QUOTE-ID(8)
           MOVE 'DRIDI RIDHA' TO QT-CLIENT-NAME(8)
           MOVE 68 TO QT-DRIVER-AGE(8)
           MOVE 45 TO QT-LICENSE-YEARS(8)
           MOVE 'TR' TO QT-VEHICLE-CAT(8)
           MOVE 05 TO QT-VEHICLE-POWER(8)
           MOVE 22000.00 TO QT-VEHICLE-VALUE(8)
           MOVE 'TI' TO QT-COVERAGE(8)
           MOVE 0.50 TO QT-CRM-COEF(8)
           MOVE 'KEF' TO QT-GOVERNORATE(8)
           MOVE 0 TO QT-ACCIDENTS-3Y(8)

      *--- Quote 9: Utility vehicle, small business ---
           MOVE 10000009 TO QT-QUOTE-ID(9)
           MOVE 'KHELIFA SLIM' TO QT-CLIENT-NAME(9)
           MOVE 35 TO QT-DRIVER-AGE(9)
           MOVE 12 TO QT-LICENSE-YEARS(9)
           MOVE 'UT' TO QT-VEHICLE-CAT(9)
           MOVE 10 TO QT-VEHICLE-POWER(9)
           MOVE 65000.00 TO QT-VEHICLE-VALUE(9)
           MOVE 'TC' TO QT-COVERAGE(9)
           MOVE 0.75 TO QT-CRM-COEF(9)
           MOVE 'SFX' TO QT-GOVERNORATE(9)
           MOVE 1 TO QT-ACCIDENTS-3Y(9)

      *--- Quote 10: Over age limit (REJECTED) ---
           MOVE 10000010 TO QT-QUOTE-ID(10)
           MOVE 'HAMROUNI LEILA' TO QT-CLIENT-NAME(10)
           MOVE 82 TO QT-DRIVER-AGE(10)
           MOVE 50 TO QT-LICENSE-YEARS(10)
           MOVE 'TR' TO QT-VEHICLE-CAT(10)
           MOVE 06 TO QT-VEHICLE-POWER(10)
           MOVE 28000.00 TO QT-VEHICLE-VALUE(10)
           MOVE 'TC' TO QT-COVERAGE(10)
           MOVE 0.50 TO QT-CRM-COEF(10)
           MOVE 'TUN' TO QT-GOVERNORATE(10)
           MOVE 0 TO QT-ACCIDENTS-3Y(10).

      *================================================================
      * 2000-PROCESS-ALL-QUOTES
      *================================================================
       2000-PROCESS-ALL-QUOTES.
           PERFORM VARYING WS-CURRENT-IDX FROM 1 BY 1
               UNTIL WS-CURRENT-IDX > 10
               PERFORM 2100-VALIDATE-QUOTE
               IF PR-DECISION(WS-CURRENT-IDX) = 'REFUSE'
                   PERFORM 4000-DISPLAY-REJECTED
               ELSE
                   PERFORM 2200-COMPUTE-PREMIUM
                   PERFORM 2300-APPLY-LIMITS
                   PERFORM 2400-COMPUTE-TAXES
                   PERFORM 2500-FINAL-DECISION
                   PERFORM 4100-DISPLAY-QUOTE
               END-IF
           END-PERFORM.

      *================================================================
      * 2100-VALIDATE-QUOTE
      * Reject clearly invalid quotes upfront
      *================================================================
       2100-VALIDATE-QUOTE.
           MOVE QT-QUOTE-ID(WS-CURRENT-IDX)
               TO PR-QUOTE-ID(WS-CURRENT-IDX)
           MOVE SPACES TO PR-REJECTION-REASON(WS-CURRENT-IDX)
           EVALUATE TRUE
               WHEN QT-DRIVER-AGE(WS-CURRENT-IDX) < WS-MIN-DRIVER-AGE
                   MOVE 'REFUSE' TO PR-DECISION(WS-CURRENT-IDX)
                   MOVE 'AGE CONDUCTEUR INFERIEUR A 18 ANS'
                       TO PR-REJECTION-REASON(WS-CURRENT-IDX)
                   ADD 1 TO WS-REJECTED-COUNT
               WHEN QT-DRIVER-AGE(WS-CURRENT-IDX) > WS-MAX-DRIVER-AGE
                   MOVE 'REFUSE' TO PR-DECISION(WS-CURRENT-IDX)
                   MOVE 'AGE CONDUCTEUR DEPASSE 80 ANS'
                       TO PR-REJECTION-REASON(WS-CURRENT-IDX)
                   ADD 1 TO WS-REJECTED-COUNT
               WHEN QT-LICENSE-YEARS(WS-CURRENT-IDX) = 0
                   MOVE 'REFUSE' TO PR-DECISION(WS-CURRENT-IDX)
                   MOVE 'PERMIS DE CONDUIRE REQUIS'
                       TO PR-REJECTION-REASON(WS-CURRENT-IDX)
                   ADD 1 TO WS-REJECTED-COUNT
               WHEN QT-CRM-COEF(WS-CURRENT-IDX) > 3.50
                   MOVE 'REFUSE' TO PR-DECISION(WS-CURRENT-IDX)
                   MOVE 'COEFFICIENT CRM TROP ELEVE'
                       TO PR-REJECTION-REASON(WS-CURRENT-IDX)
                   ADD 1 TO WS-REJECTED-COUNT
               WHEN OTHER
                   CONTINUE
           END-EVALUATE.

      *================================================================
      * 2200-COMPUTE-PREMIUM
      *================================================================
       2200-COMPUTE-PREMIUM.
           PERFORM 2210-SET-BASE-RATE
           PERFORM 2220-COMPUTE-AGE-COEF
           PERFORM 2230-COMPUTE-POWER-COEF
           PERFORM 2240-COMPUTE-COVERAGE-COEF
           PERFORM 2250-COMPUTE-REGION-COEF
           PERFORM 2260-COMPUTE-ACCIDENT-LOAD
           COMPUTE PR-NET-PREMIUM(WS-CURRENT-IDX) ROUNDED =
               PR-BASE-PREMIUM(WS-CURRENT-IDX)
             * PR-AGE-COEF(WS-CURRENT-IDX)
             * PR-POWER-COEF(WS-CURRENT-IDX)
             * PR-COVERAGE-COEF(WS-CURRENT-IDX)
             * PR-REGION-COEF(WS-CURRENT-IDX)
             * QT-CRM-COEF(WS-CURRENT-IDX)
             + PR-ACCIDENT-LOAD(WS-CURRENT-IDX).

       2210-SET-BASE-RATE.
           EVALUATE QT-VEHICLE-CAT(WS-CURRENT-IDX)
               WHEN 'TR'
                   MOVE WS-RATE-TOURISME
                       TO PR-BASE-PREMIUM(WS-CURRENT-IDX)
               WHEN 'UT'
                   MOVE WS-RATE-UTILITAIRE
                       TO PR-BASE-PREMIUM(WS-CURRENT-IDX)
               WHEN 'MT'
                   MOVE WS-RATE-MOTO
                       TO PR-BASE-PREMIUM(WS-CURRENT-IDX)
               WHEN 'CM'
                   MOVE WS-RATE-CAMION
                       TO PR-BASE-PREMIUM(WS-CURRENT-IDX)
               WHEN 'LX'
                   MOVE WS-RATE-LUXE
                       TO PR-BASE-PREMIUM(WS-CURRENT-IDX)
               WHEN OTHER
                   MOVE WS-RATE-TOURISME
                       TO PR-BASE-PREMIUM(WS-CURRENT-IDX)
           END-EVALUATE.

       2220-COMPUTE-AGE-COEF.
           EVALUATE TRUE
               WHEN QT-DRIVER-AGE(WS-CURRENT-IDX) < 25
                   MOVE 1.60 TO PR-AGE-COEF(WS-CURRENT-IDX)
               WHEN QT-DRIVER-AGE(WS-CURRENT-IDX) < 30
                   MOVE 1.25 TO PR-AGE-COEF(WS-CURRENT-IDX)
               WHEN QT-DRIVER-AGE(WS-CURRENT-IDX) < 65
                   MOVE 1.00 TO PR-AGE-COEF(WS-CURRENT-IDX)
               WHEN OTHER
                   MOVE 1.30 TO PR-AGE-COEF(WS-CURRENT-IDX)
           END-EVALUATE
      *--- Reduce for experience (max 20 pct reduction) ---
           IF QT-LICENSE-YEARS(WS-CURRENT-IDX) >= 10 AND
              QT-DRIVER-AGE(WS-CURRENT-IDX) < 65
               COMPUTE PR-AGE-COEF(WS-CURRENT-IDX) =
                   PR-AGE-COEF(WS-CURRENT-IDX) * 0.85
           END-IF.

       2230-COMPUTE-POWER-COEF.
           EVALUATE TRUE
               WHEN QT-VEHICLE-POWER(WS-CURRENT-IDX) <= 4
                   MOVE 0.85 TO PR-POWER-COEF(WS-CURRENT-IDX)
               WHEN QT-VEHICLE-POWER(WS-CURRENT-IDX) <= 7
                   MOVE 1.00 TO PR-POWER-COEF(WS-CURRENT-IDX)
               WHEN QT-VEHICLE-POWER(WS-CURRENT-IDX) <= 10
                   MOVE 1.20 TO PR-POWER-COEF(WS-CURRENT-IDX)
               WHEN QT-VEHICLE-POWER(WS-CURRENT-IDX) <= 14
                   MOVE 1.50 TO PR-POWER-COEF(WS-CURRENT-IDX)
               WHEN OTHER
                   MOVE 2.00 TO PR-POWER-COEF(WS-CURRENT-IDX)
           END-EVALUATE.

       2240-COMPUTE-COVERAGE-COEF.
           EVALUATE QT-COVERAGE(WS-CURRENT-IDX)
               WHEN 'RC'
                   MOVE 1.00 TO PR-COVERAGE-COEF(WS-CURRENT-IDX)
               WHEN 'TC'
                   MOVE 1.80 TO PR-COVERAGE-COEF(WS-CURRENT-IDX)
               WHEN 'TI'
                   MOVE 3.20 TO PR-COVERAGE-COEF(WS-CURRENT-IDX)
               WHEN OTHER
                   MOVE 1.00 TO PR-COVERAGE-COEF(WS-CURRENT-IDX)
           END-EVALUATE.

       2250-COMPUTE-REGION-COEF.
           EVALUATE QT-GOVERNORATE(WS-CURRENT-IDX)
               WHEN 'TUN'
                   MOVE 1.20 TO PR-REGION-COEF(WS-CURRENT-IDX)
               WHEN 'ARI'
                   MOVE 1.15 TO PR-REGION-COEF(WS-CURRENT-IDX)
               WHEN 'BAR'
                   MOVE 1.10 TO PR-REGION-COEF(WS-CURRENT-IDX)
               WHEN 'SFX'
                   MOVE 1.05 TO PR-REGION-COEF(WS-CURRENT-IDX)
               WHEN 'SOU'
                   MOVE 1.05 TO PR-REGION-COEF(WS-CURRENT-IDX)
               WHEN 'NAB'
                   MOVE 1.00 TO PR-REGION-COEF(WS-CURRENT-IDX)
               WHEN 'BIZ'
                   MOVE 0.95 TO PR-REGION-COEF(WS-CURRENT-IDX)
               WHEN OTHER
                   MOVE 0.90 TO PR-REGION-COEF(WS-CURRENT-IDX)
           END-EVALUATE.

       2260-COMPUTE-ACCIDENT-LOAD.
           IF QT-ACCIDENTS-3Y(WS-CURRENT-IDX) = 0
               MOVE 0.00 TO PR-ACCIDENT-LOAD(WS-CURRENT-IDX)
           ELSE
               COMPUTE PR-ACCIDENT-LOAD(WS-CURRENT-IDX) ROUNDED =
                   QT-ACCIDENTS-3Y(WS-CURRENT-IDX) * 75.00
           END-IF.

      *================================================================
      * 2300-APPLY-LIMITS
      * Enforce minimum and maximum premium bounds
      *================================================================
       2300-APPLY-LIMITS.
           IF PR-NET-PREMIUM(WS-CURRENT-IDX) < WS-MIN-PREMIUM-MILL
               MOVE WS-MIN-PREMIUM-MILL
                   TO PR-NET-PREMIUM(WS-CURRENT-IDX)
           END-IF
           IF PR-NET-PREMIUM(WS-CURRENT-IDX) > WS-MAX-PREMIUM-MILL
               MOVE WS-MAX-PREMIUM-MILL
                   TO PR-NET-PREMIUM(WS-CURRENT-IDX)
           END-IF.

      *================================================================
      * 2400-COMPUTE-TAXES
      *================================================================
       2400-COMPUTE-TAXES.
           COMPUTE PR-TVA(WS-CURRENT-IDX) ROUNDED =
               PR-NET-PREMIUM(WS-CURRENT-IDX) * WS-TVA-RATE / 100
           COMPUTE PR-PARAFISCAL(WS-CURRENT-IDX) ROUNDED =
               PR-NET-PREMIUM(WS-CURRENT-IDX) * WS-PARAFISCAL-RATE / 100
           COMPUTE PR-TOTAL-PREMIUM(WS-CURRENT-IDX) =
               PR-NET-PREMIUM(WS-CURRENT-IDX)
             + PR-TVA(WS-CURRENT-IDX)
             + PR-PARAFISCAL(WS-CURRENT-IDX).

      *================================================================
      * 2500-FINAL-DECISION
      *================================================================
       2500-FINAL-DECISION.
           EVALUATE TRUE
               WHEN QT-ACCIDENTS-3Y(WS-CURRENT-IDX)
                 >= WS-HIGH-RISK-LIMIT
                   MOVE 'MANUEL'   TO PR-DECISION(WS-CURRENT-IDX)
                   MOVE 'SINISTRES > 3 - REVUE MANUELLE REQUISE'
                       TO PR-REJECTION-REASON(WS-CURRENT-IDX)
                   ADD 1 TO WS-MANUAL-COUNT
               WHEN QT-CRM-COEF(WS-CURRENT-IDX) > 2.00
                   MOVE 'MANUEL'   TO PR-DECISION(WS-CURRENT-IDX)
                   MOVE 'CRM ELEVE - REVUE MANUELLE'
                       TO PR-REJECTION-REASON(WS-CURRENT-IDX)
                   ADD 1 TO WS-MANUAL-COUNT
               WHEN OTHER
                   MOVE 'ACCEPTE'  TO PR-DECISION(WS-CURRENT-IDX)
                   ADD 1 TO WS-ACCEPTED-COUNT
                   ADD PR-NET-PREMIUM(WS-CURRENT-IDX)
                       TO WS-TOTAL-NET
                   ADD PR-TOTAL-PREMIUM(WS-CURRENT-IDX)
                       TO WS-TOTAL-GROSS
           END-EVALUATE.

      *================================================================
      * 3000-DISPLAY-SUMMARY
      *================================================================
       3000-DISPLAY-SUMMARY.
           DISPLAY ' '
           DISPLAY '======================================='
           DISPLAY 'RECAPITULATIF DU LOT'
           DISPLAY '======================================='
           DISPLAY '  DEVIS ACCEPTES   : ' WS-ACCEPTED-COUNT
           DISPLAY '  DEVIS REFUSES    : ' WS-REJECTED-COUNT
           DISPLAY '  REVUE MANUELLE   : ' WS-MANUAL-COUNT
           MOVE WS-TOTAL-NET TO WS-DISP-AMOUNT
           DISPLAY '  PRIME NETTE TOT  : ' WS-DISP-AMOUNT ' TND'
           MOVE WS-TOTAL-GROSS TO WS-DISP-AMOUNT
           DISPLAY '  PRIME TTC TOTALE : ' WS-DISP-AMOUNT ' TND'
           DISPLAY '======================================='.

      *================================================================
      * 4000-DISPLAY-REJECTED
      *================================================================
       4000-DISPLAY-REJECTED.
           DISPLAY ' '
           MOVE QT-QUOTE-ID(WS-CURRENT-IDX) TO WS-DISP-QUOTE
           DISPLAY 'DEVIS ' WS-DISP-QUOTE ' --- REFUSE'
           DISPLAY '  Client: ' QT-CLIENT-NAME(WS-CURRENT-IDX)
           DISPLAY '  Motif : ' PR-REJECTION-REASON(WS-CURRENT-IDX).

      *================================================================
      * 4100-DISPLAY-QUOTE
      *================================================================
       4100-DISPLAY-QUOTE.
           DISPLAY ' '
           MOVE QT-QUOTE-ID(WS-CURRENT-IDX) TO WS-DISP-QUOTE
           DISPLAY 'DEVIS ' WS-DISP-QUOTE ' --- '
               PR-DECISION(WS-CURRENT-IDX)
           DISPLAY '  Client    : ' QT-CLIENT-NAME(WS-CURRENT-IDX)
           MOVE QT-DRIVER-AGE(WS-CURRENT-IDX) TO WS-DISP-AGE
           MOVE QT-VEHICLE-POWER(WS-CURRENT-IDX) TO WS-DISP-POWER
           DISPLAY '  Age conducteur: ' WS-DISP-AGE ' ans   '
               'Puissance: ' WS-DISP-POWER ' CV'
           DISPLAY '  Categorie : '
               QT-VEHICLE-CAT(WS-CURRENT-IDX)
               '    Couverture: ' QT-COVERAGE(WS-CURRENT-IDX)
               '    Gouvernorat: ' QT-GOVERNORATE(WS-CURRENT-IDX)
           MOVE PR-BASE-PREMIUM(WS-CURRENT-IDX) TO WS-DISP-AMOUNT
           DISPLAY '  Prime base : ' WS-DISP-AMOUNT ' TND'
           MOVE PR-AGE-COEF(WS-CURRENT-IDX) TO WS-DISP-COEF
           DISPLAY '    Coef age      : ' WS-DISP-COEF
           MOVE PR-POWER-COEF(WS-CURRENT-IDX) TO WS-DISP-COEF
           DISPLAY '    Coef puissance: ' WS-DISP-COEF
           MOVE PR-COVERAGE-COEF(WS-CURRENT-IDX) TO WS-DISP-COEF
           DISPLAY '    Coef garantie : ' WS-DISP-COEF
           MOVE PR-REGION-COEF(WS-CURRENT-IDX) TO WS-DISP-COEF
           DISPLAY '    Coef region   : ' WS-DISP-COEF
           MOVE QT-CRM-COEF(WS-CURRENT-IDX) TO WS-DISP-COEF
           DISPLAY '    CRM           : ' WS-DISP-COEF
           MOVE PR-NET-PREMIUM(WS-CURRENT-IDX) TO WS-DISP-AMOUNT
           DISPLAY '  Prime nette: ' WS-DISP-AMOUNT ' TND'
           MOVE PR-TVA(WS-CURRENT-IDX) TO WS-DISP-AMOUNT
           DISPLAY '    TVA 19 pct   : ' WS-DISP-AMOUNT ' TND'
           MOVE PR-PARAFISCAL(WS-CURRENT-IDX) TO WS-DISP-AMOUNT
           DISPLAY '    Parafiscal 5 : ' WS-DISP-AMOUNT ' TND'
           MOVE PR-TOTAL-PREMIUM(WS-CURRENT-IDX) TO WS-DISP-AMOUNT
           DISPLAY '  PRIME TTC  : ' WS-DISP-AMOUNT ' TND'
           IF PR-DECISION(WS-CURRENT-IDX) = 'MANUEL'
               DISPLAY '  Note: '
                   PR-REJECTION-REASON(WS-CURRENT-IDX)
           END-IF.

       END PROGRAM AUTOPREM.
