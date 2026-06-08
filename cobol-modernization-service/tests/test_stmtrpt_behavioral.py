"""STMTRPT live compile/run with report-derived stdout."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.behavioral_diff_runner import _compile_and_run_cobol, _prepare_behavioral_sources, run_behavioral_diff

FIXTURE_COB = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "usecase3" / "STMTRPT.cbl"
).read_text(encoding="utf-8")

REFERENCE_JAVA = """public class Stmtrpt {
    public static void main(String[] args) {
        System.out.println("0000-MAIN");
        System.out.println("0100-OPEN-FILES");
        System.out.println("0200-WRITE-GRAND-TOTALS");
        System.out.println("CUSTOMER STATEMENT REPORT");
        System.out.println("GRAND TOTAL:");
        System.out.println("TOTAL RECORDS: 00000");
        System.out.println("END OF REPORT");
    }
}
"""


class TestStmtrptBehavioral:
    def test_java_sanitizer_removes_paragraph_labels_from_reference(self):
        from app.services.java_output_sanitizer import prepare_java_for_behavioral_compile

        java, _ = prepare_java_for_behavioral_compile(REFERENCE_JAVA)
        assert "0000-MAIN" not in java
        assert "0100-OPEN-FILES" not in java
        assert "CUSTOMER STATEMENT REPORT" in java

    @pytest.mark.skipif(not shutil.which("cobc"), reason="GnuCOBOL not installed")
    def test_stmtrpt_cobol_compiles_after_prep(self):
        cobol, _, _, _ = _prepare_behavioral_sources(
            FIXTURE_COB,
            "",
            "STMTRPT",
            parser_output={
                "dependencies": {
                    "copybooks": ["CUSTCOPY", "RPTHDCPY", "ERRORCOPY"],
                },
            },
        )
        assert "RPT-PAGE-NO" in cobol or "RPT-LINE-TEXT" in cobol
        with tempfile.TemporaryDirectory() as tmp:
            cap = _compile_and_run_cobol(
                cobol,
                stdin_text="",
                tmp=Path(tmp),
                timeout_seconds=30,
                program_name="STMTRPT",
            )
            assert cap.execution_status != "compile_failure", cap.compile_stderr or cap.error
            assert (Path(tmp) / "ACME.STMT.REPORT").is_file()

    @pytest.mark.skipif(not shutil.which("cobc"), reason="GnuCOBOL not installed")
    def test_stmtrpt_behavioral_diff_report_stdout(self):
        from app.services.java_output_sanitizer import prepare_java_for_behavioral_compile

        java, _ = prepare_java_for_behavioral_compile(REFERENCE_JAVA)
        result = run_behavioral_diff(
            {
                "target_type": "single_file",
                "run_id": "stmtrpt-beh",
                "program_name": "STMTRPT",
                "cobol_source": FIXTURE_COB,
                "java_source": java,
                "parser_output": {
                    "dependencies": {
                        "copybooks": ["CUSTCOPY", "RPTHDCPY", "ERRORCOPY"],
                    },
                },
                "scripted_input": "",
                "fallback_mode": False,
                "timeout_seconds": 45,
            }
        )
        cob_out = (result.get("cobol_output") or "").strip()
        java_out = (result.get("java_output") or "").strip()
        assert "0000-MAIN" not in java_out
        assert "CUSTOMER STATEMENT REPORT" in cob_out
        assert "CUSTOMER STATEMENT REPORT" in java_out
        ed = (result.get("execution_details") or [{}])[0]
        assert ed.get("cobol_execution", {}).get("execution_status") != "compile_failure"
        assert ed.get("java_execution", {}).get("execution_status") != "compile_failure"
