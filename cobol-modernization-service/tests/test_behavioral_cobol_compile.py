"""Tests for GnuCOBOL compile helpers used in behavioral testing."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.services.behavioral_baseline import acme_bank_v3_root
from app.services.behavioral_cobol_compile import (
    SUB_PROGRAMS,
    build_cobc_argv,
    compile_cobol_for_testing,
    find_acme_cobol_source,
    resolve_copybook_dirs,
)


class TestBuildCobcArgv:
    def test_main_program_includes_std_and_copybook_path(self, tmp_path: Path):
        cob = tmp_path / "RISKSCOR.cbl"
        cob.write_text("       IDENTIFICATION DIVISION.\n       PROGRAM-ID. RISKSCOR.\n", encoding="utf-8")
        cpy = tmp_path / "copybooks"
        cpy.mkdir()
        argv = build_cobc_argv(
            cob,
            tmp_path,
            "RISKSCOR",
            copybook_dirs=[cpy],
            is_sub_program=False,
        )
        assert argv[1:4] == ["-x", "-std=ibm-strict", "-o"]
        assert "-I" in argv
        assert str(cpy) in argv
        assert str(cob) in argv[-1]

    def test_sub_program_uses_module_flag(self, tmp_path: Path):
        cob = tmp_path / "CALCFEE.cbl"
        cob.write_text("       IDENTIFICATION DIVISION.\n       PROGRAM-ID. CALCFEE.\n", encoding="utf-8")
        argv = build_cobc_argv(
            cob,
            tmp_path,
            "CALCFEE",
            copybook_dirs=[],
            is_sub_program=True,
        )
        assert "-m" in argv
        assert "-std=ibm-strict" in argv
        assert "CALCFEE" in argv[argv.index("-o") + 1]

    def test_sub_program_set(self):
        assert "CALCFEE" in SUB_PROGRAMS
        assert "CHKAML" in SUB_PROGRAMS


class TestAcmeIntegration:
    def test_acme_copybooks_on_include_path(self):
        root = acme_bank_v3_root()
        if root is None:
            pytest.skip("acme-bank-v3 not present")
        dirs = resolve_copybook_dirs(root)
        assert any(d.name == "copybooks" for d in dirs)

    def test_find_sequential_riskscor(self):
        root = acme_bank_v3_root()
        if root is None:
            pytest.skip("acme-bank-v3 not present")
        src = find_acme_cobol_source("RISKSCOR", project_dir=root)
        assert src is not None
        assert "sequential" in str(src).replace("\\", "/")

    @pytest.mark.skipif(not shutil.which("cobc"), reason="GnuCOBOL not installed")
    def test_compile_riskscor_sequential(self, tmp_path: Path):
        root = acme_bank_v3_root()
        if root is None:
            pytest.skip("acme-bank-v3 not present")
        src = find_acme_cobol_source("RISKSCOR", project_dir=root)
        assert src is not None
        staged = tmp_path / "RISKSCOR.cbl"
        staged.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        result = compile_cobol_for_testing(
            str(staged),
            str(tmp_path),
            str(root),
            program_name="RISKSCOR",
            timeout_seconds=120.0,
        )
        assert result.ok, result.stderr
        assert result.binary_path is not None
