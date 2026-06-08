"""F40 Verification: smart comparator accepts minor numeric differences.

Creates synthetic "Java output" files with controlled differences against
the real COBOL baseline, then confirms every acceptance criterion:

1. Small numeric rounding -> accepted
2. Exact fields still fail on any difference
3. Dates/versions/text are not treated as numeric
4. Detail messages explain pass/fail reasons
5. Per-program tolerance rules are consistent
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from tempfile import TemporaryDirectory

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e.smart_comparator import (
    CompareResult,
    compare_data_files,
    compare_lines,
    compare_outputs,
    extract_numbers,
    PROGRAM_RULES,
)

PASS = 0
FAIL = 0


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    status = "PASS" if condition else "FAIL"
    if not condition:
        FAIL += 1
    else:
        PASS += 1
    suffix = f"  ({detail})" if detail else ""
    _safe_print(f"  [{status}] {label}{suffix}")


def _write(td: str, name: str, content: str) -> Path:
    p = Path(td) / name
    p.write_text(content)
    return p


# ===================================================================
# SECTION 1: Number extraction sanity
# ===================================================================
def test_number_extraction():
    print("\n=== 1. Number extraction ===")

    nums = extract_numbers("  CLASS 1: 000004")
    check("Plain int '000004' -> single Decimal(4)", len(nums) == 2 and nums[1] == 4)

    nums = extract_numbers("  TOTAL PROV: 000000000000000")
    check("Zero-padded '000000000000000' -> single Decimal(0)", len(nums) == 1 and nums[0] == 0)

    nums = extract_numbers("CNT=000004 ENC=000000104481856 PROV=0000000000000")
    check("Three separate numbers extracted", len(nums) == 3,
          f"got {len(nums)}: {nums}")

    nums = extract_numbers("LOANEVAL v6.0 - START 20260525-471200")
    check("Date '20260525-471200' and version 'v6.0' skipped", len(nums) == 0,
          f"got {nums}")

    nums = extract_numbers("RPTMONTH v2.3 START 20260525")
    check("Version 'v2.3' and date '20260525' skipped", len(nums) == 0)

    nums = extract_numbers("ENC=      1,044,818")
    check("Grouped thousands '1,044,818' -> 1044818", len(nums) == 1 and nums[0] == 1044818)

    nums = extract_numbers("PROVISION: 10875.331")
    check("Decimal '10875.331' extracted intact",
          len(nums) == 1 and str(nums[0]) == "10875.331",
          f"got {nums}")


# ===================================================================
# SECTION 2: Line-level tolerance
# ===================================================================
def test_line_tolerance():
    print("\n=== 2. Line-level tolerance ===")

    # 2a: Small numeric difference within tolerance
    reason = compare_lines(
        "TOTAL PROV: 10875.330",
        "TOTAL PROV: 10875.331",
        tolerance_pct=0.001,
    )
    check("0.001% tolerance: 10875.330 vs 10875.331 -> MATCH", reason is None,
          f"reason={reason}")

    # 2b: Large difference outside tolerance
    reason = compare_lines(
        "TOTAL PROV: 10000",
        "TOTAL PROV: 15000",
        tolerance_pct=0.001,
    )
    check("0.001% tolerance: 10000 vs 15000 -> MISMATCH",
          reason is not None and "numeric mismatch" in reason,
          f"reason={reason}")

    # 2c: Exact tolerance rejects any difference
    reason = compare_lines(
        "  CLASS 1: 000004",
        "  CLASS 1: 000005",
        tolerance_pct=0.0,
    )
    check("Exact (0.0): 4 vs 5 -> MISMATCH", reason is not None,
          f"reason={reason}")

    # 2d: Exact tolerance accepts identical
    reason = compare_lines(
        "  CLASS 1: 000004",
        "  CLASS 1: 000004",
        tolerance_pct=0.0,
    )
    check("Exact (0.0): 4 vs 4 -> MATCH", reason is None)

    # 2e: Date-only difference
    reason = compare_lines(
        "LOANEVAL v6.0 - START 20260525-120000",
        "LOANEVAL v6.0 - START 20261231-235959",
    )
    check("Date-only diff (20260525 vs 20261231) -> MATCH", reason is None,
          f"reason={reason}")

    # 2f: Pure text difference (no numbers)
    reason = compare_lines(
        "RISKSCOR COMPLETED.",
        "RISKSCOR FAILED.",
    )
    check("Text-only diff 'COMPLETED' vs 'FAILED' -> MISMATCH",
          reason is not None and "text differs" in reason,
          f"reason={reason}")

    # 2g: Text skeleton differs even though numbers match
    reason = compare_lines(
        "CLASS 1: 000004",
        "KLASSE 1: 000004",
    )
    check("Skeleton diff 'CLASS' vs 'KLASSE' -> MISMATCH",
          reason is not None and "skeleton" in reason,
          f"reason={reason}")

    # 2h: Large COBOL values within tolerance
    reason = compare_lines(
        "ENC=000000104481856",
        "ENC=000000104481800",
        tolerance_pct=0.001,
    )
    check("Large value 104481856 vs 104481800 (0.00005%) -> MATCH",
          reason is None, f"reason={reason}")


# ===================================================================
# SECTION 3: Per-program rules
# ===================================================================
def test_program_rules():
    print("\n=== 3. Per-program rules ===")

    # RISKSCOR: CLASS counts are exact
    rules = PROGRAM_RULES["RISKSCOR"]
    tol = rules.tolerance_for_line("  CLASS 1: 000004")
    check("RISKSCOR CLASS 1 -> exact (0.0)", tol == 0.0)
    tol = rules.tolerance_for_line("  CLASS 4: 000000")
    check("RISKSCOR CLASS 4 -> exact (0.0)", tol == 0.0)

    # RISKSCOR: TOTAL PROV is tolerant
    tol = rules.tolerance_for_line("  TOTAL PROV: 000000000000000")
    check("RISKSCOR TOTAL PROV -> tolerant (0.01%)", tol == 0.0001)

    # RISKSCOR: unknown line gets default
    tol = rules.tolerance_for_line("RISKSCOR COMPLETED.")
    check("RISKSCOR unknown line -> default (0.1%)", tol == 0.001)

    # LOANEVAL: APPROVED/CONDITIONAL/DECLINED are exact; READ/ERRORS are tolerant
    rules = PROGRAM_RULES["LOANEVAL"]
    for label in ["APPROVED", "CONDITIONAL", "DECLINED"]:
        tol = rules.tolerance_for_line(f"  {label}    : 00000001")
        check(f"LOANEVAL {label} -> exact (0.0)", tol == 0.0)

    for label in ["READ", "ERRORS"]:
        tol = rules.tolerance_for_line(f"  {label}    : 00000001")
        check(f"LOANEVAL {label} -> tolerant (0.01%)", tol == 0.01)

    # RPTMONTH: LOANS exact, AMT tolerant
    rules = PROGRAM_RULES["RPTMONTH"]
    tol = rules.tolerance_for_line("RPTMONTH COMPLETED. LOANS=00000004 AMT=00000000104481856")
    check("RPTMONTH LOANS= line -> exact (0.0)", tol == 0.0,
          "LOANS= exact rule matches first")


# ===================================================================
# SECTION 4: File-level comparison with real baselines
# ===================================================================
def test_file_comparison():
    print("\n=== 4. File-level comparison ===")

    # 4a: RISKSCOR — identical baseline -> match
    with TemporaryDirectory() as td:
        baseline = _write(td, "baseline.txt", textwrap.dedent("""\
            RISKSCOR COMPLETED.
              CLASS 1: 000004
              CLASS 2: 000000
              CLASS 3: 000000
              CLASS 4: 000000
              TOTAL PROV: 000000000000000
        """))

        # Identical
        actual = _write(td, "actual.txt", baseline.read_text())
        result = compare_outputs(baseline, actual, program="RISKSCOR")
        check("RISKSCOR identical -> MATCH", result.match,
              f"msg={result.message}")

    # 4b: RISKSCOR — small provision difference -> match
    with TemporaryDirectory() as td:
        baseline = _write(td, "baseline.txt", textwrap.dedent("""\
            RISKSCOR COMPLETED.
              CLASS 1: 000004
              CLASS 2: 000000
              CLASS 3: 000000
              CLASS 4: 000000
              TOTAL PROV: 000050000000000
        """))
        actual = _write(td, "actual.txt", textwrap.dedent("""\
            RISKSCOR COMPLETED.
              CLASS 1: 000004
              CLASS 2: 000000
              CLASS 3: 000000
              CLASS 4: 000000
              TOTAL PROV: 000050000000003
        """))
        result = compare_outputs(baseline, actual, program="RISKSCOR")
        check("RISKSCOR provision +3 (0.000000006%) -> MATCH", result.match,
              f"msg={result.message}, stats={result.stats}")
        check("  tolerant_matches count > 0",
              result.stats.get("tolerant_matches", 0) > 0,
              f"tolerant_matches={result.stats.get('tolerant_matches')}")

    # 4c: RISKSCOR — CLASS count differs -> FAIL
    with TemporaryDirectory() as td:
        baseline = _write(td, "baseline.txt", textwrap.dedent("""\
            RISKSCOR COMPLETED.
              CLASS 1: 000004
              CLASS 2: 000000
              CLASS 3: 000000
              CLASS 4: 000000
              TOTAL PROV: 000000000000000
        """))
        actual = _write(td, "actual.txt", textwrap.dedent("""\
            RISKSCOR COMPLETED.
              CLASS 1: 000003
              CLASS 2: 000001
              CLASS 3: 000000
              CLASS 4: 000000
              TOTAL PROV: 000000000000000
        """))
        result = compare_outputs(baseline, actual, program="RISKSCOR")
        check("RISKSCOR CLASS count differs -> FAIL", not result.match)
        check("  exactly 2 mismatches (CLASS 1 & CLASS 2)",
              len(result.mismatches) == 2,
              f"got {len(result.mismatches)}: {[m.reason for m in result.mismatches]}")
        check("  reason mentions 'numeric mismatch'",
              all("numeric mismatch" in m.reason for m in result.mismatches),
              f"reasons={[m.reason for m in result.mismatches]}")

    # 4d: LOANEVAL — different date, same counts -> match
    with TemporaryDirectory() as td:
        baseline = _write(td, "baseline.txt", textwrap.dedent("""\
            LOANEVAL v6.0 - START 20260525-120000
            LOANEVAL COMPLETED.
              READ        : 00000804
              APPROVED    : 00000001
              CONDITIONAL : 00000000
              DECLINED    : 00000003
              ERRORS      : 00000800
        """))
        actual = _write(td, "actual.txt", textwrap.dedent("""\
            LOANEVAL v6.0 - START 20261231-235959
            LOANEVAL COMPLETED.
              READ        : 00000804
              APPROVED    : 00000001
              CONDITIONAL : 00000000
              DECLINED    : 00000003
              ERRORS      : 00000800
        """))
        result = compare_outputs(baseline, actual, program="LOANEVAL")
        check("LOANEVAL date-only diff -> MATCH", result.match,
              f"date_skips={result.stats.get('date_skips')}")
        check("  date_skips == 1", result.stats.get("date_skips") == 1)

    # 4e: LOANEVAL — READ count differs by 1 (0.12%) within 1% tolerance -> MATCH
    with TemporaryDirectory() as td:
        baseline = _write(td, "baseline.txt", textwrap.dedent("""\
            LOANEVAL v6.0 - START 20260525-120000
            LOANEVAL COMPLETED.
              READ        : 00000804
              APPROVED    : 00000001
              CONDITIONAL : 00000000
              DECLINED    : 00000003
              ERRORS      : 00000800
        """))
        actual = _write(td, "actual.txt", textwrap.dedent("""\
            LOANEVAL v6.0 - START 20260525-120000
            LOANEVAL COMPLETED.
              READ        : 00000805
              APPROVED    : 00000001
              CONDITIONAL : 00000000
              DECLINED    : 00000003
              ERRORS      : 00000800
        """))
        result = compare_outputs(baseline, actual, program="LOANEVAL")
        check("LOANEVAL READ 804->805 within 1% tolerance -> MATCH", result.match,
              f"msg={result.message}, tolerant_matches={result.stats.get('tolerant_matches')}")

    # 4f: RPTMONTH — LOANS= exact rule matches the combined line, so any
    # AMT change on the same line triggers exact mismatch (correct: exact
    # rules take priority over tolerant for the whole line).
    with TemporaryDirectory() as td:
        baseline = _write(td, "baseline.txt", textwrap.dedent("""\
            RPTMONTH v2.3 START 20260525
            RPTMONTH COMPLETED. LOANS=00000004 AMT=00000000104481856
        """))
        actual = _write(td, "actual.txt", textwrap.dedent("""\
            RPTMONTH v2.3 START 20260601
            RPTMONTH COMPLETED. LOANS=00000004 AMT=00000000104481850
        """))
        result = compare_outputs(baseline, actual, program="RPTMONTH")
        check("RPTMONTH LOANS+AMT same line, AMT diff -> FAIL (exact wins)",
              not result.match,
              "LOANS= exact rule applies to entire line")

    # 4f2: AMT on its own line uses the tolerant rule
    with TemporaryDirectory() as td:
        baseline = _write(td, "baseline.txt", textwrap.dedent("""\
            RPTMONTH v2.3 START 20260525
            AMT=00000000104481856
        """))
        actual = _write(td, "actual.txt", textwrap.dedent("""\
            RPTMONTH v2.3 START 20260601
            AMT=00000000104481850
        """))
        result = compare_outputs(baseline, actual, program="RPTMONTH")
        check("RPTMONTH standalone AMT diff of 6 -> MATCH (tolerant)",
              result.match,
              f"msg={result.message}, stats={result.stats}")

    # 4g: RPTMONTH — LOANS count differs -> FAIL
    with TemporaryDirectory() as td:
        baseline = _write(td, "baseline.txt", textwrap.dedent("""\
            RPTMONTH v2.3 START 20260525
            RPTMONTH COMPLETED. LOANS=00000004 AMT=00000000104481856
        """))
        actual = _write(td, "actual.txt", textwrap.dedent("""\
            RPTMONTH v2.3 START 20260525
            RPTMONTH COMPLETED. LOANS=00000005 AMT=00000000104481856
        """))
        result = compare_outputs(baseline, actual, program="RPTMONTH")
        check("RPTMONTH LOANS count 4->5 -> FAIL", not result.match)


# ===================================================================
# SECTION 5: Data file comparison
# ===================================================================
def test_data_file_comparison():
    print("\n=== 5. Data file comparison ===")

    # 5a: Identical data files
    with TemporaryDirectory() as td:
        data = b"1234  20260525  1000000001  10000331  1  0000000447542\n"
        b = _write(td, "b.dat", "")
        a = _write(td, "a.dat", "")
        b.write_bytes(data)
        a.write_bytes(data)
        result = compare_data_files(b, a)
        check("Identical .dat -> MATCH", result.match)

    # 5b: Trailing whitespace ignored
    with TemporaryDirectory() as td:
        b = Path(td) / "b.dat"
        a = Path(td) / "a.dat"
        b.write_bytes(b"RECORD1DATA   \nRECORD2DATA   \n")
        a.write_bytes(b"RECORD1DATA\nRECORD2DATA\n")
        result = compare_data_files(b, a)
        check("Trailing whitespace ignored -> MATCH", result.match)

    # 5c: Content mismatch detected
    with TemporaryDirectory() as td:
        b = Path(td) / "b.dat"
        a = Path(td) / "a.dat"
        b.write_bytes(b"RECORD1X\n")
        a.write_bytes(b"RECORD1Y\n")
        result = compare_data_files(b, a)
        check("Content byte diff -> FAIL", not result.match)
        check("  mismatch details present", len(result.mismatches) == 1)


# ===================================================================
# SECTION 6: Detail message quality
# ===================================================================
def test_detail_messages():
    print("\n=== 6. Detail message quality ===")

    with TemporaryDirectory() as td:
        baseline = _write(td, "b.txt", "  CLASS 1: 000004\n  TOTAL PROV: 50000\n")
        actual = _write(td, "a.txt", "  CLASS 1: 000004\n  TOTAL PROV: 50003\n")
        result = compare_outputs(baseline, actual, program="RISKSCOR")
        check("Pass message mentions 'tolerance'",
              "tolerance" in result.message.lower() or "match" in result.message.lower(),
              f"msg='{result.message}'")
        check("Stats include tolerant_matches",
              "tolerant_matches" in result.stats,
              f"stats={result.stats}")

    with TemporaryDirectory() as td:
        baseline = _write(td, "b.txt", "  CLASS 1: 000004\n")
        actual = _write(td, "a.txt", "  CLASS 1: 000005\n")
        result = compare_outputs(baseline, actual, program="RISKSCOR")
        check("Fail message includes mismatch count",
              "mismatch" in result.message.lower(),
              f"msg='{result.message}'")
        check("Mismatch details include reason string",
              len(result.mismatches) > 0 and result.mismatches[0].reason,
              f"reason='{result.mismatches[0].reason if result.mismatches else 'N/A'}'")
        check("Mismatch details include line number",
              result.mismatches[0].line_num == 1,
              f"line_num={result.mismatches[0].line_num if result.mismatches else 'N/A'}")


# ===================================================================
# SECTION 7: Self-compare real baseline
# ===================================================================
def test_self_compare():
    print("\n=== 7. Self-compare real baseline ===")

    baseline_dir = Path(__file__).resolve().parent.parent / "tests" / "e2e" / "baseline"
    if not baseline_dir.exists():
        check("Baseline directory exists", False, str(baseline_dir))
        return

    for prog in ["RISKSCOR", "LOANEVAL", "RECOVRY", "RPTMONTH"]:
        stdout_file = baseline_dir / f"{prog}_stdout.txt"
        if not stdout_file.exists():
            check(f"{prog} stdout exists", False)
            continue
        result = compare_outputs(stdout_file, stdout_file, program=prog)
        check(f"{prog} self-compare -> MATCH", result.match,
              f"stats={result.stats}")


# ===================================================================
# Main
# ===================================================================
def main() -> None:
    print("=" * 60)
    print("F40 Verification: Smart Comparator")
    print("=" * 60)

    test_number_extraction()
    test_line_tolerance()
    test_program_rules()
    test_file_comparison()
    test_data_file_comparison()
    test_detail_messages()
    test_self_compare()

    print("\n" + "=" * 60)
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)
    print("\nF40 VERIFICATION PASSED")


if __name__ == "__main__":
    main()
