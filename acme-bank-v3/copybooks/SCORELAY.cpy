      *****************************************************************
      * COPYBOOK:    SCORELAY.cpy
      * DESCRIPTION: Scoring parameters and work fields (no file record).
      *              SCORE-RESULT layout remains in SCORECOPY.cpy.
      *              Used by: LOANEVAL (WORKING-STORAGE)
      *****************************************************************
       01 SCORE-PARAMETERS.
          05 SCR-MODEL-VERSION    PIC X(6)      VALUE '2023.1'.
          05 SCR-MAX-SCORE        PIC 9(4)      VALUE 1000.
          05 SCR-MIN-APPROVE      PIC 9(4)      VALUE 600.
          05 SCR-MIN-COND         PIC 9(4)      VALUE 450.
          05 SCR-MIN-REVIEW       PIC 9(4)      VALUE 350.
          05 SCR-WEIGHT-INCOME    PIC 9(3)V99   VALUE 25,00.
          05 SCR-WEIGHT-HISTORY   PIC 9(3)V99   VALUE 30,00.
          05 SCR-WEIGHT-DSCR      PIC 9(3)V99   VALUE 20,00.
          05 SCR-WEIGHT-COLLAT    PIC 9(3)V99   VALUE 15,00.
          05 SCR-WEIGHT-TENURE    PIC 9(3)V99   VALUE 10,00.

       01 SCORE-WORK-FIELDS.
          05 SCR-INCOME-SCORE     PIC 9(4)      VALUE ZEROS.
          05 SCR-HISTORY-SCORE    PIC 9(4)      VALUE ZEROS.
          05 SCR-DSCR-SCORE       PIC 9(4)      VALUE ZEROS.
          05 SCR-COLLAT-SCORE     PIC 9(4)      VALUE ZEROS.
          05 SCR-TENURE-SCORE     PIC 9(4)      VALUE ZEROS.
          05 SCR-RAW-SCORE        PIC 9(4)V99   VALUE ZEROS.
          05 SCR-FINAL-SCORE      PIC 9(4)      VALUE ZEROS.
          05 SCR-DSCR-RATIO       PIC 9(3)V9(4) VALUE ZEROS.
          05 SCR-LTV-RATIO        PIC 9(3)V9(4) VALUE ZEROS.
          05 SCR-DEBT-INCOME      PIC 9(3)V9(4) VALUE ZEROS.
