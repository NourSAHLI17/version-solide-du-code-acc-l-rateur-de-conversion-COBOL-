       01 CUSTOMER-RECORD-FIELDS.
          05 CUST-ID             PIC X(10).
          05 CUST-NAME           PIC X(30).
          05 CUST-ADDRESS        PIC X(50).
          05 CUST-BALANCE        PIC S9(9)V99 COMP-3.
          05 CUST-CREDIT-LIMIT   PIC S9(9)V99 COMP-3.
          05 CUST-STATUS         PIC X VALUE 'A'.
          88 CUST-ACTIVE         VALUE 'A'.
