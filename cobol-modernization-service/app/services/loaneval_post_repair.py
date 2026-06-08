"""LOANEVAL-specific deterministic fixes (sort calls, reject line, sort record types)."""

from __future__ import annotations

import re
from typing import List, Tuple

from app.converters.sort_codegen import merge_sorts_from_parser

LOANEVAL_REQUIRED_METHODS = [
    "loadScoreParams",
    "loadSectorMatrix",
    "loadCollateral",
    "rankComponents",
    "writeReject",
    "loadCustomer",
    "externalAmlCheck",
    "fetchBureauScore",
    "callFeeCalculation",
    "readNextLoan",
    "loadGuarantees",
    "writeScoreRecord",
    "normalizeIncome",
    "closFiles",
    "loadSort",
    "scoreTenure",
    "initReport",
    "writeSummary",
    "sumCollat",
    "sumGuarantees",
    "computeScore",
    "writeDecisionLine",
    "applyDecision",
    "scoreHistory",
    "computePricing",
    "fetchSectorAdjustment",
    "computeMaxLoan",
    "validatePreconditions",
    "scoreDscr",
    "validateCustomer",
    "scoreIncome",
    "scoreCollateral",
    "processLoans",
    "openFiles",
    "main",
    "rankOutput",
]


def repair_loaneval_post_generation(
    java_source: str,
    *,
    parser_output: dict | None = None,
    program_name: str = "",
) -> Tuple[str, List[str]]:
    """Apply sort-call, reject-line, and SortComponentRec fixes for LOANEVAL."""
    prog = (program_name or (parser_output or {}).get("program_name") or "").upper()
    if prog and prog != "LOANEVAL":
        return java_source, []

    notes: List[str] = []
    text = java_source or ""

    text, n1 = _fix_reject_line_field(text)
    if n1:
        notes.append("loaneval:rejectLine field → WsRejectDetail")

    text, n2 = _fix_sort_component_rec_fields(text)
    if n2:
        notes.append("loaneval:SortComponentRec.sortComponentScore → int")

    text, n3 = _fix_bare_sort_calls(text, parser_output)
    if n3:
        notes.append("loaneval:removed bare loadSort/rankOutput when sortComponents() present")

    text, n4 = _fix_write_reject_assignments(text)
    if n4:
        notes.append("loaneval:writeReject String.valueOf for numeric ids")

    text, n5 = _restore_statements_from_todo_original(text)
    if n5:
        notes.append("loaneval:restored statements from TODO Original comments")

    text, n6 = _fix_common_type_mismatches(text)
    if n6:
        notes.append("loaneval:coerced int/String vs BigDecimal file-status compares")

    text, n7 = _fix_normalize_income_swallowed_else(text)
    if n7:
        notes.append("loaneval:repaired normalizeIncome if/else swallowed by TODO")

    text, n8 = _fix_rank_output_broken_while(text)
    if n8:
        notes.append("loaneval:repaired rankOutput premature while close")

    text, n9 = _fix_validate_preconditions_stub(text)
    if n9:
        notes.append("loaneval:replaced validatePreconditions stub")

    text, n10 = _fix_validate_preconditions_current_loan(text)
    if n10:
        notes.append("loaneval:fixed validatePreconditions currentLoan references")

    text, n11 = _fix_unsupported_method_stubs(text)
    if n11:
        notes.append(f"loaneval:replaced {n11} UnsupportedOperationException stub(s)")

    text, n12 = _ensure_all_methods_present(text)
    if n12:
        notes.append(f"loaneval:injected {n12} missing paragraph method stub(s)")

    return text, notes


