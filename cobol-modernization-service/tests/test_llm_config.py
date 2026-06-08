import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.llm_config import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_AZURE_OPENAI_FALLBACK_MODEL,
    DEFAULT_AZURE_OPENAI_MODEL,
    resolve_llm_runtime,
    resolve_openai_fallback_model,
    resolve_openai_model,
)


class LlmConfigTests(unittest.TestCase):
    def _clear_llm_env(self) -> None:
        for key in (
            "LLM_PROVIDER",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
            "GOOGLE_API_KEY",
            "ANTHROPIC_MODEL",
            "ANTHROPIC_MODEL_ANALYSIS",
            "ANTHROPIC_MODEL_CONVERSION",
            "OPENAI_MODEL",
            "OPENAI_ENDPOINT",
            "OPENAI_API_VERSION",
        ):
            os.environ.pop(key, None)

    def test_anthropic_explicit_provider_uses_per_agent_models(self):
        self._clear_llm_env()
        os.environ["LLM_PROVIDER"] = "anthropic"
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        os.environ["ANTHROPIC_MODEL_ANALYSIS"] = "claude-opus-analysis"
        os.environ["ANTHROPIC_MODEL_CONVERSION"] = "claude-opus-conversion"
        try:
            runtime = resolve_llm_runtime()
        finally:
            self._clear_llm_env()

        self.assertEqual(runtime.provider, "anthropic")
        self.assertEqual(runtime.model_analysis, "claude-opus-analysis")
        self.assertEqual(runtime.model_conversion, "claude-opus-conversion")

    def test_anthropic_conversion_falls_back_to_analysis_model(self):
        self._clear_llm_env()
        os.environ["LLM_PROVIDER"] = "anthropic"
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        os.environ["ANTHROPIC_MODEL_ANALYSIS"] = "claude-opus-only"
        try:
            runtime = resolve_llm_runtime()
        finally:
            self._clear_llm_env()

        self.assertEqual(runtime.model_analysis, "claude-opus-only")
        self.assertEqual(runtime.model_conversion, "claude-opus-only")

    def test_anthropic_default_models_are_sonnet_when_unset(self):
        self._clear_llm_env()
        os.environ["LLM_PROVIDER"] = "anthropic"
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        try:
            runtime = resolve_llm_runtime()
        finally:
            self._clear_llm_env()

        self.assertEqual(runtime.model_analysis, DEFAULT_ANTHROPIC_MODEL)
        self.assertEqual(runtime.model_conversion, DEFAULT_ANTHROPIC_MODEL)

    def test_anthropic_model_env_overrides_both_roles(self):
        self._clear_llm_env()
        os.environ["LLM_PROVIDER"] = "anthropic"
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        os.environ["ANTHROPIC_MODEL"] = "claude-custom-project"
        try:
            runtime = resolve_llm_runtime()
        finally:
            self._clear_llm_env()

        self.assertEqual(runtime.model_analysis, "claude-custom-project")
        self.assertEqual(runtime.model_conversion, "claude-custom-project")

    @patch.dict(os.environ, {}, clear=True)
    def test_auto_prefers_anthropic_when_key_present(self):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        os.environ["OPENAI_API_KEY"] = "openai-key"
        runtime = resolve_llm_runtime()
        self.assertEqual(runtime.provider, "anthropic")

    def test_azure_endpoint_defaults_to_gpt_4o_with_gpt_4_1_mini_fallback(self):
        self._clear_llm_env()
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["OPENAI_ENDPOINT"] = "https://example.fabric/api"
        os.environ["OPENAI_API_VERSION"] = "2024-02-15-preview"
        try:
            self.assertEqual(resolve_openai_model(), DEFAULT_AZURE_OPENAI_MODEL)
            self.assertEqual(DEFAULT_AZURE_OPENAI_MODEL, "gpt-4o")
            self.assertEqual(resolve_openai_fallback_model(), DEFAULT_AZURE_OPENAI_FALLBACK_MODEL)
            self.assertEqual(DEFAULT_AZURE_OPENAI_FALLBACK_MODEL, "gpt-4.1-mini")
        finally:
            self._clear_llm_env()

    @patch.dict(os.environ, {}, clear=True)
    def test_openai_explicit_overrides_anthropic_key(self):
        os.environ["LLM_PROVIDER"] = "openai"
        os.environ["OPENAI_API_KEY"] = "openai-key"
        os.environ["ANTHROPIC_API_KEY"] = "anthropic-key"
        os.environ["OPENAI_MODEL"] = "gpt-4o"
        os.environ["OPENAI_MODEL_FALLBACK"] = "gpt-4.1-mini"
        runtime = resolve_llm_runtime()
        self.assertEqual(runtime.provider, "openai")
        self.assertEqual(runtime.model_conversion, "gpt-4o")
        self.assertEqual(runtime.model_analysis, "gpt-4o")


if __name__ == "__main__":
    unittest.main()
