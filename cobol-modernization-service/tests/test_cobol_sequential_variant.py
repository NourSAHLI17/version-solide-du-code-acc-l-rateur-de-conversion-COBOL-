"""Tests for SEQUENTIAL baseline COBOL variant generation."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.cobol_sequential_variant import create_sequential_variant
from app.services.behavioral_baseline import (
    acme_bank_v3_root,
    resolve_cobol_for_baseline,
    sequential_variant_path,
)

_INDEXED_SNIPPET = """\
       SELECT LOAN-FILE
           ASSIGN TO "LOANFILE.dat"
           ORGANIZATION IS INDEXED
           ACCESS MODE IS RANDOM
           RECORD KEY IS LOAN-ID
           FILE STATUS IS WS-LOAN-FS.

           SELECT COLLATERAL-FILE
               ASSIGN TO "COLFILE.dat"
               ORGANIZATION IS INDEXED
               ACCESS MODE IS DYNAMIC
               RECORD KEY IS COL-ID
               ALTERNATE RECORD KEY IS COL-LOAN-ID
                   WITH DUPLICATES
               FILE STATUS IS WS-COL-FS.
"""

_PROC_SNIPPET = """
           START COLLATERAL-FILE KEY = COL-LOAN-ID
               INVALID KEY CONTINUE
               NOT INVALID KEY
                   READ COLLATERAL-FILE NEXT RECORD
"""


class CobolSequentialVariantTests(unittest.TestCase):
    def test_replaces_organization_and_access(self):
        text = _INDEXED_SNIPPET
        out = create_sequential_variant(text)
        self.assertNotIn("ORGANIZATION IS INDEXED", out.upper())
        self.assertIn("ORGANIZATION IS SEQUENTIAL", out.upper())
        self.assertNotIn("ACCESS MODE IS RANDOM", out.upper())
        self.assertNotIn("ACCESS MODE IS DYNAMIC", out.upper())

    def test_removes_record_keys(self):
        out = create_sequential_variant(_INDEXED_SNIPPET)
        self.assertNotIn("RECORD KEY IS", out.upper())
        self.assertNotIn("ALTERNATE RECORD KEY", out.upper())

    def test_invalid_key_and_start(self):
        out = create_sequential_variant(_PROC_SNIPPET)
        self.assertNotIn("INVALID KEY", out.upper())
        # START block is commented out, not removed
        for line in out.splitlines():
            stripped = line.lstrip()
            if "START COLLATERAL" in stripped.upper():
                self.assertTrue(
                    stripped.startswith("*"),
                    f"START line should be a comment: {line!r}",
                )
        self.assertIn("BASELINE:", out)

    def test_occurs_indexed_by_unchanged(self):
        text = "05 WS-ENTRY OCCURS 10 TIMES INDEXED BY WS-IDX.\n"
        out = create_sequential_variant(text)
        self.assertIn("INDEXED BY WS-IDX", out)

    def test_patches_flat_loan_fd_to_239_bytes(self):
        text = (
            "       FD LOAN-FILE\n"
            "           RECORD CONTAINS 238 CHARACTERS.\n"
            "       COPY LOANCOPY.\n"
        )
        out = create_sequential_variant(text)
        self.assertIn("RECORD CONTAINS 239 CHARACTERS", out.upper())
        self.assertIn("COPY LOANCOPY REPLACING", out.upper())
        self.assertIn("PIC X(9)", out.upper())

    def test_acme_sequential_files_exist_after_generator(self):
        root = acme_bank_v3_root()
        if root is None:
            self.skipTest("acme-bank-v3 not in workspace")
        seq = root / "src" / "sequential" / "LOANEVAL.cbl"
        if not seq.is_file():
            self.skipTest("run scripts/create_sequential_variants.py first")
        text = seq.read_text(encoding="utf-8")
        self.assertIn("ORGANIZATION IS SEQUENTIAL", text.upper())
        self.assertNotIn("ORGANIZATION IS INDEXED", text.upper())

    def test_resolve_uses_sequential_file_when_present(self):
        root = acme_bank_v3_root()
        if root is None:
            self.skipTest("acme-bank-v3 not in workspace")
        indexed = (root / "src" / "LOANEVAL.cbl").read_text(encoding="utf-8")
        resolved, tag = resolve_cobol_for_baseline(
            indexed,
            "LOANEVAL",
            baseline_mode=False,
        )
        self.assertEqual(tag, "sequential_file")
        self.assertNotIn("ORGANIZATION IS INDEXED", resolved.upper())

    def test_resolve_unchanged_when_no_sequential_file_and_baseline_off(self):
        text = _INDEXED_SNIPPET
        with patch(
            "app.services.behavioral_baseline.sequential_variant_path",
            return_value=None,
        ):
            resolved, tag = resolve_cobol_for_baseline(text, "LOANEVAL", baseline_mode=False)
        self.assertEqual(tag, "indexed")
        self.assertIn("ORGANIZATION IS INDEXED", resolved.upper())


if __name__ == "__main__":
    unittest.main()
