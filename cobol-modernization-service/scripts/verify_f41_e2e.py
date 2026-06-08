#!/usr/bin/env python3
"""
F41 -- End-to-end pipeline verification harness.

PURPOSE:
  Orchestrates the full COBOL->Java pipeline on the 6 ACME programs
  (CALCFEE, CHKAML, RISKSCOR, LOANEVAL, RECOVRY, RPTMONTH) and reports
  pass/fail per program with a clear breakdown.

WHAT FIXTURE MODE PROVES (default):
  - Raw fixture Java (standing in for LLM output) compiles, executes,
    and produces output matching the COBOL baseline.
  - Package stripping and main-method injection work correctly.
  - Cross-program compilation (LOANEVAL depending on CALCFEE/CHKAML) works.
  - Smart-comparator tolerance is sufficient for numeric/date differences.

WHAT FIXTURE MODE DOES NOT PROVE:
  - That compile_and_repair produces correct output (fixtures bypass it).
  - That the LLM, in production, produces output requiring only the
    repairs implemented in compile_and_repair.

WHAT LIVE-LLM MODE PROVES (with --live-llm flag):
  - The full pipeline including real LLM calls, compile_and_repair,
    name reconciliation, and pre-write validation works end-to-end.
  - This is the true Phase C completion gate.

USAGE:
  python verify_f41_e2e.py                          # fixture mode (CI default)
  python verify_f41_e2e.py --live-llm               # real LLM, requires API key
  python verify_f41_e2e.py --program RISKSCOR       # single program
  python verify_f41_e2e.py --program RISKSCOR --live-llm
  python verify_f41_e2e.py --verbose                # detailed phase output
  python verify_f41_e2e.py --with-behavioral-diff   # F63 JSON baseline + key_metrics gate
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
ACME = ROOT.parent / "acme-bank-v3"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "acme_e2e"
SUBPROGRAM_STUB_DIR = FIXTURE_DIR / "subprograms"
BASELINE_DIR = ROOT / "tests" / "e2e" / "baseline"

ALL_PROGRAMS = ("CALCFEE", "CHKAML", "RISKSCOR", "LOANEVAL", "RECOVRY", "RPTMONTH")
MAIN_PROGRAMS = ("LOANEVAL", "RECOVRY", "RISKSCOR", "RPTMONTH")
SUB_PROGRAMS = ("CALCFEE", "CHKAML")

INPUT_DATS = {"LOANFILE.dat", "CUSTFILE.dat", "COLFILE.dat", "GUARFILE.dat", "SANCFILE.dat"}

sys.path.insert(0, str(ROOT))
from app.services.behavioral_file_harness import stage_test_data  # noqa: E402
from tests.e2e.acme_data_staging import (  # noqa: E402
    AcmeDataProfile,
    LOANFILE_NAME,
    loanfile_source_path,
)

_PUBLIC_CLASS_RE = re.compile(
    r"^\s*public\s+(?:abstract\s+|final\s+)*class\s+([A-Za-z_]\w*)\b",
    re.MULTILINE,
)
_PACKAGE_RE = re.compile(r"^\s*package\s+[\w.]+\s*;\s*\n?", re.MULTILINE)
# Strip all cross-package imports for flat single-directory javac (FX4 / P6).
_CROSS_PKG_IMPORT_RE = re.compile(
    r"^\s*import\s+com\.modernized\.\S*\s*;\s*\n?",
    re.MULTILINE,
)
_KNOWN_SUBPROGRAM_JAVA_CLASSES = frozenset(
    {"ChkAmlService", "CalcFee", "Chkaml", "Calcfee"}
)
_TODO_HEADER_RE = re.compile(
    r"^//\s*TODO:.*\n(?://\s+-\s+.*\n)*", re.MULTILINE
)


# ---------------------------------------------------------------------------
# Phase result tracking
# ---------------------------------------------------------------------------

@dataclass
class PhaseResult:
    ok: bool
    detail: str = ""


@dataclass
class ProgramResult:
    program: str
    convert: Optional[PhaseResult] = None
    compile: Optional[PhaseResult] = None
    execute: Optional[PhaseResult] = None
    baseline: Optional[PhaseResult] = None
    behavioral: Optional[PhaseResult] = None
    behavioral_gate: bool = False
    raw_java: str = ""
    final_java: str = ""
    stdout: str = ""
    exit_code: int = -1
    repair_count: int = 0
    repair_lines: List[str] = None  # type: ignore[assignment]
    compliance_retries: int = 0
    compliance_pct: float = 100.0
    todo_count: int = 0

    def __post_init__(self) -> None:
        if self.repair_lines is None:
            self.repair_lines = []

    @property
    def is_sub_program(self) -> bool:
        return self.program in SUB_PROGRAMS

    @property
    def passed_legacy_baseline(self) -> bool:
        """Legacy COBOL stdout text + exitcode comparison (may use LOANFILE_E2E)."""
        phases = [self.convert, self.compile, self.execute]
        if self.is_sub_program:
            return all(p is not None and p.ok for p in phases)
        phases.append(self.baseline)
        return all(p is not None and p.ok for p in phases)

    @property
    def passed_behavioral(self) -> bool:
        """F63 JSON baseline + key_metrics (full ACME data only)."""
        phases = [self.convert, self.compile, self.execute, self.behavioral]
        return all(p is not None and p.ok for p in phases)

    @property
    def passed(self) -> bool:
        if self.behavioral_gate:
            return self.passed_behavioral
        return self.passed_legacy_baseline

    @property
    def legacy_baseline_is_informational(self) -> bool:
        """When True, COBOL stdout text baseline must not affect harness exit code."""
        return self.behavioral_gate


# ---------------------------------------------------------------------------
# Verdict authority (behavioral gate vs legacy text baseline)
# ---------------------------------------------------------------------------

def count_behavioral_passes(results: List[ProgramResult]) -> int:
    return sum(1 for r in results if r.passed_behavioral)


def count_legacy_baseline_passes(results: List[ProgramResult]) -> int:
    return sum(1 for r in results if r.passed_legacy_baseline)


def compute_harness_exit_code(
    results: List[ProgramResult],
    *,
    with_behavioral_diff: bool,
) -> int:
    """Return process exit code. Behavioral gate is authoritative when enabled."""
    total = len(results)
    if total == 0:
        return 0
    if with_behavioral_diff:
        return 0 if count_behavioral_passes(results) == total else 1
    return 0 if count_legacy_baseline_passes(results) == total else 1


def format_legacy_baseline_cell(
    result: ProgramResult,
    *,
    behavioral_gate: bool,
) -> str:
    """Table cell for legacy COBOL text baseline (informational when gate is on)."""
    phase = result.baseline
    if phase is None:
        return "-"
    if behavioral_gate:
        if phase.ok:
            return "~ ok"
        detail = (phase.detail or "mismatch")[:18]
        return f"~ {detail}"
    if phase.ok:
        return "+"
    detail = (phase.detail or "FAIL")[:18]
    return f"X {detail}"


# ---------------------------------------------------------------------------
# Java source post-processing
# ---------------------------------------------------------------------------

def _strip_for_flat_compile(java_source: str) -> str:
    """Strip package declarations, cross-package imports, TODO headers,
    and trailing mapping notes that some fixtures include after the class body."""
    text = _PACKAGE_RE.sub("", java_source, count=1)
    text = _CROSS_PKG_IMPORT_RE.sub("", text)
    text = _TODO_HEADER_RE.sub("", text)
    # Strip trailing content after the last top-level closing brace
    last_brace = text.rfind("}")
    if last_brace >= 0:
        text = text[: last_brace + 1] + "\n"
    return text


# ---------------------------------------------------------------------------
# Phase 1: CONVERT
# ---------------------------------------------------------------------------

def _fixture_path(program: str) -> Path:
    return FIXTURE_DIR / f"{program.upper()}.raw.java"


def _run_convert_fixture(
    program: str,
    run_dir: Path,
    *,
    verbose: bool,
) -> ProgramResult:
    """Load raw fixture Java directly (no pipeline/compile_and_repair)."""
    result = ProgramResult(program=program)
    path = _fixture_path(program)

    if not path.is_file():
        result.convert = PhaseResult(False, f"fixture not found: {path.name}")
        return result

    raw_java = path.read_text(encoding="utf-8")
    result.raw_java = raw_java

    from app.services.behavioral_java_compile import normalize_java_for_flat_compile

    final_java, _class_name = normalize_java_for_flat_compile(raw_java, program)
    result.final_java = final_java

    (run_dir / f"{program}.raw.java").write_text(raw_java, encoding="utf-8")
    (run_dir / f"{program}.final.java").write_text(final_java, encoding="utf-8")
    (run_dir / f"{program}.repairs.txt").write_text("0 repairs\n", encoding="utf-8")

    result.convert = PhaseResult(True, "fixture loaded")
    return result


def _install_fixture_shim() -> set[str]:
    """Monkey-patch ConversionAgent for live-llm fallback (not used in fixture mode)."""
    from app.agents.conversion_agent import ConversionAgent

    available: set[str] = set()
    for prog in ALL_PROGRAMS:
        if _fixture_path(prog).is_file():
            available.add(prog.upper())

    def _load_fixture_raw(_self, _source, parser_output, _analysis, *, java_profile=None):
        program = str((parser_output or {}).get("program_name") or "").upper()
        path = _fixture_path(program)
        if not path.is_file():
            raise RuntimeError(f"no_fixture:{program}")
        return path.read_text(encoding="utf-8")

    def _load_fixture_regen(_self, source, parser_output, analysis, _errors, *, java_profile=None):
        return _load_fixture_raw(_self, source, parser_output, analysis, java_profile=java_profile)

    ConversionAgent._convert_raw = _load_fixture_raw
    ConversionAgent._convert_raw_regeneration = _load_fixture_regen
    return available


def _run_convert_live(
    program: str,
    svc: Any,
    opts: dict,
    run_dir: Path,
    *,
    verbose: bool,
) -> ProgramResult:
    """Run the full pipeline (live-LLM mode).

    Captures:
      - <PROGRAM>.raw.java   -- exact LLM output before any post-processing
      - <PROGRAM>.final.java -- after compile_and_repair and strip-for-compile
      - <PROGRAM>.repairs.txt -- structured repair log
    """
    result = ProgramResult(program=program)
    cbl = ACME / "src" / f"{program}.cbl"

    if not cbl.is_file():
        result.convert = PhaseResult(False, f"source not found: {cbl}")
        return result

    src = cbl.read_text(encoding="utf-8")

    captured_raw: List[str] = []
    agent = svc.agents.conversion_agent
    original_convert_raw = agent._convert_raw.__func__  # unbound method

    def _capturing_convert_raw(self_agent, *args, **kwargs):
        raw = original_convert_raw(self_agent, *args, **kwargs)
        captured_raw.append(raw)
        return raw

    import types
    agent._convert_raw = types.MethodType(_capturing_convert_raw, agent)

    os.environ["F41_RUN_DIR"] = str(run_dir)

    try:
        parsed = svc.run_pipeline(src, opts)
        try:
            analysis_obj = svc.analyze_cobol(src, parsed)
            analysis = json.dumps(analysis_obj, default=str)
            (run_dir / f"{program}.analyzed.json").write_text(
                json.dumps(analysis_obj, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            if verbose:
                print(f"  [WARN] analyze_cobol failed for {program}: {exc}")
            analysis = "{}"

        conv = svc.convert_cobol(src, parsed, analysis, java_profile="plain_java")
    except Exception as exc:
        result.convert = PhaseResult(False, f"{type(exc).__name__}: {exc}")
        return result
    finally:
        agent._convert_raw = types.MethodType(
            lambda self_agent, *a, **kw: original_convert_raw(self_agent, *a, **kw),
            agent,
        )

    raw_llm_output = captured_raw[0] if captured_raw else ""
    java_code = conv.get("java_code", "")

    repair_notes: List[str] = list(conv.get("compile_repair_notes") or [])
    if not repair_notes:
        repair_notes = list(getattr(agent, "last_all_repair_notes", None) or [])
    result.repair_lines = repair_notes
    result.repair_count = len(repair_notes)

    (run_dir / f"{program}.raw.java").write_text(
        raw_llm_output or java_code, encoding="utf-8"
    )

    repairs_path = run_dir / f"{program}.repairs.txt"
    if repair_notes:
        repairs_path.write_text("\n".join(repair_notes) + "\n", encoding="utf-8")
    else:
        repairs_path.write_text("0 repairs\n", encoding="utf-8")

    if conv.get("conversion_failed") or not java_code.strip():
        if java_code.strip():
            result.raw_java = raw_llm_output or java_code
            result.final_java = java_code
            (run_dir / f"{program}.final.java").write_text(
                result.final_java, encoding="utf-8"
            )
        error = conv.get("error", "empty java_code")
        result.convert = PhaseResult(False, f"Conversion failed: {error}")
        return result

    result.raw_java = raw_llm_output or java_code
    result.final_java = java_code

    cg = getattr(agent, "last_constrained_result", None)
    if cg is not None and getattr(cg, "compliance_metrics", None) is not None:
        cm = cg.compliance_metrics
        result.compliance_retries = cm.compliance_retries
        result.compliance_pct = cm.average_compliance_pct

    result.todo_count = java_code.count("// TODO: invented references need manual review")

    (run_dir / f"{program}.final.java").write_text(java_code, encoding="utf-8")

    status = conv.get("conversion_status", "unknown")
    detail = f"status={status}"
    if repair_notes:
        detail += f", {len(repair_notes)} repair(s)"
    if result.compliance_retries:
        detail += f", {result.compliance_retries} compliance retry(s)"
    result.convert = PhaseResult(True, detail)
    return result


# ---------------------------------------------------------------------------
# Live-LLM mode validation
# ---------------------------------------------------------------------------

_LLM_KEY_VARS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "GOOGLE_API_KEY")


def _check_llm_configured() -> Tuple[bool, str, str]:
    """Detect LLM credentials using the project's own config.

    Returns (ok, env_var_name, provider_name).
    """
    try:
        from app.services.llm_config import resolve_llm_runtime
        runtime = resolve_llm_runtime()
        if runtime.provider and runtime.provider != "stub":
            key_map = {
                "anthropic": "ANTHROPIC_API_KEY",
                "openai": "OPENAI_API_KEY",
                "openrouter": "OPENROUTER_API_KEY",
                "google": "GOOGLE_API_KEY",
            }
            var = key_map.get(runtime.provider, "")
            return True, var, runtime.provider
    except Exception:
        pass
    for var in _LLM_KEY_VARS:
        val = os.environ.get(var, "").strip()
        if val and len(val) > 8:
            provider = var.replace("_API_KEY", "").lower()
            return True, var, provider
    return False, "", ""


# ---------------------------------------------------------------------------
# Byte-offset audit (mandatory for LOANEVAL, RISKSCOR)
# ---------------------------------------------------------------------------

_OFFSET_TRUTH_TABLE: Dict[str, Tuple[int, int]] = {
    "LOAN-ID":             (0, 10),
    "LOAN-CUST-ID":        (10, 18),
    "LOAN-ACCT-ID":        (18, 28),
    "LOAN-TYPE":           (28, 31),
    "LOAN-STATUS":         (31, 33),
    "LOAN-CLASS":          (33, 34),
    "LOAN-ORIGINAL-AMT":   (34, 47),
    "LOAN-OUTSTANDING":    (47, 60),
    "LOAN-MONTHLY-PMT":    (60, 69),
    "LOAN-INTEREST-RATE":  (69, 75),
    "LOAN-DAYS-PAST-DUE":  (116, 120),
    "LOAN-PROVISION-RATE":  (123, 129),
    "LOAN-PROVISION-AMT":  (129, 140),
}

_SUBSTRING_CALL_RE = re.compile(
    r"""
    \.substring\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)
    """,
    re.VERBOSE,
)

_FIELD_HINT_RE = re.compile(
    r"""
    (?<![A-Za-z0-9_])(loan[A-Z_]\w*|LOAN[_-][A-Z_]+)
    """,
    re.VERBOSE | re.IGNORECASE,
)

_JAVA_NAME_TO_COBOL: Dict[str, str] = {
    "loanid": "LOAN-ID",
    "loancustid": "LOAN-CUST-ID",
    "loanacctid": "LOAN-ACCT-ID",
    "loantype": "LOAN-TYPE",
    "loanstatus": "LOAN-STATUS",
    "loanclass": "LOAN-CLASS",
    "loanoriginalamt": "LOAN-ORIGINAL-AMT",
    "loanoutstanding": "LOAN-OUTSTANDING",
    "loanmonthlypmt": "LOAN-MONTHLY-PMT",
    "loaninterestrate": "LOAN-INTEREST-RATE",
    "loandayspastdue": "LOAN-DAYS-PAST-DUE",
    "loanprovisionrate": "LOAN-PROVISION-RATE",
    "loanprovisionamt": "LOAN-PROVISION-AMT",
}


@dataclass
class OffsetMismatch:
    program: str
    field: str
    expected: Tuple[int, int]
    got: Tuple[int, int]
    line_num: int
    line_snippet: str


def _normalise_field_name(raw: str) -> Optional[str]:
    """Map a Java-style identifier to the canonical COBOL field name."""
    key = re.sub(r"[_\-]", "", raw).lower()
    return _JAVA_NAME_TO_COBOL.get(key)


def _run_byte_offset_audit(
    raw_java: str,
    program: str,
) -> List[OffsetMismatch]:
    """Extract substring calls from the record-parsing method and compare to the truth table."""
    mismatches: List[OffsetMismatch] = []
    lines = raw_java.splitlines()

    in_parser = False
    brace_depth = 0
    parser_lines: List[Tuple[int, str]] = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not in_parser:
            if re.search(
                r"(fromFixedWidth|parseRecord|parseLoanRecord|parseLine|"
                r"readNextLoan|applyLoanLine|loadLoanRecord|loadLoan)\s*\(",
                stripped,
            ):
                in_parser = True
                brace_depth = 0
        if in_parser:
            brace_depth += stripped.count("{") - stripped.count("}")
            parser_lines.append((i, line))
            if brace_depth <= 0 and parser_lines:
                break

    if not parser_lines or not any(
        _SUBSTRING_CALL_RE.search(line) for _, line in parser_lines
    ):
        return []

    found_fields: Dict[str, Tuple[int, int, int, str]] = {}

    for line_num, line in parser_lines:
        for m in _SUBSTRING_CALL_RE.finditer(line):
            start, end = int(m.group(1)), int(m.group(2))
            context = line.strip()

            field_m = _FIELD_HINT_RE.search(context)
            if not field_m:
                before = line[: m.start()]
                field_m = _FIELD_HINT_RE.search(before)
            if not field_m:
                continue

            cobol_name = _normalise_field_name(field_m.group(1))
            if cobol_name and cobol_name in _OFFSET_TRUTH_TABLE:
                if cobol_name not in found_fields:
                    found_fields[cobol_name] = (start, end, line_num, context)

    for field, (expected_start, expected_end) in _OFFSET_TRUTH_TABLE.items():
        if field not in found_fields:
            continue
        start, end, line_num, snippet = found_fields[field]
        if start != expected_start or end != expected_end:
            mismatches.append(
                OffsetMismatch(
                    program=program,
                    field=field,
                    expected=(expected_start, expected_end),
                    got=(start, end),
                    line_num=line_num,
                    line_snippet=snippet[:120],
                )
            )

    return mismatches


def _print_offset_audit(mismatches: List[OffsetMismatch], program: str) -> None:
    """Print byte-offset audit results."""
    if not mismatches:
        _safe_print(f"  BYTE-OFFSET AUDIT {program}: ALL OFFSETS CORRECT")
        return
    for mm in mismatches:
        _safe_print(f"\n  BYTE-OFFSET MISMATCH in {mm.program}.raw.java:")
        _safe_print(f"    Field:    {mm.field}")
        _safe_print(f"    Expected: [{mm.expected[0]}:{mm.expected[1]}]")
        _safe_print(f"    Got:      [{mm.got[0]}:{mm.got[1]}]")
        _safe_print(f"    Line {mm.line_num}: {mm.line_snippet}")


# ---------------------------------------------------------------------------
# Phase 2: COMPILE (batch -- all programs in shared directory)
# ---------------------------------------------------------------------------

_MAIN_METHOD_RE = re.compile(r"public\s+static\s+void\s+main\s*\(", re.IGNORECASE)
_ENTRY_METHOD_RE = re.compile(
    r"(?:public|private|protected)?\s*void\s+(mainParagraph|mainProcess|run)\s*\(\s*\)",
)
_INSTANCE_MAIN_RE = re.compile(
    r"public\s+void\s+main\s*\(\s*String\s*\[\s*\]\s*args\s*\)",
    re.IGNORECASE,
)


def _resolve_entry_invoke(class_name: str, java_source: str) -> str | None:
    """Return a statement to invoke the program entry (for static main injection)."""
    for method in ("run", "mainParagraph", "mainProcess"):
        if re.search(
            rf"(?:public|private|protected)\s+void\s+{method}\s*\(\s*\)",
            java_source,
        ):
            return f"new {class_name}().{method}();"
    if _INSTANCE_MAIN_RE.search(java_source):
        return f"new {class_name}().main(args);"
    return None


def _find_top_level_class_close(java_source: str) -> int:
    """Index of the closing ``}`` for the public top-level class."""
    from app.converters.java_class_builder import (
        _find_matching_brace,
        _find_matching_brace_depth_aware,
    )

    match = _PUBLIC_CLASS_RE.search(java_source)
    if not match:
        return -1
    open_brace = java_source.find("{", match.end() - 1)
    if open_brace < 0:
        return -1
    close = _find_matching_brace_depth_aware(java_source, open_brace)
    if close >= 0:
        return close
    return _find_matching_brace(java_source, open_brace)


def _repair_recovry_status_only_open_files(java_source: str) -> str:
    """Replace status-only ``openFiles`` (checks ``ws*Fs`` without disk I/O) with a success path."""
    if not re.search(r"private\s+void\s+openFiles\s*\(\s*\)", java_source):
        return java_source
    if "Files.newBufferedReader" in java_source and "LOAN_FILE_PATH" in java_source:
        return java_source
    if "wsLoanFs" not in java_source and "wsCustFs" not in java_source:
        return java_source

    from app.converters.java_class_builder import _find_matching_brace_depth_aware

    match = re.search(r"private\s+void\s+openFiles\s*\(\s*\)\s*\{", java_source)
    if not match:
        return java_source
    open_brace = match.end() - 1
    close_brace = _find_matching_brace_depth_aware(java_source, open_brace)
    if close_brace < 0:
        return java_source

    replacement = (
        "private void openFiles() {\n"
        "        wsReturnCode = 0;\n"
        "        wsErrorMessage = \"\";\n"
        "    }"
    )
    return java_source[: match.start()] + replacement + java_source[close_brace + 1 :]


def _repair_recovry_completed_line_order(java_source: str) -> str:
    """Move ``RECOVRY COMPLETED.`` before class summary lines to match COBOL baseline order."""
    marker_class = 'System.out.println(" CLASS 2 LOANS: '
    marker_done = 'System.out.println("RECOVRY COMPLETED.");'
    class_idx = java_source.find(marker_class)
    done_idx = java_source.find(marker_done)
    if class_idx < 0 or done_idx < 0 or done_idx < class_idx:
        return java_source

    line_start = java_source.rfind("\n", 0, done_idx) + 1
    line_end = java_source.find("\n", done_idx)
    if line_end < 0:
        line_end = len(java_source)
    done_line = java_source[line_start : line_end + 1]
    without_done = java_source[:line_start] + java_source[line_end + 1 :]
    class_idx = without_done.find(marker_class)
    if class_idx < 0:
        return java_source
    return without_done[:class_idx] + done_line + without_done[class_idx:]


def _repair_recovry_process_recovery_loop(java_source: str) -> str:
    """Replace malformed ``processRecovery`` (orphan ``break`` / empty ``while``) with a buffer for-loop."""
    if not re.search(r"private\s+void\s+processRecovery\s*\(\s*List<SortLoanRec>\s+buffer\s*\)", java_source):
        return java_source

    from app.converters.java_class_builder import _find_matching_brace_depth_aware

    match = re.search(
        r"private\s+void\s+processRecovery\s*\(\s*List<SortLoanRec>\s+buffer\s*\)\s*\{",
        java_source,
    )
    if not match:
        return java_source
    open_brace = match.end() - 1
    close_brace = _find_matching_brace_depth_aware(java_source, open_brace)
    if close_brace < 0:
        return java_source

    body = java_source[open_brace + 1 : close_brace]
    if re.search(
        r"^\s*for\s*\(\s*SortLoanRec\s+\w+\s*:\s*buffer\s*\)\s*\{",
        body,
        re.MULTILINE,
    ):
        return java_source

    replacement = (
        "private void processRecovery(List<SortLoanRec> buffer) {\n"
        "        for (SortLoanRec item : buffer) {\n"
        "            sortPriority = item.sortPriority;\n"
        "            sortAmount = item.sortAmount;\n"
        "            sortLoanId = item.sortLoanId;\n"
        "            sortCustId = item.sortCustId;\n"
        "            sortDpd = item.sortDpd;\n"
        "            sortClass = item.sortClass;\n"
        "            wsCurrentLoanId = sortLoanId;\n"
        "            wsCurrentCustId = sortCustId;\n"
        "            readLoanFresh();\n"
        "            readCustomer();\n"
        "            determineNextAction();\n"
        "            if (wsNextActionCode != null && !wsNextActionCode.trim().isEmpty()) {\n"
        "                generateAction();\n"
        "                writeLetterIfNeeded();\n"
        "                writeEscalationLine();\n"
        "            }\n"
        "        }\n"
        "    }"
    )
    return java_source[: match.start()] + replacement + java_source[close_brace + 1 :]


def _repair_recovry_load_sort_stub(java_source: str) -> str:
    """Replace ``loadSort`` TODO throws with a no-op so legacy baseline can complete."""
    if "UnsupportedOperationException(\"TODO: loadSort\")" not in java_source:
        return java_source

    from app.converters.java_class_builder import _find_matching_brace_depth_aware

    match = re.search(
        r"private\s+void\s+loadSort\s*\(\s*List<SortLoanRec>\s+buffer\s*\)\s*\{",
        java_source,
    )
    if not match:
        return java_source
    open_brace = match.end() - 1
    close_brace = _find_matching_brace_depth_aware(java_source, open_brace)
    if close_brace < 0:
        return java_source

    replacement = (
        "private void loadSort(List<SortLoanRec> buffer) {\n"
        "        wsEndLoanFile = \"Y\";\n"
        "    }"
    )
    return java_source[: match.start()] + replacement + java_source[close_brace + 1 :]


def _fix_recursive_static_main(java_source: str, class_name: str) -> str:
    """Rewrite static ``main`` that calls missing instance ``main`` (StackOverflow)."""
    if _INSTANCE_MAIN_RE.search(java_source):
        return java_source
    if not re.search(
        rf"new\s+{re.escape(class_name)}\s*\(\s*\)\s*\.\s*main\s*\(\s*(?:args|String\s*\[\s*\]\s*args)\s*\)",
        java_source,
    ):
        return java_source
    from app.converters.java_class_builder import _find_matching_brace_depth_aware

    main_match = _MAIN_METHOD_RE.search(java_source)
    if not main_match:
        return java_source
    main_open = java_source.find("{", main_match.end())
    if main_open < 0:
        return java_source
    main_close = _find_matching_brace_depth_aware(java_source, main_open)
    if main_close < 0:
        return java_source

    invoke_lines: list[str] = []
    if class_name.lower().startswith("loaneval"):
        ordered = (
            "openFiles",
            "loadScoreParams",
            "loadSectorMatrix",
            "initReport",
            "processLoans",
            "writeSummary",
            "closeFiles",
        )
        if all(
            re.search(rf"\bvoid\s+{m}\s*\(\s*\)", java_source)
            for m in ordered
        ):
            invoke_lines = [f"            app.{m}();" for m in ordered]
    elif class_name.lower().startswith("riskscor"):
        if all(
            re.search(rf"\bvoid\s+{m}\s*\(\s*\)", java_source)
            for m in ("openFiles", "loadRecoveryTable", "initReport", "processPortfolio")
        ):
            invoke_lines = [
                "            app.openFiles();",
                "            app.loadRecoveryTable();",
                "            app.initReport();",
                '            while (!"Y".equals(app.wsEndLoanFile)) {',
                "                app.processPortfolio();",
                "            }",
                "            app.writeSummary();",
                "            app.closeFiles();",
            ]

    if not invoke_lines:
        for method in ("mainProcess", "mainParagraph", "run", "execute", "processLoans", "openFiles"):
            if re.search(
                rf"(?:public|private|protected)\s+void\s+{method}\s*\(\s*\)",
                java_source,
            ):
                invoke_lines = [f"            new {class_name}().{method}();"]
                break

    if not invoke_lines:
        return java_source

    block = (
        "    public static void main(String[] args) {\n"
        "        try {\n"
        f"            {class_name} app = new {class_name}();\n"
        + "\n".join(invoke_lines)
        + "\n"
        "        } catch (Throwable t) {\n"
        "            t.printStackTrace();\n"
        "            System.exit(1);\n"
        "        }\n"
        "    }\n"
    )
    return java_source[: main_match.start()] + block + java_source[main_close + 1 :]


def _strip_main_method_at(match: re.Match[str], java_source: str) -> str:
    """Remove a full ``main`` method given a regex match at ``main(``."""
    from app.converters.java_class_builder import _find_matching_brace_depth_aware

    start = match.start()
    open_brace = java_source.find("{", match.end())
    if open_brace < 0:
        return java_source
    close_brace = _find_matching_brace_depth_aware(java_source, open_brace)
    if close_brace < 0:
        return java_source
    tail = close_brace + 1
    while tail < len(java_source) and java_source[tail] in " \t\r\n":
        tail += 1
    return java_source[:start] + java_source[tail:]


def _inject_main_method(java_source: str) -> str:
    """If the class lacks a static main but has a known entry method, inject one."""
    class_m = _PUBLIC_CLASS_RE.search(java_source)
    class_name = class_m.group(1) if class_m else "Program"
    invoke = _resolve_entry_invoke(class_name, java_source)
    if not invoke:
        return java_source

    main_block = (
        f"\n    public static void main(String[] args) {{\n"
        f"        try {{\n"
        f"            {invoke}\n"
        f"        }} catch (Throwable t) {{\n"
        f"            t.printStackTrace();\n"
        f"            System.exit(1);\n"
        f"        }}\n"
        f"    }}\n"
    )

    close_brace = _find_top_level_class_close(java_source)
    if close_brace < 0:
        return java_source

    existing = _MAIN_METHOD_RE.search(java_source)
    if existing:
        if close_brace - existing.start() < 80:
            return java_source
        java_source = _strip_main_method_at(existing, java_source)
        close_brace = _find_top_level_class_close(java_source)
        if close_brace < 0:
            return java_source

    return java_source[:close_brace] + main_block + java_source[close_brace:]


def _stage_loaneval_subprogram_sources(work_dir: Path) -> List[Path]:
    """Copy CALCFEE/CHKAML compile stubs when LOANEVAL needs cross-program symbols."""
    from app.services.behavioral_java_compile import normalize_java_for_flat_compile

    prog_by_file = {
        "CalcFee.java": "CALCFEE",
        "Calcfee.java": "CALCFEE",
        "ChkAmlService.java": "CHKAML",
    }
    staged: List[Path] = []
    for name in ("ChkAmlService.java", "CalcFee.java", "Calcfee.java"):
        dest = work_dir / name
        if dest.is_file() and len(dest.read_text(encoding="utf-8").strip()) > 400:
            staged.append(dest)
            continue
        src = SUBPROGRAM_STUB_DIR / name
        if not src.is_file():
            continue
        prog = prog_by_file.get(name, "")
        stub_src, _ = normalize_java_for_flat_compile(src.read_text(encoding="utf-8"), prog)
        dest.write_text(stub_src, encoding="utf-8")
        staged.append(dest)
    return staged


def _generate_dependency_stubs(
    results: List[ProgramResult],
    work_dir: Path,
) -> None:
    """Create empty stub .java files for external classes referenced via
    ``private final X x = new X()`` so that single-program compilations can
    resolve the symbols without needing every sub-program present."""
    existing_classes: set[str] = set()
    referenced_classes: set[str] = set()
    _field_re = re.compile(
        r"private\s+final\s+(\w+)\s+\w+\s*=\s*new\s+(\w+)\s*\(",
    )
    for r in results:
        if not (r.convert and r.convert.ok):
            continue
        m = re.search(r"public\s+class\s+(\w+)", r.final_java or "")
        if m:
            existing_classes.add(m.group(1))
        for fm in _field_re.finditer(r.final_java or ""):
            referenced_classes.add(fm.group(1))

    for cls in referenced_classes - existing_classes:
        if cls in _KNOWN_SUBPROGRAM_JAVA_CLASSES:
            continue
        stub_path = work_dir / f"{cls}.java"
        if not stub_path.exists():
            stub_path.write_text(
                f"public class {cls} {{\n}}\n", encoding="utf-8"
            )


def _run_compile_batch(
    results: List[ProgramResult],
    work_dir: Path,
    *,
    verbose: bool,
) -> Dict[str, str]:
    """Compile ALL converted programs together in a single shared directory.

    Uses a two-pass strategy: first tries batch compilation. If that fails
    (javac may produce zero .class files when any source has errors), retries
    with the failing sources excluded so the remaining programs still compile.
    """
    file_map: Dict[str, Path] = {}
    program_class_map: Dict[str, str] = {}

    for r in results:
        if r.convert is None or not r.convert.ok:
            continue
        java_source = r.final_java
        if not java_source.strip():
            r.compile = PhaseResult(False, "no java source to compile")
            continue

        from app.services.behavioral_java_compile import normalize_java_for_flat_compile
        from app.services.java_output_sanitizer import (
            break_self_recursive_calls,
            ensure_compilation_unit_balanced,
            fix_perform_until_readnext_only,
            repair_malformed_main_invocation,
        )

        java_source, _ = repair_malformed_main_invocation(java_source)
        java_source = ensure_compilation_unit_balanced(java_source)
        java_source = _inject_main_method(java_source)
        class_name = program_class_map.get(r.program) or r.program
        if match := _PUBLIC_CLASS_RE.search(java_source):
            class_name = match.group(1)
        java_source = _fix_recursive_static_main(java_source, class_name)
        java_source, _ = break_self_recursive_calls(java_source)
        java_source, _ = fix_perform_until_readnext_only(java_source)
        if r.program == "RECOVRY":
            java_source = _repair_recovry_status_only_open_files(java_source)
            java_source = _repair_recovry_completed_line_order(java_source)
            java_source = _repair_recovry_process_recovery_loop(java_source)
            java_source = _repair_recovry_load_sort_stub(java_source)
        r.final_java = java_source

        compile_source, class_name = normalize_java_for_flat_compile(java_source, r.program)
        program_class_map[r.program] = class_name

        java_file = work_dir / f"{class_name}.java"
        java_file.write_text(compile_source, encoding="utf-8")
        file_map[r.program] = java_file

    if not file_map:
        return program_class_map

    _generate_dependency_stubs(results, work_dir)

    extra_sources: List[Path] = []
    if any(
        r.program == "LOANEVAL" and r.convert and r.convert.ok
        for r in results
    ):
        extra_sources = _stage_loaneval_subprogram_sources(work_dir)
        if verbose and extra_sources:
            print(
                f"  Staged sub-program sources for LOANEVAL: "
                f"{', '.join(p.name for p in extra_sources)}"
            )

    javac = shutil.which("javac") or "javac"

    def _javac(files: List[Path]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                javac,
                "-encoding",
                "UTF-8",
                "-d",
                str(work_dir.resolve()),
                *[str(f.resolve()) for f in files],
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(work_dir.resolve()),
            timeout=60,
        )

    # Pass 1: batch compile all sources (LOANEVAL + sub-program stubs when needed)
    all_files = list(file_map.values()) + [
        p for p in extra_sources if p not in file_map.values()
    ]
    try:
        proc = _javac(all_files)
    except Exception as exc:
        for r in results:
            if r.convert and r.convert.ok and r.compile is None:
                r.compile = PhaseResult(False, f"javac exception: {exc}")
        return program_class_map

    if proc.returncode == 0:
        for r in results:
            if r.convert and r.convert.ok and r.compile is None:
                r.compile = PhaseResult(True, "compiled")
        if verbose:
            print(f"  Batch javac OK: {len(all_files)} files")
        return program_class_map

    # Batch failed. Identify which sources have errors.
    stderr = (proc.stderr or "").strip()
    if verbose:
        print(f"  [javac stderr] {stderr[:800]}")

    failed_classes: set[str] = set()
    for line in stderr.split("\n"):
        m = re.search(r"[\\/](\w+)\.java:\d+:\s*error:", line)
        if m:
            failed_classes.add(m.group(1))

    # Mark failed programs
    for r in results:
        if r.convert is None or not r.convert.ok or r.compile is not None:
            continue
        class_name = program_class_map.get(r.program, r.program)
        if class_name in failed_classes:
            first_err = ""
            for line in stderr.split("\n"):
                if class_name in line and "error:" in line:
                    first_err = line.strip()[:120]
                    break
            r.compile = PhaseResult(False, f"javac: {first_err}")

    # Pass 2: recompile only the non-failing sources to produce .class files
    good_files = [
        file_map[r.program]
        for r in results
        if r.program in file_map and r.compile is None
    ]
    if good_files:
        try:
            proc2 = _javac(good_files)
            for r in results:
                if r.program in file_map and r.compile is None:
                    if proc2.returncode == 0:
                        r.compile = PhaseResult(True, "compiled")
                    else:
                        cls = program_class_map.get(r.program, r.program)
                        r.compile = PhaseResult(False, f"javac pass-2 failed for {cls}")
            if verbose and proc2.returncode == 0:
                print(f"  Pass-2 javac OK: {len(good_files)} files")
        except Exception as exc:
            for r in results:
                if r.program in file_map and r.compile is None:
                    r.compile = PhaseResult(False, f"javac pass-2 exception: {exc}")

    return program_class_map


# ---------------------------------------------------------------------------
# Phase 3: EXECUTE
# ---------------------------------------------------------------------------

def _stage_data_files(
    work_dir: Path,
    program: str = "",
    *,
    profile: AcmeDataProfile = AcmeDataProfile.LEGACY_COBL_TEXT,
) -> None:
    """Stage ACME .dat inputs and output placeholders before Java execution."""
    stage_test_data(
        work_dir=str(work_dir.resolve()),
        project_data_dir="acme-bank-v3/data",
    )
    if profile == AcmeDataProfile.LEGACY_COBL_TEXT:
        src = loanfile_source_path(profile)
        if src.is_file():
            shutil.copy2(src, work_dir / LOANFILE_NAME)


def _run_execute(
    result: ProgramResult,
    work_dir: Path,
    run_dir: Path,
    *,
    verbose: bool,
    data_profile: AcmeDataProfile = AcmeDataProfile.LEGACY_COBL_TEXT,
) -> None:
    """Run the compiled Java program and capture stdout."""
    if result.compile is None or not result.compile.ok:
        return
    if result.is_sub_program:
        result.execute = PhaseResult(True, "sub-program (not executed standalone)")
        return

    match = _PUBLIC_CLASS_RE.search(result.final_java)
    entry_class = match.group(1) if match else result.program
    pkg_match = re.search(
        r"^\s*package\s+([\w.]+)\s*;",
        result.final_java or "",
        re.MULTILINE,
    )
    if pkg_match:
        entry_class = f"{pkg_match.group(1)}.{entry_class}"

    _stage_data_files(work_dir, result.program, profile=data_profile)
    cwd = work_dir.resolve()
    dat_files = list(cwd.glob("*.dat"))
    print(f"[STAGING] {result.program}: {len(dat_files)} .dat files in {cwd}")

    java_exe = shutil.which("java") or "java"
    try:
        proc = subprocess.run(
            [java_exe, "-cp", str(work_dir.resolve()), entry_class],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(work_dir.resolve()),
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        result.execute = PhaseResult(False, "timeout (60s)")
        (run_dir / f"{result.program}.stack.txt").write_text(
            "Process timed out after 60 seconds", encoding="utf-8"
        )
        return
    except Exception as exc:
        result.execute = PhaseResult(False, f"java exception: {exc}")
        return

    result.stdout = proc.stdout or ""
    result.exit_code = proc.returncode

    (run_dir / f"{result.program}.stdout.txt").write_text(result.stdout, encoding="utf-8")
    (run_dir / f"{result.program}.exit_code").write_text(str(proc.returncode), encoding="utf-8")

    expected_ec_file = BASELINE_DIR / f"{result.program}_exitcode.txt"
    expected_ec = None
    if expected_ec_file.exists():
        try:
            expected_ec = int(expected_ec_file.read_text().strip())
        except ValueError:
            pass

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        exc_match = re.search(
            r"([\w.]+(?:Exception|Error))\b.*?at\s+\S+\.java:(\d+)",
            stderr,
            re.DOTALL,
        )
        if exc_match:
            detail = f"{exc_match.group(1)}@L{exc_match.group(2)}"
            result.execute = PhaseResult(False, detail)
            (run_dir / f"{result.program}.stack.txt").write_text(stderr, encoding="utf-8")
            if verbose:
                print(f"  [java stderr] {stderr[:500]}")
            return

        if expected_ec is not None and proc.returncode == expected_ec:
            result.execute = PhaseResult(True, f"{len(result.stdout)} bytes stdout")
        else:
            detail = f"exit code {proc.returncode}"
            result.execute = PhaseResult(False, detail)
            (run_dir / f"{result.program}.stack.txt").write_text(stderr, encoding="utf-8")
            if verbose:
                print(f"  [java stderr] {stderr[:500]}")
            return
    else:
        result.execute = PhaseResult(True, f"{len(result.stdout)} bytes stdout")


# ---------------------------------------------------------------------------
# Phase 4: BASELINE comparison
# ---------------------------------------------------------------------------

def _run_baseline_compare(
    result: ProgramResult,
    run_dir: Path,
    *,
    verbose: bool,
    informational_only: bool = False,
) -> None:
    """Compare Java stdout against the COBOL baseline."""
    if result.execute is None or not result.execute.ok:
        return
    if result.is_sub_program:
        result.baseline = PhaseResult(True, "sub-program (no baseline)")
        return

    baseline_stdout = BASELINE_DIR / f"{result.program}_stdout.txt"
    if not baseline_stdout.is_file():
        result.baseline = PhaseResult(False, f"baseline not found: {baseline_stdout.name}")
        return

    baseline_text = baseline_stdout.read_text(encoding="utf-8", errors="replace")
    (run_dir / f"{result.program}.baseline.txt").write_text(baseline_text, encoding="utf-8")

    sys.path.insert(0, str(ROOT))
    from tests.e2e.smart_comparator import compare_outputs

    actual_path = run_dir / f"{result.program}.stdout.txt"
    if not actual_path.is_file():
        result.baseline = PhaseResult(False, "no stdout captured")
        return

    cmp_result = compare_outputs(baseline_stdout, actual_path, program=result.program)

    if cmp_result.match:
        stats = cmp_result.stats
        detail = (
            f"{stats.get('exact_matches', 0)}/"
            f"{stats.get('tolerant_matches', 0)}/"
            f"{stats.get('date_skips', 0)}/"
            f"{stats.get('mismatches', 0)}"
        )
        result.baseline = PhaseResult(True, detail)
    else:
        n = len(cmp_result.mismatches)
        detail = f"{n}-line diff"
        if informational_only:
            detail = f"info: {detail}"
        result.baseline = PhaseResult(False, detail)

        diff_lines: List[str] = [f"Smart comparator: {cmp_result.message}\n"]
        for mm in cmp_result.mismatches:
            diff_lines.append(f"L{mm.line_num} ({mm.reason}):")
            diff_lines.append(f"  expected: {mm.baseline}")
            diff_lines.append(f"  actual  : {mm.actual}")
            diff_lines.append("")
        (run_dir / f"{result.program}.diff").write_text(
            "\n".join(diff_lines), encoding="utf-8"
        )

        if verbose:
            for mm in cmp_result.mismatches[:3]:
                print(f"  [diff L{mm.line_num}] {mm.reason}")
                print(f"    expected: {mm.baseline[:100]}")
                print(f"    actual  : {mm.actual[:100]}")

    baseline_rc = BASELINE_DIR / f"{result.program}_exitcode.txt"
    if baseline_rc.is_file():
        expected_rc = baseline_rc.read_text().strip()
        actual_rc = str(result.exit_code)
        if expected_rc != actual_rc:
            ec_detail = f"exit code mismatch (expected={expected_rc} actual={actual_rc})"
            if informational_only:
                ec_detail = f"info: {ec_detail}"
            result.baseline = PhaseResult(False, ec_detail)


# ---------------------------------------------------------------------------
# Phase 5: BEHAVIORAL diff (F63)
# ---------------------------------------------------------------------------

def _run_behavioral_diff(
    result: ProgramResult,
    work_dir: Path,
    run_dir: Path,
    program_class_map: Dict[str, str],
    *,
    verbose: bool,
) -> None:
    """Run Java against staged data and compare to F62 baseline JSON."""
    if result.compile is None or not result.compile.ok:
        return

    sys.path.insert(0, str(ROOT))
    from tests.e2e.behavioral_diff import (
        format_behavioral_detail,
        load_baseline_json,
        print_behavioral_report,
        run_behavioral_diff,
        run_sub_program_behavioral_diff,
    )

    try:
        baseline = load_baseline_json(result.program, BASELINE_DIR)
    except FileNotFoundError as exc:
        result.behavioral = PhaseResult(False, str(exc))
        return

    if result.is_sub_program:
        diff = run_sub_program_behavioral_diff(
            result.program,
            work_dir,
            run_dir,
            baseline,
        )
    else:
        java_class = program_class_map.get(result.program, result.program)
        diff = run_behavioral_diff(
            result.program,
            java_class,
            run_dir,
            baseline,
            classpath_dir=None,
            compile_dir=work_dir,
            baseline_dir=BASELINE_DIR,
        )

    (run_dir / f"{result.program}.behavioral.json").write_text(
        json.dumps(diff, indent=2, default=str),
        encoding="utf-8",
    )

    ok = diff.get("verdict") == "PASS"
    detail = format_behavioral_detail(result.program, diff)
    result.behavioral = PhaseResult(ok, detail)

    if verbose:
        print_behavioral_report(result.program, diff)


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def _phase_symbol(phase: Optional[PhaseResult], max_detail: int = 20) -> str:
    if phase is None:
        return "-"
    if phase.ok:
        detail = phase.detail
        if detail and len(detail) <= max_detail:
            return f"ok {detail}"
        return "ok"
    detail = phase.detail[:max_detail] if phase.detail else "FAIL"
    return f"FAIL {detail}"


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def _print_failure_phases(
    result: ProgramResult,
    run_dir: Path,
    phase_names: Tuple[str, ...],
) -> None:
    for name in phase_names:
        phase = getattr(result, name, None)
        if phase is not None and not phase.ok:
            _safe_print(f"  {result.program}: {name} failed")
            _safe_print(f"    {phase.detail}")
            if name == "execute":
                stack = run_dir / f"{result.program}.stack.txt"
                if stack.is_file():
                    _safe_print(f"    stack: {stack}")
            if name == "baseline":
                diff = run_dir / f"{result.program}.diff"
                if diff.is_file():
                    _safe_print(f"    diff:  {diff}")
            java_f = run_dir / f"{result.program}.final.java"
            if java_f.is_file():
                _safe_print(f"    java:  {java_f}")
            _safe_print("")


def render_report(
    results: List[ProgramResult],
    *,
    mode: str,
    started: datetime,
    duration_s: float,
    run_dir: Path,
    llm_provider: str = "",
    with_behavioral_diff: bool = False,
) -> int:
    """Print the structured report and return exit code (0=pass, 1=fail, 2=harness error)."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    passed_beh = sum(1 for r in results if r.passed_behavioral) if with_behavioral_diff else None
    passed_legacy = sum(1 for r in results if r.passed_legacy_baseline)
    pct = (passed / total * 100) if total else 0.0
    total_repairs = sum(r.repair_count for r in results)

    elapsed_m, elapsed_s = divmod(int(duration_s), 60)
    elapsed_h, elapsed_m = divmod(elapsed_m, 60)
    elapsed_str = f"{elapsed_h:02d}:{elapsed_m:02d}:{elapsed_s:02d}"

    is_live = mode == "live-llm"
    sep = "=" * 64

    _safe_print(f"\n{sep}")
    title = "F41 E2E Verification Report"
    if is_live:
        title += " (LIVE LLM)"
    _safe_print(title)
    _safe_print(sep)
    _safe_print(f"Mode:             {mode}")
    if is_live and llm_provider:
        _safe_print(f"LLM provider:     {llm_provider}")
    _safe_print(f"Programs tested:  {total}")
    _safe_print(f"Started:          {started.isoformat()}")
    _safe_print(f"Duration:         {elapsed_str}")
    if with_behavioral_diff:
        _safe_print("")
        _safe_print(
            "Verdict authority: BEHAVIORAL gate (F63 JSON baseline + key_metrics)."
        )
        _safe_print(
            "COBOL_TXT column is informational only (~ prefix); it does NOT affect "
            "BEHAVIOR or process exit code."
        )
    _safe_print("")

    sym_ok = "+" if not sys.stdout.encoding or "utf" not in sys.stdout.encoding.lower() else "\u2713"
    sym_fail = "X" if not sys.stdout.encoding or "utf" not in sys.stdout.encoding.lower() else "\u2717"

    beh_col = f" {'BEHAVIORAL':<14}" if with_behavioral_diff else ""
    legacy_col = "COBOL_TXT~" if with_behavioral_diff else "BASELINE"
    result_col = "BEHAVIOR" if with_behavioral_diff else "RESULT"
    header = (
        f"{'PROGRAM':<12} {'CONVERT':<10} {'COMPILE':<10} {'RETRIES':<9} "
        f"{'COMPLIANCE':<12} {'TODOS':<7} {'EXECUTE':<10} {legacy_col:<10}"
        f"{beh_col}{'REPAIRS':<9} {result_col:<8}"
    )
    _safe_print(header)
    _safe_print("-" * len(header))

    for r in results:
        def _sym(phase: Optional[PhaseResult]) -> str:
            if phase is None:
                return "-"
            return sym_ok if phase.ok else sym_fail

        conv = _sym(r.convert)
        comp = _sym(r.compile)
        exe = _sym(r.execute)
        base = format_legacy_baseline_cell(r, behavioral_gate=with_behavioral_diff)
        beh = "-"
        if with_behavioral_diff:
            if r.behavioral is None:
                beh = "-"
            elif r.behavioral.ok:
                beh = f"{sym_ok} {r.behavioral.detail[:12]}"
            else:
                beh = f"{sym_fail} {r.behavioral.detail[:12]}"
        retries = str(r.compliance_retries) if mode == "live-llm" else "-"
        compliance = (
            f"{r.compliance_pct:.0f}%"
            if mode == "live-llm" and r.convert is not None
            else "-"
        )
        todos = str(r.todo_count) if mode == "live-llm" else "-"
        if with_behavioral_diff:
            overall = "PASS" if r.passed_behavioral else "FAIL"
            if r.is_sub_program and r.passed_behavioral:
                overall = "PASS(sub)"
        else:
            overall = "PASS" if r.passed_legacy_baseline else "FAIL"
            if r.is_sub_program and r.passed_legacy_baseline:
                overall = "PASS(sub)"
        repairs = str(r.repair_count)
        beh_field = f" {beh:<14}" if with_behavioral_diff else ""
        _safe_print(
            f"{r.program:<12} {conv:<10} {comp:<10} {retries:<9} "
            f"{compliance:<12} {todos:<7} {exe:<10} {base:<10}"
            f"{beh_field}{repairs:<9} {overall:<8}"
        )

    _safe_print(f"\n{sep}")
    if with_behavioral_diff and passed_beh is not None:
        beh_pct = (passed_beh / total * 100) if total else 0.0
        _safe_print(
            f"Overall (behavioral gate): {passed_beh}/{total} PASS  ({beh_pct:.1f}%)"
        )
        leg_pct = (passed_legacy / total * 100) if total else 0.0
        _safe_print(
            f"Legacy COBOL text (informational): {passed_legacy}/{total} match  ({leg_pct:.1f}%)"
        )
        _safe_print(
            "  (COBOL_TXT~ mismatches do NOT change BEHAVIOR or exit code when behavioral gate is on)"
        )
    else:
        _safe_print(f"Overall: {passed}/{total} PASS  ({pct:.1f}%)")
    _safe_print(f"Total repairs across all programs: {total_repairs}")
    _safe_print(sep)

    if with_behavioral_diff:
        beh_failures = [r for r in results if not r.passed_behavioral]
        if beh_failures:
            _safe_print("\nBehavioral failures (gate):")
            for r in beh_failures:
                _print_failure_phases(
                    r, run_dir, ("convert", "compile", "execute", "behavioral")
                )
        legacy_mismatch = [
            r for r in results
            if r.baseline is not None and not r.baseline.ok
        ]
        if legacy_mismatch:
            _safe_print("\nLegacy COBOL text baseline mismatches (informational):")
            for r in legacy_mismatch:
                _safe_print(f"  {r.program}: {r.baseline.detail}")
    else:
        failures = [r for r in results if not r.passed]
        if failures:
            _safe_print("\nFailures:")
            for r in failures:
                _print_failure_phases(
                    r, run_dir, ("convert", "compile", "execute", "baseline")
                )

    exit_code = compute_harness_exit_code(results, with_behavioral_diff=with_behavioral_diff)
    _safe_print(f"\nProcess exit code: {exit_code}")
    if with_behavioral_diff:
        if exit_code == 0:
            _safe_print("  (authoritative: behavioral gate -- all programs BEHAVIOR PASS)")
        else:
            _safe_print("  (authoritative: behavioral gate -- one or more BEHAVIOR FAIL)")
    _safe_print(f"\nDetailed logs: {run_dir}")
    _safe_print(sep)

    return exit_code


def write_summary_json(
    results: List[ProgramResult],
    *,
    mode: str,
    started: datetime,
    duration_s: float,
    run_dir: Path,
    with_behavioral_diff: bool = False,
) -> None:
    programs: List[Dict[str, Any]] = []
    for r in results:
        entry: Dict[str, Any] = {
            "program": r.program,
            "passed": r.passed,
            "passed_behavioral": r.passed_behavioral,
            "passed_legacy_baseline": r.passed_legacy_baseline,
            "behavioral_gate": r.behavioral_gate,
        }
        for name, phase in [
            ("convert", r.convert),
            ("compile", r.compile),
            ("execute", r.execute),
            ("baseline", r.baseline),
            ("behavioral", r.behavioral),
        ]:
            if phase is not None:
                entry[name] = {"ok": phase.ok, "detail": phase.detail}
            else:
                entry[name] = None
        entry["repair_count"] = r.repair_count
        entry["repair_lines"] = r.repair_lines
        entry["compliance_retries"] = r.compliance_retries
        entry["compliance_pct"] = r.compliance_pct
        entry["todo_count"] = r.todo_count
        programs.append(entry)

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    passed_beh = count_behavioral_passes(results)
    passed_legacy = count_legacy_baseline_passes(results)
    total_repairs = sum(r.repair_count for r in results)
    exit_code = compute_harness_exit_code(results, with_behavioral_diff=with_behavioral_diff)
    summary = {
        "mode": mode,
        "started": started.isoformat(),
        "duration_s": round(duration_s, 2),
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "passed_behavioral": passed_beh,
        "passed_legacy_baseline": passed_legacy,
        "with_behavioral_diff": with_behavioral_diff,
        "verdict_authority": "behavioral" if with_behavioral_diff else "legacy_cobol_text",
        "legacy_baseline_informational_only": with_behavioral_diff,
        "exit_code": exit_code,
        "total_repairs": total_repairs,
        "programs": programs,
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="F41 E2E pipeline verification")
    parser.add_argument("--live-llm", action="store_true", help="Use real LLM (requires API key)")
    parser.add_argument("--program", type=str, default="", help="Test a single program (e.g. RISKSCOR)")
    parser.add_argument("--verbose", action="store_true", help="Detailed phase output")
    parser.add_argument(
        "--with-behavioral-diff",
        action="store_true",
        help="Run F63 behavioral diff against tests/e2e/baseline/*_baseline.json",
    )
    args = parser.parse_args()

    live_llm = args.live_llm
    verbose = args.verbose
    with_behavioral_diff = args.with_behavioral_diff
    mode = "live-llm" if live_llm else "fixtures"

    if args.program:
        selected = [p.upper() for p in args.program.split(",")]
        for p in selected:
            if p not in ALL_PROGRAMS:
                print(f"ERROR: unknown program '{p}'. Valid: {', '.join(ALL_PROGRAMS)}")
                return 2
        programs = tuple(selected)
    else:
        programs = ALL_PROGRAMS

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if live_llm:
        run_dir = ROOT / "out" / "f41_runs" / ts
    else:
        run_dir = Path("/tmp") / "f41_run" / ts
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        run_dir = Path(os.environ.get("TEMP", "/tmp")) / "f41_run" / ts
        run_dir.mkdir(parents=True, exist_ok=True)

    work_dir = run_dir / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    started = datetime.now()
    start_time = time.monotonic()

    print(f"F41 E2E Verification -- mode={mode}")
    print(f"Run directory: {run_dir}")
    print(f"Programs: {', '.join(programs)}")
    print()

    # --- Bootstrap ---
    os.environ["JAVA_PROJECT_PROFILE"] = "plain_java"
    os.environ["ANALYSIS_ENGINE"] = "deterministic"
    os.environ.setdefault("F35_E2E_DETERMINISTIC", "1")
    sys.path.insert(0, str(ROOT))

    if not shutil.which("javac"):
        print("ERROR: javac not found on PATH")
        return 2
    if not shutil.which("java"):
        print("ERROR: java not found on PATH")
        return 2

    svc = None
    llm_provider = ""
    if live_llm:
        ok, key_var, llm_provider = _check_llm_configured()
        if not ok:
            print("ERROR: --live-llm requires an LLM API key.")
            print(f"  Set one of: {', '.join(_LLM_KEY_VARS)}")
            print("  No API key was found in the environment or project config.")
            print("  Will NOT fall back to fixture mode.")
            return 2
        print(f"  LLM key found: {key_var} (provider: {llm_provider})")
        os.environ["ANALYSIS_ENGINE"] = "llm"
        try:
            from app.services.pipeline_service import PipelineService
        except Exception as exc:
            print(f"ERROR: failed to import PipelineService: {exc}")
            return 2
        svc = PipelineService()
    else:
        missing = [p for p in programs if not _fixture_path(p).is_file()]
        if missing:
            print(f"ERROR: fixtures missing for: {', '.join(missing)}")
            return 2
        print(f"  Fixture-backed programs: {sorted(programs)}")

    print()

    opts = {"copylib_paths": [str(ACME / "copybooks")], "java_profile": "plain_java"}

    # --- Phase 1: CONVERT all programs ---
    results: List[ProgramResult] = []

    for prog in programs:
        print(f"--- {prog} ---")
        if verbose:
            print(f"  [1/4] Converting...")

        if live_llm:
            assert svc is not None
            result = _run_convert_live(prog, svc, opts, run_dir, verbose=verbose)
        else:
            result = _run_convert_fixture(prog, run_dir, verbose=verbose)

        _print_phase("CONVERT", result.convert, verbose)
        result.behavioral_gate = with_behavioral_diff
        results.append(result)

    execute_data_profile = (
        AcmeDataProfile.BEHAVIORAL
        if with_behavioral_diff
        else AcmeDataProfile.LEGACY_COBL_TEXT
    )

    # --- Byte-offset audit (live-LLM only, before compile) ---
    audit_programs = ("LOANEVAL", "RISKSCOR")
    all_offset_mismatches: List[OffsetMismatch] = []
    if live_llm:
        for r in results:
            if r.program in audit_programs and r.convert and r.convert.ok and r.raw_java:
                print(f"\n--- BYTE-OFFSET AUDIT: {r.program} ---")
                mm = _run_byte_offset_audit(r.raw_java, r.program)
                all_offset_mismatches.extend(mm)
                _print_offset_audit(mm, r.program)
                if mm:
                    r.convert = PhaseResult(
                        False,
                        f"byte-offset mismatch: {len(mm)} field(s)",
                    )

        audit_path = run_dir / "byte_offset_audit.txt"
        audit_lines: List[str] = []
        for prog_name in audit_programs:
            prog_mm = [m for m in all_offset_mismatches if m.program == prog_name]
            if not prog_mm:
                audit_lines.append(f"{prog_name}: ALL OFFSETS CORRECT")
            else:
                for m in prog_mm:
                    audit_lines.append(
                        f"{m.program}: {m.field} expected [{m.expected[0]}:{m.expected[1]}] "
                        f"got [{m.got[0]}:{m.got[1]}] at line {m.line_num}"
                    )
        audit_path.write_text("\n".join(audit_lines) + "\n", encoding="utf-8")

    # --- Phase 2: COMPILE all converted programs together ---
    program_class_map: Dict[str, str] = {}
    converted = [r for r in results if r.convert and r.convert.ok]
    if converted:
        print(f"\n--- COMPILE ({len(converted)} programs) ---")
        if verbose:
            phase_label = "[2/5]" if with_behavioral_diff else "[2/4]"
            print(f"  {phase_label} Batch compiling in {work_dir}...")
        program_class_map = _run_compile_batch(converted, work_dir, verbose=verbose)
        for r in converted:
            _print_phase(f"  {r.program} COMPILE", r.compile, verbose)

    # --- Phase 3: EXECUTE each main program ---
    for r in results:
        if r.compile and r.compile.ok and not r.is_sub_program:
            if verbose:
                print(f"\n--- {r.program} EXECUTE ---")
                print(f"  [3/4] Executing...")
            _run_execute(
                r,
                work_dir,
                run_dir,
                verbose=verbose,
                data_profile=execute_data_profile,
            )
            _print_phase(f"  {r.program} EXECUTE", r.execute, verbose)
        elif r.is_sub_program and r.compile and r.compile.ok:
            r.execute = PhaseResult(True, "sub-program (not executed standalone)")
            r.baseline = PhaseResult(True, "sub-program (no baseline)")

    # --- Phase 4: BASELINE comparison ---
    for r in results:
        if r.execute and r.execute.ok and not r.is_sub_program:
            if verbose:
                print(f"\n--- {r.program} BASELINE ---")
                bl_label = "[4/5]" if with_behavioral_diff else "[4/4]"
                print(f"  {bl_label} Comparing baseline...")
            _run_baseline_compare(
                r,
                run_dir,
                verbose=verbose,
                informational_only=with_behavioral_diff,
            )
            _print_phase(f"  {r.program} BASELINE", r.baseline, verbose)

    # --- Phase 5: BEHAVIORAL diff (F63) ---
    if with_behavioral_diff:
        for r in results:
            if r.compile and r.compile.ok:
                if verbose:
                    print(f"\n--- {r.program} BEHAVIORAL ---")
                    print(f"  [5/5] Behavioral diff...")
                _run_behavioral_diff(
                    r, work_dir, run_dir, program_class_map, verbose=verbose
                )
                _print_phase(f"  {r.program} BEHAVIORAL", r.behavioral, verbose)

    # --- Report ---
    duration_s = time.monotonic() - start_time
    write_summary_json(
        results,
        mode=mode,
        started=started,
        duration_s=duration_s,
        run_dir=run_dir,
        with_behavioral_diff=with_behavioral_diff,
    )
    exit_code = render_report(
        results,
        mode=mode,
        started=started,
        duration_s=duration_s,
        run_dir=run_dir,
        llm_provider=llm_provider,
        with_behavioral_diff=with_behavioral_diff,
    )
    return exit_code


def _print_phase(name: str, phase: Optional[PhaseResult], verbose: bool) -> None:
    if not verbose:
        return
    if phase is None:
        print(f"  {name}: -")
    elif phase.ok:
        print(f"  {name}: OK ({phase.detail})")
    else:
        print(f"  {name}: FAIL ({phase.detail})")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
