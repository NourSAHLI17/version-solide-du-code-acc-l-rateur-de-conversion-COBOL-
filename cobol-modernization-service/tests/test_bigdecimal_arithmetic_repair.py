"""Tests for BigDecimal arithmetic repair."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.bigdecimal_arithmetic_repair import (
    fix_bigdecimal_to_string_assignments,
    fix_dangling_chains,
    fix_string_char_comparisons,
    repair_bigdecimal_arithmetic,
)
from app.services.loaneval_post_repair import repair_loaneval_post_generation


class BigDecimalArithmeticRepairTests(unittest.TestCase):
    def test_add_and_compare(self):
        src = """import java.math.BigDecimal;
public class X {
    private BigDecimal wsTotalCollatValue = BigDecimal.ZERO;
    private BigDecimal wsTotalGuarValue = BigDecimal.ZERO;
    void m() {
        wsTotalCollatValue = wsTotalCollatValue + wsTotalGuarValue;
        if (wsTotalCollatValue == 0) { return; }
    }
}
"""
        fixed, notes = repair_bigdecimal_arithmetic(src)
        self.assertIn(".add(wsTotalGuarValue)", fixed)
        self.assertIn("compareTo(BigDecimal.ZERO)", fixed)
        self.assertTrue(notes)

    def test_divide_multiply(self):
        src = """import java.math.BigDecimal;
import java.math.RoundingMode;
public class X {
    private BigDecimal loanOutstanding = BigDecimal.ZERO;
    private BigDecimal wsTotalCollatValue = BigDecimal.ZERO;
    private BigDecimal scrLtvRatio = BigDecimal.ZERO;
    void m() {
        scrLtvRatio = loanOutstanding / wsTotalCollatValue * 100;
        if (scrLtvRatio <= 60) { }
    }
}
"""
        fixed, _notes = repair_bigdecimal_arithmetic(src)
        self.assertIn(".divide(wsTotalCollatValue", fixed)
        self.assertIn("RoundingMode.HALF_UP", fixed)
        self.assertIn(".multiply(", fixed)

    def test_commented_assignment_chain(self):
        src = """import java.math.BigDecimal;
import java.math.RoundingMode;
public class X {
    private BigDecimal scrRawScore = BigDecimal.ZERO;
    void m() {
        // scrRawScore = scrWeightIncome.multiply(new BigDecimal(scrIncomeScore))
            .add(scrWeightHistory.multiply(new BigDecimal(scrHistoryScore)));
        // .divide(new BigDecimal("100"), 0, RoundingMode.HALF_UP);
    }
}
"""
        fixed, notes = repair_bigdecimal_arithmetic(src)
        self.assertIn("scrRawScore = scrWeightIncome", fixed)
        self.assertNotIn("// scrRawScore =", fixed)
        self.assertIn(".divide(new BigDecimal(\"100\")", fixed)
        self.assertTrue(any("chain" in n for n in notes))

    def test_fix_dangling_chains_orphan_add(self):
        src = """void m() {
    scoreTenure();
    .add(scrWeightTenure.multiply(BigDecimal.valueOf(scrTenureScore)));
    scrFinalScore = 0;
}
"""
        fixed, n = fix_dangling_chains(src)
        self.assertIn("// TODO: dangling chain", fixed)
        self.assertIn("// .add(scrWeightTenure", fixed)
        self.assertNotIn("\n    .add(scrWeightTenure", fixed)
        self.assertEqual(n, 1)

    def test_fix_dangling_chains_preserves_valid_multiline(self):
        src = """void m() {
    scrRawScore =
        scrWeightIncome.multiply(BigDecimal.valueOf(scrIncomeScore))
            .add(scrWeightHistory.multiply(BigDecimal.valueOf(scrHistoryScore)));
}
"""
        fixed, n = fix_dangling_chains(src)
        self.assertEqual(n, 0)
        self.assertIn(".add(scrWeightHistory", fixed)

    def test_fix_dangling_chains_preserves_incomplete_assignment_multiline(self):
        src = """void m() {
    scrLtvRatio = loanOutstanding
        .divide(wsTotalCollatValue, 10, RoundingMode.HALF_UP)
        .multiply(new BigDecimal("100"))
        .setScale(0, RoundingMode.HALF_UP);
}
"""
        fixed, n = fix_dangling_chains(src)
        self.assertEqual(n, 0)
        self.assertIn("scrLtvRatio = loanOutstanding", fixed)
        self.assertIn(".divide(wsTotalCollatValue", fixed)

    def test_fix_dangling_string_concat(self):
        src = """void m() {
    // escaRptLine = String.valueOf(x)
        + String.valueOf(wsNextActionCode);
}
"""
        fixed, n = fix_dangling_chains(src)
        self.assertGreater(n, 0)
        self.assertIn("// TODO: dangling string concat", fixed)
        self.assertNotIn("\n        + String.valueOf(wsNextActionCode)", fixed)
        from app.services.bigdecimal_arithmetic_repair import _comment_unclosed_paren_fragments

        src = """if (x) {
    // wsNormalizedIncome = new BigDecimal(wsIncomeWhole).add(
                new BigDecimal(wsIncomeCents).divide(new BigDecimal(100), 10, RoundingMode.HALF_UP));
}
"""
        fixed, n = _comment_unclosed_paren_fragments(src)
        self.assertGreater(n, 0)
        self.assertIn("// TODO: orphan expression fragment", fixed)
        self.assertNotIn("\n                new BigDecimal(wsIncomeCents)", fixed)

    def test_incomplete_chain_gets_semicolon(self):
        src = """void m() {
    scrRawScore =
        scrWeightIncome.multiply(BigDecimal.valueOf(1))
            .add(scrWeightHistory.multiply(BigDecimal.valueOf(2)))
    // .divide(BigDecimal.valueOf(100), 0, RoundingMode.HALF_UP);
    scrFinalScore = 0;
}
"""
        fixed, notes = repair_bigdecimal_arithmetic(src)
        self.assertIn(".add(scrWeightHistory", fixed)
        self.assertIn(".add(scrWeightHistory.multiply(BigDecimal.valueOf(2)));", fixed)
        self.assertTrue(any("incomplete" in n or "terminated" in n for n in notes))


class LoanevalPostRepairTests(unittest.TestCase):
    def test_reject_line_and_sort_calls(self):
        src = """public class LoanevalApplication {
    private String rejectLine = "";
    private void rankComponents() {
        loadSort();
        rankOutput();
        sortComponents();
    }
    private void sortComponents() {
        List<SortComponentRec> sortBuffer = new ArrayList<>();
        loadSort(sortBuffer);
    }
    public static class SortComponentRec {
        private String sortComponentScore = "";
    }
    public static class WsRejectDetail {
        private String rejLoanId = "";
    }
    private void writeReject() {
        rejectLine = new WsRejectDetail();
        rejectLine.rejLoanId = rejLoanId;
    }
}
"""
        fixed, notes = repair_loaneval_post_generation(src, program_name="LOANEVAL")
        self.assertNotIn("loadSort();", fixed)
        self.assertIn("sortComponents();", fixed)
        self.assertIn("WsRejectDetail rejectLine", fixed)
        self.assertIn("private int sortComponentScore", fixed)
        self.assertTrue(notes)

    def test_normalize_income_swallowed_else_repaired(self) -> None:
        broken = """
