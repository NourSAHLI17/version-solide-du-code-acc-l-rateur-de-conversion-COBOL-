"""Smart baseline comparator with numeric tolerance and date skipping.

Compares COBOL baseline output to Java conversion output, allowing:
- Numeric rounding tolerance (configurable per-field)
- Date/timestamp skipping (YYYYMMDD, YYYYMMDD-HHMMSS)
- Per-program rules (exact counts vs tolerant amounts)
- Data file comparison (byte-exact records, ignore trailing whitespace)

Usage as CLI:
    python tests/e2e/smart_comparator.py stdout BASELINE ACTUAL [--program RISKSCOR]
    python tests/e2e/smart_comparator.py datfile BASELINE ACTUAL
    python tests/e2e/smart_comparator.py full BASELINE_DIR ACTUAL_DIR
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Number extraction
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(
    r"""
    (?<![A-Za-z_\d])          # not preceded by letter/underscore/digit
    -?                        # optional sign
    (?:
        \d{1,3}(?:,\d{3})+   # grouped thousands: 1,044,818 (must have >=1 comma group)
        |
        \d+                   # plain integer/zero-padded: 000004
    )
    (?:\.\d+)?                # optional decimal: .331
    %?                        # optional percent sign
    (?![A-Za-z_\d])           # not followed by letter/underscore/digit
    """,
    re.VERBOSE,
)

# Dates embedded in output: 20260525, 20260525-471200
_DATE_RE = re.compile(r"\b20\d{6}(?:-\d{6})?\b")

# Version strings like "v6.0", "v2.3", "v2.5" — these are labels, not values.
_VERSION_RE = re.compile(r"\bv\d+\.\d+\b", re.IGNORECASE)


def extract_numbers(line: str) -> List[Decimal]:
    """Extract all numeric values from a line, ignoring dates and versions."""
    cleaned = _DATE_RE.sub("__DATE__", line)
    cleaned = _VERSION_RE.sub("__VER__", cleaned)
    results: List[Decimal] = []
    for m in _NUM_RE.finditer(cleaned):
        raw = m.group(0).rstrip("%").replace(",", "")
        try:
            results.append(Decimal(raw))
        except InvalidOperation:
            continue
    return results


def replace_numbers_with_placeholder(line: str) -> str:
    """Replace all numbers with a placeholder, normalizing the text skeleton."""
    cleaned = _DATE_RE.sub("__DATE__", line)
    cleaned = _VERSION_RE.sub("__VER__", cleaned)
    return _NUM_RE.sub("__NUM__", cleaned).strip()


def normalize_for_skeleton(line: str) -> str:
    """Strip dates, versions, numbers, and whitespace for structural comparison."""
    return replace_numbers_with_placeholder(line)


def normalize_stdout_line(line: str) -> str:
    """Normalize cosmetic differences between COBOL and Java stdout."""
    stripped = re.sub(r"\s+", " ", (line or "").strip())
    return _VERSION_RE.sub(lambda m: m.group(0).upper(), stripped)


_LOANS_SUMMARY_RE = re.compile(r"LOANS=(\d+)", re.IGNORECASE)


def _loans_summary_line_match(cobol_line: str, java_line: str) -> bool:
    """Match RPTMONTH COMPLETED lines on LOANS= count, ignoring trailing AMT= on COBOL."""
    mc = _LOANS_SUMMARY_RE.search(cobol_line)
    mj = _LOANS_SUMMARY_RE.search(java_line)
    if mc and mj:
        return mc.group(1) == mj.group(1)
    return False


_CLASS_LOANS_RE = re.compile(r"CLASS\s+(\d+)\s+LOANS:\s*(\d+)", re.IGNORECASE)


def _class_loans_line_match(cobol_line: str, java_line: str) -> bool:
    """Match CLASS N LOANS count lines, ignoring trailing AMOUNT suffix on COBOL."""
    mc = _CLASS_LOANS_RE.search(cobol_line)
    mj = _CLASS_LOANS_RE.search(java_line)
    if mc and mj:
        return mc.group(1) == mj.group(1) and mc.group(2) == mj.group(2)
    return False


def _line_matches_ignore_field(line: str, field: str) -> bool:
    """Case-insensitive substring match for configured ignore fields."""
    needle = str(field or "").strip()
    if not needle:
        return False
    hay = line or ""
    return needle.casefold() in hay.casefold()


def compare_stdout_lines(cobol_line: str, java_line: str) -> bool:
    """Return True when two stdout lines match after cosmetic normalization."""
    if _class_loans_line_match(cobol_line, java_line):
        return True
    if _loans_summary_line_match(cobol_line, java_line):
        return True
    return normalize_stdout_line(cobol_line) == normalize_stdout_line(java_line)


def _normalize_whitespace_enabled(config: Dict[str, Any]) -> bool:
    """True when diff config requests leading/trailing whitespace normalization."""
    if config.get("normalize_whitespace"):
        return True
    tol = stdout_tolerance_config(config)
    return bool(tol.get("normalize_whitespace"))


# ---------------------------------------------------------------------------
# Per-program comparison rules
# ---------------------------------------------------------------------------

@dataclass
class FieldRule:
    """How to compare a specific labeled field."""
    label_pattern: str
    tolerance_pct: float = 0.0  # 0.0 = exact match
    _re: re.Pattern = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._re = re.compile(self.label_pattern, re.IGNORECASE)

    def matches(self, line: str) -> bool:
        return bool(self._re.search(line))


@dataclass
class ProgramRules:
    """Comparison rules for a specific COBOL program's output."""
    default_tolerance_pct: float = 0.001  # 0.1%
    exact_fields: List[FieldRule] = field(default_factory=list)
    tolerant_fields: List[FieldRule] = field(default_factory=list)
    ignore_patterns: List[re.Pattern] = field(default_factory=list)

    def tolerance_for_line(self, line: str) -> float:
        for fr in self.exact_fields:
            if fr.matches(line):
                return 0.0
        for fr in self.tolerant_fields:
            if fr.matches(line):
                return fr.tolerance_pct
        return self.default_tolerance_pct


