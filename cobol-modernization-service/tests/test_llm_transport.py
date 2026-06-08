import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import llm_transport


class LlmTransportTests(unittest.TestCase):
    def test_split_system_messages_merges_system_and_keeps_user(self):
        system, rest = llm_transport._split_system_messages(
            [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello"},
            ]
        )
        self.assertEqual(system, "You are helpful.")
        self.assertEqual(rest, [{"role": "user", "content": "Hello"}])

    @patch("app.services.llm_transport.httpx.Client")
    def test_complete_anthropic_posts_messages_api(self, mock_client_cls: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "public class Demo {}"}],
        }
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            text = llm_transport.complete_chat(
                provider="anthropic",
                model="claude-sonnet-4-5",
                messages=[
                    {"role": "system", "content": "Convert COBOL."},
                    {"role": "user", "content": "SOURCE"},
                ],
                max_output_tokens=1024,
            )

        self.assertEqual(text, "public class Demo {}")
        call_kwargs = mock_client.post.call_args
        self.assertEqual(call_kwargs[0][0], llm_transport._ANTHROPIC_URL)
        payload = call_kwargs[1]["json"]
        self.assertEqual(payload["model"], "claude-sonnet-4-5")
        self.assertEqual(payload["system"], "Convert COBOL.")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "SOURCE"}])
        self.assertEqual(payload["max_tokens"], 1024)

    def test_complete_chat_returns_stub_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            text = llm_transport.complete_chat(
                provider="anthropic",
                model="claude-sonnet-4-5",
                messages=[{"role": "user", "content": "x"}],
            )
        self.assertIn("Conversion agent is not configured", text)


if __name__ == "__main__":
    unittest.main()
