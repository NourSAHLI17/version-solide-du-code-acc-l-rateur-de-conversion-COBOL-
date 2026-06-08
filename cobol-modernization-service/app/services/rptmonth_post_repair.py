"""RPTMONTH-specific deterministic fixes (aggregateBySegment stub, etc.)."""

from __future__ import annotations

import re
from typing import List, Tuple


def repair_rptmonth_post_generation(
    java_source: str,
    *,
    program_name: str = "",
) -> Tuple[str, List[str]]:
    """Apply post-generation repairs for RPTMONTH."""
    prog = str(program_name or "").upper()
    if prog and prog != "RPTMONTH":
        return java_source, []

    notes: List[str] = []
    text = java_source or ""

    text, n1 = _fix_aggregate_by_segment_stub(text)
    if n1:
        notes.append("rptmonth:replaced aggregateBySegment UnsupportedOperationException stub")

    text, n2 = _fix_ws_disp_pct_assignments(text)
    if n2:
        notes.append(f"rptmonth:fixed {n2} wsDispPct BigDecimal-to-String assignment(s)")

    text, n3 = _fix_write_section5_stub(text)
    if n3:
        notes.append("rptmonth:replaced writeSection5 UnsupportedOperationException stub")

    text, n4 = _fix_write_section_stubs(text)
    if n4:
        notes.append("rptmonth:replaced writeSection1/writeSection3 UnsupportedOperationException stub(s)")

    return text, notes


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


def _aggregate_by_segment_body(java_source: str) -> str:
    if re.search(r"String\s*\[\s*\]\s*wsseCode\b", java_source):
        loan_active = (
            '"AC".equals(loanStatus)'
            if "loanStatus" in java_source
            else "loanActive"
        )
        cust_seg = (
            "currentCustomerRecord.custSegment"
            if "currentCustomerRecord" in java_source
            else "custSegment"
        )
        return f"""    private void aggregateBySegment() {{
        for (int i = 0; i < wsseCode.length; i++) {{
            if (wsseCode[i].equals({cust_seg} != null ? {cust_seg}.trim() : "")) {{
                wsseCount[i]++;
                wsseOutstanding[i] = wsseOutstanding[i].add(
                        loanOutstanding != null ? loanOutstanding : BigDecimal.ZERO);
                if ({loan_active}) {{
                    wsseApproved[i]++;
                }} else {{
                    wsseDeclined[i]++;
                }}
                return;
            }}
        }}
    }}"""
    return """    private void aggregateBySegment() {
        final String[] segCodes = {"MM", "MB", "PR", "PB"};
        String segment = custSegment != null ? custSegment.trim() : "";
        for (String code : segCodes) {
            if (code.equals(segment)) {
                wsseCode = code;
                wsseCount = wsseCount + 1;
                if (loanOutstanding != null) {
                    wsseOutstanding = wsseOutstanding.add(loanOutstanding);
                }
                if ("AC".equals(loanStatus)) {
                    wsseApproved = wsseApproved + 1;
                } else {
                    wsseDeclined = wsseDeclined + 1;
                }
                return;
            }
        }
    }"""


def _fix_aggregate_by_segment_stub(java_source: str) -> Tuple[str, int]:
    if 'UnsupportedOperationException("TODO: aggregateBySegment")' not in java_source:
        return java_source, 0
    body = _aggregate_by_segment_body(java_source)
    return _replace_void_method(java_source, "aggregateBySegment", body)


_WSDISP_PCT_ASSIGN_RE = re.compile(
    r"^(\s*)wsDispPct\s*=\s*(.+);\s*$",
    re.MULTILINE,
)


