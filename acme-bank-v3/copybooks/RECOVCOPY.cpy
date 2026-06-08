      *****************************************************************
      * COPYBOOK:    RECOVCOPY.cpy
      * DESCRIPTION: Loan recovery and collection action record.
      *              Tracks all recovery actions: dunning letters,
      *              phone calls, legal proceedings, guarantor calls,
      *              collateral seizure, restructuring.
      *              Used by: RECOVRY
      * VERSION:     2.0
      * BCT REF:     Circulaire BCT 2021-02 Art.18 (gestion creances)
      *****************************************************************
       01 RECOVERY-ACTION.
          05 REC-ACTION-ID        PIC 9(12)     VALUE ZEROS.
          05 REC-LOAN-ID          PIC 9(10)     VALUE ZEROS.
          05 REC-CUST-ID          PIC 9(8)      VALUE ZEROS.
          05 REC-ACTION-DATE      PIC 9(8)      VALUE ZEROS.
          05 REC-ACTION-TIME      PIC 9(6)      VALUE ZEROS.
          05 REC-ACTION-TYPE      PIC X(3)      VALUE SPACES.
             88 REC-DUNNING-LETTER VALUE 'DUL'.
             88 REC-PHONE-CALL    VALUE 'PHN'.
             88 REC-SMS-REMINDER  VALUE 'SMS'.
             88 REC-EMAIL-NOTICE  VALUE 'EML'.
             88 REC-LEGAL-NOTICE  VALUE 'LEG'.
             88 REC-COURT-FILING  VALUE 'CRT'.
             88 REC-GUARANTOR-CALL VALUE 'GTR'.
             88 REC-COLLAT-SEIZURE VALUE 'CSZ'.
             88 REC-RESTRUCTURE   VALUE 'RST'.
             88 REC-WRITE-OFF     VALUE 'WOF'.
             88 REC-PAYMENT-PLAN  VALUE 'PMT'.
          05 REC-AMOUNT-CLAIMED   PIC 9(11)V99  VALUE ZEROS.
          05 REC-AMOUNT-RECOVERED PIC 9(11)V99  VALUE ZEROS.
          05 REC-RESPONSE         PIC X(1)      VALUE SPACES.
             88 REC-RESP-PROMISED VALUE 'P'.
             88 REC-RESP-PAID     VALUE 'A'.
             88 REC-RESP-DISPUTED VALUE 'D'.
             88 REC-RESP-NORESPONSE VALUE 'N'.
             88 REC-RESP-REFUSED  VALUE 'R'.
          05 REC-NEXT-ACTION-DATE PIC 9(8)      VALUE ZEROS.
          05 REC-OFFICER-ID       PIC 9(6)      VALUE ZEROS.
          05 REC-LEGAL-FIRM       PIC X(40)     VALUE SPACES.
          05 REC-COURT-CASE-NUM   PIC X(20)     VALUE SPACES.
          05 REC-COMMENTS         PIC X(80)     VALUE SPACES.
          05 REC-FILLER           PIC X(10)     VALUE SPACES.

       01 RECOVERY-STATS.
          05 REC-STG-ACTIVE       PIC 9(6)      VALUE ZEROS.
          05 REC-STG-RESOLVED     PIC 9(6)      VALUE ZEROS.
          05 REC-STG-LEGAL        PIC 9(6)      VALUE ZEROS.
          05 REC-STG-WRITTEN-OFF  PIC 9(6)      VALUE ZEROS.
          05 REC-AMT-TARGETED     PIC 9(13)V99  VALUE ZEROS.
          05 REC-AMT-RECOVERED    PIC 9(13)V99  VALUE ZEROS.
          05 REC-RECOVERY-RATE    PIC 9(3)V9(4) VALUE ZEROS.
