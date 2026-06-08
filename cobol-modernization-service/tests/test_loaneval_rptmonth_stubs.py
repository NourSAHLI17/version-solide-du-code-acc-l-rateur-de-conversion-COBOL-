"""Tests for LOANEVAL / RPTMONTH UnsupportedOperationException stub repairs."""

from app.services.loaneval_post_repair import repair_loaneval_post_generation
from app.services.rptmonth_post_repair import repair_rptmonth_post_generation


def test_loaneval_replaces_score_income_and_history_stubs():
    src = """
public class Loaneval {
    private int scrIncomeScore = 0;
    private int scrHistoryScore = 0;
    private String scrReason1 = "";
    private String scrReason2 = "";
    private BigDecimal wsNormalizedIncome = BigDecimal.ZERO;
    private BigDecimal loanMonthlyPmt = BigDecimal.ONE;
    private BigDecimal wsIncomeToPmt = BigDecimal.ZERO;
    private int loanDaysPastDue = 0;
    private int loanMissedPmts = 0;

    private void scoreIncome() {
        throw new UnsupportedOperationException("TODO: scoreIncome");
    }

    private void scoreHistory() {
        throw new UnsupportedOperationException("TODO: scoreHistory");
    }
}
"""
    out, notes = repair_loaneval_post_generation(src, program_name="LOANEVAL")
    assert "UnsupportedOperationException" not in out
    assert "scrIncomeScore = 1000" in out or "scrIncomeScore = 0" in out
    assert "scrHistoryScore = 1000" in out
    assert any("UnsupportedOperationException stub" in n for n in notes)


def test_rptmonth_replaces_aggregate_by_segment_stub():
    src = """
public class Rptmonth {
    private String custSegment = "MM";
    private String loanStatus = "AC";
    private String wsseCode = "";
    private int wsseCount = 0;
    private java.math.BigDecimal wsseOutstanding = java.math.BigDecimal.ZERO;
    private int wsseApproved = 0;
    private int wsseDeclined = 0;
    private java.math.BigDecimal loanOutstanding = new java.math.BigDecimal("100");

    private void aggregateBySegment() {
        throw new UnsupportedOperationException("TODO: aggregateBySegment");
    }
}
"""
    out, notes = repair_rptmonth_post_generation(src, program_name="RPTMONTH")
    assert "UnsupportedOperationException" not in out
    assert "wsseCount = wsseCount + 1" in out
    assert notes


def test_rptmonth_fixes_wsdisp_pct_and_write_section5():
    src = """
import java.math.BigDecimal;
import java.math.RoundingMode;

public class Rptmonth {
    private String wsDispPct = "";
    private String monthLine = "";
    private int wsLineCount = 0;
    private BigDecimal wsTotalOutstanding = new BigDecimal("1000");
    private BigDecimal wsTotalProvision = new BigDecimal("50");

    private void checkPage() {}

    private void writeSection5() {
        throw new UnsupportedOperationException("TODO: writeSection5");
    }

    void m() {
        wsDispPct = wsTotalProvision.divide(wsTotalOutstanding, 10, RoundingMode.HALF_UP).multiply(new BigDecimal("100"));
    }
}
"""
    out, notes = repair_rptmonth_post_generation(src, program_name="RPTMONTH")
    assert "UnsupportedOperationException" not in out
    assert "wsDispPct = (wsTotalProvision.divide" in out
    assert "SECTION 5 - INDICATEURS DE RISQUE" in out
    assert any("writeSection5" in n for n in notes)
    assert any("wsDispPct" in n for n in notes)
