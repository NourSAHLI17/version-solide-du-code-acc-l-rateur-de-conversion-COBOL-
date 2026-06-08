import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cobol_samples import COB_SIMPLE_INVENTORY

from app.parsers import copybook_resolver
from app.parsers.cobol_parser import ParserLayer


class ParserLayerTests(unittest.TestCase):
    def setUp(self):
        self.parser = ParserLayer()

    def test_output_contract_keys(self):
        result = self.parser.parse("PROCEDURE DIVISION.")
        self.assertEqual(
            sorted(result.keys()),
            sorted(
                [
                    "program_name",
                    "source_format",
                    "column_aware",
                    "preflight_errors",
                    "errors",
                    "files",
                    "divisions",
                    "sections",
                    "paragraphs",
                    "paragraph_table",
                    "java_class",
                    "symbol_table",
                    "symbol_table_entries",
                    "control_flow",
                    "operations",
                    "sorts",
                    "dependencies",
                    "risk_flags",
                    "warnings",
                    "parser_revision",
                ]
            ),
        )

    def test_control_flow_has_gotos_key(self):
        result = self.parser.parse("PROCEDURE DIVISION.")
        self.assertIn("gotos", result["control_flow"])

    # ─── ISSUE-01: Division name corruption ──────────────────────────────

    def test_simple_conditional(self):
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 BALANCE PIC 9(5)V99 VALUE 1000.
       01 AMOUNT  PIC 9(5)V99 VALUE 200.
       01 STATUS  PIC X(10).

       PROCEDURE DIVISION.
           IF BALANCE < AMOUNT
               MOVE 'REJECTED' TO STATUS
           ELSE
               SUBTRACT AMOUNT FROM BALANCE
               MOVE 'APPROVED' TO STATUS
           END-IF.
        """

        result = self.parser.parse(source)

        self.assertEqual(result["program_name"], None)
        self.assertEqual(result["source_format"], "fixed")
        self.assertEqual(result["preflight_errors"], [])
        self.assertEqual(result["divisions"], ["DATA DIVISION", "PROCEDURE DIVISION"])
        self.assertEqual(result["sections"], ["WORKING-STORAGE SECTION"])
        self.assertEqual(result["paragraphs"], [])
        self.assertIn("conditional_logic", result["risk_flags"])

    def test_division_name_not_truncated(self):
        """ISSUE-01: IDENTIFICATION DIVISION must not be truncated."""
        source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTPROG.
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       PROCEDURE DIVISION.
           STOP RUN.
        """
        result = self.parser.parse(source)
        self.assertEqual(result["divisions"], [
            "IDENTIFICATION DIVISION",
            "ENVIRONMENT DIVISION",
            "DATA DIVISION",
            "PROCEDURE DIVISION",
        ])

    def test_id_division_normalized(self):
        """ISSUE-01: ID DIVISION should be normalized to IDENTIFICATION DIVISION."""
        source = """
       ID DIVISION.
       PROGRAM-ID. TESTPROG.
       DATA DIVISION.
       PROCEDURE DIVISION.
           STOP RUN.
        """
        result = self.parser.parse(source)
        self.assertIn("IDENTIFICATION DIVISION", result["divisions"])

    # ─── ISSUE-02: PERFORM UNTIL loop ────────────────────────────────────

    def test_perform_varying_loop(self):
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 I PIC 9(2).
       01 TOTAL PIC 9(5).
       PROCEDURE DIVISION.
           PERFORM VARYING I FROM 1 BY 1 UNTIL I > 10
               ADD I TO TOTAL
           END-PERFORM.
        """

        result = self.parser.parse(source)

        self.assertEqual(result["preflight_errors"], [])
        loops = result["control_flow"]["loops"]
        self.assertEqual(len(loops), 1)
        self.assertEqual(loops[0]["type"], "PERFORM_VARYING")
        self.assertEqual(loops[0]["iterator"], "I")
        self.assertEqual(loops[0]["start"], "1")
        self.assertEqual(loops[0]["step"], "1")
        self.assertEqual(loops[0]["until"], "I > 10")
        self.assertTrue(loops[0]["inline"])
        self.assertIn("loop_logic", result["risk_flags"])

    def test_perform_external_until_captured(self):
        """ISSUE-02: PERFORM <para> UNTIL must be captured as loop + call."""
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 MENU-CHOICE PIC X(1).
       PROCEDURE DIVISION.
       MAIN-PARAGRAPH.
           PERFORM DISPLAY-MENU UNTIL MENU-CHOICE = "0".
           STOP RUN.
       DISPLAY-MENU.
           DISPLAY "MENU".
           ACCEPT MENU-CHOICE.
        """
        result = self.parser.parse(source)
        loops = result["control_flow"]["loops"]
        loop_types = [l["type"] for l in loops]
        self.assertIn("PERFORM_UNTIL", loop_types)

        until_loops = [l for l in loops if l["type"] == "PERFORM_UNTIL"]
        self.assertTrue(any(l.get("target_paragraph") == "DISPLAY-MENU" for l in until_loops))
        self.assertFalse(any(l.get("inline") for l in until_loops if l.get("target_paragraph") == "DISPLAY-MENU"))

    # ─── ISSUE-03: Inter-paragraph PERFORM calls ────────────────────────

    def test_simple_perform_captured_as_call(self):
        """ISSUE-03: Simple PERFORM <para> must go into calls array."""
        source = """
       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM PROCESS-DATA.
           STOP RUN.
       PROCESS-DATA.
           DISPLAY "PROCESSING".
        """
        result = self.parser.parse(source)
        calls = result["control_flow"]["calls"]
        perform_calls = [c for c in calls if c.get("type") == "PERFORM"]
        self.assertTrue(len(perform_calls) >= 1)
        self.assertTrue(any(c["to"] == "PROCESS-DATA" for c in perform_calls))

    def test_perform_until_external_recorded_in_calls_and_loops(self):
        """ISSUE-03: PERFORM <para> UNTIL is both a loop and a call."""
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 X PIC 9.
       PROCEDURE DIVISION.
       MAIN.
           PERFORM WORKER UNTIL X = 0.
           STOP RUN.
       WORKER.
           DISPLAY "WORK".
        """
        result = self.parser.parse(source)
        loops = result["control_flow"]["loops"]
        calls = result["control_flow"]["calls"]

        self.assertTrue(any(l.get("target_paragraph") == "WORKER" for l in loops))
        self.assertTrue(any(c.get("to") == "WORKER" for c in calls))

    # ─── ISSUE-04: MOVE to subscripted fields ────────────────────────────

    def test_move_to_subscripted_field(self):
        """ISSUE-04: MOVE X TO FIELD(I) must capture subscript and array flag."""
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 I PIC 9(3).
       01 ITEMS.
          05 INV-NAME PIC X(20) OCCURS 100 TIMES.
       01 ITEM-NAME PIC X(20).
       PROCEDURE DIVISION.
       ADD-ITEM.
           PERFORM VARYING I FROM 1 BY 1 UNTIL I > 100
               MOVE ITEM-NAME TO INV-NAME(I)
           END-PERFORM.
        """
        result = self.parser.parse(source)
        move_ops = [op for op in result["operations"] if op["type"] == "MOVE"]
        subscripted = [op for op in move_ops if op.get("target_subscript")]
        self.assertTrue(len(subscripted) >= 1)
        self.assertEqual(subscripted[0]["target"], "INV-NAME")
        self.assertEqual(subscripted[0]["target_subscript"], "I")
        self.assertTrue(subscripted[0].get("target_is_array_element"))

    def test_move_figurative_captured(self):
        """ISSUE-04: MOVE SPACES TO FIELD must flag value_is_figurative."""
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 I PIC 9(3).
       01 ITEMS.
          05 INV-NAME PIC X(20) OCCURS 100 TIMES.
       PROCEDURE DIVISION.
       DELETE-ITEM.
           MOVE SPACES TO INV-NAME(I).
        """
        result = self.parser.parse(source)
        move_ops = [op for op in result["operations"] if op["type"] == "MOVE"]
        self.assertTrue(any(op.get("value_is_figurative") for op in move_ops))

    # ─── ISSUE-05: EXIT PERFORM ──────────────────────────────────────────

    def test_exit_perform_captured(self):
        """ISSUE-05: EXIT PERFORM must be captured in operations."""
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 I PIC 9(3).
       01 FLAG PIC X.
       PROCEDURE DIVISION.
       FIND-ITEM.
           PERFORM VARYING I FROM 1 BY 1 UNTIL I > 100
               IF FLAG = 'Y'
                   EXIT PERFORM
               END-IF
           END-PERFORM.
        """
        result = self.parser.parse(source)
        op_types = [op["type"] for op in result["operations"]]
        self.assertIn("EXIT_PERFORM", op_types)

    def test_exit_perform_cycle_captured(self):
        """ISSUE-05: EXIT PERFORM CYCLE must be captured."""
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 I PIC 9(3).
       PROCEDURE DIVISION.
       LOOP-PARA.
           PERFORM VARYING I FROM 1 BY 1 UNTIL I > 10
               EXIT PERFORM CYCLE
           END-PERFORM.
        """
        result = self.parser.parse(source)
        op_types = [op["type"] for op in result["operations"]]
        self.assertIn("EXIT_PERFORM_CYCLE", op_types)

    def test_stop_run_captured(self):
        """ISSUE-05: STOP RUN must be captured in operations."""
        source = """
       PROCEDURE DIVISION.
       QUIT.
           STOP RUN.
        """
        result = self.parser.parse(source)
        op_types = [op["type"] for op in result["operations"]]
        self.assertIn("STOP_RUN", op_types)

    # ─── GO TO tracking ──────────────────────────────────────────────────

    def test_goto_captured_in_gotos_array(self):
        source = """
       PROCEDURE DIVISION.
       MAIN.
           GO TO ERR-PARA.
       ERR-PARA.
           DISPLAY "ERROR".
        """
        result = self.parser.parse(source)
        gotos = result["control_flow"]["gotos"]
        self.assertTrue(len(gotos) >= 1)
        self.assertEqual(gotos[0]["to_paragraph"], "ERR-PARA")

    # ─── Structured warnings ─────────────────────────────────────────────

    def test_parser_truncates_at_column_72(self):
        long_move = (
            "       MOVE 'A' TO X-VAR-WITH-VERY-LONG-NAME-EXCEEDING-COLUMN-72."
        )
        overflow_line = long_move.ljust(72) + "OVERFL"
        src = f"""
       IDENTIFICATION DIVISION.
       PROGRAM-ID. COL72TEST.
       PROCEDURE DIVISION.
{overflow_line}
       STOP RUN.