PROGRAM_RULES: Dict[str, ProgramRules] = {
    "RISKSCOR": ProgramRules(
        default_tolerance_pct=0.001,
        exact_fields=[
            FieldRule(r"CLASS\s+[1-4]\s*:"),
        ],
        tolerant_fields=[
            FieldRule(r"TOTAL\s+PROV", tolerance_pct=0.0001),  # 0.01%
        ],
    ),
    "LOANEVAL": ProgramRules(
        default_tolerance_pct=0.001,
        exact_fields=[
            FieldRule(r"READ\s*:"),
            FieldRule(r"APPROVED\s*:"),
            FieldRule(r"CONDITIONAL\s*:"),
            FieldRule(r"DECLINED\s*:"),
        ],
        tolerant_fields=[
            FieldRule(r"ERRORS\s*:", tolerance_pct=0.01),
        ],
    ),
    "RECOVRY": ProgramRules(
        default_tolerance_pct=0.001,
        exact_fields=[
            FieldRule(r"CLASS\s+\d\s+LOANS\s*:"),
            FieldRule(r"SMS\s*:"),
            FieldRule(r"EMAIL\s*:"),
            FieldRule(r"PHONE\s*:"),
            FieldRule(r"DUL\s*:"),
            FieldRule(r"LEG\s*:"),
            FieldRule(r"GTR\s*:"),
            FieldRule(r"RST\s*:"),
            FieldRule(r"CRT\s*:"),
            FieldRule(r"CSZ\s*:"),
            FieldRule(r"WOF\s*:"),
        ],
        tolerant_fields=[
            FieldRule(r"AMOUNT\s*:", tolerance_pct=0.0001),
        ],
    ),
    "RPTMONTH": ProgramRules(
        default_tolerance_pct=0.001,
        exact_fields=[
            FieldRule(r"LOANS\s*="),
        ],
        tolerant_fields=[
            FieldRule(r"AMT\s*=", tolerance_pct=0.0001),
        ],
    ),
}

DEFAULT_RULES = ProgramRules(default_tolerance_pct=0.001)

BASELINE_DIR = Path(__file__).resolve().parent / "baseline"


