"""Tests for COBOL CALL sub-program codegen and parser metadata."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.converters.call_codegen import (
    generate_call_site_java,
    generate_call_todo_java,
    generate_constrained_call_method_body,
    merge_external_call_metadata,
    paragraph_calls_subprogram,
    subprogram_import_lines,
)
from app.parsers.cobol_parser import ParserLayer
from app.services.call_java_repair import paragraph_to_java_method, repair_call_java

ACME_LOANEVAL = (
    Path(__file__).resolve().parents[2] / "acme-bank-v3" / "src" / "LOANEVAL.cbl"
)


def test_f14_loaneval_parser_external_calls_chkaml_and_calcfee():
    """F14: LOANEVAL parser captures both CALL targets with USING clauses."""
    assert ACME_LOANEVAL.is_file()
    result = ParserLayer().parse(ACME_LOANEVAL.read_text(encoding="utf-8"))
    names = {e["program_name"] for e in result["dependencies"]["external_calls"]}
    assert names == {"CALCFEE", "CHKAML"}

    by_prog = {e["program_name"]: e for e in result["dependencies"]["external_calls"]}
    assert by_prog["CHKAML"]["using"] == ["WS-AML-REQUEST", "WS-AML-RESPONSE"]
    assert by_prog["CALCFEE"]["using"] == ["WS-FEE-REQUEST", "WS-FEE-RESPONSE"]

    call_ops = [o for o in result.get("operations", []) if o.get("type") == "CALL"]
    assert {o["target"] for o in call_ops} == {"CALCFEE", "CHKAML"}
    paragraphs = {o["target"]: o["paragraph"] for o in call_ops}
    assert paragraphs["CHKAML"] == "2200-EXTERNAL-AML-CHECK"
    assert paragraphs["CALCFEE"] == "5300-CALL-FEE-CALCULATION"


def test_f14_loaneval_repair_wires_both_call_sites():
    """F14: repair injects both service fields and call bodies into paragraph methods."""
    parser_output = ParserLayer().parse(ACME_LOANEVAL.read_text(encoding="utf-8"))
    merged = merge_external_call_metadata(parser_output["dependencies"]["external_calls"])
    assert {m["program_name"] for m in merged} == {"CALCFEE", "CHKAML"}
    methods = {m["java_method"] for m in merged}
    assert methods == {"calculate", "checkAml"}

    stub = """
public class Loaneval {
    private void externalAmlCheck() {
        // placeholder AML
    }

