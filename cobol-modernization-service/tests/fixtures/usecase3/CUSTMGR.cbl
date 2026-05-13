       IDENTIFICATION DIVISION.
       PROGRAM-ID. CUSTMGR.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CUSTOMER-FILE
               ASSIGN TO 'ACME.CUSTOMER.MASTER'
               ORGANIZATION IS INDEXED
               ACCESS MODE IS DYNAMIC
               RECORD KEY IS CUST-ID
               FILE STATUS IS WS-FILE-STATUS.
       DATA DIVISION.
       FILE SECTION.
       FD CUSTOMER-FILE.
       01 CUSTOMER-RECORD.
          COPY CUSTCOPY.
       WORKING-STORAGE SECTION.
       01 WS-FILE-STATUS        PIC XX VALUE '00'.
       01 WS-MENU-CHOICE        PIC 9 VALUE 0.
       01 WS-CONFIRM            PIC X VALUE SPACE.
       77 WS-PAD-01             PIC X VALUE SPACE.
       77 WS-PAD-02             PIC X VALUE SPACE.
       77 WS-PAD-03             PIC X VALUE SPACE.
       77 WS-PAD-04             PIC X VALUE SPACE.
       77 WS-PAD-05             PIC X VALUE SPACE.
       77 WS-PAD-06             PIC X VALUE SPACE.
       77 WS-PAD-07             PIC X VALUE SPACE.
       77 WS-PAD-08             PIC X VALUE SPACE.
       77 WS-PAD-09             PIC X VALUE SPACE.
       77 WS-PAD-10             PIC X VALUE SPACE.
       77 WS-PAD-11             PIC X VALUE SPACE.
       77 WS-PAD-12             PIC X VALUE SPACE.
       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN I-O CUSTOMER-FILE.
           PERFORM 1000-MENU UNTIL WS-MENU-CHOICE = 9.
           CLOSE CUSTOMER-FILE.
           STOP RUN.
       1000-MENU.
           DISPLAY "1=Add 2=View 3=Update 4=Delete 9=Exit".
           ACCEPT WS-MENU-CHOICE.
           EVALUATE WS-MENU-CHOICE
               WHEN 1 PERFORM 2000-ADD-CUSTOMER
               WHEN 2 PERFORM 3000-VIEW-CUSTOMER
               WHEN 3 PERFORM 4000-UPDATE-CUSTOMER
               WHEN 4 PERFORM 5000-DELETE-CUSTOMER
               WHEN 9 CONTINUE
               WHEN OTHER DISPLAY "Invalid choice"
           END-EVALUATE.
       2000-ADD-CUSTOMER.
           DISPLAY "Enter customer ID:".
           ACCEPT CUST-ID.
           DISPLAY "Enter customer name:".
           ACCEPT CUST-NAME.
           WRITE CUSTOMER-RECORD
               INVALID KEY DISPLAY "Duplicate ID - not added".
       3000-VIEW-CUSTOMER.
           DISPLAY "Enter customer ID to view:".
           ACCEPT CUST-ID.
           READ CUSTOMER-FILE KEY IS CUST-ID
               INVALID KEY DISPLAY "Customer not found"
               NOT INVALID KEY
                   DISPLAY "ID: " CUST-ID
                   DISPLAY "Name: " CUST-NAME.
       4000-UPDATE-CUSTOMER.
           DISPLAY "Enter customer ID to update:".
           ACCEPT CUST-ID.
           READ CUSTOMER-FILE KEY IS CUST-ID
               INVALID KEY DISPLAY "Customer not found"
               NOT INVALID KEY
                   DISPLAY "Enter new name:"
                   ACCEPT CUST-NAME
                   REWRITE CUSTOMER-RECORD
                       INVALID KEY DISPLAY "Update failed".
       5000-DELETE-CUSTOMER.
           DISPLAY "Enter customer ID to delete:".
           ACCEPT CUST-ID.
           READ CUSTOMER-FILE KEY IS CUST-ID
               INVALID KEY DISPLAY "Customer not found"
               NOT INVALID KEY
                   DISPLAY "Confirm delete (Y/N):"
                   ACCEPT WS-CONFIRM
                   IF WS-CONFIRM = 'Y'
                       DELETE CUSTOMER-FILE RECORD
                           INVALID KEY DISPLAY "Delete failed"
                   END-IF.