def load_diff_config(program: str, baseline_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Load per-program F64 diff config; empty dict when missing."""
    path = (baseline_dir or BASELINE_DIR) / f"{program.upper()}_diff_config.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def stdout_tolerance_config(diff_config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize stdout rules from a full diff config or bare tolerance dict."""
    if "stdout_tolerance" in diff_config:
        return diff_config["stdout_tolerance"]
    return diff_config


def _log(msg: str) -> None:
    """Lightweight diagnostic hook (stdout in CLI mode)."""
    print(msg, file=sys.stderr)


def numeric_match(b_line: str, a_line: str, tolerance: float) -> bool:
    """Return True when two lines match within numeric *tolerance* (0 = exact)."""
    if compare_stdout_lines(b_line, a_line):
        return True
    if _is_date_only_diff(b_line, a_line):
        return True
    b_nums = extract_numbers(b_line)
    a_nums = extract_numbers(a_line)
    if not b_nums and not a_nums:
        return compare_stdout_lines(b_line, a_line)
    if len(b_nums) != len(a_nums):
        return False
    return _numbers_within_tolerance(b_nums, a_nums, tolerance)


def compare_stdout(baseline: str, actual: str, config: Dict[str, Any]) -> bool:
    """Compare stdout line-by-line with per-field rules from F64 diff config."""
    result = compare_stdout_result(baseline, actual, config)
    return result.match


def compare_stdout_result(
    baseline: str,
    actual: str,
    config: Dict[str, Any],
) -> CompareResult:
    """Compare stdout with per-field rules; returns structured :class:`CompareResult`."""
    tol_cfg = stdout_tolerance_config(config)
    exact_fields = set(tol_cfg.get("exact_fields", []))
    tolerant_fields: Dict[str, float] = dict(tol_cfg.get("tolerant_fields", {}))
    ignore_fields = set(tol_cfg.get("ignore_fields", []))
    ignore_pattern_res = [
        re.compile(str(p), re.IGNORECASE)
        for p in (config.get("ignore_patterns") or [])
        if str(p).strip()
    ]
    default_tolerance = float(tol_cfg.get("default_numeric_tolerance_pct", 0.001))
    normalize_ws = _normalize_whitespace_enabled(config)

    def _line_ignored(line: str) -> bool:
        if any(_line_matches_ignore_field(line, field) for field in ignore_fields):
            return True
        return any(p.search(line or "") for p in ignore_pattern_res)

    baseline_lines = baseline.splitlines()
    actual_lines = actual.splitlines()

    if len(baseline_lines) != len(actual_lines):
        if normalize_ws:
            max_lines = max(len(baseline_lines), len(actual_lines))
        else:
            msg = f"Line count mismatch: {len(baseline_lines)} vs {len(actual_lines)}"
            _log(msg)
            return CompareResult(False, msg)
    else:
        max_lines = len(baseline_lines)

    def _lines_equal(b_line: str, a_line: str) -> bool:
        if _class_loans_line_match(b_line, a_line):
            return True
        if _loans_summary_line_match(b_line, a_line):
            return True
        if normalize_ws:
            return compare_stdout_lines(b_line, a_line)
        return b_line == a_line

    mismatches: List[LineMismatch] = []
    ignored = 0
    exact_ok = 0
    tolerant_ok = 0
    default_ok = 0

    for i in range(max_lines):
        b_line = baseline_lines[i] if i < len(baseline_lines) else ""
        a_line = actual_lines[i] if i < len(actual_lines) else ""
        if _line_ignored(b_line) or _line_ignored(a_line):
            ignored += 1
            continue

        matched_exact = next(
            (f for f in exact_fields if f.casefold() in b_line.casefold() or f.casefold() in a_line.casefold()),
            None,
        )
        if matched_exact:
            if not _lines_equal(b_line, a_line):
                mismatches.append(
                    LineMismatch(
                        i + 1,
                        normalize_stdout_line(b_line),
                        normalize_stdout_line(a_line),
                        f"exact mismatch ({matched_exact})",
                    )
                )
                _log(f"  Line {i + 1} ({matched_exact}): exact mismatch")
                _log(f"    Expected: {normalize_stdout_line(b_line)}")
                _log(f"    Actual:   {normalize_stdout_line(a_line)}")
            else:
                exact_ok += 1
            continue

        matched_tolerant = next(
            (f for f in tolerant_fields if f.casefold() in b_line.casefold() or f.casefold() in a_line.casefold()),
            None,
        )
        if matched_tolerant:
            tolerance = float(tolerant_fields[matched_tolerant])
            if not numeric_match(b_line, a_line, tolerance):
                mismatches.append(
                    LineMismatch(
                        i + 1,
                        b_line.strip(),
                        a_line.strip(),
                        f"outside tolerance {tolerance} ({matched_tolerant})",
                    )
                )
            else:
                tolerant_ok += 1
            continue

        if not numeric_match(b_line, a_line, default_tolerance):
            mismatches.append(
                LineMismatch(
                    i + 1,
                    b_line.strip(),
                    a_line.strip(),
                    f"default tolerance {default_tolerance} failed",
                )
            )
        else:
            default_ok += 1

    stats = {
        "baseline_lines": len(baseline_lines),
        "actual_lines": len(actual_lines),
        "lines_compared": max_lines,
        "ignored_lines": ignored,
        "exact_ok": exact_ok,
        "tolerant_ok": tolerant_ok,
        "default_ok": default_ok,
        "exact_matches": exact_ok,
        "tolerant_matches": tolerant_ok,
        "date_skips": 0,
        "mismatches": len(mismatches),
    }

    if mismatches:
        msg = f"stdout comparison: {len(mismatches)} mismatch(es)"
        _log(msg)
        for m in mismatches[:10]:
            _log(f"  L{m.line_num}: {m.reason}")
        return CompareResult(False, msg, mismatches, stats)

    return CompareResult(True, "stdout matches (F64 config)", [], stats)


def compare_generated_file(expected: Dict[str, Any], actual: Dict[str, Any], config: Dict[str, Any]) -> bool:
    """Compare a generated .dat file using per-file rules from F64 diff config."""
    filename = actual.get("filename") or expected.get("filename", "")
    file_config = (config.get("generated_files_tolerance") or {}).get(filename, {})

    if file_config.get("record_count_must_match"):
        if expected.get("record_count") != actual.get("record_count"):
            return False

    expected_bytes = expected.get("bytes")
    actual_bytes = actual.get("bytes")
    if expected_bytes is None or actual_bytes is None:
        if file_config.get("verify_md5", False):
            return expected.get("md5") == actual.get("md5")
        if expected.get("record_count") is not None and actual.get("record_count") is not None:
            return expected["record_count"] == actual["record_count"]
        return expected.get("size_bytes") == actual.get("size_bytes")

    from tests.e2e.baseline_metrics import GENERATED_FILE_RECORD_LEN as _rec_lens

    rec_len = _rec_lens.get(filename)
    exp_buf = bytearray(expected_bytes)
    act_buf = bytearray(actual_bytes)
    for start, end in file_config.get("ignore_byte_ranges", []):
        if rec_len and len(exp_buf) % rec_len == 0:
            for rec_off in range(0, len(exp_buf), rec_len):
                for idx in range(rec_off + start, min(rec_off + end, len(exp_buf))):
                    exp_buf[idx] = 0
                for idx in range(rec_off + start, min(rec_off + end, len(act_buf))):
                    act_buf[idx] = 0
        else:
            for idx in range(start, min(end, len(exp_buf))):
                exp_buf[idx] = 0
            for idx in range(start, min(end, len(act_buf))):
                act_buf[idx] = 0
    if file_config.get("record_structure_must_match") and rec_len:
        if (
            len(exp_buf) % rec_len == 0
            and len(act_buf) % rec_len == 0
            and len(exp_buf) == len(act_buf)
        ):
            for off in range(0, len(exp_buf), rec_len):
                if bytes(exp_buf[off : off + rec_len]) != bytes(act_buf[off : off + rec_len]):
                    return False
            return True

    return bytes(exp_buf) == bytes(act_buf)


# ---------------------------------------------------------------------------
# Line comparison
# ---------------------------------------------------------------------------

@dataclass
class LineMismatch:
    line_num: int
    baseline: str
    actual: str
    reason: str


def _is_date_only_diff(baseline: str, actual: str) -> bool:
    """True if the only difference between the lines is a date/timestamp."""
    b_no_date = _DATE_RE.sub("__DATE__", baseline).strip()
    a_no_date = _DATE_RE.sub("__DATE__", actual).strip()
    return b_no_date == a_no_date


def _numbers_within_tolerance(
    b_nums: List[Decimal], a_nums: List[Decimal], tolerance_pct: float
) -> bool:
    """Check whether all corresponding number pairs are within tolerance."""
    if len(b_nums) != len(a_nums):
        return False
    for bn, an in zip(b_nums, a_nums):
        if bn == an:
            continue
        if tolerance_pct == 0.0:
            return False
        denom = max(abs(bn), abs(an), Decimal("1E-9"))
        if abs(bn - an) / denom > Decimal(str(tolerance_pct)):
            return False
    return True


def compare_lines(
    baseline: str,
    actual: str,
    tolerance_pct: float = 0.001,
) -> Optional[str]:
    """Compare two lines. Returns None if they match, or a reason string."""
    if compare_stdout_lines(baseline, actual):
        return None

    if _is_date_only_diff(baseline, actual):
        return None

    b_nums = extract_numbers(baseline)
    a_nums = extract_numbers(actual)

    if not b_nums and not a_nums:
        return "text differs"

    if len(b_nums) != len(a_nums):
        return f"number count differs ({len(b_nums)} vs {len(a_nums)})"

    if not _numbers_within_tolerance(b_nums, a_nums, tolerance_pct):
        pairs = [(str(b), str(a)) for b, a in zip(b_nums, a_nums) if b != a]
        return f"numeric mismatch: {pairs[:3]}"

    b_skel = normalize_for_skeleton(baseline)
    a_skel = normalize_for_skeleton(actual)
    if b_skel != a_skel:
        return "text skeleton differs"

    return None


# ---------------------------------------------------------------------------
# File-level comparison
# ---------------------------------------------------------------------------

@dataclass
class CompareResult:
    match: bool
    message: str
    mismatches: List[LineMismatch] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)


