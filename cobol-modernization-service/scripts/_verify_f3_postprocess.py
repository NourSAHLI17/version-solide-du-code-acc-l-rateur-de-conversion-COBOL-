#!/usr/bin/env python3
"""Verify FX3 final-pass repairs in _postprocess_conversion."""
from __future__ import annotations

import re
from pathlib import Path

from app.agents.conversion_agent import ConversionAgent
from app.services.java_compile_repair import CompileRepairResult
from app.services.pipeline_service import PipelineService

ROOT = Path(__file__).resolve().parents[2] / "acme-bank-v3" / "src"
PROGRAMS = ("CALCFEE", "CHKAML", "RECOVRY", "LOANEVAL", "RPTMONTH")


def _postprocess(prog: str, java: str) -> str:
    svc = PipelineService()
    src = (ROOT / f"{prog}.cbl").read_text(encoding="utf-8")
    po = svc.parse_cobol(src)
    agent = ConversionAgent()
    agent.last_compile_repair = CompileRepairResult(
        success=True,
        java_files={f"{prog.title()}.java": java},
        stderr="",
    )
    out, _ = agent._postprocess_conversion(
        java,
        source_code=src,
        parser_output=po,
        analysis_output="{}",
        program_name=prog,
        skip_compile_repair=True,
        skip_structure_finalize=True,
    )
    cached = next(iter(agent.last_compile_repair.java_files.values()))
    assert cached == out, f"{prog}: compile cache not synced with final output"
    return out


def main() -> None:
    calcfee = _postprocess(
        "CALCFEE",
        "public class Calcfee {\n  public static void main(String[] args) {}\n}\n",
    )
    assert "public class CalcFee" in calcfee, calcfee[:200]

    chkaml = _postprocess(
        "CHKAML",
        "public class Chkaml {\n  public static void main(String[] args) {}\n}\n",
    )
    assert "public class ChkAmlService" in chkaml, chkaml[:200]

    recovry = _postprocess(
        "RECOVRY",
        (
            "public class RecovryApplication {\n"
            "  public static void main(String[] args) {\n"
            "    new RecovryApplication().run();\n"
            "    sortRecoveryWork();\n"
            "  }\n"
            "  public void run() {}\n"
            "}\n"
        ),
    )
    main_body = re.search(r"public static void main[\s\S]*?\}", recovry)
    assert main_body and "sortRecoveryWork" not in main_body.group(0), main_body

    loaneval = _postprocess(
        "LOANEVAL",
        (
            "public class LoanevalApplication {\n"
            "  private void scoreIncome() {\n"
            '    throw new UnsupportedOperationException("TODO: scoreIncome");\n'
            "  }\n"
            "}\n"
        ),
    )
    assert "UnsupportedOperationException" not in loaneval

    rptmonth = _postprocess(
        "RPTMONTH",
        (
            "public class RptmonthApplication {\n"
            "  private void aggregateBySegment() {\n"
            '    throw new UnsupportedOperationException("TODO: aggregateBySegment");\n'
            "  }\n"
            "}\n"
        ),
    )
    assert "UnsupportedOperationException" not in rptmonth

    for prog in PROGRAMS:
        out = _postprocess(prog, f"public class X {{\n}}\n")
        assert re.search(r"^\s*package com\.modernized\.", out, re.M), prog

    print("FX3 postprocess verification: OK")


if __name__ == "__main__":
    main()