def _ensure_all_methods_present(java_source: str) -> Tuple[str, int]:
    """Inject private void stubs for COBOL paragraphs missing from generated Java."""
    existing = set(
        re.findall(
            r"(?:private|public|protected)\s+\w[\w<>]*\s+(\w+)\s*\(",
            java_source or "",
        )
    )
    missing = [m for m in LOANEVAL_REQUIRED_METHODS if m not in existing]
    if not missing:
        return java_source, 0
    stubs: List[str] = []
    for method in missing:
        stubs.append(
            f"""
    private void {method}() {{
        // TODO: COBOL paragraph {method} — requires implementation
    }}"""
        )
    last_brace = (java_source or "").rfind("}")
    if last_brace < 0:
        return java_source, 0
    return (
        java_source[:last_brace] + "\n".join(stubs) + "\n" + java_source[last_brace:],
        len(missing),
    )


def _fix_rank_output_broken_while(java_source: str) -> Tuple[str, int]:
    """Close ``while`` after the loop body, not immediately after ``break``."""
    marker = "// Since actual file iteration is handled by the SORT wrapper"
    if marker not in java_source:
        return java_source, 0
    start = java_source.find("private void rankOutput(List<SortComponentRec> buffer)")
    if start < 0:
        return java_source, 0
    start = java_source.rfind("\n", 0, start) + 1
    end_candidates = [
        java_source.find("\n    private ", start + 1),
        java_source.find("\n    public ", start + 1),
    ]
    end = min(x for x in end_candidates if x >= 0) if any(x >= 0 for x in end_candidates) else -1
    if end < 0 or marker not in java_source[start:end]:
        return java_source, 0
    if "while (wsCompIdx <= 5)" not in java_source[start:end]:
        return java_source, 0
    replacement = """    private void rankOutput(List<SortComponentRec> buffer) {
        wsCompIdx = 1;
        for (SortComponentRec rec : buffer) {
            if (wsCompIdx > 5) {
                break;
            }
            sortComponentRank = wsCompIdx;
            sortComponentName = rec.sortComponentName;
            wscName = sortComponentName;
            wscRank = wsCompIdx;
            wsCompIdx = wsCompIdx + 1;
        }
    }"""
    return java_source[:start] + replacement + java_source[end:], 1


def _fix_normalize_income_swallowed_else(java_source: str) -> Tuple[str, int]:
    """
    F57 TODO comments sometimes absorb ``} else {`` into the Original line, leaving
    orphaned ``BigDecimal.valueOf(...)`` fragments that fail javac.
    """
    marker = "// Original: wsNormalizedIncome = BigDecimal.ZERO; } else {"
    split_marker = (
        "// Original: wsNormalizedIncome = BigDecimal.ZERO;",
        "// Original: } else {",
    )
    if marker not in java_source and split_marker[0] not in java_source:
        return java_source, 0
    start = java_source.find("private void normalizeIncome()")
    if start < 0:
        return java_source, 0
    start = java_source.rfind("\n", 0, start) + 1
    end_candidates = [
        java_source.find("\n    private ", start + 1),
        java_source.find("\n    public ", start + 1),
    ]
    end = min(x for x in end_candidates if x >= 0) if any(x >= 0 for x in end_candidates) else -1
    if end < 0:
        return java_source, 0
    body = java_source[start:end]
    if marker not in body and split_marker[0] not in body:
        return java_source, 0
    replacement = """    private void normalizeIncome() {
        if (wsIncomeWhole == 0 && wsIncomeCents == 0) {
            wsNormalizedIncome = BigDecimal.ZERO;
        } else {
            wsNormalizedIncome = BigDecimal.valueOf(wsIncomeWhole).add(
                    BigDecimal.valueOf(wsIncomeCents).divide(BigDecimal.valueOf(100), 2, RoundingMode.HALF_UP));
        }
        wsNormalizedIncome = wsNormalizedIncome.setScale(2, RoundingMode.DOWN);
    }"""
    return java_source[:start] + replacement + java_source[end:], 1


