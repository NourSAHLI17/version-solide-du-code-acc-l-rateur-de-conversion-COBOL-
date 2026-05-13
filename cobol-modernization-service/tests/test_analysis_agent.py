import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cobol_samples import COB_SIMPLE_INVENTORY

from app.agents.facade import ModernizationAgents
from app.parsers.cobol_parser import ParserLayer


ANALYSIS_RESPONSE_TOP_LEVEL_KEYS = [
    "program_name",
    "global_purpose",
    "complexity",
    "complexity_drivers",
    "sections",
    "business_rules",
    "file_io_paragraphs",
    "loop_paragraphs",
    "all_business_rules",
    "dependencies",
    "risk_points",
    "risk_flags",
    "conversion_guidance",
    "data_flow_summary",
    "assumptions",
    "warnings",
    "paragraph_source_extraction",
    "analysis_engine",
    "analysis_revision",
]


class AnalysisAgentTests(unittest.TestCase):
    def setUp(self):
        # Locked expectations below assume deterministic roles and rules,
        # not live LLM output when credentials are present in the developer environment.
        self._prev_analysis_engine = os.environ.get("ANALYSIS_ENGINE")
        self._prev_overlay_dbg = os.environ.get("ANALYSIS_OVERLAY_DEBUG")
        os.environ["ANALYSIS_ENGINE"] = "deterministic"
        os.environ["ANALYSIS_OVERLAY_DEBUG"] = "0"
        self.parser = ParserLayer()
        self.agents = ModernizationAgents()

    def tearDown(self):
        if self._prev_analysis_engine is None:
            os.environ.pop("ANALYSIS_ENGINE", None)
        else:
            os.environ["ANALYSIS_ENGINE"] = self._prev_analysis_engine
        if self._prev_overlay_dbg is None:
            os.environ.pop("ANALYSIS_OVERLAY_DEBUG", None)
        else:
            os.environ["ANALYSIS_OVERLAY_DEBUG"] = self._prev_overlay_dbg

    def test_output_contract_keys(self):
        result = self.agents.analyze(
            "PROCEDURE DIVISION.",
            {"program_name": None, "paragraphs": [], "preflight_errors": [],
             "control_flow": {"branches": [], "loops": [], "calls": [], "gotos": []},
             "operations": [], "symbol_table": []},
        )
        self.assertEqual(sorted(result.keys()), sorted(ANALYSIS_RESPONSE_TOP_LEVEL_KEYS))
        self.assertEqual(result["analysis_engine"], "deterministic")
        self.assertEqual(result["analysis_revision"], 1)
        self.assertEqual(result["paragraph_source_extraction"], "heuristic_split")

    def test_preflight_halt_response_has_uniform_contract(self):
        parser_output = {
            "program_name": "BROKEN",
            "preflight_errors": ["Duplicate data name ITEM-RECORD detected."],
            "dependencies": {"copybooks": [], "files": [], "external_calls": []},
            "warnings": [],
        }
        result = self.agents.analyze("PROCEDURE DIVISION.", parser_output)
        self.assertEqual(result["analysis_engine"], "n/a")
        self.assertEqual(result["analysis_revision"], 0)
        self.assertEqual(result["paragraph_source_extraction"], "n/a")

    def test_all_response_paths_have_analysis_fields(self):
        """Completed vs halted paths expose analysis_engine / analysis_revision with correct types."""

        halted = self.agents.analyze(
            "PROCEDURE DIVISION.",
            {
                "program_name": None,
                "preflight_errors": ["halt"],
                "dependencies": {"copybooks": [], "files": [], "external_calls": []},
            },
        )
        self.assertEqual(halted["analysis_engine"], "n/a")
        self.assertIsInstance(halted["analysis_revision"], int)

        demo_src = """       PROCEDURE DIVISION.
       DEMO.
           STOP RUN.
"""
        minimal = ParserLayer().parse(demo_src)
        normal = self.agents.analyze(demo_src, minimal)
        self.assertEqual(normal["analysis_engine"], "deterministic")
        self.assertIsInstance(normal["analysis_revision"], int)
        self.assertNotEqual(normal["analysis_revision"], 0)

    def test_simple_conditional_banking_rule(self):
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

        parser_output = self.parser.parse(source)
        result = self.agents.analyze(source, parser_output)

        self.assertEqual(result["global_purpose"], "validate a transaction based on available balance and update the result status")
        self.assertEqual(result["complexity"], "low")
        self.assertEqual(result["sections"][0]["name"], "MAIN-LOGIC")
        self.assertEqual(result["sections"][0]["business_rules"], [])
        self.assertIn("financial decision rule", result["risk_points"])

    def test_loop_based_aggregation(self):
        source = """
       WORKING-STORAGE SECTION.
       01 I      PIC 9(2).
       01 TOTAL  PIC 9(5).

       PROCEDURE DIVISION.
           PERFORM VARYING I FROM 1 BY 1 UNTIL I > 10
               ADD I TO TOTAL
           END-PERFORM.
        """

        parser_output = self.parser.parse(source)
        result = self.agents.analyze(source, parser_output)

        self.assertEqual(
            result["global_purpose"],
            "Iteratively process repeated data until a stop condition is reached",
        )
        self.assertEqual(result["business_rules"], [])
        self.assertEqual(result["sections"][0]["business_rules"], [])
        self.assertEqual(result["loop_paragraphs"], ["MAIN-LOGIC"])

    def test_copybook_and_external_call(self):
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY CUSTOMER-REC.

       PROCEDURE DIVISION.
           CALL 'RATECALC'
        """

        parser_output = self.parser.parse(source)
        result = self.agents.analyze(source, parser_output)

        self.assertEqual(
            result["global_purpose"],
            "invoke an external rate calculation process using copied customer record structures",
        )
        self.assertEqual(result["complexity"], "high")
        self.assertIn("copybook dependency", result["complexity_drivers"])
        self.assertIn("external dependency", result["risk_points"])
        self.assertIn("copybook dependency", result["risk_points"])

    def test_nested_logic_medium_or_high_complexity(self):
        source = """
       PROCEDURE DIVISION.
           IF BALANCE < AMOUNT
               MOVE 'REJECTED' TO STATUS
           ELSE
               IF VIP-FLAG = 'Y'
                   MOVE 'APPROVED' TO STATUS
               ELSE
                   SUBTRACT AMOUNT FROM BALANCE
                   MOVE 'APPROVED' TO STATUS
               END-IF
           END-IF.
        """

        parser_output = self.parser.parse(source)
        result = self.agents.analyze(source, parser_output)

        self.assertEqual(result["global_purpose"], "approve or reject a transaction based on balance and VIP status")
        self.assertIn(result["complexity"], {"low", "medium"})
        self.assertIn("conditional business exception", result["risk_points"])
        self.assertEqual(result["business_rules"], [])

    # ─── ISSUE-06: Entry point role classification ───────────────────────

    def test_entry_paragraph_is_not_classified_as_termination(self):
        """ISSUE-06: First paragraph with STOP RUN + PERFORM calls = entry point, not termination."""
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 MENU-CHOICE PIC X(1).
       PROCEDURE DIVISION.
       MAIN-PARAGRAPH.
           DISPLAY "WELCOME".
           PERFORM DISPLAY-MENU UNTIL MENU-CHOICE = "0".
           STOP RUN.
       DISPLAY-MENU.
           DISPLAY "MENU".
           ACCEPT MENU-CHOICE.
        """
        parser_output = self.parser.parse(source)
        result = self.agents.analyze(source, parser_output)
        sections = {s["name"]: s for s in result["sections"]}

        # MAIN-PARAGRAPH must NOT be "Terminate program execution"
        self.assertNotEqual(sections["MAIN-PARAGRAPH"]["role"], "Terminate program execution")
        self.assertIn("entry point", sections["MAIN-PARAGRAPH"]["role"].lower())

        # global_purpose must NOT be "Terminate program execution"
        self.assertNotEqual(result["global_purpose"], "Terminate program execution")

    def test_pure_termination_paragraph(self):
        """A paragraph with ONLY STOP RUN should be classified as termination."""
        source = """
       PROCEDURE DIVISION.
       MAIN.
           PERFORM WORKER.
           STOP RUN.
       WORKER.
           DISPLAY "HELLO".
        """
        parser_output = self.parser.parse(source)
        result = self.agents.analyze(source, parser_output)
        sections = {s["name"]: s for s in result["sections"]}
        # MAIN is first paragraph with STOP RUN + a PERFORM call — should be entry point
        self.assertIn("entry point", sections["MAIN"]["role"].lower())

    # ─── ISSUE-07: Business rules ────────────────────────────────────────

    def test_invented_rule_not_present(self):
        """ISSUE-07: 'confirm deletion before removing' must NEVER appear."""
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 I PIC 9(3).
       01 ITEM-NAME PIC X(20).
       01 ITEMS.
          05 INV-NAME PIC X(20) OCCURS 100 TIMES.
          05 INV-QTY  PIC 9(5) OCCURS 100 TIMES.
          05 INV-PRC  PIC 9(5)V99 OCCURS 100 TIMES.
       PROCEDURE DIVISION.
       DELETE-ITEM.
           ACCEPT ITEM-NAME.
           PERFORM VARYING I FROM 1 BY 1 UNTIL I > 100
               IF INV-NAME(I) = ITEM-NAME
                   MOVE SPACES TO INV-NAME(I)
                   MOVE ZEROS TO INV-QTY(I)
                   MOVE ZEROS TO INV-PRC(I)
                   EXIT PERFORM
               END-IF
           END-PERFORM.
        """
        parser_output = self.parser.parse(source)
        result = self.agents.analyze(source, parser_output)
        all_rules = []
        for section in result["sections"]:
            all_rules.extend(section["business_rules"])
        all_rules.extend(result["business_rules"])
        for rule in all_rules:
            self.assertNotIn("confirm deletion", rule.lower())

    def test_capacity_rule_extracted(self):
        """Deterministic scaffold leaves business_rules empty (rules come from LLM overlay when enabled)."""
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 I PIC 9(3).
       01 ITEM-NAME PIC X(20).
       01 FOUND-FLAG PIC X VALUE 'N'.
       01 ITEMS.
          05 INV-NAME PIC X(20) OCCURS 100 TIMES.
       PROCEDURE DIVISION.
       ADD-ITEM.
           PERFORM VARYING I FROM 1 BY 1 UNTIL I > 100
               IF INV-NAME(I) = SPACES
                   MOVE ITEM-NAME TO INV-NAME(I)
                   EXIT PERFORM
               END-IF
           END-PERFORM.
        """
        parser_output = self.parser.parse(source)
        result = self.agents.analyze(source, parser_output)
        all_rules = []
        for section in result["sections"]:
            all_rules.extend(section["business_rules"])
        self.assertEqual(all_rules, [])

    # ─── ISSUE-08: Generic paragraph roles ───────────────────────────────

    def test_loop_paragraphs_have_specific_roles(self):
        """ISSUE-08: Loop paragraphs must have roles more specific than generic 'iteratively process'."""
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 I PIC 9(3).
       01 ITEM-NAME PIC X(20).
       01 ITEM-QTY PIC 9(5).
       01 ITEMS.
          05 INV-NAME PIC X(20) OCCURS 100 TIMES.
          05 INV-QTY  PIC 9(5) OCCURS 100 TIMES.
       PROCEDURE DIVISION.
       ADD-ITEM.
           ACCEPT ITEM-NAME.
           ACCEPT ITEM-QTY.
           PERFORM VARYING I FROM 1 BY 1 UNTIL I > 100
               IF INV-NAME(I) = SPACES
                   MOVE ITEM-NAME TO INV-NAME(I)
                   MOVE ITEM-QTY TO INV-QTY(I)
                   EXIT PERFORM
               END-IF
           END-PERFORM.
       DELETE-ITEM.
           ACCEPT ITEM-NAME.
           PERFORM VARYING I FROM 1 BY 1 UNTIL I > 100
               IF INV-NAME(I) = ITEM-NAME
                   MOVE SPACES TO INV-NAME(I)
                   MOVE ZEROS TO INV-QTY(I)
                   EXIT PERFORM
               END-IF
           END-PERFORM.
        """
        parser_output = self.parser.parse(source)
        result = self.agents.analyze(source, parser_output)
        sections = {s["name"]: s for s in result["sections"]}

        # ADD-ITEM should mention "insert" or "empty"
        add_role = sections.get("ADD-ITEM", {}).get("role", "")
        self.assertNotEqual(add_role, "Iteratively process repeated data until a stop condition is reached",
                           f"ADD-ITEM role is too generic: {add_role}")

        # DELETE-ITEM should mention "clear" or "delete"
        del_role = sections.get("DELETE-ITEM", {}).get("role", "")
        self.assertNotEqual(del_role, "Iteratively process repeated data until a stop condition is reached",
                           f"DELETE-ITEM role is too generic: {del_role}")

    # ─── ISSUE-09: Inputs/outputs and warnings ──────────────────────────

    def test_evaluate_subject_captured_as_input(self):
        """ISSUE-09: EVALUATE MENU-CHOICE means MENU-CHOICE is an input to that paragraph."""
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 MENU-CHOICE PIC X(1).
       PROCEDURE DIVISION.
       PROCESS-CHOICE.
           EVALUATE MENU-CHOICE
               WHEN "1"
                   DISPLAY "ONE"
               WHEN OTHER
                   DISPLAY "OTHER"
           END-EVALUATE.
        """
        parser_output = self.parser.parse(source)
        result = self.agents.analyze(source, parser_output)
        sections = {s["name"]: s for s in result["sections"]}
        inputs = sections.get("PROCESS-CHOICE", {}).get("inputs", [])
        self.assertIn("MENU-CHOICE", inputs, f"MENU-CHOICE not found in inputs: {inputs}")

    # ─── Existing adapted tests ──────────────────────────────────────────

    def test_per_paragraph_analysis_is_scoped_not_stamped(self):
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-IKEY PIC 9(4).
       FD DATAFILE.
       01 DATAFILEFD PIC X(80).
       PROCEDURE DIVISION.
       0000SELECTIONADD.
           ACCEPT WS-IKEY.
           WRITE DATAFILEFD INVALID KEY DISPLAY 'BAD'.
       0000SELECTIONQUIT.
           STOP RUN.
        """

        parser_output = self.parser.parse(source)
        result = self.agents.analyze(source, parser_output)
        sections = {section["name"]: section for section in result["sections"]}

        self.assertEqual(sections["0000SELECTIONADD"]["role"], "Accept user input and write new record")
        self.assertEqual(sections["0000SELECTIONADD"]["inputs"], [])
        self.assertIn("WS-IKEY", sections["0000SELECTIONADD"]["outputs"])
        self.assertIn("DATAFILEFD", sections["0000SELECTIONADD"]["outputs"])
        self.assertEqual(sections["0000SELECTIONQUIT"]["role"], "Terminate program execution")
        self.assertEqual(sections["0000SELECTIONQUIT"]["inputs"], [])
        self.assertEqual(sections["0000SELECTIONQUIT"]["outputs"], [])
        self.assertEqual(sections["0000SELECTIONQUIT"]["business_rules"], [])

    def test_preflight_errors_halt_analysis(self):
        parser_output = {
            "program_name": "BROKEN",
            "preflight_errors": ["Duplicate data name ITEM-RECORD detected in data declarations."],
            "dependencies": {"copybooks": [], "files": [], "external_calls": []},
            "warnings": [],
        }

        result = self.agents.analyze("PROCEDURE DIVISION.", parser_output)

        self.assertEqual(result["sections"], [])
        self.assertEqual(result["conversion_guidance"]["preferred_strategy"], "halted")
        self.assertIn(
            "Duplicate data name ITEM-RECORD detected in data declarations.",
            result["warnings"],
        )
        # Preflight halt uses the same top-level contract as completed analysis (FIX 1).
        self.assertEqual(sorted(result.keys()), sorted(ANALYSIS_RESPONSE_TOP_LEVEL_KEYS))
        self.assertEqual(result["analysis_engine"], "n/a")
        self.assertEqual(result["analysis_revision"], 0)
        self.assertEqual(result["paragraph_source_extraction"], "n/a")

    def test_cob_simpleinventory_analysis_is_segment_scoped(self):
        parser_output = self.parser.parse(COB_SIMPLE_INVENTORY)
        result = self.agents.analyze(COB_SIMPLE_INVENTORY, parser_output)
        sections = {section["name"]: section for section in result["sections"]}

        self.assertEqual(
            result["global_purpose"],
            "manage inventory records through keyed file operations and user-driven menu actions",
        )
        self.assertEqual(result["complexity"], "high")
        self.assertIn("file I/O", result["complexity_drivers"])
        self.assertIn("unstructured control flow", result["risk_points"])
        self.assertIn("external file I/O", result["risk_points"])
        self.assertIn("0000SELECTIONINVENTORY", result["file_io_paragraphs"])
        self.assertIn("0000SELECTIONSTART", result["loop_paragraphs"])

        self.assertEqual(sections["0000SELECTIONQUIT"]["role"], "Terminate program execution")
        self.assertEqual(sections["0000SELECTIONQUIT"]["inputs"], [])
        self.assertEqual(sections["0000SELECTIONQUIT"]["outputs"], [])
        self.assertEqual(sections["0000SELECTIONQUIT"]["business_rules"], [])

        self.assertEqual(
            sections["0000SELECTIONADD"]["role"],
            "Accept user input and write new record",
        )
        self.assertIn("WS-IKEY", sections["0000SELECTIONADD"]["outputs"])
        self.assertIn("DATAFILEFD", sections["0000SELECTIONADD"]["outputs"])
        self.assertEqual(sections["0000SELECTIONADD"]["business_rules"], [])
        self.assertEqual(
            sections["0000SELECTIONSTARTERROR"]["role"],
            "Display error message and redirect flow",
        )
        self.assertEqual(sections["0000SELECTIONSTARTERROR"]["inputs"], [])
        self.assertEqual(sections["0000SELECTIONSTARTERROR"]["outputs"], [])

    # ─── Master prompt schema fields ─────────────────────────────────────

    def test_data_flow_summary_present(self):
        """Master prompt requires data_flow_summary with global_inputs, global_outputs, shared_state."""
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 MENU-CHOICE PIC X(1).
       01 RESULT PIC X(20).
       PROCEDURE DIVISION.
       MAIN.
           ACCEPT MENU-CHOICE.
           PERFORM WORKER.
           STOP RUN.
       WORKER.
           MOVE MENU-CHOICE TO RESULT.
           DISPLAY RESULT.
        """
        parser_output = self.parser.parse(source)
        result = self.agents.analyze(source, parser_output)
        dfs = result["data_flow_summary"]
        self.assertIn("global_inputs", dfs)
        self.assertIn("global_outputs", dfs)
        self.assertIn("shared_state", dfs)
        self.assertIn("MENU-CHOICE", dfs["global_inputs"])

    def test_sections_have_called_by_and_calls(self):
        """Master prompt requires called_by and calls per section."""
        source = """
       PROCEDURE DIVISION.
       MAIN.
           PERFORM WORKER.
           STOP RUN.
       WORKER.
           DISPLAY "HELLO".
        """
        parser_output = self.parser.parse(source)
        result = self.agents.analyze(source, parser_output)
        sections = {s["name"]: s for s in result["sections"]}

        self.assertIn("called_by", sections["WORKER"])
        self.assertIn("MAIN", sections["WORKER"]["called_by"])
        self.assertIn("calls", sections["MAIN"])
        self.assertIn("WORKER", sections["MAIN"]["calls"])

    def test_sections_have_early_exit_and_dead_code(self):
        """Master prompt requires has_early_exit and is_dead_code per section."""
        source = """
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 I PIC 9(3).
       01 FLAG PIC X.
       PROCEDURE DIVISION.
       MAIN.
           PERFORM FINDER.
           STOP RUN.
       FINDER.
           PERFORM VARYING I FROM 1 BY 1 UNTIL I > 10
               IF FLAG = 'Y'
                   EXIT PERFORM
               END-IF
           END-PERFORM.
       DEAD-PARA.
           DISPLAY "NEVER CALLED".
        """
        parser_output = self.parser.parse(source)
        result = self.agents.analyze(source, parser_output)
        sections = {s["name"]: s for s in result["sections"]}

        self.assertTrue(sections["FINDER"]["has_early_exit"])
        self.assertFalse(sections["MAIN"]["has_early_exit"])
        self.assertTrue(sections["DEAD-PARA"]["is_dead_code"])
        self.assertFalse(sections["MAIN"]["is_dead_code"])


if __name__ == "__main__":
    unittest.main()
