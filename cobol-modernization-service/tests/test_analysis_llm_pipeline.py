"""Mocked LLM-path tests for AnalysisAgent (segment manifest + chunker plumbing)."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.parsers.cobol_parser import ParserLayer


_GP_STUB = '{"global_purpose":"Test program purpose stub."}'


def _llm_invoke_with_gp_stub(chunk_json: str):
    """First prompt is standalone global_purpose; later prompts are chunk analysis."""

    def _fn(template, _prompt_input, **_kwargs):
        if "your sentence here" in template:
            return _GP_STUB
        return chunk_json

    return _fn


class AnalysisLLMPipelineTests(unittest.TestCase):
    """Requires no API keys: ConversionAgent is mocked."""

    def tearDown(self):
        import os

        os.environ.pop("ANALYSIS_ENGINE", None)
        os.environ.pop("ANALYSIS_USE_COLUMN_PARAGRAPH_SOURCES", None)

    def test_llm_engine_overlays_role_and_keeps_schema(self):
        import os

        os.environ["ANALYSIS_ENGINE"] = "llm"

        from app.agents.analysis_agent import AnalysisAgent

        source = """       PROCEDURE DIVISION.
       MAIN.
           STOP RUN.
"""
        parser_output = ParserLayer().parse(source)

        mock_conv = MagicMock()
        mock_conv.can_invoke_llm.return_value = True
        mock_conv.provider = "openai"
        chunk_json = (
            '{"paragraph_analyses":['
            '{"name":"MAIN","role":"LLM-assigned test role",'
            '"business_rules":["explicit LLM rule"],"risk_flags":[],"warnings":[]}'
            "]}"
        )
        mock_conv.invoke_prompt.side_effect = _llm_invoke_with_gp_stub(chunk_json)

        agent = AnalysisAgent(conversion_agent=mock_conv)
        result = agent.analyze(source, parser_output)

        self.assertEqual(result["analysis_engine"], "llm")
        self.assertEqual(result["analysis_revision"], 2)
        self.assertEqual(result["paragraph_source_extraction"], "column_aware")
        self.assertEqual(result["sections"][0]["name"], "MAIN")
        self.assertEqual(result["sections"][0]["role"], "LLM-assigned test role")
        self.assertIn("explicit LLM rule", result["sections"][0]["business_rules"])
        self.assertEqual(result["global_purpose"], "Test program purpose stub.")
        mock_conv.invoke_prompt.assert_called()
        tokens_used = [c.kwargs.get("max_output_tokens") for c in mock_conv.invoke_prompt.call_args_list]
        self.assertIn(512, tokens_used)
        self.assertIn(4096, tokens_used)
        chunk_calls = [
            c for c in mock_conv.invoke_prompt.call_args_list
            if c.kwargs.get("max_output_tokens") == 4096
        ]
        self.assertTrue(len(chunk_calls) >= 1)
        inner = chunk_calls[0][0][1]
        self.assertIn("cobol_source_excerpt", inner)
        self.assertIn("parser_json", inner)
        self.assertIn("MAIN", inner["paragraph_names"])
        self.assertIn("MAIN", inner["paragraph_list"])
        self.assertEqual(inner["n"], "1")

    def test_parse_llm_global_purpose_only(self):
        from app.agents.analysis_agent import AnalysisAgent

        gp = AnalysisAgent()._parse_llm_global_purpose_only('{"global_purpose":"  Banking ledger.  "}')
        self.assertEqual(gp, "Banking ledger.")

    def test_parse_llm_analysis_json_accepts_sections_key(self):
        from app.agents.analysis_agent import AnalysisAgent

        raw = (
            '{"sections":[{"name":"A","role":"r","business_rules":[],"risk_flags":[],"warnings":[]}]}'
        )
        rows = AnalysisAgent._parse_llm_analysis_json(raw)
        self.assertIsNotNone(rows)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "A")

    def test_parse_llm_analysis_chunk_response_extracts_global_purpose(self):
        from app.agents.analysis_agent import AnalysisAgent

        raw = (
            '{"global_purpose":"Payroll demo","sections":['
            '{"name":"A","role":"r","business_rules":[],"risk_flags":[],"warnings":[]}]}'
        )
        rows, gp = AnalysisAgent._parse_llm_analysis_chunk_response(raw)
        self.assertIsNotNone(rows)
        self.assertEqual(gp, "Payroll demo")
        self.assertEqual(len(rows), 1)

    def test_deterministic_engine_skips_llm(self):
        import os

        os.environ["ANALYSIS_ENGINE"] = "deterministic"

        from app.agents.analysis_agent import AnalysisAgent

        source = """       PROCEDURE DIVISION.
       MAIN.
           STOP RUN.