public class LoanevalApplication {
    private int wsIncomeWhole;
    private int wsIncomeCents;
    private BigDecimal wsNormalizedIncome = BigDecimal.ZERO;
    private void normalizeIncome() {
        if (wsIncomeWhole == 0 && wsIncomeCents == 0) {
            // TODO: original statement referenced undeclared: ZERO
            // Original: wsNormalizedIncome = BigDecimal.ZERO; } else {
        // wsNormalizedIncome = BigDecimal.valueOf(wsIncomeWhole).add(
                BigDecimal.valueOf(wsIncomeCents).divide(BigDecimal.valueOf(100))
            );
        }
    }
    private void other() {}
}
"""
        fixed, notes = repair_loaneval_post_generation(broken, program_name="LOANEVAL")
        self.assertTrue(
            any("normalizeIncome if/else" in n for n in notes),
            notes,
        )
        self.assertIn("wsNormalizedIncome = BigDecimal.ZERO;", fixed)
        self.assertNotIn("BigDecimal.ZERO; } else {", fixed)
        self.assertIn("setScale(2, RoundingMode.DOWN)", fixed)

    def test_bigdecimal_to_string_assignment(self):
        src = """public class T {
    private String wsDispAmount = "";
    private BigDecimal wstopOutstanding = BigDecimal.ZERO;
    void m() {
        wsDispAmount = wstopOutstanding;
    }
}
"""
        fixed, n = fix_bigdecimal_to_string_assignments(src)
        self.assertEqual(n, 1)
        self.assertIn("wsDispAmount = wstopOutstanding.toPlainString();", fixed)

    def test_bigdecimal_to_string_complex_expression(self):
        src = """public class T {
    private String wsDispPct = "";
    private BigDecimal wsTotalProvision = BigDecimal.ZERO;
    private BigDecimal wsTotalOutstanding = BigDecimal.ONE;
    void m() {
        wsDispPct = wsTotalProvision.divide(wsTotalOutstanding, 10, RoundingMode.HALF_UP).multiply(new BigDecimal("100"));
    }
}
"""
        fixed, n = fix_bigdecimal_to_string_assignments(src)
        self.assertEqual(n, 1)
        self.assertIn("wsDispPct = (wsTotalProvision.divide", fixed)
        self.assertIn(".toPlainString();", fixed)

    def test_bigdecimal_to_string_skips_bigdecimal_lhs(self):
        src = """public class T {
    private BigDecimal wsCl2Amount = BigDecimal.ZERO;
    private BigDecimal loanOutstanding = BigDecimal.ZERO;
    void m() {
        wsCl2Amount = loanOutstanding;
    }
}
"""
        fixed, n = fix_bigdecimal_to_string_assignments(src)
        self.assertEqual(n, 0)
        self.assertIn("wsCl2Amount = loanOutstanding;", fixed)
        self.assertNotIn("toPlainString", fixed)


    def test_fix_dangling_java_time_plus(self):
        src = """void m() {
    // wsTodayDate = java.time.LocalDate.now().getYear() * 10000
    // + java.time.LocalDate.now().getMonthValue() * 100
        + java.time.LocalDate.now().getDayOfMonth();
}
"""
        fixed, n = fix_dangling_chains(src)
        self.assertGreater(n, 0)
        self.assertIn("// TODO: dangling expression", fixed)
        self.assertNotIn("\n        + java.time", fixed)

    def test_fix_string_char_comparisons(self):
        src = """void m() {
    if (wsEndLoanFile == 'Y') { return; }
    while (wsEndLoanFile != 'Y') { readNext(); }
}
"""
        fixed, n = fix_string_char_comparisons(src)
        self.assertEqual(n, 2)
        self.assertIn('"Y".equals(wsEndLoanFile)', fixed)
        self.assertIn('!"Y".equals(wsEndLoanFile)', fixed)
        self.assertNotIn("== 'Y'", fixed)
        self.assertNotIn("!= 'Y'", fixed)


if __name__ == "__main__":
    unittest.main()