"""
        result = self.parser.parse(src)
        self.assertTrue(result.get("column_aware"))
        self.assertTrue(
            any("line exceeds column 72" in w["message"] for w in result["warnings"]),
            result["warnings"],
        )
        move_ops = [op for op in result["operations"] if op.get("type") == "MOVE"]
        self.assertTrue(move_ops)
        target = str(move_ops[0].get("target", ""))
        self.assertNotIn("OVERFL", target)

    def test_warnings_are_structured(self):
        """Warnings should now be structured with code/severity/message."""
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 UNUSED-VAR PIC X(10).
       PROCEDURE DIVISION.
           STOP RUN.
        """
        result = self.parser.parse(source)
        for w in result["warnings"]:
            self.assertIsInstance(w, dict)
            self.assertIn("code", w)
            self.assertIn("severity", w)
            self.assertIn("message", w)

    # ─── Existing tests (adapted) ────────────────────────────────────────

    def test_copybook_detection(self):
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY CUSTOMER-REC.
        """

        result = self.parser.parse(source)
        self.assertEqual(
            result["dependencies"]["copybooks"],
            ["CUSTOMER-REC"],
        )
        self.assertEqual(result["dependencies"]["files"], [])
        self.assertEqual(result["dependencies"]["file_kinds"], {})

    def test_redefines_and_occurs(self):
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 CUSTOMER-DATA.
          05 CUSTOMER-ID      PIC 9(5).
          05 CUSTOMER-NAME    PIC X(20).
       01 RAW-DATA REDEFINES CUSTOMER-DATA PIC X(25).
       01 ITEMS.
          05 ITEM-CODE PIC X(3) OCCURS 10 TIMES.
        """

        result = self.parser.parse(source)
        symbols = {item["name"]: item for item in result["symbol_table_entries"]}

        self.assertEqual(symbols["CUSTOMER-DATA"]["kind"], "group")
        self.assertEqual(symbols["RAW-DATA"]["kind"], "redefines")
        self.assertEqual(symbols["ITEM-CODE"]["kind"], "array")
        self.assertEqual(symbols["ITEM-CODE"]["occurs"], 10)
        self.assertIn("redefines_present", result["risk_flags"])
        self.assertIn("occurs_present", result["risk_flags"])

    def test_false_paragraphs_are_not_detected_from_display_continuations(self):
        source = """
000100 IDENTIFICATION DIVISION.
000200 PROGRAM-ID. LICENSED.
000300 PROCEDURE DIVISION.
000400 MAIN-PARA.
000500     DISPLAY "-----------------------------------------------------"
000600-    "-----------------------------------------------------"
000700-    "-----------".
000800     DISPLAY
000900-    "furnished to do so, subject to the following "
001000-    "conditions:".
001100     DISPLAY
001200-    "THE SOFTWARE.".
001300     END-WRITE.
001400     END-READ.
001500     STOP-RUN.
        """

        result = self.parser.parse(source)

        self.assertEqual(result["preflight_errors"], [])
        self.assertEqual(result["paragraphs"], ["MAIN-PARA"])
        self.assertNotIn("-----------", result["paragraphs"])
        self.assertNotIn("conditions:", result["paragraphs"])
        self.assertNotIn("SOFTWARE", result["paragraphs"])
        self.assertNotIn("END-WRITE", result["paragraphs"])
        self.assertNotIn("END-READ", result["paragraphs"])
        self.assertNotIn("STOP-RUN", result["paragraphs"])

    def test_program_id_and_valid_paragraph_detection(self):
        source = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYROLL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       77 WS-COUNT PIC 9(4).
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE 1 TO WS-COUNT.
       NEXT-PARA.
           MOVE 2 TO WS-COUNT.
        """

        result = self.parser.parse(source)

        self.assertEqual(result["program_name"], "PAYROLL")
        self.assertEqual(result["paragraphs"], ["MAIN-PARA", "NEXT-PARA"])

    def test_comments_sequence_numbers_and_continuation(self):
        source = """
