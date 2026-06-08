import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.conversion_agent import ConversionAgent
from app.agents.facade import ModernizationAgents
from app.parsers.cobol_parser import ParserLayer
from app.services.java_pre_write_validator import JavaPreWriteValidationError


class ConversionAgentTests(unittest.TestCase):
    def setUp(self):
        self._prev_analysis_engine = os.environ.get("ANALYSIS_ENGINE")
        os.environ["ANALYSIS_ENGINE"] = "deterministic"
        self.parser = ParserLayer()
        self.agents = ModernizationAgents()

    def tearDown(self):
        if self._prev_analysis_engine is None:
            os.environ.pop("ANALYSIS_ENGINE", None)
        else:
            os.environ["ANALYSIS_ENGINE"] = self._prev_analysis_engine

    def test_convert_with_metadata_strips_mapping_notes_from_java(self):
        agent = ConversionAgent()
        agent.provider = "openai"
        raw = (
            "public class Demo {\n"
            "  public void run() {\n"
            "    System.out.println(\"ok\");\n"
            "  }\n"
            "}\n\n"
            "## MAPPING NOTES\n"
            "- block -> main\n"
        )
        agent._convert_raw = lambda *_a, **_k: raw  # type: ignore[method-assign]
        java, notes = agent.convert_with_metadata("PROCEDURE DIVISION.", {}, "{}")
        self.assertIn("public class Demo", java)
        self.assertNotIn("MAPPING", java)
        self.assertNotIn("→", java)
        self.assertIn("MAPPING", notes.upper())

    def test_convert_returns_stub_when_llm_unavailable(self):
        original_llm = self.agents.llm
        original_conversion_llm = self.agents.conversion_agent.llm
        original_provider = self.agents.conversion_agent.provider
        self.agents.llm = None
        self.agents.conversion_agent.llm = None
        self.agents.conversion_agent.provider = "stub"
        try:
            with self.assertRaises(JavaPreWriteValidationError) as ctx:
                self.agents.convert("PROCEDURE DIVISION.", {}, "{}")
            result = ctx.exception.source
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
        self.assertIn("plain_java", prompt_input["runtime_profile_section"])
        self.assertIn("Do NOT use Spring Boot", prompt_input["runtime_profile_section"])
        self.assertIn('"java_profile": "plain_java"', prompt_input["conversion_config"])
        self.assertIn("explicit_symbol_table_markdown", prompt_input)
        self.assertIn("symbol_table_llm_context", prompt_input)
        self.assertIn("java_symbol_table_json", prompt_input)
        self.assertIn("java_paragraph_table_json", prompt_input)
        self.assertIn("=== AVAILABLE SYMBOLS", prompt_input["symbol_table_llm_context"])
        rendered = self.agents.conversion_agent._render_prompt_for_openrouter(
            prompt, prompt_input
        )
        self.assertIn("Available Symbols", rendered)
        self.assertIn("=== FIELDS YOU MAY READ/WRITE ===", rendered)
        self.assertIn("| COBOL Name | Java Name | Java Type | Source |", rendered)

    def test_build_conversion_prompt_spring_boot_profile_section(self):
        source = "       PROCEDURE DIVISION.\n           STOP RUN.\n"
        parser_output = self.parser.parse(source)
        analysis_output = self.agents.analyze(source, parser_output)
        _prompt, prompt_input = self.agents.build_conversion_prompt_input(
            source,
            parser_output,
            analysis_output,
            java_profile="spring_boot",
        )
        self.assertIn("spring_boot", prompt_input["runtime_profile_section"])
        self.assertIn("Spring Boot", prompt_input["runtime_profile_section"])
        self.assertIn('"framework": "spring-boot"', prompt_input["conversion_config"])

    def test_default_conversion_config_uses_dependency_aware_io_defaults(self):
        parser_output = {
            "program_name": "TXNPROC",
            "dependencies": {"copybooks": [], "files": ["INPUT-FILE"], "external_calls": []},
        }
        analysis_output = {"complexity": "medium"}

        config = self.agents._default_conversion_config(
            parser_output,
            analysis_output,
            java_profile="plain_java",
        )

        self.assertEqual(config["target_language"], "java")
        self.assertEqual(config["java_version"], "17")
        self.assertEqual(config["java_profile"], "plain_java")
        self.assertEqual(config["framework"], "none")
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
        self.assertIn("analysis_model_name", status)

    def test_select_model_uses_fast_for_standard_openai(self):
        agent = ConversionAgent()
        agent.provider = "openai"
        agent.model_name = "gpt-4o"
        selected = agent.select_model("CALCFEE", "Standard", base_model="gpt-4o")
        self.assertEqual(selected, "gpt-4o-mini")

    def test_select_model_uses_full_for_complex(self):
        agent = ConversionAgent()
        agent.provider = "openai"
        agent.model_name = "gpt-4o"
        selected = agent.select_model("LOANEVAL", "Complex", base_model="gpt-4o")
        self.assertEqual(selected, "gpt-4o")

    def test_conversion_file_cache_roundtrip(self):
        from app.services import conversion_cache as cache_mod

        cache_mod.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        key = cache_mod.get_cache_key("CACHE_TEST_PROG", "IDENTIFICATION DIVISION CACHE TEST.")
        payload = {"java_code": "public class CalcFee { }", "mapping_notes": "cached"}
        cache_mod.save_to_cache(key, payload)
        loaded = cache_mod.load_from_cache(key)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["java_code"], payload["java_code"])
        path = cache_mod._cache_path(key)
        if path.is_file():
            path.unlink()


if __name__ == "__main__":
    unittest.main()
