import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.behavioral_copybook_prep import (
    _find_remaining_copy_directives,
    expand_cobol_copybooks_for_behavioral,
)


FIXTURE_COB = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "usecase3" / "TXNPOST.cbl"
).read_text(encoding="utf-8")


class TestBehavioralCopybookPrep:
    def test_expands_copybooks_from_fixture_disk(self):
        parser_output = {
            "dependencies": {
                "copybooks": ["CUSTCOPY", "TXNCOPY", "RPTCOPY"],
            }
        }
        expanded, unresolved = expand_cobol_copybooks_for_behavioral(
            FIXTURE_COB,
            parser_output=parser_output,
        )
        assert ">>>" not in expanded
        assert "BEGIN COPY" not in expanded.upper()
        assert "END COPY" not in expanded.upper()
        assert unresolved == []
        assert _find_remaining_copy_directives(expanded) == []
        assert "CUST-ID" in expanded

    def test_expands_copy_without_trailing_period(self):
        source = (
            "DATA DIVISION.\n"
            "FILE SECTION.\n"
            "01 CUSTOMER-RECORD.\n"
            "COPY CUSTCOPY\n"
            "01 TRANSACTION-RECORD.\n"
            "COPY TXNCOPY\n"
        )
        expanded, unresolved = expand_cobol_copybooks_for_behavioral(
            source,
            copybooks={
                "CUSTCOPY": "05 CUST-ID PIC X(10).\n",
                "TXNCOPY": "05 TXN-ID PIC X(10).\n",
            },
        )
        assert unresolved == []
        assert _find_remaining_copy_directives(expanded) == []
        assert "CUST-ID" in expanded
        assert "TXN-ID" in expanded

    def test_parser_dependencies_under_ast_key(self):
        source = "       01 X.\n          COPY CUSTCOPY.\n"
        expanded, unresolved = expand_cobol_copybooks_for_behavioral(
            source,
            parser_output={"ast": {"dependencies": {"copybooks": ["CUSTCOPY"]}}},
            copybooks={"CUSTCOPY": "05 CUST-ID PIC X(5).\n"},
        )
        assert unresolved == []
        assert "CUST-ID" in expanded

    def test_discovers_copybooks_from_source_without_parser(self):
        source = "       DATA DIVISION.\n       WORKING-STORAGE.\n          COPY CUSTCOPY.\n"
        expanded, unresolved = expand_cobol_copybooks_for_behavioral(
            source,
            copybooks={"CUSTCOPY": "       05 CUST-ID PIC X(5).\n"},
        )
        assert "CUST-ID" in expanded
        assert unresolved == []

    def test_resolves_errorcopy_and_rpthdcpy_from_fixture_disk(self):
        source = (
            "       DATA DIVISION.\n"
            "       WORKING-STORAGE SECTION.\n"
            "       01 WS-ERROR-AREA.\n"
            "          COPY ERRORCOPY.\n"
            "       01 REPORT-LINE.\n"
            "          COPY RPTHDCPY.\n"
        )
        expanded, unresolved = expand_cobol_copybooks_for_behavioral(
            source,
            parser_output={
                "dependencies": {"copybooks": ["ERRORCOPY", "RPTHDCPY", "CUSTCOPY"]},
            },
        )
        assert unresolved == []
        assert _find_remaining_copy_directives(expanded) == []
        assert ">>>" not in expanded
        assert "ERR-CODE" in expanded
        assert "RPT-LINE-TEXT" in expanded

    def test_honors_inline_copybook_library(self):
        source = "       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n       01 X.\n          COPY MYBOOK.\n"
        expanded, unresolved = expand_cobol_copybooks_for_behavioral(
            source,
            copybooks={"MYBOOK": "       01 MYBOOK-REC PIC X(5) VALUE 'HELLO'.\n"},
        )
        assert "MYBOOK-REC" in expanded
        assert unresolved == []

    @pytest.mark.skipif(not shutil.which("cobc"), reason="GnuCOBOL not installed")
    def test_copy_under_fd_emits_01_record_wrapper(self):
        source = (
            "       DATA DIVISION.\n"
            "       FILE SECTION.\n"
            "       FD CUSTOMER-FILE.\n"
            "          COPY CUSTCOPY.\n"
        )
        expanded, unresolved = expand_cobol_copybooks_for_behavioral(source)
        assert unresolved == []
        assert "01 CUSTOMER-RECORD-FIELDS" in expanded
        assert _find_remaining_copy_directives(expanded) == []
        lines = expanded.splitlines()
        fd_idx = next(i for i, ln in enumerate(lines) if "FD CUSTOMER-FILE" in ln)
        after_fd = [ln for ln in lines[fd_idx + 1 :] if ln.strip()][:2]
        assert after_fd[0].lstrip().startswith("01 ")
        assert after_fd[1].lstrip().startswith("05 ")

    @pytest.mark.skipif(not shutil.which("cobc"), reason="GnuCOBOL not installed")
    def test_copy_under_fd_passes_cobc_syntax_check(self):
        source = (
            "       IDENTIFICATION DIVISION.\n"
            "       PROGRAM-ID. TXFD.\n"
            "       ENVIRONMENT DIVISION.\n"
            "       INPUT-OUTPUT SECTION.\n"
            "       FILE-CONTROL.\n"
            "           SELECT CUSTOMER-FILE ASSIGN TO 'CUST.DAT'.\n"
            "       DATA DIVISION.\n"
            "       FILE SECTION.\n"
            "       FD CUSTOMER-FILE.\n"
            "          COPY CUSTCOPY.\n"
            "       PROCEDURE DIVISION.\n"
            "       STOP RUN.\n"
        )
        expanded, unresolved = expand_cobol_copybooks_for_behavioral(source)
        assert unresolved == []
        assert expanded.endswith("\n")
        with tempfile.TemporaryDirectory() as tmp:
            cob_path = Path(tmp) / "fd_copy.cob"
            cob_path.write_text(expanded, encoding="utf-8")
            proc = subprocess.run(
                ["cobc", "-fsyntax-only", "-x", str(cob_path)],
                capture_output=True,
                text=True,
            )
        assert proc.returncode == 0, (proc.stderr or "")[:2000]

    @pytest.mark.skipif(not shutil.which("cobc"), reason="GnuCOBOL not installed")
    def test_txnpost_expanded_source_passes_cobc_syntax_check(self):
        expanded, unresolved = expand_cobol_copybooks_for_behavioral(
            FIXTURE_COB,
            parser_output={
                "dependencies": {"copybooks": ["CUSTCOPY", "TXNCOPY", "RPTCOPY"]},
            },
        )
        assert unresolved == []
        assert ">>>" not in expanded
        with tempfile.TemporaryDirectory() as tmp:
            cob_path = Path(tmp) / "TXNPOST.cob"
            cob_path.write_text(expanded, encoding="utf-8")
            proc = subprocess.run(
                ["cobc", "-fsyntax-only", "-x", str(cob_path)],
                capture_output=True,
                text=True,
            )
        combined = (proc.stderr or "") + (proc.stdout or "")
        assert proc.returncode == 0, combined[:2000]
        assert ">>>BEGIN COPY" not in combined
