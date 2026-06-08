      ******************************************************************
      * TEMPCNVT — Minimal temperature conversion (Celsius ↔ Fahrenheit)
      ******************************************************************
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEMPCNVT.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-CELSIUS       PIC S9(4)V99.
       01 WS-FAHRENHEIT    PIC S9(4)V99.

       PROCEDURE DIVISION.
       0000-MAIN.
           MOVE 0 TO WS-CELSIUS
           PERFORM 1000-CNVRT
           STOP RUN.

       1000-CNVRT.
           COMPUTE WS-FAHRENHEIT = (WS-CELSIUS * 9 / 5) + 32.
