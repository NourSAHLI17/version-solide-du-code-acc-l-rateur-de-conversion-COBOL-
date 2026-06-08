      *****************************************************************
      * PROGRAM:     PAYRPT
      * DESCRIPTION: Employee payroll calculation system.
      *              Maintains an in-memory roster of up to 30
      *              employees. Calculates gross pay, tax deductions,
      *              net pay. Supports add, view, update hours,
      *              run payroll, and produce a pay summary report.
      *              Demonstrates: COMPUTE with expressions, ADD,
      *              SUBTRACT, EVALUATE TRUE with ranges, nested IF,
      *              PERFORM VARYING, EXIT PARAGRAPH, ROUNDED,
      *              formatted display output, accumulator patterns.
      * AUTHOR:      Test Use Case - Medium
      * VERSION:     1.0
      *****************************************************************
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYRPT.
       AUTHOR. TEST-CASE-MEDIUM.

       ENVIRONMENT DIVISION.

       DATA DIVISION.
       WORKING-STORAGE SECTION.

      *--- Control ---
       01 WS-MENU-CHOICE          PIC 9         VALUE ZERO.
       01 WS-CONTINUE-FLAG        PIC X         VALUE 'Y'.
       01 WS-FOUND-FLAG           PIC X         VALUE 'N'.
       01 WS-CONFIRM              PIC X         VALUE SPACE.

      *--- Loop and index ---
       01 WS-IDX                  PIC 9(3)      VALUE ZERO.
       01 WS-FOUND-IDX            PIC 9(3)      VALUE ZERO.
       01 WS-EMP-COUNT            PIC 9(3)      VALUE ZERO.
       01 WS-PROCESSED-COUNT      PIC 9(3)      VALUE ZERO.

      *--- Input buffer ---
       01 WS-INPUT-ID             PIC 9(5)      VALUE ZEROS.
       01 WS-INPUT-NAME           PIC X(25)     VALUE SPACES.
       01 WS-INPUT-DEPT           PIC X(10)     VALUE SPACES.
       01 WS-INPUT-RATE           PIC 9(3)V99   VALUE ZEROS.
       01 WS-INPUT-HOURS          PIC 9(3)V9    VALUE ZEROS.
       01 WS-SEARCH-ID            PIC 9(5)      VALUE ZEROS.

      *--- Pay computation work fields ---
       01 WS-REGULAR-HOURS        PIC 9(3)V9    VALUE ZEROS.
       01 WS-OVERTIME-HOURS       PIC 9(3)V9    VALUE ZEROS.
       01 WS-REGULAR-PAY          PIC 9(6)V99   VALUE ZEROS.
       01 WS-OVERTIME-PAY         PIC 9(6)V99   VALUE ZEROS.
       01 WS-GROSS-PAY            PIC 9(6)V99   VALUE ZEROS.
       01 WS-TAX-AMOUNT           PIC 9(6)V99   VALUE ZEROS.
       01 WS-NET-PAY              PIC 9(6)V99   VALUE ZEROS.
       01 WS-TAX-RATE             PIC V9(4)     VALUE ZEROS.

      *--- Overtime constants ---
       01 WS-STANDARD-HOURS       PIC 9(3)V9    VALUE 40.0.
       01 WS-OVERTIME-MULTIPLIER  PIC 9V99      VALUE 1.50.

      *--- Report accumulators ---
       01 WS-TOTAL-GROSS          PIC 9(8)V99   VALUE ZEROS.
       01 WS-TOTAL-TAX            PIC 9(8)V99   VALUE ZEROS.
       01 WS-TOTAL-NET            PIC 9(8)V99   VALUE ZEROS.
       01 WS-HIGHEST-PAY          PIC 9(6)V99   VALUE ZEROS.
       01 WS-HIGHEST-PAY-NAME     PIC X(25)     VALUE SPACES.

      *--- Display formatting ---
       01 WS-DISP-RATE            PIC ZZ9.99    VALUE ZEROS.
       01 WS-DISP-HOURS           PIC ZZ9.9     VALUE ZEROS.
       01 WS-DISP-GROSS           PIC Z(5)9.99  VALUE ZEROS.
       01 WS-DISP-TAX             PIC Z(5)9.99  VALUE ZEROS.
       01 WS-DISP-NET             PIC Z(5)9.99  VALUE ZEROS.
       01 WS-DISP-TOTAL-GROSS     PIC Z(7)9.99  VALUE ZEROS.
       01 WS-DISP-TOTAL-TAX       PIC Z(7)9.99  VALUE ZEROS.
       01 WS-DISP-TOTAL-NET       PIC Z(7)9.99  VALUE ZEROS.
       01 WS-DISP-ID              PIC 99999     VALUE ZEROS.
       01 WS-DISP-PCT             PIC Z9.99     VALUE ZEROS.

      *--- Employee roster OCCURS 30 ---
       01 WS-ROSTER.
          05 WS-EMPLOYEE OCCURS 30 TIMES.
             10 EMP-ID            PIC 9(5)      VALUE ZEROS.
             10 EMP-NAME          PIC X(25)     VALUE SPACES.
             10 EMP-DEPT          PIC X(10)     VALUE SPACES.
             10 EMP-HOURLY-RATE   PIC 9(3)V99   VALUE ZEROS.
             10 EMP-HOURS-WORKED  PIC 9(3)V9    VALUE ZEROS.
             10 EMP-GROSS-PAY     PIC 9(6)V99   VALUE ZEROS.
             10 EMP-TAX           PIC 9(6)V99   VALUE ZEROS.
             10 EMP-NET-PAY       PIC 9(6)V99   VALUE ZEROS.
             10 EMP-ACTIVE        PIC X         VALUE 'N'.
             10 EMP-PAY-COMPUTED  PIC X         VALUE 'N'.

       PROCEDURE DIVISION.

       0000-MAIN.
           DISPLAY "================================================".
           DISPLAY "        EMPLOYEE PAYROLL CALCULATOR             ".
           DISPLAY "================================================".
           PERFORM 1000-SHOW-MENU
               UNTIL WS-CONTINUE-FLAG = 'N'.
           DISPLAY " ".
           DISPLAY "Payroll session ended. Goodbye.".
           STOP RUN.

       1000-SHOW-MENU.
           MOVE ZERO TO WS-MENU-CHOICE.
           DISPLAY " ".
           DISPLAY "----------- PAYROLL MENU ----------------------".
           DISPLAY "  1 - Add Employee".
           DISPLAY "  2 - View Employee".
           DISPLAY "  3 - Enter Hours Worked".
           DISPLAY "  4 - Run Payroll Calculation".
           DISPLAY "  5 - Pay Summary Report".
           DISPLAY "  6 - Reset Pay Period".
           DISPLAY "  0 - Exit".
           DISPLAY "-----------------------------------------------".
           DISPLAY "Choice: ".
           ACCEPT WS-MENU-CHOICE.
           PERFORM 2000-ROUTE-CHOICE.

       2000-ROUTE-CHOICE.
           EVALUATE WS-MENU-CHOICE
               WHEN 1 PERFORM 3000-ADD-EMPLOYEE
               WHEN 2 PERFORM 3100-VIEW-EMPLOYEE
               WHEN 3 PERFORM 3200-ENTER-HOURS
               WHEN 4 PERFORM 3300-RUN-PAYROLL
               WHEN 5 PERFORM 3400-PAY-SUMMARY
               WHEN 6 PERFORM 3500-RESET-PAY-PERIOD
               WHEN 0 MOVE 'N' TO WS-CONTINUE-FLAG
               WHEN OTHER
                   DISPLAY "! Invalid choice. Enter 0 through 6."
           END-EVALUATE.

      *---------------------------------------------------------------
      * 3000 - ADD EMPLOYEE
      *---------------------------------------------------------------
       3000-ADD-EMPLOYEE.
           MOVE 'N' TO WS-FOUND-FLAG.
           PERFORM VARYING WS-IDX FROM 1 BY 1 UNTIL WS-IDX > 30
               IF EMP-ACTIVE(WS-IDX) = 'N'
                   MOVE WS-IDX TO WS-FOUND-IDX
                   MOVE 'Y'    TO WS-FOUND-FLAG
                   EXIT PERFORM
               END-IF
           END-PERFORM.
           IF WS-FOUND-FLAG = 'N'
               DISPLAY "! Roster full. Maximum 30 employees."
               EXIT PARAGRAPH
           END-IF.
           DISPLAY " ".
           DISPLAY "--- Add New Employee ---".
           DISPLAY "Employee ID (5 digits): ".
           ACCEPT WS-INPUT-ID.
           PERFORM 8000-CHECK-DUPLICATE-ID.
           IF WS-FOUND-FLAG = 'Y'
               DISPLAY "! Employee ID already exists."
               EXIT PARAGRAPH
           END-IF.
           DISPLAY "Full Name (max 25 chars): ".
           ACCEPT WS-INPUT-NAME.
           DISPLAY "Department (max 10 chars): ".
           ACCEPT WS-INPUT-DEPT.
           DISPLAY "Hourly Rate: ".
           ACCEPT WS-INPUT-RATE.
           MOVE WS-INPUT-ID    TO EMP-ID(WS-FOUND-IDX).
           MOVE WS-INPUT-NAME  TO EMP-NAME(WS-FOUND-IDX).
           MOVE WS-INPUT-DEPT  TO EMP-DEPT(WS-FOUND-IDX).
           MOVE WS-INPUT-RATE  TO EMP-HOURLY-RATE(WS-FOUND-IDX).
           MOVE ZEROS          TO EMP-HOURS-WORKED(WS-FOUND-IDX).
           MOVE ZEROS          TO EMP-GROSS-PAY(WS-FOUND-IDX).
           MOVE ZEROS          TO EMP-TAX(WS-FOUND-IDX).
           MOVE ZEROS          TO EMP-NET-PAY(WS-FOUND-IDX).
           MOVE 'Y'            TO EMP-ACTIVE(WS-FOUND-IDX).
           MOVE 'N'            TO EMP-PAY-COMPUTED(WS-FOUND-IDX).
           DISPLAY "Employee added successfully.".

      *---------------------------------------------------------------
      * 3100 - VIEW EMPLOYEE
      *---------------------------------------------------------------
       3100-VIEW-EMPLOYEE.
           DISPLAY " ".
           DISPLAY "--- View Employee ---".
           DISPLAY "Enter Employee ID: ".
           ACCEPT WS-SEARCH-ID.
           PERFORM 8100-FIND-BY-ID.
           IF WS-FOUND-FLAG = 'N'
               DISPLAY "! Employee ID not found."
           ELSE
               PERFORM 9000-DISPLAY-EMPLOYEE
           END-IF.

      *---------------------------------------------------------------
      * 3200 - ENTER HOURS WORKED
      *---------------------------------------------------------------
       3200-ENTER-HOURS.
           DISPLAY " ".
           DISPLAY "--- Enter Hours Worked ---".
           DISPLAY "Enter Employee ID: ".
           ACCEPT WS-SEARCH-ID.
           PERFORM 8100-FIND-BY-ID.
           IF WS-FOUND-FLAG = 'N'
               DISPLAY "! Employee ID not found."
               EXIT PARAGRAPH
           END-IF.
           DISPLAY "Employee: " EMP-NAME(WS-FOUND-IDX).
           MOVE EMP-HOURS-WORKED(WS-FOUND-IDX) TO WS-DISP-HOURS.
           DISPLAY "Current hours: " WS-DISP-HOURS.
           DISPLAY "Enter hours worked this period: ".
           ACCEPT WS-INPUT-HOURS.
           MOVE WS-INPUT-HOURS TO EMP-HOURS-WORKED(WS-FOUND-IDX).
           MOVE 'N'            TO EMP-PAY-COMPUTED(WS-FOUND-IDX).
           DISPLAY "Hours recorded.".

      *---------------------------------------------------------------
      * 3300 - RUN PAYROLL CALCULATION
      *---------------------------------------------------------------
       3300-RUN-PAYROLL.
           MOVE ZERO TO WS-PROCESSED-COUNT.
           DISPLAY " ".
           DISPLAY "--- Running Payroll ---".
           PERFORM VARYING WS-IDX FROM 1 BY 1 UNTIL WS-IDX > 30
               IF EMP-ACTIVE(WS-IDX) = 'Y' AND
                  EMP-PAY-COMPUTED(WS-IDX) = 'N' AND
                  EMP-HOURS-WORKED(WS-IDX) > ZERO
                   PERFORM 8200-CALCULATE-PAY
                   ADD 1 TO WS-PROCESSED-COUNT
               END-IF
           END-PERFORM.
           IF WS-PROCESSED-COUNT = ZERO
               DISPLAY "No employees to process."
           ELSE
               DISPLAY "Payroll computed for "
                   WS-PROCESSED-COUNT " employees."
           END-IF.

      *---------------------------------------------------------------
      * 3400 - PAY SUMMARY REPORT
      *---------------------------------------------------------------
       3400-PAY-SUMMARY.
           MOVE ZEROS TO WS-TOTAL-GROSS.
           MOVE ZEROS TO WS-TOTAL-TAX.
           MOVE ZEROS TO WS-TOTAL-NET.
           MOVE ZEROS TO WS-HIGHEST-PAY.
           MOVE SPACES TO WS-HIGHEST-PAY-NAME.
           MOVE ZERO  TO WS-EMP-COUNT.
           DISPLAY " ".
           DISPLAY "============================================".
           DISPLAY "          PAY SUMMARY REPORT               ".
           DISPLAY "============================================".
           PERFORM VARYING WS-IDX FROM 1 BY 1 UNTIL WS-IDX > 30
               IF EMP-ACTIVE(WS-IDX) = 'Y' AND
                  EMP-PAY-COMPUTED(WS-IDX) = 'Y'
                   ADD 1 TO WS-EMP-COUNT
                   ADD EMP-GROSS-PAY(WS-IDX) TO WS-TOTAL-GROSS
                   ADD EMP-TAX(WS-IDX)       TO WS-TOTAL-TAX
                   ADD EMP-NET-PAY(WS-IDX)   TO WS-TOTAL-NET
                   MOVE EMP-ID(WS-IDX)    TO WS-DISP-ID
                   MOVE EMP-GROSS-PAY(WS-IDX) TO WS-DISP-GROSS
                   MOVE EMP-TAX(WS-IDX)   TO WS-DISP-TAX
                   MOVE EMP-NET-PAY(WS-IDX) TO WS-DISP-NET
                   DISPLAY WS-DISP-ID "  "
                       EMP-NAME(WS-IDX)
                   DISPLAY "         Gross:" WS-DISP-GROSS
                       "  Tax:" WS-DISP-TAX
                       "  Net:" WS-DISP-NET
                   IF EMP-GROSS-PAY(WS-IDX) > WS-HIGHEST-PAY
                       MOVE EMP-GROSS-PAY(WS-IDX) TO WS-HIGHEST-PAY
                       MOVE EMP-NAME(WS-IDX)      TO
                           WS-HIGHEST-PAY-NAME
                   END-IF
               END-IF
           END-PERFORM.
           IF WS-EMP-COUNT = ZERO
               DISPLAY "No payroll records to report."
           ELSE
               DISPLAY "--------------------------------------------"
               MOVE WS-TOTAL-GROSS TO WS-DISP-TOTAL-GROSS
               MOVE WS-TOTAL-TAX   TO WS-DISP-TOTAL-TAX
               MOVE WS-TOTAL-NET   TO WS-DISP-TOTAL-NET
               DISPLAY "Total Gross Pay : " WS-DISP-TOTAL-GROSS
               DISPLAY "Total Tax       : " WS-DISP-TOTAL-TAX
               DISPLAY "Total Net Pay   : " WS-DISP-TOTAL-NET
               DISPLAY "Employees Paid  : " WS-EMP-COUNT
               DISPLAY "Highest Pay     : " WS-HIGHEST-PAY-NAME
           END-IF.
           DISPLAY "============================================".

      *---------------------------------------------------------------
      * 3500 - RESET PAY PERIOD
      *---------------------------------------------------------------
       3500-RESET-PAY-PERIOD.
           DISPLAY " ".
           DISPLAY "This will clear all hours and pay data.".
           DISPLAY "Type Y to confirm: ".
           ACCEPT WS-CONFIRM.
           IF WS-CONFIRM = 'Y' OR WS-CONFIRM = 'y'
               PERFORM VARYING WS-IDX FROM 1 BY 1
                   UNTIL WS-IDX > 30
                   IF EMP-ACTIVE(WS-IDX) = 'Y'
                       MOVE ZEROS TO EMP-HOURS-WORKED(WS-IDX)
                       MOVE ZEROS TO EMP-GROSS-PAY(WS-IDX)
                       MOVE ZEROS TO EMP-TAX(WS-IDX)
                       MOVE ZEROS TO EMP-NET-PAY(WS-IDX)
                       MOVE 'N'  TO EMP-PAY-COMPUTED(WS-IDX)
                   END-IF
               END-PERFORM
               DISPLAY "Pay period reset."
           ELSE
               DISPLAY "Reset cancelled."
           END-IF.

      *---------------------------------------------------------------
      * 8000 - UTILITY: CHECK DUPLICATE ID
      *---------------------------------------------------------------
       8000-CHECK-DUPLICATE-ID.
           MOVE 'N' TO WS-FOUND-FLAG.
           PERFORM VARYING WS-IDX FROM 1 BY 1 UNTIL WS-IDX > 30
               IF EMP-ACTIVE(WS-IDX) = 'Y' AND
                  EMP-ID(WS-IDX) = WS-INPUT-ID
                   MOVE 'Y' TO WS-FOUND-FLAG
                   EXIT PERFORM
               END-IF
           END-PERFORM.

      *---------------------------------------------------------------
      * 8100 - UTILITY: FIND EMPLOYEE BY ID
      *---------------------------------------------------------------
       8100-FIND-BY-ID.
           MOVE 'N'  TO WS-FOUND-FLAG.
           MOVE ZERO TO WS-FOUND-IDX.
           PERFORM VARYING WS-IDX FROM 1 BY 1 UNTIL WS-IDX > 30
               IF EMP-ACTIVE(WS-IDX) = 'Y' AND
                  EMP-ID(WS-IDX) = WS-SEARCH-ID
                   MOVE 'Y'    TO WS-FOUND-FLAG
                   MOVE WS-IDX TO WS-FOUND-IDX
                   EXIT PERFORM
               END-IF
           END-PERFORM.

      *---------------------------------------------------------------
      * 8200 - UTILITY: CALCULATE PAY FOR WS-IDX EMPLOYEE
      *   Business rules:
      *     - Hours <= 40: regular pay = hours * rate
      *     - Hours > 40: overtime at 1.5x rate
      *     - Tax brackets (EVALUATE TRUE):
      *         gross <  500:  5%
      *         gross < 1500: 12%
      *         gross < 3000: 22%
      *         gross >= 3000: 30%
      *     - Net pay = gross - tax
      *---------------------------------------------------------------
       8200-CALCULATE-PAY.
           MOVE ZEROS TO WS-REGULAR-HOURS.
           MOVE ZEROS TO WS-OVERTIME-HOURS.
           MOVE ZEROS TO WS-REGULAR-PAY.
           MOVE ZEROS TO WS-OVERTIME-PAY.
           MOVE ZEROS TO WS-GROSS-PAY.
           MOVE ZEROS TO WS-TAX-AMOUNT.
           MOVE ZEROS TO WS-NET-PAY.
           IF EMP-HOURS-WORKED(WS-IDX) > WS-STANDARD-HOURS
               MOVE WS-STANDARD-HOURS TO WS-REGULAR-HOURS
               COMPUTE WS-OVERTIME-HOURS ROUNDED =
                   EMP-HOURS-WORKED(WS-IDX) - WS-STANDARD-HOURS
           ELSE
               MOVE EMP-HOURS-WORKED(WS-IDX) TO WS-REGULAR-HOURS
               MOVE ZEROS TO WS-OVERTIME-HOURS
           END-IF.
           COMPUTE WS-REGULAR-PAY ROUNDED =
               WS-REGULAR-HOURS * EMP-HOURLY-RATE(WS-IDX).
           COMPUTE WS-OVERTIME-PAY ROUNDED =
               WS-OVERTIME-HOURS * EMP-HOURLY-RATE(WS-IDX)
               * WS-OVERTIME-MULTIPLIER.
           COMPUTE WS-GROSS-PAY ROUNDED =
               WS-REGULAR-PAY + WS-OVERTIME-PAY.
           PERFORM 8300-DETERMINE-TAX-RATE.
           COMPUTE WS-TAX-AMOUNT ROUNDED =
               WS-GROSS-PAY * WS-TAX-RATE.
           COMPUTE WS-NET-PAY =
               WS-GROSS-PAY - WS-TAX-AMOUNT.
           MOVE WS-GROSS-PAY  TO EMP-GROSS-PAY(WS-IDX).
           MOVE WS-TAX-AMOUNT TO EMP-TAX(WS-IDX).
           MOVE WS-NET-PAY    TO EMP-NET-PAY(WS-IDX).
           MOVE 'Y'           TO EMP-PAY-COMPUTED(WS-IDX).

      *---------------------------------------------------------------
      * 8300 - UTILITY: DETERMINE TAX RATE FROM GROSS PAY
      *---------------------------------------------------------------
       8300-DETERMINE-TAX-RATE.
           EVALUATE TRUE
               WHEN WS-GROSS-PAY < 500
                   MOVE 0.05 TO WS-TAX-RATE
               WHEN WS-GROSS-PAY < 1500
                   MOVE 0.12 TO WS-TAX-RATE
               WHEN WS-GROSS-PAY < 3000
                   MOVE 0.22 TO WS-TAX-RATE
               WHEN OTHER
                   MOVE 0.30 TO WS-TAX-RATE
           END-EVALUATE.

      *---------------------------------------------------------------
      * 9000 - DISPLAY ONE EMPLOYEE RECORD
      *---------------------------------------------------------------
       9000-DISPLAY-EMPLOYEE.
           MOVE EMP-ID(WS-FOUND-IDX)          TO WS-DISP-ID.
           MOVE EMP-HOURLY-RATE(WS-FOUND-IDX) TO WS-DISP-RATE.
           MOVE EMP-HOURS-WORKED(WS-FOUND-IDX) TO WS-DISP-HOURS.
           MOVE EMP-GROSS-PAY(WS-FOUND-IDX)   TO WS-DISP-GROSS.
           MOVE EMP-TAX(WS-FOUND-IDX)         TO WS-DISP-TAX.
           MOVE EMP-NET-PAY(WS-FOUND-IDX)     TO WS-DISP-NET.
           DISPLAY " ".
           DISPLAY "--- Employee Record ----------------------".
           DISPLAY "  ID         : " WS-DISP-ID.
           DISPLAY "  Name       : " EMP-NAME(WS-FOUND-IDX).
           DISPLAY "  Department : " EMP-DEPT(WS-FOUND-IDX).
           DISPLAY "  Hourly Rate: " WS-DISP-RATE.
           DISPLAY "  Hours      : " WS-DISP-HOURS.
           IF EMP-PAY-COMPUTED(WS-FOUND-IDX) = 'Y'
               DISPLAY "  Gross Pay  : " WS-DISP-GROSS
               DISPLAY "  Tax        : " WS-DISP-TAX
               DISPLAY "  Net Pay    : " WS-DISP-NET
           ELSE
               DISPLAY "  Pay: not yet computed for this period."
           END-IF.
           DISPLAY "-----------------------------------------".
