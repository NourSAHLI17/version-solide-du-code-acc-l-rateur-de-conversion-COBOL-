"""F47 — Streaming LLM transport."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.llm_streaming import LLMStallError, call_llm_with_retry
from app.services.llm_transport import _check_stream_limits, _should_use_streaming


class LlmStreamingTests(unittest.TestCase):
    def test_should_use_streaming_for_conversion(self):
        self.assertTrue(_should_use_streaming("conversion"))
        self.assertTrue(_should_use_streaming("method_body"))
        self.assertFalse(_should_use_streaming("analysis_chunk"))

    def test_stall_on_total_timeout(self):
        with self.assertRaises(LLMStallError):
            _check_stream_limits(
                start=time.time() - 400,
                last_chunk_time=time.time(),
                chunk_count=1,
                timeout_seconds=300,
                stall_gap_seconds=60,
            )

    def test_retry_succeeds_on_second_attempt(self):
        calls = {"n": 0}

        def flaky() -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                raise LLMStallError("stall")
            return "ok"

        with patch("app.services.llm_streaming.time.sleep"):
            result = call_llm_with_retry(flaky, program_name="TST", max_retries=3)
        self.assertEqual(result, "ok")
        self.assertEqual(calls["n"], 2)


if __name__ == "__main__":
    unittest.main()
