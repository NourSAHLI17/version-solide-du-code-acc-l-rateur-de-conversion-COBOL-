"""PAYROLL-CALC integration checks for parser + semantic analysis (fix-pack)."""

import json
from pathlib import Path

import pytest

from app.agents.analysis_agent import AnalysisAgent
from app.parsers.cobol_parser import ParserLayer

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "payroll" / "PAYROLL-CALC.cbl"


@pytest.fixture(autouse=True)
def _force_deterministic_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Assertions target deterministic analysis output, not developer LLM keys."""
    monkeypatch.setenv("ANALYSIS_ENGINE", "deterministic")


@pytest.fixture
def payroll_source() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture
def payroll_parse(payroll_source: str) -> dict:
    return ParserLayer().parse(payroll_source)


class TestPayrollParserPICDisplayCompute:
    def test_ws_tax_rate_pic_v_decimal(self, payroll_parse: dict):
        sym = next(s for s in payroll_parse["symbol_table_entries"] if s["name"] == "WS-TAX-RATE")
        pd = sym["pic_decoded"]
        assert pd["java_type"] == "BigDecimal"
        assert pd["dec_digits"] == 4
        assert pd["is_numeric"] is True

    def test_display_literal_has_no_references(self, payroll_parse: dict):
        hits = [
            op
            for op in payroll_parse["operations"]
            if op.get("type") == "DISPLAY"
            and "EMPLOYEE PAYROLL CALCULATOR" in str(op.get("value", ""))
        ]
        assert hits, "expected DISPLAY of EMPLOYEE PAYROLL CALCULATOR"
        assert not hits[0].get("references")

    def test_display_mixed_literal_and_var(self, payroll_parse: dict):
        hits = [
            op
            for op in payroll_parse["operations"]
            if op.get("type") == "DISPLAY"
            and "EMP-NAME" in str(op.get("value", ""))
            and "WS-FOUND-IDX" in str(op.get("value", ""))
        ]
        assert hits
        refs = set(hits[0].get("references") or [])
        assert "EMP-NAME" in refs and "WS-FOUND-IDX" in refs

    def test_compute_rounded_flags(self, payroll_parse: dict):
        computes = [op for op in payroll_parse["operations"] if op.get("type") == "COMPUTE"]
        assert len(computes) >= 6
        rounded_true = sum(1 for c in computes if c.get("rounded") is True)
        rounded_false = sum(1 for c in computes if c.get("rounded") is False)
        assert rounded_true >= 5
        assert rounded_false >= 1

    def test_parser_revision_present(self, payroll_parse: dict):
        assert payroll_parse.get("parser_revision") == "2026-02-10"


class TestPayrollAnalysisSemantics:
    def test_global_purpose_payroll(self, payroll_parse: dict):
        analysis = AnalysisAgent().analyze(FIXTURE.read_text(encoding="utf-8"), payroll_parse)
        gp = str(analysis.get("global_purpose", "")).lower()
        assert "payroll" in gp or "employee" in gp
        assert "accumulated total" not in gp

    def test_no_sum_one_to_thirty_hallucination(self, payroll_parse: dict):
        analysis = AnalysisAgent().analyze(FIXTURE.read_text(encoding="utf-8"), payroll_parse)
        blob = json.dumps(analysis).lower()
        assert "sum values from 1 to 30" not in blob

    def test_determine_tax_inputs_include_gross_pay(self, payroll_parse: dict):
        analysis = AnalysisAgent().analyze(FIXTURE.read_text(encoding="utf-8"), payroll_parse)
        sec = next(s for s in analysis["sections"] if s["name"] == "8300-DETERMINE-TAX-RATE")
        ins = [str(x) for x in sec.get("inputs", [])]
        assert "WS-GROSS-PAY" in ins

    def test_payroll_roles_not_bulk_terminated(self, payroll_parse: dict):
        analysis = AnalysisAgent().analyze(FIXTURE.read_text(encoding="utf-8"), payroll_parse)
        terminated = [s["name"] for s in analysis["sections"] if s.get("role") == "Terminate program execution"]
        assert not terminated, f"unexpected Terminate roles: {terminated}"

    def test_analysis_includes_engine_metadata(self, payroll_parse: dict):
        analysis = AnalysisAgent().analyze(FIXTURE.read_text(encoding="utf-8"), payroll_parse)
        assert analysis.get("analysis_engine") == "deterministic"
        assert analysis.get("analysis_revision") >= 1


class TestPayrollConversionRoundingContract:
    def test_prompt_includes_per_compute_rounding_modes(self, payroll_source: str, payroll_parse: dict):
        from app.agents.conversion_agent import ConversionAgent

        _, prompt_input = ConversionAgent().build_conversion_prompt_input(
            payroll_source, payroll_parse, "{}",
        )
        rc = prompt_input["rounding_contract"]
        assert "WS-NET-PAY" in rc
        assert "RoundingMode.DOWN" in rc
        assert "HALF_UP" in rc
