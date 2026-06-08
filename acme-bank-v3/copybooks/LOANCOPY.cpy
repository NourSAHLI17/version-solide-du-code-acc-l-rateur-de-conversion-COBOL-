      *****************************************************************
      * COPYBOOK:    LOANCOPY.cpy
      * DESCRIPTION: Loan and credit facility master record layout.
      *              Covers consumer loans, mortgage, revolving credit.
      *              Used by: LOANEVAL, LOANPOST, RISKSCOR, RPTMONTH
      * VERSION:     3.1
      * BCT REF:     Circulaire BCT 2021-02 (class. des creances)
      *****************************************************************
       01 LOAN-RECORD.
          05 LOAN-ID              PIC 9(10)     VALUE ZEROS.
          05 LOAN-CUST-ID         PIC 9(8)      VALUE ZEROS.
          05 LOAN-ACCT-ID         PIC 9(10)     VALUE ZEROS.
          05 LOAN-TYPE            PIC X(3)      VALUE SPACES.
             88 LOAN-CONSUMER     VALUE 'CON'.
             88 LOAN-MORTGAGE     VALUE 'IMM'.
             88 LOAN-AUTO         VALUE 'AUT'.
             88 LOAN-BUSINESS     VALUE 'PRO'.
             88 LOAN-REVOLVING    VALUE 'REV'.
             88 LOAN-OVERDRAFT    VALUE 'DEC'.
          05 LOAN-STATUS          PIC X(2)      VALUE SPACES.
             88 LOAN-ACTIVE       VALUE 'AC'.
             88 LOAN-RESTRUCTURED VALUE 'RS'.
             88 LOAN-LITIGIOUS    VALUE 'LT'.
             88 LOAN-SETTLED      VALUE 'SD'.
             88 LOAN-WRITTEN-OFF  VALUE 'WO'.
          05 LOAN-CLASS           PIC X(1)      VALUE SPACES.
             88 LOAN-CLASS-1      VALUE '1'.
             88 LOAN-CLASS-2      VALUE '2'.
             88 LOAN-CLASS-3      VALUE '3'.
             88 LOAN-CLASS-4      VALUE '4'.
          05 LOAN-ORIGINAL-AMT    PIC 9(11)V99  VALUE ZEROS.
          05 LOAN-OUTSTANDING     PIC 9(11)V99  VALUE ZEROS.
          05 LOAN-MONTHLY-PMT     PIC 9(7)V99   VALUE ZEROS.
          05 LOAN-INTEREST-RATE   PIC 9(2)V9(4) VALUE ZEROS.
          05 LOAN-RATE-TYPE       PIC X(1)      VALUE SPACES.
             88 LOAN-FIXED-RATE   VALUE 'F'.
             88 LOAN-VARIABLE     VALUE 'V'.
          05 LOAN-START-DATE      PIC 9(8)      VALUE ZEROS.
          05 LOAN-MATURITY-DATE   PIC 9(8)      VALUE ZEROS.
          05 LOAN-LAST-PMT-DATE   PIC 9(8)      VALUE ZEROS.
          05 LOAN-NEXT-PMT-DATE   PIC 9(8)      VALUE ZEROS.
          05 LOAN-PAYMENTS-MADE   PIC 9(4)      VALUE ZEROS.
          05 LOAN-PAYMENTS-TOTAL  PIC 9(4)      VALUE ZEROS.
          05 LOAN-DAYS-PAST-DUE   PIC 9(4)      VALUE ZEROS.
          05 LOAN-MISSED-PMTS     PIC 9(3)      VALUE ZEROS.
          05 LOAN-PROVISION-RATE  PIC 9(2)V9(4) VALUE ZEROS.
          05 LOAN-PROVISION-AMT   PIC 9(9)V99   VALUE ZEROS.
          05 LOAN-COLLATERAL-TYPE PIC X(3)      VALUE SPACES.
             88 LOAN-COL-PROPERTY VALUE 'IMM'.
             88 LOAN-COL-VEHICLE  VALUE 'VEH'.
             88 LOAN-COL-DEPOSIT  VALUE 'DEP'.
             88 LOAN-COL-NONE     VALUE 'NON'.
          05 LOAN-COLLATERAL-VAL  PIC 9(11)V99  VALUE ZEROS.
          05 LOAN-GUARANTOR-ID    PIC 9(8)      VALUE ZEROS.
          05 LOAN-BRANCH-CODE     PIC 9(4)      VALUE ZEROS.
          05 LOAN-OFFICER-ID      PIC 9(6)      VALUE ZEROS.
          05 LOAN-PURPOSE         PIC X(40)     VALUE SPACES.
          05 LOAN-RESTRUCTURE-DT  PIC 9(8)      VALUE ZEROS.
          05 LOAN-WRITE-OFF-DT    PIC 9(8)      VALUE ZEROS.
          05 LOAN-FILLER          PIC X(8)      VALUE SPACES.
