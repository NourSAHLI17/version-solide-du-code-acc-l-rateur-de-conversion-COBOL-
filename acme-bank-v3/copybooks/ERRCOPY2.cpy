      *****************************************************************
      * COPYBOOK:    ERRCOPY2.cpy
      * DESCRIPTION: Standard error handling, return codes and
      *              file status definitions for the loan processing
      *              suite. Extended version with audit trail support.
      *              Used by all programs in the ACME loan suite.
      * VERSION:     2.1
      *****************************************************************
       01 ERROR-BLOCK.
          05 WS-RETURN-CODE       PIC 9(4)      VALUE ZEROS.
             88 RC-SUCCESS        VALUE 0.
             88 RC-WARNING        VALUE 4.
             88 RC-ERROR          VALUE 8.
             88 RC-FATAL          VALUE 12.
          05 WS-ERROR-CODE        PIC 9(6)      VALUE ZEROS.
          05 WS-ERROR-MESSAGE     PIC X(100)    VALUE SPACES.
          05 WS-PROGRAM-NAME      PIC X(8)      VALUE SPACES.
          05 WS-PARAGRAPH-NAME    PIC X(30)     VALUE SPACES.

       01 FILE-STATUS-BLOCK.
          05 WS-CUST-FS           PIC X(2)      VALUE SPACES.
             88 CUST-FS-OK        VALUE '00'.
             88 CUST-FS-EOF       VALUE '10'.
             88 CUST-FS-NOTFOUND  VALUE '23'.
             88 CUST-FS-DUPKEY    VALUE '22'.
          05 WS-LOAN-FS           PIC X(2)      VALUE SPACES.
             88 LOAN-FS-OK        VALUE '00'.
             88 LOAN-FS-EOF       VALUE '10'.
             88 LOAN-FS-NOTFOUND  VALUE '23'.
             88 LOAN-FS-DUPKEY    VALUE '22'.
          05 WS-COL-FS            PIC X(2)      VALUE SPACES.
             88 COL-FS-OK         VALUE '00'.
             88 COL-FS-EOF        VALUE '10'.
             88 COL-FS-NOTFOUND   VALUE '23'.
          05 WS-GTR-FS            PIC X(2)      VALUE SPACES.
             88 GTR-FS-OK         VALUE '00'.
             88 GTR-FS-EOF        VALUE '10'.
             88 GTR-FS-NOTFOUND   VALUE '23'.
          05 WS-SCR-FS            PIC X(2)      VALUE SPACES.
             88 SCR-FS-OK         VALUE '00'.
             88 SCR-FS-EOF        VALUE '10'.
          05 WS-RPT-FS            PIC X(2)      VALUE SPACES.
             88 RPT-FS-OK         VALUE '00'.
          05 WS-LOG-FS            PIC X(2)      VALUE SPACES.
             88 LOG-FS-OK         VALUE '00'.
          05 WS-REJ-FS            PIC X(2)      VALUE SPACES.
             88 REJ-FS-OK         VALUE '00'.
          05 WS-OUT-FS            PIC X(2)      VALUE SPACES.
             88 OUT-FS-OK         VALUE '00'.

       01 PROCESS-STATS.
          05 STAT-READ            PIC 9(8)      VALUE ZEROS.
          05 STAT-PROCESSED       PIC 9(8)      VALUE ZEROS.
          05 STAT-APPROVED        PIC 9(8)      VALUE ZEROS.
          05 STAT-DECLINED        PIC 9(8)      VALUE ZEROS.
          05 STAT-CONDITIONAL     PIC 9(8)      VALUE ZEROS.
          05 STAT-ERRORS          PIC 9(8)      VALUE ZEROS.
          05 STAT-SKIPPED         PIC 9(8)      VALUE ZEROS.
          05 STAT-TOTAL-AMT       PIC 9(13)V99  VALUE ZEROS.
          05 STAT-APPROVED-AMT    PIC 9(13)V99  VALUE ZEROS.
          05 STAT-DECLINED-AMT    PIC 9(13)V99  VALUE ZEROS.