def compare_outputs(
    baseline_path: str | Path,
    actual_path: str | Path,
    *,
    program: str = "",
    tolerance_pct: float = 0.001,
    diff_config: Optional[Dict[str, Any]] = None,
) -> CompareResult:
    """Compare two text output files line-by-line with numeric tolerance.

    Uses per-program rules when *program* is provided (e.g. "RISKSCOR"),
    falling back to the global *tolerance_pct*.
    """
    bp = Path(baseline_path)
    ap = Path(actual_path)

    if not bp.exists():
        return CompareResult(False, f"baseline not found: {bp}")
    if not ap.exists():
        return CompareResult(False, f"actual not found: {ap}")

    baseline_text = bp.read_text(encoding="utf-8", errors="replace")
    actual_text = ap.read_text(encoding="utf-8", errors="replace")

    cfg = diff_config
    if cfg is None and program:
        cfg = load_diff_config(program)
    if cfg and (cfg.get("stdout_tolerance") or cfg.get("exact_fields")):
        return compare_stdout_result(baseline_text, actual_text, cfg)

    b_lines = baseline_text.splitlines()
    a_lines = actual_text.splitlines()

    rules = PROGRAM_RULES.get(program.upper(), DEFAULT_RULES)

    mismatches: List[LineMismatch] = []
    exact_matches = 0
    tolerant_matches = 0
    date_skips = 0

    max_lines = max(len(b_lines), len(a_lines))
    for i in range(max_lines):
        b = b_lines[i] if i < len(b_lines) else ""
        a = a_lines[i] if i < len(a_lines) else ""

        if b.strip() == a.strip() or compare_stdout_lines(b, a):
            exact_matches += 1
            continue

        if _is_date_only_diff(b, a):
            date_skips += 1
            continue

        tol = rules.tolerance_for_line(b) if b else rules.default_tolerance_pct
        reason = compare_lines(b, a, tol)
        if reason is None:
            tolerant_matches += 1
        else:
            mismatches.append(LineMismatch(i + 1, b.strip(), a.strip(), reason))

    stats = {
        "baseline_lines": len(b_lines),
        "actual_lines": len(a_lines),
        "exact_matches": exact_matches,
        "tolerant_matches": tolerant_matches,
        "date_skips": date_skips,
        "mismatches": len(mismatches),
    }

    if mismatches:
        summary = f"{len(mismatches)} line mismatch(es)"
        return CompareResult(False, summary, mismatches, stats)

    return CompareResult(True, "all lines match (with tolerance)", [], stats)


