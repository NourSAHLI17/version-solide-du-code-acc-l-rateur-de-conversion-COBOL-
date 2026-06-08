"""COBOL symbol repair for modernized TXNPOST-style workspace sources."""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.behavioral_diff_runner import _compile_and_run_cobol, _prepare_behavioral_sources
from app.services.cobol_conversion_symbol_repair import repair_cobol_conversion_symbols

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "usecase3" / "TXNPOST.cbl"


def _broken_workspace_txnpost() -> str:
    """Source shape that fails cobc: stale RC-SUCCESS / WS-ERROR-MESSAGE without declarations."""
    lines: list[str] = []
    skip_block = False
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        if re.search(r"\b01\s+WS-ERROR-AREA\b", line, re.IGNORECASE):
            skip_block = True
            continue
        if re.search(r"\b01\s+WS-RETURN-CODE\b", line, re.IGNORECASE):
            skip_block = True
            continue
        if skip_block:
            if re.search(r"^\s*88\s+RC-SUCCESS\b", line, re.IGNORECASE):
                continue
            if re.match(r"^\s{10,}\S", line):
                continue
            skip_block = False
        if re.search(r"^\s*88\s+RC-SUCCESS\b", line, re.IGNORECASE):
            continue
        lines.append(line.replace("ERR-MESSAGE", "WS-ERROR-MESSAGE"))
    return "\n".join(lines) + "\n"


class TestCobolConversionSymbolRepair:
    def test_renames_ws_error_message_and_injects_rc_success(self):
        broken = _broken_workspace_txnpost()
        assert "WS-ERROR-MESSAGE" in broken
        assert "88 RC-SUCCESS" not in broken

        fixed, notes = repair_cobol_conversion_symbols(broken)
        assert "WS-ERROR-MESSAGE" not in fixed
        assert re.search(r"88\s+RC-SUCCESS", fixed, re.IGNORECASE)
        assert "ERR-MESSAGE" in fixed
        assert any("ERR-MESSAGE" in n or "RC-SUCCESS" in n for n in notes)

    def test_idempotent_on_canonical_fixture(self):
        canonical = FIXTURE.read_text(encoding="utf-8")
        fixed, notes = repair_cobol_conversion_symbols(canonical)
        assert fixed == canonical
        assert notes == []

    def test_upgrades_rptcopy_when_rpt_page_no_referenced(self):
        src = FIXTURE.read_text(encoding="utf-8").replace("RPTHDCPY", "RPTCOPY")
        src = src.replace("01 WS-ERROR-AREA.", "01 WS-X.")
        src = re.sub(
            r"^\s*01 WS-RETURN-CODE\..*?^\s*88 RC-SUCCESS.*$",
            "",
            src,
            flags=re.MULTILINE | re.DOTALL,
        )
        src += "\n           MOVE 1 TO RPT-PAGE-NO.\n"
        fixed, notes = repair_cobol_conversion_symbols(src)
        assert "COPY RPTHDCPY" in fixed.upper() or "RPT-PAGE-NO" in fixed
        assert any("RPTHDCPY" in n for n in notes) or "RPTCOPY" not in fixed.upper()

    @pytest.mark.skipif(not shutil.which("cobc"), reason="GnuCOBOL not installed")
    def test_repaired_source_compiles_after_prep(self):
        broken = _broken_workspace_txnpost()
        cobol, _, _, _ = _prepare_behavioral_sources(
            broken,
            "",
            "TXNPOST",
            parser_output={
                "dependencies": {
                    "copybooks": ["CUSTCOPY", "TXNCOPY", "RPTCOPY", "ERRORCOPY"],
                },
            },
        )
        assert "WS-ERROR-MESSAGE" not in cobol
        assert re.search(r"88\s+RC-SUCCESS", cobol, re.IGNORECASE)
        with tempfile.TemporaryDirectory() as tmp:
            cap = _compile_and_run_cobol(
                cobol,
                stdin_text="",
                tmp=Path(tmp),
                timeout_seconds=30,
                program_name="TXNPOST",
            )
            assert cap.execution_status != "compile_failure", cap.compile_stderr or cap.error
