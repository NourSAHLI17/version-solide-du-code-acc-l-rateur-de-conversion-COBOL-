      *****************************************************************
      * COPYBOOK:    RPTCOPY2.cpy
      * DESCRIPTION: Report header, footer and detail line layouts
      *              for the loan evaluation and risk reporting suite.
      *              All labels in French per Tunisian banking regs.
      *              Used by: LOANEVAL, RISKSCOR, RPTMONTH
      * VERSION:     1.6
      *****************************************************************
       01 RPT-MAIN-HEADER.
          05 FILLER               PIC X(10)     VALUE SPACES.
          05 RPT-BANK-NAME        PIC X(25)     VALUE 'ACME BANK SA'.
          05 FILLER               PIC X(5)      VALUE SPACES.
          05 RPT-PROGRAM          PIC X(8)      VALUE SPACES.
          05 FILLER               PIC X(5)      VALUE SPACES.
          05 RPT-PAGE-LBL         PIC X(6)      VALUE 'PAGE: '.
          05 RPT-PAGE-NO          PIC Z(4)9     VALUE ZEROS.
          05 FILLER               PIC X(73)     VALUE SPACES.

       01 RPT-SUB-HEADER.
          05 FILLER               PIC X(15)     VALUE SPACES.
          05 RPT-TITLE            PIC X(60)     VALUE SPACES.
          05 FILLER               PIC X(5)      VALUE SPACES.
          05 RPT-DATE-LBL         PIC X(6)      VALUE 'DATE: '.
          05 RPT-RUN-DATE         PIC 9(8)      VALUE ZEROS.
          05 FILLER               PIC X(43)     VALUE SPACES.

       01 RPT-COL-HEADER-LOAN.
          05 FILLER               PIC X(2)      VALUE SPACES.
          05 FILLER               PIC X(10)     VALUE 'DOSSIER'.
          05 FILLER               PIC X(2)      VALUE SPACES.
          05 FILLER               PIC X(8)      VALUE 'CLIENT'.
          05 FILLER               PIC X(2)      VALUE SPACES.
          05 FILLER               PIC X(5)      VALUE 'TYPE'.
          05 FILLER               PIC X(2)      VALUE SPACES.
          05 FILLER               PIC X(14)     VALUE 'MONTANT'.
          05 FILLER               PIC X(2)      VALUE SPACES.
          05 FILLER               PIC X(8)      VALUE 'TAUX'.
          05 FILLER               PIC X(2)      VALUE SPACES.
          05 FILLER               PIC X(6)      VALUE 'SCORE'.
          05 FILLER               PIC X(2)      VALUE SPACES.
          05 FILLER               PIC X(10)     VALUE 'DECISION'.
          05 FILLER               PIC X(62)     VALUE SPACES.

       01 RPT-SEPARATOR.
          05 FILLER               PIC X(137)    VALUE ALL '='.

       01 RPT-THIN-SEP.
          05 FILLER               PIC X(137)    VALUE ALL '-'.

       01 RPT-BLANK-LINE.
          05 FILLER               PIC X(137)    VALUE SPACES.

       01 RPT-FOOTER-LINE.
          05 FILLER               PIC X(20)     VALUE SPACES.
          05 FILLER               PIC X(60)
             VALUE 'DOCUMENT CONFIDENTIEL - USAGE INTERNE BCT'.
          05 FILLER               PIC X(57)     VALUE SPACES.