    private void callFeeCalculation() {
        // placeholder fee
    }
}
"""
    repaired, notes = repair_call_java(stub, parser_output=parser_output)
    assert "private final ChkAmlService chkAmlService" in repaired
    assert "private final CalcFee calcFee" in repaired
    assert "chkAmlService.checkAml(amlRequest)" in repaired
    assert "calcFee.calculate(feeRequest)" in repaired
    assert "wsFeeResponse.setTotal(feeResponse.getTotal())" in repaired
    assert any("call_injected:CHKAML:externalAmlCheck" in n for n in notes)
    assert any("call_injected:CALCFEE:callFeeCalculation" in n for n in notes)

    # Call bodies stay inside their paragraph methods (no spill into sibling methods).
    def _method_block(java: str, method_name: str) -> str:
        start = java.index(f"void {method_name}(")
        open_brace = java.index("{", start)
        depth = 0
        for index in range(open_brace, len(java)):
            if java[index] == "{":
                depth += 1
            elif java[index] == "}":
                depth -= 1
                if depth == 0:
                    return java[start : index + 1]
        return ""

    aml_block = _method_block(repaired, "externalAmlCheck")
    fee_block = _method_block(repaired, "callFeeCalculation")
    assert "chkAmlService.checkAml" in aml_block
    assert "calcFee.calculate" not in aml_block
    assert "calcFee.calculate" in fee_block
    assert "chkAmlService.checkAml" not in fee_block


def test_parser_extracts_chkaml_call_with_using():
    assert ACME_LOANEVAL.is_file(), "ACME LOANEVAL fixture missing"
    parser = ParserLayer()
    result = parser.parse(ACME_LOANEVAL.read_text(encoding="utf-8"))
    calls = [
        op
        for op in result.get("operations", [])
        if op.get("type") == "CALL" and op.get("target") == "CHKAML"
    ]
    assert calls, "expected at least one CHKAML CALL operation"
    assert calls[0].get("using") == ["WS-AML-REQUEST", "WS-AML-RESPONSE"]
    assert calls[0].get("paragraph") == "2200-EXTERNAL-AML-CHECK"

    ext = result["dependencies"]["external_calls"]
    chk = next(e for e in ext if e["program_name"] == "CHKAML")
    assert chk["type"] == "sub_program"
    assert chk["using"] == ["WS-AML-REQUEST", "WS-AML-RESPONSE"]


def test_merge_known_chkaml_metadata():
    merged = merge_external_call_metadata(
        [{"program_name": "CHKAML", "using": ["WS-AML-REQUEST", "WS-AML-RESPONSE"]}]
    )
    meta = merged[0]
    assert meta["java_package"] == "com.modernized.chkaml"
    assert meta["java_class"] == "ChkAmlService"
    assert meta["java_method"] == "checkAml"
    assert meta["request_class"] == "AmlRequest"
    assert meta["response_class"] == "AmlResponse"
    assert len(meta["request_fields"]) == 6
    assert len(meta["response_fields"]) == 3


def test_fx4_constrained_chkaml_method_body():
    body = "           CALL 'CHKAML' USING WS-AML-REQUEST WS-AML-RESPONSE"
    assert paragraph_calls_subprogram(body) == "CHKAML"
    java = generate_constrained_call_method_body("CHKAML", body)
    assert "new ChkAmlService.AmlRequest(amlReqCustId" in java
    assert "chkAmlService.checkAml(amlReq)" in java
    assert "amlResp.getClear()" in java
    assert "wsAmlClear = amlRespClear" in java


def test_fx4_constrained_calcfee_method_body():
    body = "           CALL 'CALCFEE' USING WS-FEE-REQUEST WS-FEE-RESPONSE."
    assert paragraph_calls_subprogram(body) == "CALCFEE"
    java = generate_constrained_call_method_body("CALCFEE", body)
    assert "new CalcFee.FeeRequest(feeReqLoanType" in java
    assert "calcFee.calculate(feeReq)" in java
    assert "feeResp.getFileFee()" in java


def test_fx4_subprogram_import_lines():
    imports = subprogram_import_lines(["CHKAML", "CALCFEE"])
    assert "com.modernized.chkaml.ChkAmlService.AmlRequest" in imports
    assert "com.modernized.calcfee.CalcFee.FeeResponse" in imports


def test_generate_chkaml_call_site_java():
    merged = merge_external_call_metadata([{"program_name": "CHKAML", "using": ["WS-AML-REQUEST", "WS-AML-RESPONSE"]}])
    java = generate_call_site_java(merged[0])
    assert "chkAmlService.checkAml(amlRequest)" in java
    assert "wsAmlRequest.getCustId()" in java
    assert "wsAmlRequest.getNationality()" in java
    assert "wsAmlResponse.setClear(amlResponse.getClear())" in java
    assert "wsAmlResponse.setScore(amlResponse.getScore())" in java
    assert "wsAmlResponse.setReason(amlResponse.getReason())" in java


def test_generate_call_todo_when_metadata_incomplete():
    java = generate_call_todo_java("MYPROG", ["WS-REQ", "WS-RESP"])
    assert "TODO: CALL 'MYPROG' USING WS-REQ WS-RESP" in java
    assert "import com.modernized.myprog." in java


def test_paragraph_to_java_method():
    assert paragraph_to_java_method("2200-EXTERNAL-AML-CHECK") == "externalAmlCheck"
    assert paragraph_to_java_method("5300-CALL-FEE-CALCULATION") == "callFeeCalculation"


def test_repair_injects_call_into_matching_method():
    parser_output = {
        "program_name": "T",
        "operations": [],
        "dependencies": {"copybooks": [], "files": [], "external_calls": []},
    }
    parser_output["operations"] = [
        {
            "type": "CALL",
            "target": "CHKAML",
            "using": ["WS-AML-REQUEST", "WS-AML-RESPONSE"],
            "paragraph": "2200-EXTERNAL-AML-CHECK",
        }
    ]
    parser_output["dependencies"] = {
        "copybooks": [],
        "files": [],
        "external_calls": [
            {
                "program_name": "CHKAML",
                "type": "sub_program",
                "using": ["WS-AML-REQUEST", "WS-AML-RESPONSE"],
            }
        ],
    }
    stub = """
public class Loaneval {
    private void externalAmlCheck() {
        // TODO: CALL 'CHKAML' USING WS-AML-REQUEST WS-AML-RESPONSE
    }
}
"""
    repaired, notes = repair_call_java(stub, parser_output=parser_output)
    assert "chkAmlService.checkAml" in repaired
    assert any("call_injected:CHKAML" in n for n in notes)
    assert "private final ChkAmlService chkAmlService" in repaired