def compare_outputs_text(
    baseline_text: str,
    actual_text: str,
    *,
    program: str = "",
    tolerance_pct: float = 0.001,
    diff_config: Optional[Dict[str, Any]] = None,
) -> CompareResult:
    """Compare two output strings with numeric tolerance.

    String-based equivalent of :func:`compare_outputs` for in-memory use
    by the behavioral diff runner. When *diff_config* is set (or loaded for
    *program*), uses F64 per-field rules from ``*_diff_config.json``.
    """
    cfg = diff_config
    if cfg is None and program:
        cfg = load_diff_config(program)
    if cfg and (cfg.get("stdout_tolerance") or cfg.get("exact_fields")):
        return compare_stdout_result(baseline_text, actual_text, cfg)

    b_lines = baseline_text.splitlines() if baseline_text else []
    a_lines = actual_text.splitlines() if actual_text else []

    rules = PROGRAM_RULES.get(program.upper(), DEFAULT_RULES) if program else DEFAULT_RULES

    mismatches: List[LineMismatch] = []
    exact_matches = 0
    tolerant_matches = 0
    date_skips = 0

    max_lines = max(len(b_lines), len(a_lines))
    for i in range(max_lines):
        b = b_lines[i] if i < len(b_lines) else ""
        a = a_lines[i] if i < len(a_lines) else ""

        if b.strip() == a.strip() or compare_stdout_lines(b, a):
            exact_matches += 1
            continue

        if _is_date_only_diff(b, a):
            date_skips += 1
            continue

        tol = rules.tolerance_for_line(b) if b else rules.default_tolerance_pct
        reason = compare_lines(b, a, tol)
        if reason is None:
            tolerant_matches += 1
        else:
            mismatches.append(LineMismatch(i + 1, b.strip(), a.strip(), reason))

    stats = {
        "baseline_lines": len(b_lines),
        "actual_lines": len(a_lines),
        "exact_matches": exact_matches,
        "tolerant_matches": tolerant_matches,
        "date_skips": date_skips,
        "mismatches": len(mismatches),
    }

    if mismatches:
        return CompareResult(False, f"{len(mismatches)} line mismatch(es)", mismatches, stats)
    return CompareResult(True, "all lines match (with tolerance)", [], stats)


