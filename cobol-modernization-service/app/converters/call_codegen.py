"""Generate Java for COBOL CALL sub-programs (metadata-driven or TODO stubs)."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from app.converters.cobol_name_converter import (
    CobolNameConverter,
    SUB_PROGRAM_JAVA_CLASS_OVERRIDES,
    cobol_program_to_java_class,
)

KNOWN_SUBPROGRAMS: Dict[str, Dict[str, Any]] = {
    "CHKAML": {
        "program_name": "CHKAML",
        "type": "sub_program",
        "java_package": "com.modernized.chkaml",
        "java_class": "ChkAmlService",
        "java_method": "checkAml",
        "request_class": "AmlRequest",
        "response_class": "AmlResponse",
        "request_fields": [
            {"cobol": "AML-REQ-CUST-ID", "java": "custId"},
            {"cobol": "AML-REQ-CIN", "java": "cin"},
            {"cobol": "AML-REQ-NAME", "java": "name"},
            {"cobol": "AML-REQ-DOB", "java": "dob"},
            {"cobol": "AML-REQ-NATIONALITY", "java": "nationality"},
            {"cobol": "AML-REQ-AMOUNT", "java": "amount"},
        ],
        "response_fields": [
            {"cobol": "AML-RESP-CLEAR", "java": "clear"},
            {"cobol": "AML-RESP-SCORE", "java": "score"},
            {"cobol": "AML-RESP-REASON", "java": "reason"},
        ],
    },
    "CALCFEE": {
        "program_name": "CALCFEE",
        "type": "sub_program",
        "java_package": "com.modernized.calcfee",
        "java_class": "CalcFee",
        "java_method": "calculate",
        "request_class": "FeeRequest",
        "response_class": "FeeResponse",
        "request_fields": [
            {"cobol": "FEE-REQ-LOAN-TYPE", "java": "loanType"},
            {"cobol": "FEE-REQ-AMOUNT", "java": "amount"},
            {"cobol": "FEE-REQ-RATE", "java": "rate"},
        ],
        "response_fields": [
            {"cobol": "FEE-RESP-FILE-FEE", "java": "fileFee"},
            {"cobol": "FEE-RESP-TAX", "java": "tax"},
            {"cobol": "FEE-RESP-INSURANCE", "java": "insurance"},
            {"cobol": "FEE-RESP-TOTAL", "java": "total"},
        ],
    },
}


def normalize_external_call(entry: Any) -> Dict[str, Any]:
    if isinstance(entry, dict):
        base = dict(entry)
    else:
        base = {"program_name": str(entry).strip().upper()}
    name = str(base.get("program_name", "")).strip().upper()
    base["program_name"] = name
    base.setdefault("type", "sub_program")
    if isinstance(base.get("using"), str):
        base["using"] = _split_using_list(base["using"])
    return base


def merge_external_call_metadata(
    parser_calls: Sequence[Any],
    analysis_calls: Optional[Sequence[Any]] = None,
) -> List[Dict[str, Any]]:
    """Merge parser/analyzer CALL metadata; known registry fills demo gaps."""

    merged: Dict[str, Dict[str, Any]] = {}
    for source in (parser_calls, analysis_calls or []):
        for raw in source:
            item = normalize_external_call(raw)
            name = item.get("program_name", "")
            if not name:
                continue
            if name in merged:
                merged[name].update({k: v for k, v in item.items() if v is not None and v != ""})
            else:
                merged[name] = item

    for name in list(merged.keys()):
        known = KNOWN_SUBPROGRAMS.get(name)
        if not known:
            continue
        for key, value in known.items():
            if key not in merged[name] or not merged[name][key]:
                merged[name][key] = value

    return [merged[k] for k in sorted(merged)]


def _split_using_list(text: str) -> List[str]:
    return [part.strip().upper() for part in re.split(r"\s+", text.strip()) if part.strip()]


def _java_getter(prop: str) -> str:
    if not prop:
        return "get"
    return f"get{prop[0].upper()}{prop[1:]}"


def _java_setter(prop: str) -> str:
    if not prop:
        return "set"
    return f"set{prop[0].upper()}{prop[1:]}"


def _has_full_metadata(meta: Mapping[str, Any]) -> bool:
    required = ("java_package", "java_class", "java_method", "request_class", "response_class")
    if not all(meta.get(k) for k in required):
        return False
    return bool(meta.get("request_fields")) and bool(meta.get("response_fields"))


def generate_call_todo_java(
    program_name: str,
    using: Sequence[str],
    *,
    package_hint: str = "com.modernized",
) -> str:
    using_text = " ".join(using) if using else ""
    pkg = f"{package_hint}.{program_name.lower()}"
    prog = str(program_name or "").strip().upper()
    if prog in SUB_PROGRAM_JAVA_CLASS_OVERRIDES:
        cls = SUB_PROGRAM_JAVA_CLASS_OVERRIDES[prog]
    else:
        cls = CobolNameConverter.to_java_class(program_name) + "Service"
    return (
        f"        // TODO: CALL '{program_name}' USING {using_text}\n"
        f"        // Sub-program needs to be wired in - import {pkg}.{cls}"
    )


def generate_call_site_java(meta: Mapping[str, Any]) -> str:
    if not _has_full_metadata(meta):
        pkg = str(meta.get("java_package") or "com.modernized")
        root = pkg.rsplit(".", 1)[0] if "." in pkg else pkg
        return generate_call_todo_java(
            str(meta.get("program_name", "UNKNOWN")),
            meta.get("using") or [],
            package_hint=root,
        )

    program = str(meta["program_name"])
    cls = str(meta["java_class"])
    method = str(meta["java_method"])
    req_cls = str(meta["request_class"])
    resp_cls = str(meta["response_class"])
    using = list(meta.get("using") or [])
    req_ws = CobolNameConverter.to_java_field(using[0]) if using else "request"
    resp_ws = CobolNameConverter.to_java_field(using[1]) if len(using) > 1 else "response"
    service_var = cls[0].lower() + cls[1:] if cls else "service"
    req_var = req_cls[0].lower() + req_cls[1:] if req_cls else "request"
    resp_var = resp_cls[0].lower() + resp_cls[1:] if resp_cls else "response"

    req_args = ",\n".join(
        f"            {req_ws}.{_java_getter(str(f.get('java') or ''))}()"
        for f in (meta.get("request_fields") or [])
    )

    lines = [
        f"        // CALL '{program}' USING {' '.join(using)}",
        "        // Build request from working storage",
        f"        {cls}.{req_cls} {req_var} = new {cls}.{req_cls}(",
        req_args,
        "        );",
        "        // Call sub-program",
        f"        {cls}.{resp_cls} {resp_var} = {service_var}.{method}({req_var});",
        "        // Copy response back to working storage",
    ]

    for field in meta.get("response_fields") or []:
        prop = str(field.get("java") or "")
        lines.append(f"        {resp_ws}.{_java_setter(prop)}({resp_var}.{_java_getter(prop)}());")

    return "\n".join(lines)


def subprogram_field_name(java_class: str, cobol_program: str = "") -> str:
    """Derive the scaffold field name from the Java service class (e.g. ChkAmlService → chkAmlService)."""
    if java_class:
        return java_class[0].lower() + java_class[1:]
    return CobolNameConverter.to_java_field(cobol_program)


def subprogram_names_from_meta(meta: Mapping[str, Any]) -> Tuple[str, str, str]:
    """Return (java_class, java_field_name, java_method) using KNOWN_SUBPROGRAMS when present."""
    prog = str(meta.get("program_name") or "").upper()
    known = KNOWN_SUBPROGRAMS.get(prog, {})
    java_cls = str(meta.get("java_class") or known.get("java_class") or cobol_program_to_java_class(prog))
    java_meth = str(meta.get("java_method") or known.get("java_method") or "process")
    java_fld = str(meta.get("java_field_name") or meta.get("java_field") or "")
    if not java_fld:
        java_fld = subprogram_field_name(java_cls, prog)
    return java_cls, java_fld, java_meth


def generate_service_field_java(meta: Mapping[str, Any]) -> str:
    if not _has_full_metadata(meta):
        return ""
    cls, var, _ = subprogram_names_from_meta(meta)
    return f"    private final {cls} {var} = new {cls}();"


def generate_all_call_sites_java(external_calls: Sequence[Mapping[str, Any]]) -> str:
    parts: List[str] = ["    // --- External CALL sites (converter-generated) ---"]
    for meta in external_calls:
        field = generate_service_field_java(meta)
        if field:
            parts.append(field)
    for meta in external_calls:
        program = str(meta.get("program_name", "CALL"))
        method_name = f"invoke{program.title().replace('-', '')}"
        body = generate_call_site_java(meta)
        parts.append(f"    private void {method_name}() {{\n{body}\n    }}")
    return "\n".join(parts)


def external_calls_for_prompt(external_calls: Sequence[Mapping[str, Any]]) -> str:
    return json.dumps(list(external_calls), indent=2)


_CALL_PROGRAM_RE = re.compile(r"CALL\s+['\"]([A-Z0-9-]+)['\"]", re.IGNORECASE)


def paragraph_calls_subprogram(cobol_body: str) -> Optional[str]:
    """Return CHKAML or CALCFEE when the paragraph body contains that CALL."""
    if not cobol_body:
        return None
    for match in _CALL_PROGRAM_RE.finditer(cobol_body):
        prog = match.group(1).upper()
        if prog in KNOWN_SUBPROGRAMS:
            return prog
    return None


def subprogram_import_lines(programs: Sequence[str]) -> List[str]:
    """Fully-qualified imports for known sub-program DTOs (FX4)."""
    imports: List[str] = []
    for prog in programs:
        key = str(prog).upper()
        known = KNOWN_SUBPROGRAMS.get(key)
        if not known:
            continue
        pkg = str(known["java_package"])
        cls = str(known["java_class"])
        req = str(known["request_class"])
        resp = str(known["response_class"])
        imports.extend(
            [
                f"{pkg}.{cls}",
                f"{pkg}.{cls}.{req}",
                f"{pkg}.{cls}.{resp}",
            ]
        )
    return imports


def generate_constrained_call_method_body(
    sub_program: str,
    cobol_body: str,
    symbol_table: Any = None,
) -> str:
    """
    Deterministic method body for paragraphs that CALL CHKAML or CALCFEE (FX4).

    Uses inline DTO construction and service fields from the symbol table.
    """
    prog = sub_program.upper()
    meta = dict(KNOWN_SUBPROGRAMS.get(prog) or {})
    java_class, service_field, java_method = subprogram_names_from_meta(meta)
    req_cls = str(meta.get("request_class") or "Request")
    resp_cls = str(meta.get("response_class") or "Response")
    short = {"AmlRequest": "amlReq", "AmlResponse": "amlResp", "FeeRequest": "feeReq", "FeeResponse": "feeResp"}
    req_var = short.get(req_cls, req_cls[0].lower() + req_cls[1:])
    resp_var = short.get(resp_cls, resp_cls[0].lower() + resp_cls[1:])

    qualified_req = f"{java_class}.{req_cls}"
    qualified_resp = f"{java_class}.{resp_cls}"

    if prog == "CHKAML":
        lines = [
            "amlReqCustId = custId;",
            "amlReqCin = custCin;",
            "amlReqName = custFirstName + \" \" + custLastName;",
            "amlReqDob = custDateOfBirth;",
            "amlReqNationality = custNationality;",
            "amlReqAmount = loanOriginalAmt;",
            (
                f"{qualified_req} {req_var} = new {qualified_req}(amlReqCustId, amlReqCin, amlReqName, "
                "amlReqDob, amlReqNationality, amlReqAmount);"
            ),
            f"{qualified_resp} {resp_var} = {service_field}.{java_method}({req_var});",
            f"amlRespClear = {resp_var}.getClear();",
            f"amlRespReason = {resp_var}.getReason();",
            f"amlRespScore = {resp_var}.getScore();",
            "wsAmlClear = amlRespClear;",
            "wsAmlReason = amlRespReason;",
        ]
        return "\n".join(lines)

    if prog == "CALCFEE":
        lines = [
            "feeReqLoanType = loanType;",
            "feeReqAmount = loanOriginalAmt;",
            "feeReqRate = scrMaxRate;",
            (
                f"{qualified_req} {req_var} = new {qualified_req}(feeReqLoanType, feeReqAmount, feeReqRate);"
            ),
            f"{qualified_resp} {resp_var} = {service_field}.{java_method}({req_var});",
            f"feeRespFileFee = {resp_var}.getFileFee();",
            f"feeRespTax = {resp_var}.getTax();",
            f"feeRespInsurance = {resp_var}.getInsurance();",
            f"feeRespTotal = {resp_var}.getTotal();",
        ]
        return "\n".join(lines)

    return generate_call_site_java(meta)