def _fix_ws_disp_pct_assignments(java_source: str) -> Tuple[str, int]:
    """Ensure wsDispPct (String) receives plain-string values from BigDecimal expressions."""
    changes = 0

    def _rewrite(match: re.Match[str]) -> str:
        nonlocal changes
        indent, rhs = match.group(1), match.group(2).strip()
        if ".toPlainString()" in rhs or rhs.endswith('""') or rhs.endswith("''"):
            return match.group(0)
        if not any(
            marker in rhs
            for marker in (".divide(", ".multiply(", ".add(", ".subtract(", "new BigDecimal(")
        ):
            return match.group(0)
        changes += 1
        return f"{indent}wsDispPct = ({rhs}).toPlainString();"

    return _WSDISP_PCT_ASSIGN_RE.sub(_rewrite, java_source), changes


def _write_section5_body(java_source: str) -> str:
    has_array = bool(re.search(r"wsclOutstanding\s*\[", java_source))
    if has_array:
        npl_block = """            BigDecimal nplNumerator = wsclOutstanding[1]
                    .add(wsclOutstanding[2])
                    .add(wsclOutstanding[3]);
            wsDispPct = nplNumerator
                    .divide(wsTotalOutstanding, 2, RoundingMode.HALF_UP)
                    .multiply(new BigDecimal("100"))
                    .toPlainString();
            monthLine = "  RATIO NPL (CL 2-3-4) : " + wsDispPct + "%";
            wsDispPct = wsclOutstanding[3]
                    .divide(wsTotalOutstanding, 2, RoundingMode.HALF_UP)
                    .multiply(new BigDecimal("100"))
                    .toPlainString();
            monthLine = "  RATIO PERTES (CL 4)  : " + wsDispPct + "%";
"""
    else:
        npl_block = ""

    return f"""    private void writeSection5() {{
        checkPage();
        monthLine = "";
        monthLine = "SECTION 5 - INDICATEURS DE RISQUE";
        monthLine = "";
        wsLineCount = wsLineCount + 3;
        if (wsTotalOutstanding != null && wsTotalOutstanding.compareTo(BigDecimal.ZERO) > 0) {{
{npl_block}            wsDispPct = wsTotalProvision
                    .divide(wsTotalOutstanding, 2, RoundingMode.HALF_UP)
                    .multiply(new BigDecimal("100"))
                    .toPlainString();
            monthLine = "  TAUX COUVERTURE PROV : " + wsDispPct + "%";
            wsLineCount = wsLineCount + {3 if has_array else 1};
        }}
    }}"""


def _fix_write_section5_stub(java_source: str) -> Tuple[str, int]:
    if 'UnsupportedOperationException("TODO: writeSection5")' not in java_source:
        return java_source, 0
    body = _write_section5_body(java_source)
    return _replace_void_method(java_source, "writeSection5", body)


def _fix_write_section_stubs(java_source: str) -> Tuple[str, int]:
    """Replace writeSection1/writeSection3 TODO stubs with minimal println output."""
    changes = 0
    text = java_source
    if 'throw new UnsupportedOperationException("TODO: writeSection1");' in text:
        text = text.replace(
            'throw new UnsupportedOperationException("TODO: writeSection1");',
            """System.out.println("--- SECTION 1: PORTFOLIO BY CLASS ---");
        for (int clIdx = 1; clIdx <= 4; clIdx++) {
            System.out.printf("  CLASS %d: COUNT=%06d%n",
                clIdx, wsClCount != null && wsClCount.length >= clIdx ?
                wsClCount[clIdx-1] : 0);
        }""",
        )
        changes += 1
    if 'throw new UnsupportedOperationException("TODO: writeSection3");' in text:
        text = text.replace(
            'throw new UnsupportedOperationException("TODO: writeSection3");',
            """System.out.println("--- SECTION 3: RISK RATIOS ---");
        if (wsTotalOutstanding != null &&
            wsTotalOutstanding.compareTo(BigDecimal.ZERO) > 0) {
            System.out.printf("  NPL RATIO: %s%%%n",
                wsDispPct != null ? wsDispPct.toPlainString() : "0");
        }""",
        )
        changes += 1
    return text, changes
