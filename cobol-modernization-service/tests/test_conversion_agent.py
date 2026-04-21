import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.facade import ModernizationAgents
from app.parsers.cobol_parser import ParserLayer


class ConversionAgentTests(unittest.TestCase):
    def setUp(self):
        self.parser = ParserLayer()
        self.agents = ModernizationAgents()

    def test_convert_returns_stub_when_llm_unavailable(self):
        original_llm = self.agents.llm
        original_conversion_llm = self.agents.conversion_agent.llm
        original_provider = self.agents.conversion_agent.provider
        self.agents.llm = None
        self.agents.conversion_agent.llm = None
        self.agents.conversion_agent.provider = "stub"
        try:
            result = self.agents.convert("PROCEDURE DIVISION.", {}, "{}")
        finally:
            self.agents.llm = original_llm
            self.agents.conversion_agent.llm = original_conversion_llm
            self.agents.conversion_agent.provider = original_provider

        self.assertIn("Conversion agent is not configured", result)

    def test_build_conversion_prompt_input_contains_required_contract(self):
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
        analysis_output = self.agents.analyze(source, parser_output)
        prompt, prompt_input = self.agents.build_conversion_prompt_input(
            source,
            parser_output,
            analysis_output,
        )

        self.assertIsNotNone(prompt)
        self.assertIn("BigDecimal", prompt_input["conversion_config"])
        self.assertIn('"target_language": "java"', prompt_input["conversion_config"])
        self.assertIn('"decimal_strategy": "bigdecimal"', prompt_input["conversion_config"])
        self.assertIn('"complexity_hint": "low"', prompt_input["conversion_config"])
        self.assertIn(
            '"global_purpose": "validate a transaction based on available balance and update the result status"',
            prompt_input["analysis_json"],
        )
        self.assertIn('"type": "SUBTRACT"', prompt_input["parser_json"])
        self.assertIn("IF BALANCE < AMOUNT", prompt_input["source"])

    def test_default_conversion_config_uses_dependency_aware_io_defaults(self):
        parser_output = {
            "program_name": "TXNPROC",
            "dependencies": {"copybooks": [], "files": ["INPUT-FILE"], "external_calls": []},
        }
        analysis_output = {"complexity": "medium"}

        config = self.agents._default_conversion_config(parser_output, analysis_output)

        self.assertEqual(config["target_language"], "java")
        self.assertEqual(config["java_version"], "17")
        self.assertEqual(config["framework"], "spring-boot")
        self.assertEqual(config["package_name"], "com.modernized.txnproc")
        self.assertEqual(config["decimal_strategy"], "bigdecimal")
        self.assertEqual(config["io_strategy"], "buffered")
        self.assertEqual(config["complexity_hint"], "medium")

    def test_normalize_analysis_output_accepts_json_string(self):
        normalized = self.agents._normalize_analysis_output('{"program_name": "TXNPROC", "complexity": "simple"}')
        self.assertEqual(normalized["program_name"], "TXNPROC")
        self.assertEqual(normalized["complexity"], "simple")

    def test_runtime_status_reports_provider(self):
        status = self.agents.get_runtime_status()
        self.assertIn("provider", status)
        self.assertIn("model_name", status)


if __name__ == "__main__":
    unittest.main()