"""
        parser_output = ParserLayer().parse(source)
        mock_conv = MagicMock()
        mock_conv.can_invoke_llm.return_value = True

        agent = AnalysisAgent(conversion_agent=mock_conv)
        result = agent.analyze(source, parser_output)

        self.assertEqual(result["analysis_engine"], "deterministic")
        self.assertEqual(result["paragraph_source_extraction"], "heuristic_split")
        mock_conv.invoke_prompt.assert_not_called()

    def test_llm_engine_always_uses_column_aware_sources(self):
        import os

        os.environ["ANALYSIS_ENGINE"] = "llm"
        os.environ["ANALYSIS_USE_COLUMN_PARAGRAPH_SOURCES"] = "false"

        from app.agents.analysis_agent import AnalysisAgent

        fixed_source = (
            "000100 IDENTIFICATION DIVISION.\n"
            "000200 PROGRAM-ID. COL-AWARE.\n"
            "000300 DATA DIVISION.\n"
            "000400 WORKING-STORAGE SECTION.\n"
            "000500* fixed-format comment line must not leak into excerpt\n"
            "000600 01  FLAG PIC X VALUE 'N'.\n"
            "000700 PROCEDURE DIVISION.\n"
            "000800 MAIN-PARA.\n"
            "000900     DISPLAY FLAG.\n"
        )
        parser_output = ParserLayer().parse(fixed_source)
        self.assertIn("MAIN-PARA", parser_output.get("paragraphs", []))

        mock_conv = MagicMock()
        mock_conv.can_invoke_llm.return_value = True
        mock_conv.provider = "openai"
        mock_conv.invoke_prompt.side_effect = _llm_invoke_with_gp_stub(
            '{"paragraph_analyses":['
            '{"name":"MAIN-PARA","role":"show flag","business_rules":[],"risk_flags":[],"warnings":[]}'
            "]}"
        )

        agent = AnalysisAgent(conversion_agent=mock_conv)
        result = agent.analyze(fixed_source, parser_output)

        self.assertEqual(result["paragraph_source_extraction"], "column_aware")
        mock_conv.invoke_prompt.assert_called()
        chunk_calls = [
            c for c in mock_conv.invoke_prompt.call_args_list
            if c.kwargs.get("max_output_tokens") == 4096
        ]
        self.assertTrue(chunk_calls)
        excerpt = chunk_calls[0][0][1]["cobol_source_excerpt"]
        self.assertNotEqual(excerpt.strip(), "")
        self.assertIn("DISPLAY", excerpt.upper())
        for line in excerpt.splitlines():
            if not line.strip():
                continue
            if len(line) >= 7:
                self.assertNotEqual(
                    line[6],
                    "*",
                    msg=f"comment indicator line leaked into excerpt: {line!r}",
                )

    def test_deterministic_engine_respects_flag(self):
        import os

        os.environ["ANALYSIS_ENGINE"] = "deterministic"
        os.environ["ANALYSIS_USE_COLUMN_PARAGRAPH_SOURCES"] = "false"

        from app.agents.analysis_agent import AnalysisAgent

        source = """       PROCEDURE DIVISION.
       DEMO.
           STOP RUN.
"""
        parser_output = ParserLayer().parse(source)
        mock_conv = MagicMock()
        agent = AnalysisAgent(conversion_agent=mock_conv)
        result = agent.analyze(source, parser_output)
        self.assertEqual(result["paragraph_source_extraction"], "heuristic_split")

    def test_llm_payload_contains_real_cobol_lines(self):
        import os

        os.environ["ANALYSIS_ENGINE"] = "llm"

        from app.agents.analysis_agent import AnalysisAgent

        src = """       PROCEDURE DIVISION.
       ALPHA.
           DISPLAY "HI".
       BETA.
           STOP RUN.
"""
        parser_output = ParserLayer().parse(src)
        captured_payloads: list = []
        payload_json = (
            '{"paragraph_analyses":['
            '{"name":"ALPHA","role":"say hi","business_rules":[],"risk_flags":[],"warnings":[]},'
            '{"name":"BETA","role":"end","business_rules":[],"risk_flags":[],"warnings":[]}'
            "]}"
        )

        mock_conv = MagicMock()
        mock_conv.can_invoke_llm.return_value = True
        mock_conv.provider = "openrouter"

        def _capture_invoke(*args, **_kwargs):
            captured_payloads.append(args[1])
            if "your sentence here" in args[0]:
                return _GP_STUB
            return payload_json

        mock_conv.invoke_prompt.side_effect = _capture_invoke

        agent = AnalysisAgent(conversion_agent=mock_conv)
        result = agent.analyze(src, parser_output)
        self.assertEqual(result["analysis_engine"], "llm")
        self.assertGreaterEqual(len(captured_payloads), 1)
        big = "\n".join(str(p["cobol_source_excerpt"]) for p in captured_payloads)
        self.assertNotEqual(big.strip(), "")
        combined = big.upper()
        self.assertRegex(combined, r"DISPLAY")
        self.assertTrue("HI" in combined or "ALPHA" in combined or "STOP" in combined)


class ImportCycleRegressionTests(unittest.TestCase):
    """Verify the parser<->converter circular import is broken."""

    def test_parser_converter_modules_import_without_cycle(self):
        import importlib

        for mod_name in (
            "app.parsers.cobol_parser",
            "app.converters.cobol_name_converter",
            "app.converters.record_layout",
            "app.converters.rewrite_record",
        ):
            importlib.reload(importlib.import_module(mod_name))

    def test_parser_layer_instantiable_after_converter_import(self):
        from app.converters.record_layout import pic_display_byte_size
        from app.parsers.cobol_parser import ParserLayer

        self.assertIsNotNone(ParserLayer())
        self.assertGreater(pic_display_byte_size("9(5)"), 0)


if __name__ == "__main__":
    unittest.main()
