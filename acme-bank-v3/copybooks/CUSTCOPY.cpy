      *****************************************************************
      * COPYBOOK:    CUSTCOPY.cpy
      * DESCRIPTION: Customer master record layout (KYC compliant).
      *              Holds all client identification, risk profile,
      *              regulatory classification and contact data.
      *              Used by: LOANEVAL, RISKSCOR, CUSTMNT, RPTMONTH
      * VERSION:     4.2
      * BCT REF:     Circulaire BCT 2018-06 (KYC obligations)
      *****************************************************************
       01 CUSTOMER-RECORD.
          05 CUST-ID              PIC 9(8)      VALUE ZEROS.
          05 CUST-CIN             PIC X(8)      VALUE SPACES.
          05 CUST-PASSPORT        PIC X(12)     VALUE SPACES.
          05 CUST-TYPE            PIC X(2)      VALUE SPACES.
             88 CUST-INDIVIDUAL               VALUE 'PP'.
             88 CUST-CORPORATE               VALUE 'PM'.
             88 CUST-NON-RESIDENT            VALUE 'NR'.
          05 CUST-LAST-NAME       PIC X(30)     VALUE SPACES.
          05 CUST-FIRST-NAME      PIC X(25)     VALUE SPACES.
          05 CUST-DATE-OF-BIRTH   PIC 9(8)      VALUE ZEROS.
          05 CUST-NATIONALITY     PIC X(3)      VALUE 'TUN'.
          05 CUST-GENDER          PIC X(1)      VALUE SPACES.
             88 CUST-MALE                     VALUE 'M'.
             88 CUST-FEMALE                   VALUE 'F'.
          05 CUST-MARITAL-STATUS  PIC X(1)      VALUE SPACES.
             88 CUST-SINGLE                   VALUE 'S'.
             88 CUST-MARRIED                  VALUE 'M'.
             88 CUST-DIVORCED                 VALUE 'D'.
             88 CUST-WIDOWED                  VALUE 'W'.
          05 CUST-ADDRESS.
             10 CUST-ADDR-LINE1   PIC X(40)     VALUE SPACES.
             10 CUST-ADDR-LINE2   PIC X(40)     VALUE SPACES.
             10 CUST-ADDR-CITY    PIC X(20)     VALUE SPACES.
             10 CUST-ADDR-ZIP     PIC X(5)      VALUE SPACES.
             10 CUST-ADDR-GOV     PIC X(3)      VALUE SPACES.
          05 CUST-PHONE-MOBILE    PIC X(12)     VALUE SPACES.
          05 CUST-PHONE-HOME      PIC X(12)     VALUE SPACES.
          05 CUST-EMAIL           PIC X(50)     VALUE SPACES.
          05 CUST-EMPLOYER        PIC X(40)     VALUE SPACES.
          05 CUST-JOB-TITLE       PIC X(30)     VALUE SPACES.
          05 CUST-MONTHLY-INCOME  PIC 9(7)V99   VALUE ZEROS.
          05 CUST-INCOME-VERIFIED PIC X(1)      VALUE 'N'.
             88 CUST-INCOME-OK    VALUE 'Y'.
          05 CUST-SEGMENT         PIC X(2)      VALUE SPACES.
             88 CUST-MASS-MARKET  VALUE 'MM'.
             88 CUST-MIDDLE       VALUE 'MB'.
             88 CUST-PREMIUM      VALUE 'PR'.
             88 CUST-PRIVATE      VALUE 'PB'.
          05 CUST-RISK-RATING     PIC 9(2)      VALUE ZEROS.
          05 CUST-KYC-STATUS      PIC X(1)      VALUE SPACES.
             88 CUST-KYC-OK       VALUE 'V'.
             88 CUST-KYC-PENDING  VALUE 'P'.
             88 CUST-KYC-EXPIRED  VALUE 'E'.
          05 CUST-KYC-EXPIRY      PIC 9(8)      VALUE ZEROS.
          05 CUST-AML-FLAG        PIC X(1)      VALUE 'N'.
             88 CUST-AML-ALERT    VALUE 'Y'.
          05 CUST-PEP-FLAG        PIC X(1)      VALUE 'N'.
             88 CUST-IS-PEP       VALUE 'Y'.
          05 CUST-OPEN-DATE       PIC 9(8)      VALUE ZEROS.
          05 CUST-STATUS          PIC X(1)      VALUE SPACES.
             88 CUST-ACTIVE       VALUE 'A'.
             88 CUST-INACTIVE     VALUE 'I'.
             88 CUST-BLACKLISTED  VALUE 'B'.
          05 CUST-RELATIONSHIP-MGR PIC 9(6)     VALUE ZEROS.
          05 CUST-BRANCH-CODE     PIC 9(4)      VALUE ZEROS.
          05 CUST-TOTAL-ASSETS    PIC 9(13)V99  VALUE ZEROS.
          05 CUST-TOTAL-LIAB      PIC 9(13)V99  VALUE ZEROS.
          05 CUST-FILLER          PIC X(10)     VALUE SPACES.
