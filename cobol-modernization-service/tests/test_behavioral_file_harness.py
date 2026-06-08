"""Behavioral disk file staging for TXNPOST-style batch programs."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.behavioral_diff_runner import _compile_and_run_cobol, _prepare_behavioral_sources
from app.services.behavioral_file_harness import (
    needs_txnpost_file_harness,
    stage_txnpost_behavioral_files,
    txnpost_behavioral_data_dir,
)

FIXTURE_COB = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "usecase3" / "TXNPOST.cbl"
).read_text(encoding="utf-8")


class TestBehavioralFileHarness:
    def test_detects_txnpost_assignments(self):
        assert needs_txnpost_file_harness(FIXTURE_COB, "TXNPOST") is True
        assert needs_txnpost_file_harness("IDENTIFICATION DIVISION.", "HELLO") is False

    def test_fixture_data_dir_has_required_files(self):
        directory = txnpost_behavioral_data_dir()
        assert directory is not None
        for name in ("ACME.CUSTOMER.MASTER", "ACME.TRANSACTIONS"):
            assert (directory / name).is_file(), name

    def test_stage_copies_files_into_tmp(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            ok, msg = stage_txnpost_behavioral_files(
                td,
                program_name="TXNPOST",
                cobol_source=FIXTURE_COB,
            )
            assert ok, msg
            assert (td / "ACME.CUSTOMER.MASTER").is_file()
            assert (td / "ACME.TRANSACTIONS").is_file()

    @pytest.mark.skipif(not shutil.which("cobc"), reason="GnuCOBOL not installed")
    def test_txnpost_compile_and_run_completes_without_timeout(self):
        cobol, _, _, _ = _prepare_behavioral_sources(
            FIXTURE_COB,
            "",
            "TXNPOST",
            parser_output={
                "dependencies": {
                    "copybooks": ["CUSTCOPY", "TXNCOPY", "RPTCOPY", "ERRORCOPY"],
                },
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            cap = _compile_and_run_cobol(
                cobol,
                stdin_text="",
                tmp=td,
                timeout_seconds=30,
                program_name="TXNPOST",
            )
            assert cap.execution_status != "timeout", cap.error or cap.stderr
            assert cap.execution_status != "compile_failure", cap.compile_stderr
            assert (td / "ACME.POST.REPORT").is_file()
