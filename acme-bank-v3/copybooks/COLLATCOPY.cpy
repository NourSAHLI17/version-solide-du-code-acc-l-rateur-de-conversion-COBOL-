      *****************************************************************
      * COPYBOOK:    COLLATCOPY.cpy
      * DESCRIPTION: Collateral record layout. Links collateral assets
      *              (real estate, vehicles, financial instruments) to
      *              loan facilities. A loan may have multiple
      *              collateral items linked via COL-LOAN-ID.
      *              Used by: LOANEVAL, RECOVRY, RISKSCOR
      * VERSION:     3.0 (v3 - guarantor split out to GUARCOPY)
      *****************************************************************
       01 COLLATERAL-RECORD.
          05 COL-ID               PIC 9(10)     VALUE ZEROS.
          05 COL-LOAN-ID          PIC 9(10)     VALUE ZEROS.
          05 COL-CUST-ID          PIC 9(8)      VALUE ZEROS.
          05 COL-TYPE             PIC X(3)      VALUE SPACES.
             88 COL-REAL-ESTATE   VALUE 'IMM'.
             88 COL-VEHICLE       VALUE 'VEH'.
             88 COL-FINANCIAL     VALUE 'FIN'.
             88 COL-GUARANTEE     VALUE 'GAR'.
          05 COL-DESCRIPTION      PIC X(60)     VALUE SPACES.
          05 COL-LOCATION         PIC X(40)     VALUE SPACES.
          05 COL-APPRAISAL-VALUE  PIC 9(11)V99  VALUE ZEROS.
          05 COL-APPRAISAL-DATE   PIC 9(8)      VALUE ZEROS.
          05 COL-APPRAISAL-FIRM   PIC X(30)     VALUE SPACES.
          05 COL-COVERAGE-RATIO   PIC 9(3)V99   VALUE ZEROS.
          05 COL-INSURANCE-NUM    PIC X(20)     VALUE SPACES.
          05 COL-INSURANCE-EXPIRY PIC 9(8)      VALUE ZEROS.
          05 COL-REGISTRATION     PIC X(20)     VALUE SPACES.
          05 COL-STATUS           PIC X(1)      VALUE SPACES.
             88 COL-ACTIVE        VALUE 'A'.
             88 COL-RELEASED      VALUE 'R'.
             88 COL-SEIZED        VALUE 'S'.
          05 COL-FILLER           PIC X(17)     VALUE SPACES.
