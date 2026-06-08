"""GMP runtime probe for GnuCOBOL COMP-3 behavioral compiles."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.gnucobol_gmp_runtime import gnucobol_root, gmp_runtime_ready


class TestGnucobolGmpRuntime:
    def test_gmp_runtime_ready_when_headers_installed(self):
        root = gnucobol_root()
        if root is None:
            pytest.skip("GnuCOBOL not installed on this host")
        ok, msg = gmp_runtime_ready(root)
        if not ok and "gmp.h missing" in msg:
            pytest.skip("gmp.h not installed; run scripts/ensure-gnucobol-gmp.ps1")
        assert ok, msg