000100 IDENTIFICATION DIVISION.
000200 PROGRAM-ID. CONTDEMO.
000300 DATA DIVISION.
000400 WORKING-STORAGE SECTION.
000500 01 WS-TEXT PIC X(20).
000600* THIS IS A COMMENT LINE
000700 PROCEDURE DIVISION.
000800     MOVE 'HELLO'
000900-    TO WS-TEXT.
        """

        result = self.parser.parse(source)
        self.assertEqual(result["program_name"], "CONTDEMO")
        move_ops = [op for op in result["operations"] if op["type"] == "MOVE"]
        self.assertTrue(any(op["value"] == "HELLO" and op["target"] == "WS-TEXT" for op in move_ops))

    def test_parser_accepts_sd_for_sort_files(self):
        src = """
           IDENTIFICATION DIVISION.
           PROGRAM-ID. TESTSORT.
           ENVIRONMENT DIVISION.
           INPUT-OUTPUT SECTION.
           FILE-CONTROL.
               SELECT SORT-WORK ASSIGN TO "SORTWK.dat".
           DATA DIVISION.
           FILE SECTION.
           SD SORT-WORK.
           01 SORT-REC.
              05 SORT-KEY PIC 9(4).
           WORKING-STORAGE SECTION.
           PROCEDURE DIVISION.
           MAIN.
               SORT SORT-WORK ON ASCENDING KEY SORT-KEY
                   INPUT PROCEDURE LOAD-INPUT
                   OUTPUT PROCEDURE WRITE-OUTPUT.
               STOP RUN.
           LOAD-INPUT. EXIT.
           WRITE-OUTPUT. EXIT.
        """
        result = self.parser.parse(src)
        self.assertFalse(any("no matching FD" in e for e in result["errors"]))
        self.assertFalse(any("no FD or SD entry" in e for e in result["preflight_errors"]))
        self.assertTrue(
            any(f["name"] == "SORT-WORK" and f["kind"] == "SD" for f in result["files"])
        )
        self.assertEqual(result["dependencies"]["file_kinds"].get("SORT-WORK"), "SD")
        self.assertEqual(len(result["sorts"]), 1)
        sort_op = result["sorts"][0]
        self.assertEqual(sort_op["file"], "SORT-WORK")
        self.assertEqual(sort_op["keys"][0]["direction"], "ASCENDING")
        self.assertEqual(sort_op["input_procedure"]["from"], "LOAD-INPUT")
        self.assertEqual(sort_op["output_procedure"]["from"], "WRITE-OUTPUT")

    def test_missing_fd_preflight_error_halts_parse(self):
        source = """
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT INVENTORY-FILE ASSIGN TO 'INV.DAT'.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-NAME PIC X(20).
       PROCEDURE DIVISION.
           READ INVENTORY-FILE.
        """

        result = self.parser.parse(source)
        self.assertIn(
            "FILE-CONTROL references INVENTORY-FILE but no FD or SD entry was found.",
            result["preflight_errors"],
        )
        self.assertEqual(result["operations"], [])
        self.assertEqual(result["paragraphs"], [])

    def test_undeclared_perform_varying_index_is_preflight_error(self):
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 TOTAL PIC 9(5).
       PROCEDURE DIVISION.
           PERFORM VARYING I FROM 1 BY 1 UNTIL I > 10
               ADD I TO TOTAL
           END-PERFORM.
        """

        result = self.parser.parse(source)
        self.assertIn("PERFORM VARYING uses undeclared index I.", result["preflight_errors"])

    def test_fd_copy_record_key_resolved_from_copybook(self):
        """RECORD KEY in SELECT must resolve against fields from COPY inside FD."""
        src = """
           IDENTIFICATION DIVISION.
           PROGRAM-ID. TESTSCORE.
           ENVIRONMENT DIVISION.
           INPUT-OUTPUT SECTION.
           FILE-CONTROL.
               SELECT SCORE-FILE
                   ASSIGN TO "SCORFILE.dat"
                   ORGANIZATION IS INDEXED
                   ACCESS MODE IS DYNAMIC
                   RECORD KEY IS SCR-RESULT-ID
                   FILE STATUS IS WS-SCR-FS.
           DATA DIVISION.
           FILE SECTION.
           FD SCORE-FILE RECORD CONTAINS 229 CHARACTERS.
           COPY SCORECOPY.
           PROCEDURE DIVISION.
               STOP RUN.
        """
        scorecopy = """
       01 SCORE-RESULT.
          05 SCR-RESULT-ID        PIC 9(12)     VALUE ZEROS.
          05 SCR-LOAN-ID          PIC 9(10)     VALUE ZEROS.
        """
        with tempfile.TemporaryDirectory() as tmp:
            copy_dir = os.path.join(tmp, "copybooks")
            os.makedirs(copy_dir)
            with open(os.path.join(copy_dir, "SCORECOPY.cpy"), "w", encoding="utf-8") as handle:
                handle.write(scorecopy)

            prior = list(copybook_resolver.COPY_LIBRARY_CONFIG.get("default", []))
            copybook_resolver.COPY_LIBRARY_CONFIG["default"] = [copy_dir] + prior
            try:
                result = self.parser.parse(src)
            finally:
                copybook_resolver.COPY_LIBRARY_CONFIG["default"] = prior

        errors = list(result.get("preflight_errors") or []) + list(result.get("errors") or [])
        self.assertFalse(
            any("SCR-RESULT-ID" in e and "not defined" in e for e in errors),
            errors,
        )
        self.assertFalse(
            any("RECORD KEY SCR-RESULT-ID" in e for e in errors),
            errors,
        )
        score_file = next(f for f in result["files"] if f["name"] == "SCORE-FILE")
        field_names = {fld["name"] for fld in score_file["fields"]}
        self.assertIn("SCR-RESULT-ID", field_names)
        self.assertIn("SCORE-RESULT", field_names)

    def test_record_key_missing_from_fd_copy_is_preflight_error(self):
        src = """
           ENVIRONMENT DIVISION.
           INPUT-OUTPUT SECTION.
           FILE-CONTROL.
               SELECT SCORE-FILE
                   ASSIGN TO "SCORFILE.dat"
                   ORGANIZATION IS INDEXED
                   RECORD KEY IS SCR-RESULT-ID.
           DATA DIVISION.
           FILE SECTION.
           FD SCORE-FILE.
           COPY SCORECOPY.
           PROCEDURE DIVISION.
               STOP RUN.
        """
        scorecopy = """
       01 SCORE-RESULT.
          05 SCR-OTHER-ID PIC 9(12).
        """
        with tempfile.TemporaryDirectory() as tmp:
            copy_dir = os.path.join(tmp, "copybooks")
            os.makedirs(copy_dir)
            with open(os.path.join(copy_dir, "SCORECOPY.cpy"), "w", encoding="utf-8") as handle:
                handle.write(scorecopy)

            prior = list(copybook_resolver.COPY_LIBRARY_CONFIG.get("default", []))
            copybook_resolver.COPY_LIBRARY_CONFIG["default"] = [copy_dir] + prior
            try:
                result = self.parser.parse(src)
            finally:
                copybook_resolver.COPY_LIBRARY_CONFIG["default"] = prior

        self.assertIn(
            "RECORD KEY SCR-RESULT-ID for SCORE-FILE is not defined in FD record description.",
            result["preflight_errors"],
        )

    def test_parser_recognizes_indexed_by(self):
        src = """
           IDENTIFICATION DIVISION.
           PROGRAM-ID. TESTIDX.
           DATA DIVISION.
           WORKING-STORAGE SECTION.
           01 WS-TABLE.
              05 WS-ENTRY OCCURS 10 TIMES INDEXED BY MY-IDX.
                 10 WS-VALUE PIC 9(4).
           PROCEDURE DIVISION.
           MAIN.
               PERFORM VARYING MY-IDX FROM 1 BY 1 UNTIL MY-IDX > 10
                   DISPLAY WS-VALUE(MY-IDX)
               END-PERFORM.
               STOP RUN.
        """
        result = self.parser.parse(src)
        errors = list(result.get("preflight_errors") or []) + list(result.get("errors") or [])
        self.assertFalse(any("undeclared index" in e for e in errors))
        symbols = {s["name"]: s for s in result["symbol_table_entries"]}
        self.assertEqual(symbols["MY-IDX"]["kind"], "index")
        self.assertEqual(symbols["MY-IDX"]["parent_table"], "WS-ENTRY")
        self.assertEqual(symbols["MY-IDX"]["occurs_count"], 10)

    def test_duplicate_data_names_are_preflight_errors(self):
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 ITEM-RECORD.
          05 ITEM-NAME PIC X(10).
       01 ITEM-RECORD.
          05 ITEM-CODE PIC X(3).
       PROCEDURE DIVISION.
           STOP RUN.
        """

        result = self.parser.parse(source)
        self.assertIn("Duplicate data name ITEM-RECORD detected in data declarations.", result["preflight_errors"])

    def test_cob_simpleinventory_parses_without_false_paragraphs(self):
        result = self.parser.parse(COB_SIMPLE_INVENTORY)

        self.assertEqual(result["program_name"], "COB-SIMPLEINVENTORY")
        self.assertEqual(result["preflight_errors"], [])
        self.assertIn("DATAFILE", result["dependencies"]["files"])
        self.assertNotIn("FILE", result["dependencies"]["files"])
        self.assertIn("WORKING-STORAGE SECTION", result["sections"])
        self.assertIn("LOCAL-STORAGE SECTION", result["sections"])
        self.assertIn("0000SELECTIONSTART", result["paragraphs"])
        self.assertIn("0000SELECTIONINFO", result["paragraphs"])
        self.assertIn("0000SELECTIONQUIT", result["paragraphs"])
        self.assertNotIn("-----------", result["paragraphs"])
        self.assertNotIn("conditions:", result["paragraphs"])
        self.assertNotIn("SOFTWARE", result["paragraphs"])
        self.assertNotIn("END-WRITE", result["paragraphs"])
        self.assertNotIn("END-READ", result["paragraphs"])
        self.assertNotIn("STOP-RUN", result["paragraphs"])
        self.assertGreaterEqual(len(result["paragraphs"]), 15)
        self.assertGreaterEqual(len(result["operations"]), 40)
        self.assertGreaterEqual(len(result["control_flow"]["branches"]), 6)
        self.assertGreaterEqual(len(result["control_flow"]["loops"]), 4)
        self.assertIn("goto_present", result["risk_flags"])
        self.assertIn("external_io_present", result["risk_flags"])
        # ISSUE-03: calls should now be populated
        self.assertGreater(len(result["control_flow"]["calls"]), 0)

    # ─── PERFORM THRU ────────────────────────────────────────────────────

    def test_perform_thru_captured_as_call(self):
        """PERFORM A THRU B must record a PERFORM_THRU call with to_end."""
        source = """
       PROCEDURE DIVISION.
       MAIN.
           PERFORM INIT-PARA THRU END-INIT.
           STOP RUN.
       INIT-PARA.
           DISPLAY "INIT".
       END-INIT.
           DISPLAY "DONE".
        """
        result = self.parser.parse(source)
        calls = result["control_flow"]["calls"]
        thru_calls = [c for c in calls if c.get("type") == "PERFORM_THRU"]
        self.assertTrue(len(thru_calls) >= 1)
        self.assertEqual(thru_calls[0]["to"], "INIT-PARA")
        self.assertEqual(thru_calls[0]["to_end"], "END-INIT")

    def test_perform_thru_until_captured_as_loop_and_call(self):
        """PERFORM A THRU B UNTIL cond must create both a loop and a call."""
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 X PIC 9.
       PROCEDURE DIVISION.
       MAIN.
           PERFORM WORKER THRU WORKER-END UNTIL X = 0.
           STOP RUN.
       WORKER.
           DISPLAY "WORK".
       WORKER-END.
           DISPLAY "END".
        """
        result = self.parser.parse(source)
        calls = result["control_flow"]["calls"]
        loops = result["control_flow"]["loops"]
        thru_calls = [c for c in calls if c.get("type") == "PERFORM_THRU"]
        self.assertTrue(len(thru_calls) >= 1, f"Expected PERFORM_THRU call: {calls}")
        self.assertTrue(
            any(l.get("target_paragraph") == "WORKER" and l.get("type") == "PERFORM_UNTIL" for l in loops),
            f"Expected PERFORM_UNTIL loop for WORKER: {loops}"
        )


if __name__ == "__main__":
    unittest.main()
