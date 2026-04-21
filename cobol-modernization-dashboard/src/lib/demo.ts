export const SAMPLE_COBOL = `       IDENTIFICATION DIVISION.
       PROGRAM-ID. TXNPROC.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 BALANCE PIC 9(5)V99 VALUE 1000.
       01 AMOUNT  PIC 9(5)V99 VALUE 200.
       01 STATUS  PIC X(10).

       PROCEDURE DIVISION.
       MAIN-LOGIC.
           IF BALANCE < AMOUNT
               MOVE 'REJECTED' TO STATUS
           ELSE
               SUBTRACT AMOUNT FROM BALANCE
               MOVE 'APPROVED' TO STATUS
           END-IF.`;

export const DEFAULT_EXPECTED_OUTPUT = JSON.stringify(
  {
    status: "APPROVED",
    balance: "800.00",
  },
  null,
  2,
);

export const DEFAULT_ACTUAL_OUTPUT = JSON.stringify(
  {
    status: "APPROVED",
    balance: "800.00",
  },
  null,
  2,
);