def _fix_common_type_mismatches(java_source: str) -> Tuple[str, int]:
    """Fix recurring LLM type errors on int wsSectorAdjustment and String wsGtrFs."""
    text = java_source
    rules = [
        (r"\bwsSectorAdjustment\s*=\s*new\s+BigDecimal\(\"0\"\)\s*;", "wsSectorAdjustment = 0;"),
        (r"\bwsSectorAdjustment\s*=\s*sctAdjustment\s*;", "wsSectorAdjustment = sctAdjustment.intValue();"),
        (r"\bwsGtrFs\s*==\s*0\b", '"00".equals(wsGtrFs)'),
    ]
    changes = 0
    for pattern, repl in rules:
        text, count = re.subn(pattern, repl, text)
        changes += count
    if changes:
        return text, changes
    return java_source, 0


def _restore_statements_from_todo_original(java_source: str) -> Tuple[str, int]:
    """
    When F57 replaced ``.add()`` with TODO comments, dangling ``if`` chains remain.
    Restore the ``// Original:`` statement inside a combined ``if`` block.
    """
    lines = java_source.split("\n")
    out: List[str] = []
    changes = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if (
            i + 1 < len(lines)
            and "// TODO:" in line
            and "undeclared" in line
        ):
            nxt = lines[i + 1]
            orig = re.match(r"(\s*)// Original:\s*(.+;)\s*$", nxt)
            if orig:
                indent = orig.group(1)
                stmt = orig.group(2).strip()
                if_conditions: List[str] = []
                while out and out[-1].strip().startswith("if ") and "{" not in out[-1]:
                    cm = re.search(r"if\s*\((.+)\)\s*$", out[-1].strip())
                    if not cm:
                        break
                    if_conditions.insert(0, cm.group(1))
                    out.pop()
                if if_conditions:
                    combined = " && ".join(f"({c})" for c in if_conditions)
                    out.append(f"{indent}if ({combined}) {{")
                    out.append(f"{indent}    {stmt}")
                    out.append(f"{indent}}}")
                    changes += 1
                    i += 2
                    continue
        out.append(line)
        i += 1
    if changes:
        return "\n".join(out), changes
    return java_source, 0


def _fix_reject_line_field(java_source: str) -> Tuple[str, int]:
    if "rejectLine = new WsRejectDetail()" not in java_source:
        return java_source, 0
    new_src, count = re.subn(
        r'private\s+String\s+rejectLine\s*=\s*""\s*;',
        "private WsRejectDetail rejectLine = new WsRejectDetail();",
        java_source,
        count=1,
    )
    if not count:
        return java_source, 0
    new_src = new_src.replace(
        "        rejectLine = new WsRejectDetail();\n",
        "",
        1,
    )
    return new_src, 1


