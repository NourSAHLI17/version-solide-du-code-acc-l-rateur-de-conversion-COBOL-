import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_anthropic_model_defaults_are_sonnet(self):
        from app.services.llm_config import DEFAULT_ANTHROPIC_MODEL

        original_analysis = os.environ.get("ANTHROPIC_MODEL_ANALYSIS")
        original_conversion = os.environ.get("ANTHROPIC_MODEL_CONVERSION")
        original_project = os.environ.get("ANTHROPIC_MODEL")
        os.environ.pop("ANTHROPIC_MODEL", None)
        os.environ.pop("ANTHROPIC_MODEL_ANALYSIS", None)
        os.environ.pop("ANTHROPIC_MODEL_CONVERSION", None)
        try:
            config = load_config()
        finally:
            if original_project is None:
                os.environ.pop("ANTHROPIC_MODEL", None)
            else:
                os.environ["ANTHROPIC_MODEL"] = original_project
            if original_analysis is None:
                os.environ.pop("ANTHROPIC_MODEL_ANALYSIS", None)
            else:
                os.environ["ANTHROPIC_MODEL_ANALYSIS"] = original_analysis
            if original_conversion is None:
                os.environ.pop("ANTHROPIC_MODEL_CONVERSION", None)
            else:
                os.environ["ANTHROPIC_MODEL_CONVERSION"] = original_conversion

        self.assertEqual(config.anthropic_model_analysis, DEFAULT_ANTHROPIC_MODEL)
        self.assertEqual(config.anthropic_model_conversion, DEFAULT_ANTHROPIC_MODEL)

    def test_load_config_uses_environment_values(self):
        original_host = os.environ.get("HOST")
        original_port = os.environ.get("PORT")
        original_provider = os.environ.get("LLM_PROVIDER")
        original_openai_model = os.environ.get("OPENAI_MODEL")
        original_openrouter_model = os.environ.get("OPENROUTER_MODEL")
        original_anthropic_analysis = os.environ.get("ANTHROPIC_MODEL_ANALYSIS")
        original_anthropic_conversion = os.environ.get("ANTHROPIC_MODEL_CONVERSION")

        os.environ["HOST"] = "127.0.0.1"
        os.environ["PORT"] = "9001"
        os.environ["LLM_PROVIDER"] = "anthropic"
        os.environ["ANTHROPIC_MODEL_ANALYSIS"] = "claude-opus-test"
        os.environ["ANTHROPIC_MODEL_CONVERSION"] = "claude-sonnet-test"
        try:
            config = load_config()
        finally:
            if original_host is None:
                os.environ.pop("HOST", None)
            else:
                os.environ["HOST"] = original_host
            if original_port is None:
                os.environ.pop("PORT", None)
            else:
                os.environ["PORT"] = original_port
            if original_provider is None:
                os.environ.pop("LLM_PROVIDER", None)
            else:
                os.environ["LLM_PROVIDER"] = original_provider
            if original_openai_model is None:
                os.environ.pop("OPENAI_MODEL", None)
            else:
                os.environ["OPENAI_MODEL"] = original_openai_model
            if original_openrouter_model is None:
                os.environ.pop("OPENROUTER_MODEL", None)
            else:
                os.environ["OPENROUTER_MODEL"] = original_openrouter_model
            if original_anthropic_analysis is None:
                os.environ.pop("ANTHROPIC_MODEL_ANALYSIS", None)
            else:
                os.environ["ANTHROPIC_MODEL_ANALYSIS"] = original_anthropic_analysis
            if original_anthropic_conversion is None:
                os.environ.pop("ANTHROPIC_MODEL_CONVERSION", None)
            else:
                os.environ["ANTHROPIC_MODEL_CONVERSION"] = original_anthropic_conversion

        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 9001)
        self.assertEqual(config.llm_provider, "anthropic")
        self.assertEqual(config.anthropic_model_analysis, "claude-opus-test")
        self.assertEqual(config.anthropic_model_conversion, "claude-sonnet-test")


if __name__ == "__main__":
    unittest.main()
