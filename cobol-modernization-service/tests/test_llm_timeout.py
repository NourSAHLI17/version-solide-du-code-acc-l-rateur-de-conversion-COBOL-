"""F46 — Adaptive LLM read timeouts."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.llm_timeout import (
    compute_method_body_timeout,
    compute_timeout,
)


class LlmTimeoutTests(unittest.TestCase):
    def test_small_program_hits_floor(self):
        src = "\n".join(["       DISPLAY X."] * 50)
        t = compute_timeout(src, "gpt-4o")
        self.assertGreaterEqual(t, 300)

    def test_loaneval_sized_program(self):
        lines = 1125
        src = "\n" * lines
        t = compute_timeout(src, "gpt-4o")
        self.assertGreaterEqual(t, 300)
        self.assertLessEqual(t, 900)
        # base 60 + 112.5 lines/10 = 172.5 * 1.5 = 258 -> floored to 300
        self.assertEqual(t, 300)

    def test_large_program_scales_toward_ceiling(self):
        lines = 7000
        src = "\n" * lines
        t = compute_timeout(src, "gpt-4o")
        self.assertEqual(t, 900)

    def test_method_body_timeout_bounded(self):
        t = compute_method_body_timeout("gpt-4o")
        self.assertGreaterEqual(t, 60)
        self.assertLessEqual(t, 120)


if __name__ == "__main__":
    unittest.main()