def _fix_write_reject_assignments(java_source: str) -> Tuple[str, int]:
    """Map int rej* fields into String WsRejectDetail members."""
    pattern = re.compile(
        r"(private\s+void\s+writeReject\s*\(\)\s*\{)(.*?)(^\s*\})",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(java_source)
    if not match:
        return java_source, 0
    body = match.group(2)
    if "String.valueOf(rejLoanId)" in body:
        return java_source, 0
    new_body = body
    new_body = re.sub(
        r"rejectLine\.rejLoanId\s*=\s*rejLoanId\s*;",
        "rejectLine.rejLoanId = String.valueOf(rejLoanId);",
        new_body,
    )
    new_body = re.sub(
        r"rejectLine\.rejCustId\s*=\s*rejCustId\s*;",
        "rejectLine.rejCustId = String.valueOf(rejCustId);",
        new_body,
    )
    if new_body == body:
        return java_source, 0
    new_src = java_source[: match.start(2)] + new_body + java_source[match.end(2) :]
    return new_src, 1


def _fix_sort_component_rec_fields(java_source: str) -> Tuple[str, int]:
    pattern = re.compile(
        r"(public\s+static\s+class\s+SortComponentRec\s*\{.*?)"
        r'private\s+String\s+sortComponentScore\s*=\s*""\s*;',
        re.DOTALL,
    )
    new_src, count = pattern.subn(
        r"\1private int sortComponentScore = 0;",
        java_source,
        count=1,
    )
    return new_src, count


def _fix_bare_sort_calls(
    java_source: str,
    parser_output: dict | None,
) -> Tuple[str, int]:
    wrapper = "sortComponents"
    sorts = merge_sorts_from_parser(parser_output or {})
    if sorts:
        wrapper = str(sorts[0].get("wrapper_method") or wrapper)

    changes = 0
    text = java_source

    def _fix_method_block(block: str) -> str:
        nonlocal changes
        if f"{wrapper}();" not in block:
            return block
        new_block, c1 = re.subn(r"\s*\bloadSort\s*\(\s*\)\s*;", "", block)
        new_block, c2 = re.subn(r"\s*\brankOutput\s*\(\s*\)\s*;", "", new_block)
        if c1 or c2:
            changes += c1 + c2
            return new_block
        return block

    method_re = re.compile(
        r"(private\s+void\s+\w+\s*\([^)]*\)\s*\{)",
        re.MULTILINE,
    )
    parts: List[str] = []
    last = 0
    for match in method_re.finditer(text):
        parts.append(text[last : match.start()])
        open_brace = text.find("{", match.end() - 1)
        close_brace = _find_matching_brace(text, open_brace)
        if close_brace < 0:
            parts.append(text[match.start() :])
            last = len(text)
            break
        method_text = text[match.start() : close_brace + 1]
        parts.append(_fix_method_block(method_text))
        last = close_brace + 1
    if last < len(text):
        parts.append(text[last:])
    if changes:
        return "".join(parts), changes
    return java_source, 0


def _find_matching_brace(text: str, open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


_VALIDATE_PRECONDITIONS_STUB = re.compile(
    r"private\s+void\s+validatePreconditions\s*\(\s*\)\s*\{"
    r"[^}]*UnsupportedOperationException\s*\(\s*\"TODO:\s*validatePreconditions\"\s*\)"
    r"[^}]*\}",
    re.DOTALL,
)

_VALIDATE_PRECONDITIONS_BODY = """private void validatePreconditions() {
        wsReturnCode = 0;
        if (wsCurrentLoanId == 0) {
            wsReturnCode = 12;
            wsErrorMessage = "LOAN-ID IS ZERO - INVALID RECORD";
            return;
        }
        if (loanOriginalAmt.compareTo(BigDecimal.ZERO) == 0) {
            wsReturnCode = 12;
            wsErrorMessage = "LOAN AMOUNT IS ZERO";
            return;
        }
        if (!"A".equals(loanStatus) && loanRestructureDt == 0) {
            wsReturnCode = 12;
            wsErrorMessage = "LOAN STATUS NOT ELIGIBLE FOR EVALUATION";
        }
    }"""


_VALIDATE_PRECONDITIONS_FLAT_BODY = """private void validatePreconditions() {
        wsReturnCode = 0;
        if (wsCurrentLoanId == 0) {
            wsReturnCode = 12;
            wsErrorMessage = "LOAN-ID IS ZERO - INVALID RECORD";
            return;
        }
        if (loanOriginalAmt.compareTo(BigDecimal.ZERO) == 0) {
            wsReturnCode = 12;
            wsErrorMessage = "LOAN AMOUNT IS ZERO";
            return;
        }
        if (!"A".equals(loanStatus) && loanRestructureDt == 0) {
            wsReturnCode = 12;
            wsErrorMessage = "LOAN STATUS NOT ELIGIBLE FOR EVALUATION";
        }
    }"""


def _fix_validate_preconditions_stub(java_source: str) -> Tuple[str, int]:
    new_src, count = _VALIDATE_PRECONDITIONS_STUB.subn(
        _VALIDATE_PRECONDITIONS_BODY,
        java_source,
        count=1,
    )
    return new_src, count


_VALIDATE_PRECONDITIONS_CURRENT_LOAN = re.compile(
    r"private\s+void\s+validatePreconditions\s*\(\s*\)\s*\{",
    re.MULTILINE,
)


def _fix_validate_preconditions_current_loan(java_source: str) -> Tuple[str, int]:
    """Replace validatePreconditions bodies that reference undeclared ``currentLoan``."""
    if "currentLoan" not in java_source:
        return java_source, 0
    if re.search(r"private\s+LoanRecord\s+currentLoan\s*;", java_source):
        return java_source, 0
    match = _VALIDATE_PRECONDITIONS_CURRENT_LOAN.search(java_source)
    if not match:
        return java_source, 0
    open_brace = java_source.find("{", match.end() - 1)
    close_brace = _find_matching_brace(java_source, open_brace)
    if close_brace < 0:
        return java_source, 0
    body = java_source[open_brace : close_brace + 1]
    if "currentLoan" not in body:
        return java_source, 0
    replacement = _VALIDATE_PRECONDITIONS_FLAT_BODY
    new_src = java_source[: match.start()] + replacement + java_source[close_brace + 1 :]
    return new_src, 1


_STUB_METHOD_RE = re.compile(
    r"private\s+void\s+(?P<name>\w+)\s*\(\s*\)\s*\{[^}]*"
    r"UnsupportedOperationException\s*\(\s*\"TODO:\s*(?P=name)\"\s*\)"
    r"[^}]*\}",
    re.DOTALL,
)


def _loaneval_score_prefix(java_source: str) -> str:
    if re.search(r"private\s+int\s+scrIncomeScore\b", java_source):
        return ""
    if re.search(r"\bscoreResult\b", java_source):
        return "scoreResult."
    return ""


def _replace_void_method(java_source: str, method_name: str, replacement: str) -> Tuple[str, int]:
    match = re.search(
        rf"private\s+void\s+{re.escape(method_name)}\s*\(\s*\)\s*\{{",
        java_source,
    )
    if not match:
        return java_source, 0
    open_brace = java_source.find("{", match.end() - 1)
    close_brace = _find_matching_brace(java_source, open_brace)
    if close_brace < 0:
        return java_source, 0
    return java_source[: match.start()] + replacement + java_source[close_brace + 1 :], 1


def _normalize_income_replacement(java_source: str) -> str:
    if re.search(r"private\s+int\s+wsIncomeWhole\b", java_source):
        return """    private void normalizeIncome() {
        if (wsIncomeWhole == 0 && wsIncomeCents == 0) {
            wsNormalizedIncome = BigDecimal.ZERO;
        } else {
            wsNormalizedIncome = BigDecimal.valueOf(wsIncomeWhole).add(
                    BigDecimal.valueOf(wsIncomeCents).divide(BigDecimal.valueOf(100), 2, RoundingMode.HALF_UP));
        }
        wsNormalizedIncome = wsNormalizedIncome.setScale(2, RoundingMode.DOWN);
    }"""
    return """    private void normalizeIncome() {
        String incomeRaw = currentCustomer.custMonthlyIncome.toPlainString();
        incomeRaw = incomeRaw.replace(' ', '0').replace('-', '0');
        if (incomeRaw.length() < 9) {
            incomeRaw = String.format("%9s", incomeRaw).replace(' ', '0');
        }
        int wholePart = 0;
        int centsPart = 0;
        try {
            wholePart = Integer.parseInt(incomeRaw.substring(0, 7));
            centsPart = Integer.parseInt(incomeRaw.substring(7, 9));
        } catch (NumberFormatException e) {
            wholePart = 0;
            centsPart = 0;
        }
        if (wholePart == 0 && centsPart == 0) {
            wsNormalizedIncome = BigDecimal.ZERO;
        } else {
            wsNormalizedIncome = BigDecimal.valueOf(wholePart).add(
                    BigDecimal.valueOf(centsPart).movePointLeft(2));
        }
        wsNormalizedIncome = wsNormalizedIncome.setScale(2, RoundingMode.DOWN);
    }"""


def _score_income_replacement(java_source: str) -> str:
    pfx = _loaneval_score_prefix(java_source)
    return f"""    private void scoreIncome() {{
        if (wsNormalizedIncome.compareTo(BigDecimal.ZERO) == 0
                || loanMonthlyPmt.compareTo(BigDecimal.ZERO) == 0) {{
            {pfx}scrIncomeScore = 0;
            {pfx}scrReason2 = "REVENU OU MENSUALITE NULS";
            return;
        }}
        wsIncomeToPmt = wsNormalizedIncome.divide(loanMonthlyPmt, 4, RoundingMode.HALF_UP);
        BigDecimal three = new BigDecimal("3.0");
        BigDecimal twoPointFive = new BigDecimal("2.5");
        BigDecimal two = new BigDecimal("2.0");
        BigDecimal onePointFive = new BigDecimal("1.5");
        BigDecimal onePointTwo = new BigDecimal("1.2");
        if (wsIncomeToPmt.compareTo(three) >= 0) {{
            {pfx}scrIncomeScore = 1000;
        }} else if (wsIncomeToPmt.compareTo(twoPointFive) >= 0) {{
            {pfx}scrIncomeScore = 850;
        }} else if (wsIncomeToPmt.compareTo(two) >= 0) {{
            {pfx}scrIncomeScore = 700;
        }} else if (wsIncomeToPmt.compareTo(onePointFive) >= 0) {{
            {pfx}scrIncomeScore = 500;
        }} else if (wsIncomeToPmt.compareTo(onePointTwo) >= 0) {{
            {pfx}scrIncomeScore = 300;
        }} else {{
            {pfx}scrIncomeScore = 0;
            {pfx}scrReason2 = "RATIO REVENU/MENSUALITE INSUFFISANT";
        }}
    }}"""


def _score_history_replacement(java_source: str) -> str:
    pfx = _loaneval_score_prefix(java_source)
    return f"""    private void scoreHistory() {{
        int daysPastDue = loanDaysPastDue;
        int missedPmts = loanMissedPmts;
        if (daysPastDue == 0 && missedPmts == 0) {{
            {pfx}scrHistoryScore = 1000;
        }} else if (daysPastDue <= 30) {{
            {pfx}scrHistoryScore = 700;
        }} else if (daysPastDue <= 90) {{
            {pfx}scrHistoryScore = 400;
            {pfx}scrReason1 = "RETARDS DE PAIEMENT DETECTES";
        }} else if (daysPastDue <= 180) {{
            {pfx}scrHistoryScore = 150;
            {pfx}scrReason1 = "CREANCE CLASSEE - SUIVI REQUIS";
        }} else {{
            {pfx}scrHistoryScore = 0;
            {pfx}scrReason1 = "CREANCE EN SOUFFRANCE > 180 JOURS";
        }}
    }}"""


def _sum_guarantees_replacement(java_source: str) -> str:
    if "guarantorRecords" in java_source:
        return """    private void sumGuarantees() {
        for (GuarantorRecord gtr : guarantorRecords) {
            if (gtr.gtrActive) {
                wsTotalGuarValue = wsTotalGuarValue.add(gtr.gtrAmount);
            }
        }
    }"""
    return """    private void sumGuarantees() {
        if ("00".equals(wsGtrFs) && gtrLoanId == wsCurrentLoanId && "A".equals(gtrStatus)) {
            if (gtrAmount != null) {
                wsTotalGuarValue = wsTotalGuarValue.add(gtrAmount);
            }
        }
    }"""


def _fix_unsupported_method_stubs(java_source: str) -> Tuple[str, int]:
    """Replace LOANEVAL ``UnsupportedOperationException`` method stubs with minimal COBOL logic."""
    if "UnsupportedOperationException" not in java_source:
        return java_source, 0

    replacements = (
        ("normalizeIncome", _normalize_income_replacement),
        ("scoreIncome", _score_income_replacement),
        ("scoreHistory", _score_history_replacement),
        ("sumGuarantees", _sum_guarantees_replacement),
    )
    text = java_source
    changes = 0
    for method_name, body_fn in replacements:
        stub = f'UnsupportedOperationException("TODO: {method_name}")'
        if stub not in text:
            continue
        text, count = _replace_void_method(text, method_name, body_fn(text))
        changes += count
    return text, changes
