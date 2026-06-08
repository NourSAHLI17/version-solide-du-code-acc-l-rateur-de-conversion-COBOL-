"""MASTER-PLAN Phase 0 — Steps 0.1 and 0.2 encoded as permanent regression tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.analysis_agent import AnalysisAgent
from app.parsers.cobol_parser import ParserLayer

PAYROLL_FIX = Path(__file__).resolve().parent / "fixtures" / "payroll" / "PAYROLL-CALC.cbl"
STMTRPT_FIX = Path(__file__).resolve().parent / "fixtures" / "usecase3" / "STMTRPT.cbl"


@pytest.fixture(autouse=True)
def _force_deterministic_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYSIS_ENGINE", "deterministic")


@pytest.fixture
def payroll_src() -> str:
    return PAYROLL_FIX.read_text(encoding="utf-8")


@pytest.fixture
def payroll_parse(payroll_src: str) -> dict:
    return ParserLayer().parse(payroll_src)


class TestStep01ParserFixes:
    def test_ws_tax_rate_is_bigdecimal(self, payroll_parse: dict) -> None:
        sym = next(s for s in payroll_parse["symbol_table_entries"] if s["name"] == "WS-TAX-RATE")
        pd = sym["pic_decoded"]
        assert pd["java_type"] == "BigDecimal"
        assert pd["dec_digits"] == 4

    def test_display_string_has_no_variable_references(self, payroll_parse: dict) -> None:
        hits = [
            op
            for op in payroll_parse["operations"]
            if op.get("type") == "DISPLAY"
            and "EMPLOYEE PAYROLL CALCULATOR" in str(op.get("value", ""))
        ]
        assert hits, "expected DISPLAY containing EMPLOYEE PAYROLL CALCULATOR"
        refs = hits[0].get("references")
        assert refs in (None, [], ())

    def test_filler_no_preflight_errors(self) -> None:
        src = STMTRPT_FIX.read_text(encoding="utf-8")
        out = ParserLayer().parse(src)
        assert out.get("preflight_errors") == []

    def test_payroll_no_preflight_errors(self, payroll_parse: dict) -> None:
        assert payroll_parse.get("preflight_errors") == []


class TestStep02AnalysisFixes:
    def test_main_paragraph_role_is_not_terminate(self, payroll_src: str, payroll_parse: dict) -> None:
        analysis = AnalysisAgent().analyze(payroll_src, payroll_parse)
        main = next(s for s in analysis["sections"] if s.get("name") == "0000-MAIN")
        assert main.get("role") != "Terminate program execution"

    def test_no_spurious_sum_rule(self, payroll_src: str, payroll_parse: dict) -> None:
        analysis = AnalysisAgent().analyze(payroll_src, payroll_parse)
        blob = json.dumps(analysis).lower()
        assert "sum values from 1 to 30" not in blob

    def test_tax_rate_paragraph_inputs_include_gross_pay(
        self, payroll_src: str, payroll_parse: dict
    ) -> None:
        analysis = AnalysisAgent().analyze(payroll_src, payroll_parse)
        sec = next(s for s in analysis["sections"] if s.get("name") == "8300-DETERMINE-TAX-RATE")
        ins = [str(x) for x in sec.get("inputs", [])]
        assert "WS-GROSS-PAY" in ins

    def test_global_purpose_mentions_payroll(self, payroll_src: str, payroll_parse: dict) -> None:
        analysis = AnalysisAgent().analyze(payroll_src, payroll_parse)
        gp = str(analysis.get("global_purpose", "")).lower()
        assert any(k in gp for k in ("payroll", "employee", "calculation")), gp
