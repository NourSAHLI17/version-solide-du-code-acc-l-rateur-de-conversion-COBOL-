      *****************************************************************
      * COPYBOOK:    GUARCOPY.cpy
      * DESCRIPTION: Guarantor record layout for loan guarantees.
      *              Separates guarantor data from collateral physical
      *              assets. A loan can have multiple guarantors.
      *              Used by: LOANEVAL, RECOVRY, RISKSCOR
      * VERSION:     1.3
      * BCT REF:     Circulaire BCT 2018-06 Article 24
      *****************************************************************
       01 GUARANTOR-RECORD.
          05 GTR-ID               PIC 9(10)     VALUE ZEROS.
          05 GTR-LOAN-ID          PIC 9(10)     VALUE ZEROS.
          05 GTR-GUARANTOR-ID     PIC 9(8)      VALUE ZEROS.
          05 GTR-NAME             PIC X(50)     VALUE SPACES.
          05 GTR-AMOUNT           PIC 9(11)V99  VALUE ZEROS.
          05 GTR-INCOME           PIC 9(7)V99   VALUE ZEROS.
          05 GTR-SIGN-DATE        PIC 9(8)      VALUE ZEROS.
          05 GTR-EXPIRY-DATE      PIC 9(8)      VALUE ZEROS.
          05 GTR-STATUS           PIC X(1)      VALUE SPACES.
             88 GTR-ACTIVE        VALUE 'A'.
             88 GTR-CALLED        VALUE 'C'.
             88 GTR-EXPIRED       VALUE 'E'.
          05 GTR-FILLER           PIC X(13)     VALUE SPACES.
