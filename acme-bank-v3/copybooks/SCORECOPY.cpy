      *****************************************************************
      * COPYBOOK:    SCORECOPY.cpy
      * DESCRIPTION: Credit scoring model parameters and result layout.
      *              Implements ACME Bank internal scoring grid approved
      *              by BCT risk committee (2023).
      *              Used by: LOANEVAL, RISKSCOR
      * VERSION:     1.5
      *****************************************************************
       01 SCORE-PARAMETERS.
          05 SCR-MODEL-VERSION    PIC X(6)      VALUE '2023.1'.
          05 SCR-MAX-SCORE        PIC 9(4)      VALUE 1000.
          05 SCR-MIN-APPROVE      PIC 9(4)      VALUE 600.
          05 SCR-MIN-COND         PIC 9(4)      VALUE 450.
          05 SCR-MIN-REVIEW       PIC 9(4)      VALUE 350.

      *--- Weight table for scoring components ---
          05 SCR-WEIGHT-INCOME    PIC 9(3)V99   VALUE 25.00.
          05 SCR-WEIGHT-HISTORY   PIC 9(3)V99   VALUE 30.00.
          05 SCR-WEIGHT-DSCR      PIC 9(3)V99   VALUE 20.00.
          05 SCR-WEIGHT-COLLAT    PIC 9(3)V99   VALUE 15.00.
          05 SCR-WEIGHT-TENURE    PIC 9(3)V99   VALUE 10.00.

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
