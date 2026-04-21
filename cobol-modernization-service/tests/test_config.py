import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_uses_environment_values(self):
        original_host = os.environ.get("HOST")
        original_port = os.environ.get("PORT")
        original_provider = os.environ.get("LLM_PROVIDER")
        original_openai_model = os.environ.get("OPENAI_MODEL")
        original_openrouter_model = os.environ.get("OPENROUTER_MODEL")

        os.environ["HOST"] = "127.0.0.1"
        os.environ["PORT"] = "9001"
        os.environ["LLM_PROVIDER"] = "openai"
        os.environ["OPENAI_MODEL"] = "gpt-4.1-mini"
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

        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 9001)
        self.assertEqual(config.llm_provider, "openai")
        self.assertEqual(config.openai_model, "gpt-4.1-mini")


if __name__ == "__main__":
    unittest.main()