def compare_data_files(
    baseline_path: str | Path,
    actual_path: str | Path,
    *,
    ignore_trailing_whitespace: bool = True,
) -> CompareResult:
    """Compare two fixed-width data files.

    Exact byte comparison per record line, optionally ignoring trailing
    whitespace (COBOL WRITE pads to record length; Java may not).
    """
    bp = Path(baseline_path)
    ap = Path(actual_path)

    if not bp.exists():
        return CompareResult(False, f"baseline not found: {bp}")
    if not ap.exists():
        return CompareResult(False, f"actual not found: {ap}")

    b_data = bp.read_bytes()
    a_data = ap.read_bytes()

    if not ignore_trailing_whitespace:
        if b_data == a_data:
            return CompareResult(True, "byte-exact match")
        return CompareResult(
            False,
            f"binary mismatch (baseline={len(b_data)}B actual={len(a_data)}B)",
        )

    b_lines = b_data.split(b"\n")
    a_lines = a_data.split(b"\n")

    mismatches: List[LineMismatch] = []
    max_lines = max(len(b_lines), len(a_lines))
    for i in range(max_lines):
        bl = b_lines[i].rstrip() if i < len(b_lines) else b""
        al = a_lines[i].rstrip() if i < len(a_lines) else b""
        if bl != al:
            mismatches.append(LineMismatch(
                i + 1,
                bl.decode("utf-8", errors="replace")[:80],
                al.decode("utf-8", errors="replace")[:80],
                "record bytes differ",
            ))

    stats = {
        "baseline_records": len(b_lines),
        "actual_records": len(a_lines),
        "mismatches": len(mismatches),
    }

    if mismatches:
        return CompareResult(
            False,
            f"{len(mismatches)} record mismatch(es)",
            mismatches,
            stats,
        )
    return CompareResult(True, "all records match (trailing ws ignored)", [], stats)


# ---------------------------------------------------------------------------
# Full directory comparison
# ---------------------------------------------------------------------------

MAIN_PROGS = ("LOANEVAL", "RECOVRY", "RISKSCOR", "RPTMONTH")
INPUT_DATS = {"LOANFILE.dat", "CUSTFILE.dat", "COLFILE.dat", "GUARFILE.dat", "SANCFILE.dat"}


