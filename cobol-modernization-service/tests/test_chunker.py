"""F49 — Program-level chunking for LLM analysis."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.chunker import chunk_program, is_chunk_usable

ACME_SRC = Path(__file__).resolve().parents[2] / "acme-bank-v3" / "src"


def load_test_program(filename: str) -> str:
    path = ACME_SRC / filename
    if not path.is_file():
        raise unittest.SkipTest(f"fixture not found: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


class ChunkerTests(unittest.TestCase):
    def test_calcfee_produces_one_chunk(self):
        src = load_test_program("CALCFEE.cbl")
        chunks = chunk_program(src)
        self.assertGreaterEqual(len(chunks), 1, "CALCFEE must produce at least one chunk")
        self.assertEqual(chunks[0].chunk_type, "whole_program")

    def test_chkaml_produces_one_chunk(self):
        src = load_test_program("CHKAML.cbl")
        chunks = chunk_program(src)
        self.assertGreaterEqual(len(chunks), 1)

    def test_riskscor_produces_one_chunk(self):
        src = load_test_program("RISKSCOR.cbl")
        chunks = chunk_program(src)
        self.assertGreaterEqual(len(chunks), 1)

    def test_loaneval_produces_multiple_chunks(self):
        src = load_test_program("LOANEVAL.cbl")
        chunks = chunk_program(src)
        self.assertGreaterEqual(len(chunks), 2)

    def test_is_chunk_usable_rejects_tiny(self):
        from app.services.chunker import SourceChunk

        tiny = SourceChunk(content="STOP RUN.", start_line=1, end_line=1, chunk_type="test")
        self.assertFalse(is_chunk_usable(tiny))

    def test_is_chunk_usable_accepts_move(self):
        from app.services.chunker import SourceChunk

        body = SourceChunk(
            content="\n".join(
                [
                    "    MOVE WS-A TO WS-B.",
                    "    PERFORM MAIN.",
                    "    IF WS-A > ZERO",
                    "        COMPUTE WS-B = WS-A + 1",
                    "    END-IF.",
                ]
            ),
            start_line=1,
            end_line=5,
            chunk_type="test",
        )
        self.assertTrue(is_chunk_usable(body))


if __name__ == "__main__":
    unittest.main()
