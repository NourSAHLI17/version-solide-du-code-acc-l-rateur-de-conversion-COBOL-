"""F31: runtime profile section in conversion prompt and pipeline threading."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from app.agents.conversion_agent import ConversionAgent
from app.services.java_project_profile import (
    JAVA_PROFILE_JAVA_EE,
    JAVA_PROFILE_PLAIN,
    JAVA_PROFILE_QUARKUS,
    JAVA_PROFILE_SPRING_BOOT,
    build_java_runtime_profile_prompt,
    framework_hint_for_profile,
    resolve_java_profile,
)

_SOURCE = "       PROCEDURE DIVISION.\n           STOP RUN.\n"
_PARSER = {"program_name": "F31", "dependencies": {"files": [], "external_calls": []}}
_ANALYSIS = "{}"


class F31RuntimeProfilePromptTests(unittest.TestCase):
    def setUp(self):
        self.agent = ConversionAgent()

    def _prompt_input(self, **kwargs):
        _prompt, prompt_input = self.agent.build_conversion_prompt_input(
            _SOURCE,
            _PARSER,
            _ANALYSIS,
            **kwargs,
        )
        return prompt_input

    def test_all_profiles_have_distinct_prompt_sections(self):
        plain = build_java_runtime_profile_prompt(JAVA_PROFILE_PLAIN)
        spring = build_java_runtime_profile_prompt(JAVA_PROFILE_SPRING_BOOT)
        self.assertIn("plain_java", plain)
        self.assertIn("spring_boot", spring)
        self.assertNotEqual(plain, spring)

    def test_rendered_prompt_leads_with_runtime_section(self):
        prompt, prompt_input = self.agent.build_conversion_prompt_input(
            _SOURCE,
            _PARSER,
            _ANALYSIS,
            java_profile=JAVA_PROFILE_PLAIN,
        )
        rendered = self.agent._render_prompt_for_openrouter(prompt, prompt_input)
        first_line = prompt_input["runtime_profile_section"].splitlines()[0]
        self.assertTrue(rendered.startswith(first_line))

    def test_conversion_config_matches_profile(self):
        for profile, framework in (
            (JAVA_PROFILE_PLAIN, "none"),
            (JAVA_PROFILE_SPRING_BOOT, "spring-boot"),
            (JAVA_PROFILE_JAVA_EE, "jakarta-ee"),
            (JAVA_PROFILE_QUARKUS, "quarkus"),
        ):
            inp = self._prompt_input(java_profile=profile)
            config = json.loads(inp["conversion_config"])
            self.assertEqual(config["java_profile"], profile)
            self.assertEqual(config["framework"], framework)
            self.assertEqual(framework_hint_for_profile(profile), framework)

    def test_resolve_order_explicit_parser_env_default(self):
        parser_po = {**_PARSER, "java_profile": "java_ee"}
        self.assertEqual(
            resolve_java_profile(explicit="quarkus", parser_output=parser_po),
            JAVA_PROFILE_QUARKUS,
        )
        inp = self._prompt_input(java_profile="quarkus")
        self.assertEqual(json.loads(inp["conversion_config"])["java_profile"], JAVA_PROFILE_QUARKUS)

        inp = self.agent.build_conversion_prompt_input(_SOURCE, parser_po, _ANALYSIS)[1]
        self.assertEqual(json.loads(inp["conversion_config"])["java_profile"], JAVA_PROFILE_JAVA_EE)

        prev = os.environ.get("JAVA_PROJECT_PROFILE")
        try:
            os.environ["JAVA_PROJECT_PROFILE"] = "spring_boot"
            inp = self._prompt_input()
            self.assertEqual(
                json.loads(inp["conversion_config"])["java_profile"],
                JAVA_PROFILE_SPRING_BOOT,
            )
        finally:
            if prev is None:
                os.environ.pop("JAVA_PROJECT_PROFILE", None)
            else:
                os.environ["JAVA_PROJECT_PROFILE"] = prev

    def test_convert_with_metadata_threads_java_profile(self):
        captured: list[str | None] = []

        def capture(*args, **kwargs):
            captured.append(kwargs.get("java_profile"))
            return ConversionAgent.build_conversion_prompt_input(self.agent, *args, **kwargs)

        stub = "public class X {\n  public void run() { System.out.println(1); }\n}\n"
        with patch.object(self.agent, "build_conversion_prompt_input", side_effect=capture):
            with patch.object(self.agent, "_convert_with_http_llm", return_value=stub):
                self.agent.provider = "openai"
                self.agent.convert_with_metadata(
                    _SOURCE,
                    _PARSER,
                    _ANALYSIS,
                    java_profile="spring_boot",
                )
        self.assertEqual(captured, ["spring_boot"])


if __name__ == "__main__":
    unittest.main()