def compare_full(
    baseline_dir: str | Path,
    actual_dir: str | Path,
) -> Tuple[int, int, int, int]:
    """Compare all programs. Returns (total, matches, mismatches, missing)."""
    bd = Path(baseline_dir)
    ad = Path(actual_dir)
    total = match = mismatch = missing = 0

    for prog in MAIN_PROGS:
        print(f"\n--- {prog} ---")

        # stdout
        bl_stdout = bd / f"{prog}_stdout.txt"
        candidates = [
            ad / f"{prog}_stdout.txt",
            ad / prog / "stdout.txt",
        ]
        ac_stdout = next((c for c in candidates if c.exists()), None)

        if bl_stdout.exists() and ac_stdout:
            total += 1
            result = compare_outputs(bl_stdout, ac_stdout, program=prog)
            if result.match:
                print(f"  stdout: MATCH ({result.stats})")
                match += 1
            else:
                print(f"  stdout: MISMATCH - {result.message}")
                for mm in result.mismatches[:5]:
                    print(f"    L{mm.line_num}: {mm.reason}")
                    print(f"      baseline: {mm.baseline[:100]}")
                    print(f"      actual  : {mm.actual[:100]}")
                mismatch += 1
        elif bl_stdout.exists():
            print("  stdout: MISSING in actual")
            missing += 1
            total += 1

        # exit code
        bl_rc = bd / f"{prog}_exitcode.txt"
        ac_rc = ad / f"{prog}_exitcode.txt"
        if bl_rc.exists() and ac_rc.exists():
            total += 1
            if bl_rc.read_text().strip() == ac_rc.read_text().strip():
                print(f"  exit code: MATCH ({bl_rc.read_text().strip()})")
                match += 1
            else:
                print(f"  exit code: MISMATCH "
                      f"(expected={bl_rc.read_text().strip()} "
                      f"actual={ac_rc.read_text().strip()})")
                mismatch += 1

        # data files
        for bl_dat in sorted(bd.glob(f"{prog}_*.dat")):
            dat_name = bl_dat.name.removeprefix(f"{prog}_")
            total += 1
            candidates = [
                ad / dat_name,
                ad / f"{prog}_{dat_name}",
                ad / prog / dat_name,
            ]
            ac_dat = next((c for c in candidates if c.exists()), None)
            if not ac_dat:
                print(f"  {dat_name}: MISSING")
                missing += 1
                continue

            result = compare_data_files(bl_dat, ac_dat)
            if result.match:
                print(f"  {dat_name}: MATCH")
                match += 1
            else:
                print(f"  {dat_name}: MISMATCH - {result.message}")
                for mm in result.mismatches[:3]:
                    print(f"    record {mm.line_num}: {mm.reason}")
                mismatch += 1

    print(f"\n=== Summary ===")
    print(f"  Total checks : {total}")
    print(f"  Matches      : {match}")
    print(f"  Mismatches   : {mismatch}")
    print(f"  Missing      : {missing}")

    if mismatch > 0 or missing > 0:
        print("\nRESULT: DIFFERENCES FOUND")
    else:
        print("\nRESULT: ALL CHECKS PASSED")

    return total, match, mismatch, missing


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smart baseline comparator with numeric tolerance"
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    p_stdout = sub.add_parser("stdout", help="Compare two stdout text files")
    p_stdout.add_argument("baseline")
    p_stdout.add_argument("actual")
    p_stdout.add_argument("--program", default="")
    p_stdout.add_argument("--tolerance", type=float, default=0.001)

    p_dat = sub.add_parser("datfile", help="Compare two data files")
    p_dat.add_argument("baseline")
    p_dat.add_argument("actual")
    p_dat.add_argument("--exact", action="store_true",
                       help="Disable trailing-whitespace tolerance")

    p_full = sub.add_parser("full", help="Compare full baseline vs actual dirs")
    p_full.add_argument("baseline_dir")
    p_full.add_argument("actual_dir")

    args = parser.parse_args()

    if args.mode == "stdout":
        result = compare_outputs(
            args.baseline, args.actual,
            program=args.program,
            tolerance_pct=args.tolerance,
        )
        print(result.message)
        if result.mismatches:
            for mm in result.mismatches[:10]:
                print(f"  L{mm.line_num} ({mm.reason}):")
                print(f"    baseline: {mm.baseline}")
                print(f"    actual  : {mm.actual}")
        print(f"Stats: {result.stats}")
        sys.exit(0 if result.match else 1)

    elif args.mode == "datfile":
        result = compare_data_files(
            args.baseline, args.actual,
            ignore_trailing_whitespace=not args.exact,
        )
        print(result.message)
        if result.mismatches:
            for mm in result.mismatches[:10]:
                print(f"  record {mm.line_num}: {mm.reason}")
        sys.exit(0 if result.match else 1)

    elif args.mode == "full":
        _, _, mismatches, missing = compare_full(args.baseline_dir, args.actual_dir)
        sys.exit(1 if (mismatches + missing) > 0 else 0)


if __name__ == "__main__":
    main()
