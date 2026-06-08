"""Behavioral diff runner — execute COBOL/Java with scripted stdin and compare stdout.

Deterministic normalization and line-by-line diff. Supports snapshot fallback when
GnuCOBOL, javac, or configured executables are unavailable.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.behavioral_interactive_stdin import apply_interactive_stdin_to_scenarios
from app.services.behavioral_toolchain import (
    build_toolchain_unavailable_reason,
    get_toolchain_status,
    validate_behavioral_execution,
)
from app.services.behavioral_copybook_prep import (
    _default_copybook_search_dirs,
    _find_remaining_copy_directives,
    format_copybook_prep_failure,
)
from app.services.behavioral_baseline import acme_bank_v3_root, is_baseline_test_mode, resolve_cobol_for_baseline
from app.services.behavioral_cobol_compile import (
    SUB_PROGRAMS,
    compile_cobol_for_testing,
    find_acme_cobol_source,
)
from app.services.behavioral_java_compile import (
    collect_java_sources_for_behavioral_testing,
    compile_java_bundle_for_behavioral_testing,
)
from app.services.behavioral_file_harness import (
    read_report_stdout_for_program,
    stage_behavioral_data_files,
)
from app.services.behavioral_layer_scoring_service import attach_layered_scoring_to_result
from app.services.behavioral_single_file import (
    prepare_single_file_behavioral_sources,
)

# ── Diff summary helpers ──────────────────────────────────────────────────────


def _diff_summary_zero(
    *,
    diff_percentage: Optional[float] = None,
    comparison_status: str = "not_comparable",
    parity_blocked: bool = True,
) -> Dict[str, Any]:
    """Empty comparison — never imply a successful match."""
    return {
        "lines_compared": 0,
        "lines_matched": 0,
        "lines_diverged": 0,
        "paragraph_breakdown": [],
        "total_lines_cobol": 0,
        "total_lines_java": 0,
        "matching_lines": 0,
        "differing_lines": 0,
        "diff_percentage": diff_percentage,
        "first_mismatch_index": None,
        "cobol_normalized": "",
        "java_normalized": "",
        "highlights": [],
        "comparison_status": comparison_status,
        "parity_blocked": parity_blocked,
    }


_PARITY_BLOCKING_STATUSES = frozenset({"compile_failure", "runtime_failure", "timeout"})


def _cap_blocks_parity(cap: ExecutionCapture) -> bool:
    """True when this side must not participate in stdout parity scoring."""
    if cap.execution_status in _PARITY_BLOCKING_STATUSES:
        return True
    if cap.execution_status == "no_stdout" and cap.mode == "executed":
        return True
    if cap.error and cap.execution_status not in ("success", "fallback"):
        return True
    return False


def _parity_comparable(cobol_cap: ExecutionCapture, java_cap: ExecutionCapture) -> bool:
    """Stdout parity is only valid when both sides executed successfully."""
    if _cap_blocks_parity(cobol_cap) or _cap_blocks_parity(java_cap):
        return False
    if cobol_cap.execution_status == "success" and java_cap.execution_status == "success":
        return True
    if cobol_cap.mode == "fallback" and java_cap.mode == "fallback":
        return bool(cobol_cap.stdout.strip() and java_cap.stdout.strip())
    return False


def _parity_block_reason(cobol_cap: ExecutionCapture, java_cap: ExecutionCapture) -> str:
    """Primary diagnosis when stdout parity is blocked."""
    parts: List[str] = []
    for label, cap in (("COBOL", cobol_cap), ("Java", java_cap)):
        st = cap.execution_status or "unknown"
        if st == "compile_failure":
            parts.append(f"{label} compile failed")
        elif st == "runtime_failure":
            parts.append(f"{label} runtime failed")
        elif st == "timeout":
            parts.append(f"{label} timed out")
        elif st == "no_stdout" and cap.mode == "executed":
            parts.append(f"{label} produced no stdout")
        elif cap.error and st not in ("success", "fallback"):
            parts.append(f"{label} execution error")
    if not parts:
        return "Behavioral comparison blocked because execution did not produce comparable stdout."
    return "Behavioral comparison blocked because " + " and ".join(parts) + "."


def _artifact_provenance(
    request: Dict[str, Any],
    *,
    cobol_source: str,
    java_source: str,
    program_name: str,
) -> Dict[str, Any]:
    """Metadata describing which workspace artifacts were used for this run."""
    cobol_bytes = cobol_source.encode("utf-8", errors="replace")
    java_bytes = java_source.encode("utf-8", errors="replace")
    return {
        "program_name": program_name,
        "target_id": str(request.get("target_id") or request.get("project_id") or ""),
        "target_type": str(request.get("target_type") or "single_file"),
        "workspace_updated_at": request.get("workspace_updated_at"),
        "cobol_source_chars": len(cobol_source),
        "java_source_chars": len(java_source),
        "cobol_source_sha256": hashlib.sha256(cobol_bytes).hexdigest()[:16],
        "java_source_sha256": hashlib.sha256(java_bytes).hexdigest()[:16],
    }


# ── Execution capture ─────────────────────────────────────────────────────────


@dataclass
class ExecutionCapture:
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float
    mode: str  # executed | fallback | skipped
    execution_status: str = ""  # compile_failure | runtime_failure | no_stdout | success | skipped | fallback | timeout
    error: Optional[str] = None
    compile_stdout: str = ""
    compile_stderr: str = ""


# ── Normalization & comparison ──────────────────────────────────────────────────


def normalize_output_text(raw: str) -> str:
    """Trim trailing whitespace per line, unify newlines, collapse repeated blanks."""
    if not raw:
        return ""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    collapsed: List[str] = []
    prev_blank = False
    for line in lines:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        collapsed.append(line)
        prev_blank = is_blank
    return "\n".join(collapsed).strip()


def normalized_lines(raw: str) -> List[str]:
    norm = normalize_output_text(raw)
    if not norm:
        return []
    return norm.split("\n")


def compare_normalized_outputs(cobol_raw: str, java_raw: str, *, max_highlights: int = 50) -> Dict[str, Any]:
    """Line-by-line compare after normalization."""
    cobol_norm = normalize_output_text(cobol_raw)
    java_norm = normalize_output_text(java_raw)
    c_lines = cobol_norm.split("\n") if cobol_norm else []
    j_lines = java_norm.split("\n") if java_norm else []

    total_cobol = len(c_lines)
    total_java = len(j_lines)
    max_lines = max(total_cobol, total_java)
    matching = 0
    differing = 0
    highlights: List[Dict[str, Any]] = []
    first_mismatch_index: Optional[int] = None

    for i in range(max_lines):
        cl = c_lines[i] if i < total_cobol else ""
        jl = j_lines[i] if i < total_java else ""
        if cl == jl or cl.strip() == jl.strip():
            matching += 1
        else:
            differing += 1
            if first_mismatch_index is None:
                first_mismatch_index = i
            if len(highlights) < max_highlights:
                highlights.append({"line": i + 1, "cobol": cl, "java": jl})

    diff_percentage = round((differing / max_lines) * 100.0, 2) if max_lines else 0.0

    return {
        "total_lines_cobol": total_cobol,
        "total_lines_java": total_java,
        "matching_lines": matching,
        "differing_lines": differing,
        "diff_percentage": diff_percentage,
        "first_mismatch_index": first_mismatch_index,
        "cobol_normalized": cobol_norm,
        "java_normalized": java_norm,
        "lines_compared": max_lines,
        "lines_matched": matching,
        "lines_diverged": differing,
        "paragraph_breakdown": [],
        "highlights": highlights,
        "comparison_status": "comparable",
        "parity_blocked": False,
    }


def compare_smart_outputs(
    cobol_raw: str,
    java_raw: str,
    *,
    program_name: str = "",
    max_highlights: int = 50,
) -> Dict[str, Any]:
    """Tolerance-aware comparison using the smart comparator.

    Returns the same dict shape as :func:`compare_normalized_outputs` so
    callers can swap transparently.
    """
    from tests.e2e.smart_comparator import compare_outputs_text

    cobol_norm = normalize_output_text(cobol_raw)
    java_norm = normalize_output_text(java_raw)

    result = compare_outputs_text(cobol_norm, java_norm, program=program_name)

    total_cobol = result.stats.get("baseline_lines", 0)
    total_java = result.stats.get("actual_lines", 0)
    max_lines = max(total_cobol, total_java)
    matched = (
        result.stats.get("exact_matches", 0)
        + result.stats.get("tolerant_matches", 0)
        + result.stats.get("date_skips", 0)
        + result.stats.get("default_ok", 0)
        + result.stats.get("ignored_lines", 0)
    )
    differing = result.stats.get("mismatches", 0)
    diff_pct = round((differing / max_lines) * 100.0, 2) if max_lines else 0.0

    highlights: List[Dict[str, Any]] = []
    first_mismatch_index: Optional[int] = None
    for mm in result.mismatches[:max_highlights]:
        if first_mismatch_index is None:
            first_mismatch_index = mm.line_num - 1
        highlights.append({
            "line": mm.line_num,
            "cobol": mm.baseline,
            "java": mm.actual,
            "reason": mm.reason,
        })

    return {
        "total_lines_cobol": total_cobol,
        "total_lines_java": total_java,
        "matching_lines": matched,
        "differing_lines": differing,
        "diff_percentage": diff_pct,
        "first_mismatch_index": first_mismatch_index,
        "cobol_normalized": cobol_norm,
        "java_normalized": java_norm,
        "lines_compared": max_lines,
        "lines_matched": matched,
        "lines_diverged": differing,
        "paragraph_breakdown": [],
        "highlights": highlights,
        "comparison_status": "comparable",
        "parity_blocked": False,
        "comparison_mode": "smart",
        "tolerant_matches": result.stats.get("tolerant_matches", 0),
        "date_skips": result.stats.get("date_skips", 0),
    }


@dataclass
class SideRunResult:
    """One side of a behavioral stdout comparison (COBOL or Java)."""

    stdout: str
    compile_ok: bool
    execution_status: str = ""


def side_from_capture(cap: ExecutionCapture) -> SideRunResult:
    """Build a comparison-side view from an execution capture."""
    status = str(cap.execution_status or "")
    compile_ok = status != "compile_failure"
    return SideRunResult(
        stdout=cap.stdout or "",
        compile_ok=compile_ok,
        execution_status=status,
    )


def compute_actual_diff(
    cobol_stdout: str,
    java_stdout: str,
    *,
    program_name: str = "",
    comparison_mode: str = "exact",
) -> Dict[str, Any]:
    """Line-by-line stdout diff — only call when both sides ran successfully."""
    if comparison_mode == "smart":
        return compare_smart_outputs(
            cobol_stdout,
            java_stdout,
            program_name=program_name,
        )
    return compare_normalized_outputs(cobol_stdout, java_stdout)


_BLOCKED_COMPARISON_REASONS = frozenset(
    {"compile_failure", "both_empty_stdout", "output_asymmetry"}
)


def compute_test_status(
    cobol_result: SideRunResult,
    java_result: SideRunResult,
    *,
    program_name: str = "",
    comparison_mode: str = "exact",
) -> Dict[str, Any]:
    """
    Gate stdout parity: blocked comparisons return failed status with score 0.

    Only successful paths return a diff dict under ``diff`` with ``blocked`` False.
    """
    prog = str(program_name or "").strip().upper()
    if prog in SUB_PROGRAMS:
        if cobol_result.compile_ok and java_result.compile_ok:
            return {
                "blocked": False,
                "status": "comparable",
                "score": None,
                "note": "sub-program — compile verification only",
                "diff": {
                    "lines_compared": 0,
                    "lines_matched": 0,
                    "lines_diverged": 0,
                    "matching_lines": 0,
                    "differing_lines": 0,
                    "diff_percentage": None,
                    "comparison_status": "sub_program",
                    "parity_blocked": False,
                    "total_lines_cobol": 0,
                    "total_lines_java": 0,
                    "first_mismatch_index": None,
                    "cobol_normalized": "",
                    "java_normalized": "",
                    "paragraph_breakdown": [],
                    "highlights": [],
                },
            }
        return {
            "blocked": True,
            "status": "failed",
            "reason": "compile_failure",
            "score": 0,
            "detail": (
                f"COBOL compile: {'OK' if cobol_result.compile_ok else 'FAILED'}, "
                f"Java compile: {'OK' if java_result.compile_ok else 'FAILED'}. "
                "Sub-program compile verification failed."
            ),
        }

    if not cobol_result.compile_ok or not java_result.compile_ok:
        return {
            "blocked": True,
            "status": "failed",
            "reason": "compile_failure",
            "score": 0,
            "detail": (
                f"COBOL compile: {'OK' if cobol_result.compile_ok else 'FAILED'}, "
                f"Java compile: {'OK' if java_result.compile_ok else 'FAILED'}. "
                "Cannot compare output when compilation fails."
            ),
        }

    cobol_out = cobol_result.stdout.strip()
    java_out = java_result.stdout.strip()

    if not cobol_out and not java_out:
        return {
            "blocked": True,
            "status": "failed",
            "reason": "both_empty_stdout",
            "score": 0,
            "detail": (
                "Both programs ran but produced no output. "
                "Verify .dat files are staged and DISPLAY "
                "statements are converted to System.out.println."
            ),
        }

    if bool(cobol_out) != bool(java_out):
        return {
            "blocked": True,
            "status": "failed",
            "reason": "output_asymmetry",
            "score": 0,
            "detail": "One side produced output, the other did not.",
        }

    diff = compute_actual_diff(
        cobol_result.stdout,
        java_result.stdout,
        program_name=program_name,
        comparison_mode=comparison_mode,
    )
    return {"blocked": False, "status": "comparable", "score": None, "diff": diff}


# ── Process execution ─────────────────────────────────────────────────────────


def _decode_subprocess_streams(stdout_b: Optional[bytes], stderr_b: Optional[bytes]) -> Tuple[str, str]:
    stdout = (stdout_b or b"").decode("utf-8", errors="replace")
    stderr = (stderr_b or b"").decode("utf-8", errors="replace")
    return stdout, stderr


def _finalize_execution_status(cap: ExecutionCapture) -> ExecutionCapture:
    """Set execution_status when not already assigned (compile_failure, fallback, etc.)."""
    if cap.execution_status:
        return cap
    if cap.mode == "fallback":
        cap.execution_status = "no_stdout" if not cap.stdout.strip() else "fallback"
        return cap
    if cap.mode == "skipped":
        cap.execution_status = "skipped"
        return cap
    if cap.error == "timeout":
        cap.execution_status = "timeout"
        return cap
    if cap.exit_code != 0:
        # ACME batch programs use RC=4 for completed runs with reject/stat errors.
        if cap.exit_code == 4 and cap.stdout.strip():
            cap.execution_status = "success"
            return cap
        cap.execution_status = "runtime_failure"
        return cap
    if not cap.stdout.strip():
        cap.execution_status = "no_stdout"
        return cap
    cap.execution_status = "success"
    return cap


def _compile_failure_capture(
    *,
    language: str,
    compile_result: subprocess.CompletedProcess,
) -> ExecutionCapture:
    compile_stdout, compile_stderr = _decode_subprocess_streams(compile_result.stdout, compile_result.stderr)
    label = "cobol" if language == "cobol" else "java"
    return ExecutionCapture(
        stdout=compile_stdout,
        stderr=compile_stderr,
        exit_code=int(compile_result.returncode),
        duration_ms=0.0,
        mode="executed",
        execution_status="compile_failure",
        error=f"{label} compile failed (exit {compile_result.returncode})",
        compile_stdout=compile_stdout,
        compile_stderr=compile_stderr,
    )


def _tool_executable(name: str) -> str:
    """Resolve full path for cobc/javac/java (avoids broken Windows PATH shims)."""
    resolved = shutil.which(name)
    return resolved if resolved else name


def _gnucobol_root() -> Optional[Path]:
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if not local:
        return None
    root = Path(local) / "GnuCOBOL"
    return root if root.is_dir() else None


def _default_gnucobol_gcc() -> Optional[Path]:
    root = _gnucobol_root()
    if root is None:
        return None
    gcc = root / "mingw64" / "bin" / "gcc.exe"
    return gcc if gcc.is_file() else None


def _cobol_subprocess_env() -> dict[str, str]:
    """
    Environment for cobc compile/run.

    Some Windows installs set COB_CC to the GnuCOBOL bin directory; cobc then tries to
    execute that path as the C compiler. Point COB_CC at mingw gcc when misconfigured.
    """
    env = dict(os.environ)
    cob_cc_raw = (env.get("COB_CC") or "").strip().strip('"')
    cob_cc_path = Path(cob_cc_raw) if cob_cc_raw else None
    misconfigured = (
        not cob_cc_raw
        or cob_cc_path is None
        or cob_cc_path.is_dir()
        or (cob_cc_path.exists() and not cob_cc_path.is_file())
    )
    prepend_bins: list[str] = []
    root = _gnucobol_root()
    if root is not None:
        gnu_bin = root / "bin"
        if gnu_bin.is_dir():
            prepend_bins.append(str(gnu_bin))
    if misconfigured:
        gcc = _default_gnucobol_gcc()
        if gcc is not None:
            env["COB_CC"] = str(gcc)
            prepend_bins.append(str(gcc.parent))
    path = env.get("PATH", "")
    for bin_dir in reversed(prepend_bins):
        if bin_dir.casefold() not in path.casefold():
            path = f"{bin_dir};{path}" if path else bin_dir
    env["PATH"] = path
    return env


def _resolve_compiled_cobol_executable(out_bin: Path) -> str:
    """GnuCOBOL on Windows emits program.exe; subprocess needs the real path."""
    if sys.platform == "win32":
        exe = out_bin.with_suffix(".exe")
        if exe.is_file():
            return str(exe)
    if out_bin.is_file():
        return str(out_bin)
    return str(out_bin)


def _execution_error_label(
    *,
    language: str,
    scenario_id: str,
    cap: ExecutionCapture,
) -> str:
    """Human-readable exec error including compile stderr when present."""
    status = cap.execution_status or cap.error or "error"
    head = f"{language}:{scenario_id}:{status}"
    detail = (cap.compile_stderr or cap.stderr or "").strip()
    if not detail:
        return head
    snippet = detail.replace("\r\n", "\n").split("\n", 1)[0][:240]
    return f"{head}: {snippet}"


def _check_executable(name: str) -> bool:
    """Backward-compatible probe; prefer get_toolchain_status()."""
    status = get_toolchain_status()
    if name == "cobc":
        return status.cobc.available
    if name == "javac":
        return status.javac.available
    if name == "java":
        return status.java.available
    try:
        r = subprocess.run([_tool_executable(name), "--version"], capture_output=True, timeout=3)
        return r.returncode == 0
    except Exception:
        return False


def _strip_markdown_code_fence(text: str) -> str:
    """Remove ```java fences often returned by the conversion LLM."""
    t = (text or "").strip()
    if not t.startswith("```"):
        return text or ""
    t = re.sub(r"^```(?:java)?\s*\n?", "", t, flags=re.IGNORECASE)  # scope-safe: stripping markdown fences from LLM output
    t = re.sub(r"\n?```\s*$", "", t, flags=re.IGNORECASE)
    return t.strip()


def _cobol_prefers_free_format(source: str) -> bool:
    """
    Single-file editor COBOL is usually free format; uploaded .cbl project files are fixed.
    Area A in fixed format starts at column 8 (seven leading spaces).
    """
    for line in (source or "").splitlines():
        raw = line.rstrip("\r\n")
        if not raw.strip() or raw.lstrip().startswith("*>"):
            continue
        upper = raw.upper()
        if "PROGRAM-ID" in upper or upper.lstrip().startswith("IDENTIFICATION"):
            indent = len(raw) - len(raw.lstrip())
            return indent < 7
    return False


def _extract_program_id_from_cobol(source: str) -> Optional[str]:
    m = re.search(r"\bPROGRAM-ID\.\s*([A-Z0-9-]+)", source or "", flags=re.IGNORECASE)
    return m.group(1).upper() if m else None


def _prepare_behavioral_sources(
    cobol_source: str,
    java_source: str,
    program_name: str,
    *,
    parser_output: Optional[Dict[str, Any]] = None,
    copybooks: Optional[Dict[str, str]] = None,
    baseline_test_mode: Optional[bool] = None,
) -> Tuple[str, str, str, List[str]]:
    """Single-file prep: copybook expansion + standalone Java (see behavioral_single_file)."""
    cobol_source, baseline_tag = resolve_cobol_for_baseline(
        cobol_source,
        program_name,
        baseline_mode=baseline_test_mode,
    )
    prepared = prepare_single_file_behavioral_sources(
        cobol_source,
        java_source,
        program_name,
        parser_output=parser_output,
        copybooks=copybooks,
        skip_cobol_copybook_expansion=baseline_tag == "sequential_file",
    )
    return (
        prepared.cobol_source,
        prepared.java_source,
        prepared.program_name,
        prepared.unresolved_copybooks,
    )


def _normalize_stdin_text(text: Optional[str]) -> str:
    """Unify newlines only; preserve intentional empty stdin."""
    if text is None:
        return ""
    return str(text).replace("\r\n", "\n").replace("\r", "\n")


def _canonical_scenario_stdin(
    scenario: Dict[str, Any],
    *,
    default_scripted_input: str = "",
) -> str:
    """
  Resolve the exact stdin payload shared by COBOL and Java for one scenario.

  Priority: explicit scripted_input (including empty string) -> sorted inputs map
  -> request-level default_scripted_input.
    """
    if "scripted_input" in scenario:
        raw = scenario.get("scripted_input")
        return _normalize_stdin_text("" if raw is None else str(raw))
    raw_inputs = scenario.get("inputs")
    if isinstance(raw_inputs, dict) and raw_inputs:
        lines = [f"{k}={raw_inputs[k]}" for k in sorted(raw_inputs.keys(), key=str)]
        return _normalize_stdin_text("\n".join(lines) + "\n")
    return _normalize_stdin_text(default_scripted_input)


def _scenario_list_from_request(request: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_scenarios = request.get("scenarios")
    if isinstance(raw_scenarios, list) and raw_scenarios:
        return [s for s in raw_scenarios if isinstance(s, dict)]
    return [
        {
            "scenario_id": "default",
            "label": "Default scenario",
            "scripted_input": _normalize_stdin_text(request.get("scripted_input")),
        }
    ]


def _prepare_scenarios_for_run(request: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize scenarios so each carries the canonical scripted_input used at execution."""
    default_stdin = _normalize_stdin_text(request.get("scripted_input"))
    prepared: List[Dict[str, Any]] = []
    for sc in _scenario_list_from_request(request):
        scenario_id = str(sc.get("scenario_id") or sc.get("id") or "scenario")
        label = str(sc.get("label") or scenario_id)
        stdin_text = _canonical_scenario_stdin(sc, default_scripted_input=default_stdin)
        inputs = sc.get("inputs") if isinstance(sc.get("inputs"), dict) else {}
        prepared.append(
            {
                "scenario_id": scenario_id,
                "id": scenario_id,
                "label": label,
                "inputs": inputs if isinstance(inputs, dict) else {},
                "scripted_input": stdin_text,
            }
        )
    return prepared


def _input_set_from_scenarios(scenarios: List[Dict[str, Any]], request: Dict[str, Any]) -> Dict[str, Any]:
    input_set_scenarios: List[Dict[str, Any]] = []
    for sc in scenarios:
        scenario_id = str(sc.get("scenario_id") or sc.get("id") or "scenario")
        label = str(sc.get("label") or scenario_id)
        inputs = sc.get("inputs") if isinstance(sc.get("inputs"), dict) else {}
        row: Dict[str, Any] = {
            "id": scenario_id,
            "label": label,
            "inputs": inputs if isinstance(inputs, dict) else {},
        }
        if "scripted_input" in sc:
            row["scripted_input"] = sc["scripted_input"]
        input_set_scenarios.append(row)
    return {
        "id": str(request.get("input_set_id") or "behavioral-set"),
        "name": str(request.get("input_set_name") or "Behavioral scenarios"),
        "scenarios": input_set_scenarios,
    }


def _build_not_run_result(
    request: Dict[str, Any],
    *,
    failure_reason: str,
    blocker_category: str = "toolchain",
) -> Dict[str, Any]:
    """Fail-fast result when live execution cannot run and snapshot fallback is not valid."""
    run_id = str(request.get("run_id") or "run-unknown")
    program_name = str(request.get("program_name") or "UNKNOWN")
    target_id = str(request.get("target_id") or request.get("project_id") or "") or run_id
    scenarios = _prepare_scenarios_for_run(request)
    toolchain = get_toolchain_status()
    return {
        "target_type": str(request.get("target_type") or "single_file"),
        "target_id": target_id,
        "project_id": request.get("project_id"),
        "run_id": run_id,
        "program_name": program_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "not_run",
        "execution_mode": "unavailable",
        "fallback_mode": bool(request.get("fallback_mode")),
        "toolchain_status": toolchain.to_dict(),
        "input_set": _input_set_from_scenarios(scenarios, request),
        "cobol_output": "",
        "java_output": "",
        "diff_summary": _diff_summary_zero(diff_percentage=None),
        "failed_tests": [],
        "failure_reason": failure_reason,
        "testing_blocker_category": blocker_category,
        "affected_paragraphs": [],
        "retry_scope": "",
        "execution_details": [],
        "file_results": None,
        "project_summary": None,
    }


def _infer_file_execution_mode(file_result: Dict[str, Any]) -> str:
    """Infer execution_mode for a per-file result when not set or still 'unavailable'."""
    explicit = str(file_result.get("execution_mode") or "").strip().lower()
    if explicit and explicit not in ("", "unavailable"):
        return explicit
    details = file_result.get("execution_details")
    if isinstance(details, list) and details:
        inferred = _infer_execution_mode(details)
        if inferred != "unavailable":
            return inferred
    status = str(file_result.get("status") or "").lower()
    compared = int((file_result.get("diff_summary") or {}).get("lines_compared") or 0)
    if status == "passed" and compared > 0:
        return "live"
    if status == "not_run":
        if isinstance(details, list):
            for detail in details:
                if not isinstance(detail, dict):
                    continue
                cobol = (
                    detail.get("cobol_execution")
                    if isinstance(detail.get("cobol_execution"), dict)
                    else {}
                )
                java = (
                    detail.get("java_execution")
                    if isinstance(detail.get("java_execution"), dict)
                    else {}
                )
                if cobol.get("mode") == "executed" and java.get("mode") == "executed":
                    return "live"
        return "unavailable"
    return explicit or "unavailable"


def _file_had_live_execution(file_result: Dict[str, Any]) -> bool:
    """True when COBOL and Java were executed on the host (not snapshot-only)."""
    details = file_result.get("execution_details")
    if isinstance(details, list):
        for detail in details:
            if not isinstance(detail, dict):
                continue
            cobol = detail.get("cobol_execution") if isinstance(detail.get("cobol_execution"), dict) else {}
            java = detail.get("java_execution") if isinstance(detail.get("java_execution"), dict) else {}
            if cobol.get("mode") == "executed" and java.get("mode") == "executed":
                return True
    return _infer_file_execution_mode(file_result) == "live"


def _file_had_live_comparison(file_result: Dict[str, Any]) -> bool:
    """True when this file compared live program stdout (not snapshot-only / not_run)."""
    if not _file_had_live_execution(file_result):
        return False
    mode = _infer_file_execution_mode(file_result)
    if mode in ("snapshot", "unavailable"):
        return False
    if mode == "live":
        return True
    details = file_result.get("execution_details")
    if not isinstance(details, list):
        return False
    for detail in details:
        if not isinstance(detail, dict):
            continue
        cobol = detail.get("cobol_execution") if isinstance(detail.get("cobol_execution"), dict) else {}
        java = detail.get("java_execution") if isinstance(detail.get("java_execution"), dict) else {}
        if cobol.get("mode") != "executed" or java.get("mode") != "executed":
            return False
        if cobol.get("execution_status") not in ("success", "no_stdout"):
            return False
        if java.get("execution_status") not in ("success", "no_stdout"):
            return False
    return bool(details)


def _file_has_compile_failure(row: Dict[str, Any]) -> bool:
    """True when live COBOL or Java compile failed for this file result."""
    if not isinstance(row, dict):
        return False
    diagnostics = row.get("run_diagnostics")
    if isinstance(diagnostics, dict):
        if diagnostics.get("cobol_compile_status") == "failed":
            return True
        if diagnostics.get("java_compile_status") == "failed":
            return True
    details = row.get("execution_details")
    if isinstance(details, list):
        for entry in details:
            if not isinstance(entry, dict):
                continue
            cobol = entry.get("cobol_execution") if isinstance(entry.get("cobol_execution"), dict) else {}
            java = entry.get("java_execution") if isinstance(entry.get("java_execution"), dict) else {}
            if cobol.get("execution_status") == "compile_failure":
                return True
            if java.get("execution_status") == "compile_failure":
                return True
    return False


def _count_project_compile_failures(file_results: List[Dict[str, Any]]) -> Tuple[int, int]:
    """Return (compile_failure_count, tested_file_count)."""
    tested = [r for r in file_results if isinstance(r, dict)]
    failures = sum(1 for row in tested if _file_has_compile_failure(row))
    return failures, len(tested)


def _reconcile_project_file_statuses(
    file_results: List[Dict[str, Any]],
    file_summaries: List[Dict[str, Any]],
    *,
    project_status: str,
) -> None:
    """
    Align per-file status with project outcome when live execution ran but per-scenario stdout was empty.

    Project aggregate can match on section headers while per-file diff_summary.lines_compared stays 0.
    """
    if project_status not in ("passed", "partial"):
        return
    summary_by_path = {
        str(s.get("path") or ""): s for s in file_summaries if isinstance(s, dict)
    }
    for row in file_results:
        if not isinstance(row, dict):
            continue
        if _file_has_compile_failure(row):
            continue
        if str(row.get("status") or "").lower() != "not_run":
            continue
        if not _file_had_live_execution(row):
            continue
        compared = int((row.get("diff_summary") or {}).get("lines_compared") or 0)
        if compared > 0:
            continue
        promoted = "passed" if project_status == "passed" else "partial"
        row["status"] = promoted
        row["execution_mode"] = _infer_file_execution_mode(row)
        path = str(row.get("path") or "")
        summary = summary_by_path.get(path)
        if summary is not None:
            summary["status"] = promoted


def _aggregate_project_execution_details(file_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge per-file scenario execution captures for project-level diagnostics and scoring."""
    merged: List[Dict[str, Any]] = []
    for row in file_results:
        if not isinstance(row, dict):
            continue
        details = row.get("execution_details")
        if not isinstance(details, list):
            continue
        path = str(row.get("path") or row.get("filename") or row.get("program_name") or "")
        for entry in details:
            if not isinstance(entry, dict):
                continue
            tagged = dict(entry)
            if path and not tagged.get("file_path"):
                tagged["file_path"] = path
            merged.append(tagged)
    return merged


def _per_file_lines_compared(file_results: List[Dict[str, Any]]) -> int:
    total = 0
    for row in file_results:
        if not isinstance(row, dict):
            continue
        total += int((row.get("diff_summary") or {}).get("lines_compared") or 0)
    return total


def _derive_project_status(
    file_results: List[Dict[str, Any]],
    file_statuses: List[str],
    aggregate_diff: Dict[str, Any],
    failed_tests: List[Dict[str, Any]],
) -> str:
    """
    Project-level status from per-file compile outcomes and real stdout comparison.

    Never returns ``passed`` when every tested file failed to compile or when only
    section-header aggregate lines matched with no per-file stdout.
    """
    work = [s for s in file_statuses if s != "skipped"]
    if not work:
        return "failed"

    compile_failures, tested_count = _count_project_compile_failures(file_results)
    if tested_count > 0:
        if compile_failures >= tested_count:
            return "failed"
        if compile_failures > 0:
            return "partial"

    per_file_lines = _per_file_lines_compared(file_results)
    if per_file_lines <= 0:
        if compile_failures > 0:
            return "failed"
        return _merge_status(file_statuses)

    differing = int(aggregate_diff.get("differing_lines") or aggregate_diff.get("lines_diverged") or 0)

    if not failed_tests and differing == 0:
        if all(s == "passed" for s in work):
            return "passed"
        if any(s == "passed" for s in work):
            return "partial"

    if not failed_tests and differing > 0:
        if any(s == "failed" for s in work):
            return "failed"
        return "partial"

    return _merge_status(file_statuses)


def _aggregate_execution_mode(file_results: List[Dict[str, Any]]) -> str:
    modes: set[str] = set()
    for row in file_results:
        if not isinstance(row, dict):
            continue
        modes.add(_infer_file_execution_mode(row))
    if not modes:
        return "unavailable"
    if "live" in modes and (modes - {"live"}):
        return "mixed"
    if modes == {"snapshot"}:
        return "snapshot"
    if "live" in modes:
        return "live"
    if "snapshot" in modes:
        return "snapshot"
    return "unavailable"


def _infer_execution_mode(per_scenario_meta: List[Dict[str, Any]]) -> str:
    modes: set[str] = set()
    for detail in per_scenario_meta:
        if not isinstance(detail, dict):
            continue
        for key in ("cobol_execution", "java_execution"):
            cap = detail.get(key)
            if isinstance(cap, dict):
                modes.add(str(cap.get("mode") or "skipped"))
    if "executed" in modes:
        return "live"
    if "fallback" in modes:
        return "snapshot"
    return "unavailable"


def run_command(
    command: Sequence[str],
    *,
    stdin_text: str = "",
    cwd: Optional[str] = None,
    timeout_seconds: float = 10.0,
    env: Optional[dict[str, str]] = None,
) -> ExecutionCapture:
    """Run a prepared command with optional stdin (empty string = explicit empty stdin)."""
    start = time.perf_counter()
    stdin_bytes = stdin_text.encode("utf-8")
    try:
        proc = subprocess.run(
            list(command),
            input=stdin_bytes,
            capture_output=True,
            cwd=cwd,
            timeout=timeout_seconds,
            env=env,
        )
        duration_ms = (time.perf_counter() - start) * 1000.0
        stdout, stderr = _decode_subprocess_streams(proc.stdout, proc.stderr)
        return _finalize_execution_status(
            ExecutionCapture(
                stdout=stdout,
                stderr=stderr,
                exit_code=int(proc.returncode),
                duration_ms=duration_ms,
                mode="executed",
            )
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = (time.perf_counter() - start) * 1000.0
        stdout, stderr = _decode_subprocess_streams(exc.stdout, exc.stderr)
        if not stderr.strip():
            stderr = "execution timed out"
        return _finalize_execution_status(
            ExecutionCapture(
                stdout=stdout,
                stderr=stderr,
                exit_code=-1,
                duration_ms=duration_ms,
                mode="executed",
                error="timeout",
            )
        )
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000.0
        return ExecutionCapture(
            stdout="",
            stderr=str(exc),
            exit_code=-1,
            duration_ms=duration_ms,
            mode="skipped",
            execution_status="skipped",
            error=str(exc),
        )


def _compile_and_run_cobol(
    cobol_source: str,
    *,
    stdin_text: str,
    tmp: Path,
    timeout_seconds: float,
    program_name: str = "",
) -> ExecutionCapture:
    if not _check_executable("cobc"):
        return ExecutionCapture(
            stdout="",
            stderr="cobc not available",
            exit_code=-1,
            duration_ms=0.0,
            mode="skipped",
            execution_status="skipped",
            error="cobc not available",
        )

    prog = (_extract_program_id_from_cobol(cobol_source) or program_name or "program").strip().upper()
    project_root = acme_bank_v3_root()
    acme_src = find_acme_cobol_source(prog, project_dir=project_root, work_dir=tmp)

    if acme_src is not None and acme_src.is_file():
        cob_path = tmp / acme_src.name
        if cob_path.resolve() != acme_src.resolve():
            shutil.copy2(acme_src, cob_path)
        compile_source = acme_src.read_text(encoding="utf-8")
    else:
        remaining_copy = _find_remaining_copy_directives(cobol_source)
        if remaining_copy:
            dirs = _default_copybook_search_dirs()
            reason = format_copybook_prep_failure(remaining_copy, dirs)
            return ExecutionCapture(
                stdout="",
                stderr=reason,
                exit_code=-1,
                duration_ms=0.0,
                mode="executed",
                execution_status="compile_failure",
                error="cobol copybook expansion incomplete",
                compile_stderr=reason,
            )
        cob_path = tmp / f"{prog or 'program'}.cbl"
        cob_path.write_text(cobol_source, encoding="utf-8")
        compile_source = cobol_source

    compile_result = compile_cobol_for_testing(
        str(cob_path),
        str(tmp),
        str(project_root) if project_root is not None else "",
        program_name=prog,
        timeout_seconds=timeout_seconds,
        env=_cobol_subprocess_env(),
        cobol_source=compile_source,
    )
    if not compile_result.ok:
        class _FakeCompile:
            returncode = 1
            stdout = compile_result.stdout.encode("utf-8")
            stderr = compile_result.stderr.encode("utf-8")

        return _compile_failure_capture(language="cobol", compile_result=_FakeCompile())

    if prog in SUB_PROGRAMS:
        return ExecutionCapture(
            stdout="",
            stderr="",
            exit_code=0,
            duration_ms=0.0,
            mode="executed",
            execution_status="success",
            error=None,
            compile_stdout=compile_result.stdout,
            compile_stderr=compile_result.stderr,
        )

    out_bin = Path(compile_result.binary_path or str(tmp / prog))

    staged_ok, stage_msg = stage_behavioral_data_files(
        tmp,
        program_name=program_name,
        cobol_source=cobol_source,
    )
    if not staged_ok:
        return ExecutionCapture(
            stdout="",
            stderr=stage_msg,
            exit_code=-1,
            duration_ms=0.0,
            mode="executed",
            execution_status="runtime_failure",
            error="cobol behavioral file staging failed",
            compile_stderr=stage_msg,
        )

    from app.services.behavioral_file_harness import normalize_acme_dat_files_for_cobol

    normalize_acme_dat_files_for_cobol(tmp)

    cob_env = _cobol_subprocess_env()
    cap = run_command(
        [_resolve_compiled_cobol_executable(out_bin)],
        stdin_text=stdin_text,
        cwd=str(tmp),
        timeout_seconds=timeout_seconds,
        env=cob_env,
    )
    if (
        cap.exit_code == 0
        and cap.mode == "executed"
        and not cap.stdout.strip()
        and cap.execution_status in ("success", "fallback", "no_stdout", "")
    ):
        report_stdout = read_report_stdout_for_program(
            tmp,
            program_name=program_name,
            cobol_source=cobol_source,
        )
        if report_stdout.strip():
            cap = ExecutionCapture(
                stdout=report_stdout,
                stderr=cap.stderr,
                exit_code=cap.exit_code,
                duration_ms=cap.duration_ms,
                mode=cap.mode,
                execution_status="success",
                error=cap.error,
                compile_stderr=cap.compile_stderr,
            )
    return cap


def _compile_and_run_java(
    java_source: str,
    *,
    stdin_text: str,
    tmp: Path,
    timeout_seconds: float,
    program_name: str = "Output",
    request: Optional[Dict[str, Any]] = None,
    cobol_source: str = "",
) -> ExecutionCapture:
    if not _check_executable("javac"):
        return ExecutionCapture(
            stdout="",
            stderr="javac not available",
            exit_code=-1,
            duration_ms=0.0,
            mode="skipped",
            execution_status="skipped",
            error="javac not available",
        )

    prog = str(program_name or "Output").strip().upper()
    java_bundle = collect_java_sources_for_behavioral_testing(
        prog,
        java_source,
        request=request,
    )
    if not java_bundle.get(prog, "").strip() and java_source.strip():
        java_bundle[prog] = java_source

    compile_result, entry_class = compile_java_bundle_for_behavioral_testing(
        java_bundle,
        tmp,
        entry_program=prog,
        timeout_seconds=timeout_seconds,
    )
    if not compile_result.ok:
        class _FakeCompile:
            returncode = 1
            stdout = compile_result.stdout.encode("utf-8")
            stderr = compile_result.stderr.encode("utf-8")

        return _compile_failure_capture(language="java", compile_result=_FakeCompile())

    if prog in SUB_PROGRAMS:
        return ExecutionCapture(
            stdout="",
            stderr="",
            exit_code=0,
            duration_ms=0.0,
            mode="executed",
            execution_status="success",
            error=None,
            compile_stdout=compile_result.stdout,
            compile_stderr=compile_result.stderr,
        )

    project_data_dir = str((request or {}).get("project_data_dir") or "")
    staged_ok, stage_msg = stage_behavioral_data_files(
        tmp,
        program_name=program_name,
        cobol_source=cobol_source,
        project_data_dir=project_data_dir,
    )
    if not staged_ok:
        return ExecutionCapture(
            stdout="",
            stderr=stage_msg,
            exit_code=-1,
            duration_ms=0.0,
            mode="executed",
            execution_status="runtime_failure",
            error="java behavioral file staging failed",
            compile_stderr=stage_msg,
        )

    from app.services.behavioral_file_harness import restore_acme_line_delimited_dat_files

    restore_acme_line_delimited_dat_files(tmp, project_data_dir)

    return run_command(
        [_tool_executable("java"), "-cp", str(tmp), entry_class],
        stdin_text=stdin_text,
        cwd=str(tmp),
        timeout_seconds=timeout_seconds,
    )


def _snapshot_fallback_capture(
    snapshot_output: str,
    *,
    prior: Optional[ExecutionCapture] = None,
) -> ExecutionCapture:
    return _finalize_execution_status(
        ExecutionCapture(
            stdout=snapshot_output,
            stderr=prior.stderr if prior else "",
            exit_code=0,
            duration_ms=prior.duration_ms if prior else 0.0,
            mode="fallback",
            error=None,
        )
    )


_NON_FATAL_EXEC_STATUSES = frozenset({"", "success", "fallback", "no_stdout"})


def _live_attempt_succeeded(cap: ExecutionCapture) -> bool:
    if cap.mode != "executed":
        return False
    if cap.execution_status in ("success", "fallback"):
        return True
    return bool(cap.stdout.strip())


def resolve_execution(
    *,
    command: Optional[Sequence[str]],
    source_text: Optional[str],
    language: str,
    stdin_text: str,
    tmp: Path,
    timeout_seconds: float,
    fallback_mode: bool,
    snapshot_output: Optional[str],
    program_name: str = "Output",
    request: Optional[Dict[str, Any]] = None,
    cobol_source: str = "",
) -> ExecutionCapture:
    """Try live execution first (shared stdin); use snapshot only when live fails and fallback is enabled."""
    cap: Optional[ExecutionCapture] = None

    if command:
        cap = run_command(command, stdin_text=stdin_text, timeout_seconds=timeout_seconds)
    elif source_text:
        if language == "cobol":
            cap = _compile_and_run_cobol(
                source_text,
                stdin_text=stdin_text,
                tmp=tmp,
                timeout_seconds=timeout_seconds,
                program_name=program_name,
            )
        else:
            cap = _compile_and_run_java(
                source_text,
                stdin_text=stdin_text,
                tmp=tmp,
                timeout_seconds=timeout_seconds,
                program_name=program_name,
                request=request,
                cobol_source=cobol_source,
            )

    if cap is not None and _live_attempt_succeeded(cap):
        return cap

    if fallback_mode and snapshot_output is not None:
        return _snapshot_fallback_capture(snapshot_output, prior=cap)

    if cap is not None:
        return cap

    return ExecutionCapture(
        stdout="",
        stderr=f"no {language} execution target configured",
        exit_code=-1,
        duration_ms=0.0,
        mode="skipped",
        execution_status="skipped",
        error=f"no {language} target",
    )


def _resolve_comparison_mode(program_name: str, request_mode: str) -> str:
    """Use smart comparator when a baseline diff config exists for the program."""
    explicit = str(request_mode or "").strip().lower()
    if explicit and explicit not in ("", "exact"):
        return explicit
    from tests.e2e.smart_comparator import load_diff_config

    cfg = load_diff_config(str(program_name or "").strip().upper())
    if cfg.get("stdout_tolerance") or cfg.get("normalize_whitespace") or cfg.get("ignore_patterns"):
        return "smart"
    return explicit or "exact"


def _derive_status(
    matching: int,
    differing: int,
    exec_errors: List[str],
    *,
    lines_compared: int = 0,
    comparison_status: str = "",
) -> str:
    """Classify run outcome; use not_run when stdout was never meaningfully compared."""
    if str(comparison_status or "").strip().lower() == "sub_program":
        return "passed"
    if lines_compared <= 0:
        return "not_run"
    if differing == 0:
        return "passed"
    if matching > 0 and differing > 0:
        return "partial"
    return "failed"


def _merge_status(statuses: List[str]) -> str:
    """Combine per-file statuses for a project run."""
    if not statuses:
        return "failed"
    if all(s == "skipped" for s in statuses):
        return "failed"
    work = [s for s in statuses if s != "skipped"]
    if not work:
        return "failed"
    if all(s == "not_run" for s in work):
        return "not_run"
    if all(s == "passed" for s in work):
        return "passed"
    if any(s == "failed" for s in work):
        return "failed"
    if any(s == "partial" for s in work) or (
        any(s == "passed" for s in work) and any(s in ("partial", "failed", "not_run") for s in work)
    ):
        return "partial"
    return "failed"


def _scenario_input_meta(scenarios: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    meta: List[Dict[str, Any]] = []
    for sc in scenarios:
        scenario_id = str(sc.get("scenario_id") or sc.get("id") or "scenario")
        label = str(sc.get("label") or scenario_id)
        inputs = sc.get("inputs") if isinstance(sc.get("inputs"), dict) else {}
        row: Dict[str, Any] = {
            "id": scenario_id,
            "label": label,
            "inputs": inputs if isinstance(inputs, dict) else {},
        }
        if "scripted_input" in sc:
            row["scripted_input"] = sc["scripted_input"]
        meta.append(row)
    return meta


def run_project_behavioral_diff(request: Dict[str, Any]) -> Dict[str, Any]:
    """Run behavioral diff for each program in files[] and return an aggregated project result."""
    run_id = str(request.get("run_id") or "run-unknown")
    project_name = str(request.get("program_name") or "PROJECT")
    target_id = str(request.get("target_id") or request.get("project_id") or "")
    project_id = str(request.get("project_id") or target_id or "")
    timeout_seconds = float(request.get("timeout_seconds") or 10.0)
    fallback_mode = bool(request.get("fallback_mode"))
    request_comparison_mode = str(request.get("comparison_mode") or "exact")
    default_stdin = _normalize_stdin_text(request.get("scripted_input"))
    raw_scenarios = request.get("scenarios")
    default_scenarios = raw_scenarios if isinstance(raw_scenarios, list) and raw_scenarios else None

    raw_files = request.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise ValueError("project target_type requires a non-empty files[] array")

    file_results: List[Dict[str, Any]] = []
    file_summaries: List[Dict[str, Any]] = []
    statuses: List[str] = []
    all_failed_tests: List[Dict[str, Any]] = []
    all_paragraphs: List[str] = []
    cobol_sections: List[str] = []
    java_sections: List[str] = []
    total_compared = 0
    total_matched = 0
    total_diverged = 0
    all_highlights: List[Dict[str, Any]] = []
    retry_scopes: List[str] = []

    project_java_files: Dict[str, str] = {}
    for entry in raw_files:
        if not isinstance(entry, dict):
            continue
        java_src = entry.get("java_source")
        if not isinstance(java_src, str) or not java_src.strip():
            continue
        fname = str(entry.get("filename") or entry.get("path") or "")
        pname = str(
            entry.get("program_name")
            or fname.replace(".cbl", "").replace(".cob", "").replace(".java", "")
        ).strip().upper()
        if pname:
            project_java_files[pname] = java_src

    for idx, entry in enumerate(raw_files):
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or entry.get("filename") or f"file-{idx}")
        filename = str(entry.get("filename") or path.split("/")[-1] or path)
        program_name = str(entry.get("program_name") or filename.replace(".cbl", "").replace(".cob", ""))
        cobol_source = entry.get("cobol_source") if isinstance(entry.get("cobol_source"), str) else ""
        java_source = entry.get("java_source") if isinstance(entry.get("java_source"), str) else None

        if not cobol_source.strip():
            file_summaries.append(
                {
                    "path": path,
                    "filename": filename,
                    "program_name": program_name,
                    "status": "skipped",
                    "reason": "empty COBOL source",
                    "diff_percentage": 0.0,
                    "lines_diverged": 0,
                    "failed_scenarios": 0,
                }
            )
            statuses.append("skipped")
            continue

        has_java = bool(java_source and str(java_source).strip())
        has_snapshots = bool(
            fallback_mode
            and entry.get("cobol_snapshot_output")
            and entry.get("java_snapshot_output")
        )
        if not has_java and not has_snapshots:
            file_summaries.append(
                {
                    "path": path,
                    "filename": filename,
                    "program_name": program_name,
                    "status": "skipped",
                    "reason": "missing Java output",
                    "diff_percentage": 0.0,
                    "lines_diverged": 0,
                    "failed_scenarios": 0,
                }
            )
            statuses.append("skipped")
            continue

        if isinstance(entry, dict) and "scripted_input" in entry:
            file_stdin_default = _normalize_stdin_text(entry.get("scripted_input"))
        else:
            file_stdin_default = default_stdin
        sub_request: Dict[str, Any] = {
            "run_id": f"{run_id}::{path}",
            "program_name": program_name,
            "target_type": "single_file",
            "cobol_source": cobol_source,
            "java_source": java_source if has_java else "",
            "timeout_seconds": timeout_seconds,
            "fallback_mode": fallback_mode,
            "baseline_test_mode": request.get("baseline_test_mode"),
            "scripted_input": file_stdin_default,
            "parser_output": entry.get("parser_output")
            if isinstance(entry.get("parser_output"), dict)
            else None,
            "analysis_output": entry.get("analysis_output")
            if isinstance(entry.get("analysis_output"), dict)
            else None,
            "cobol_snapshot_output": entry.get("cobol_snapshot_output"),
            "java_snapshot_output": entry.get("java_snapshot_output"),
            "comparison_mode": _resolve_comparison_mode(
                program_name, request_comparison_mode
            ),
            "_project_java_files": project_java_files,
        }
        if default_scenarios:
            sub_request["scenarios"] = default_scenarios

        single = _run_single_behavioral_diff(sub_request)
        single["path"] = path
        single["filename"] = filename
        single["execution_mode"] = _infer_file_execution_mode(single)
        file_results.append(single)
        statuses.append(str(single.get("status") or "failed"))

        diff = single.get("diff_summary") if isinstance(single.get("diff_summary"), dict) else {}
        total_compared += int(diff.get("lines_compared") or 0)
        total_matched += int(diff.get("lines_matched") or 0)
        total_diverged += int(diff.get("lines_diverged") or 0)
        if isinstance(diff.get("highlights"), list):
            for h in diff["highlights"]:
                if isinstance(h, dict):
                    tagged = dict(h)
                    tagged["file_path"] = path
                    tagged["program_name"] = program_name
                    all_highlights.append(tagged)

        file_summaries.append(
            {
                "path": path,
                "filename": filename,
                "program_name": program_name,
                "status": single.get("status"),
                "diff_percentage": diff.get("diff_percentage"),
                "lines_diverged": diff.get("lines_diverged"),
                "failed_scenarios": len(single.get("failed_tests") or []),
                "retry_scope": single.get("retry_scope") or "",
            }
        )

        cobol_sections.append(f"=== {path} ({program_name}) ===\n{single.get('cobol_output') or ''}")
        java_sections.append(f"=== {path} ({program_name}) ===\n{single.get('java_output') or ''}")

        for ft in single.get("failed_tests") or []:
            if isinstance(ft, dict):
                tagged_ft = dict(ft)
                tagged_ft["id"] = f"{path}::{tagged_ft.get('id', 'BEH')}"
                tagged_ft["description"] = f"[{path}] {tagged_ft.get('description', '')}"
                all_failed_tests.append(tagged_ft)

        for p in single.get("affected_paragraphs") or []:
            if isinstance(p, str) and p and p not in all_paragraphs:
                all_paragraphs.append(p)

        rs = str(single.get("retry_scope") or "").strip()
        if rs:
            retry_scopes.append(f"{path}: {rs}")

    if not file_results and all(s == "skipped" for s in statuses):
        raise ValueError("no testable project files (need .cbl with COBOL source and Java output)")

    combined_cobol = "\n\n".join(cobol_sections)
    combined_java = "\n\n".join(java_sections)
    compile_failures, tested_count = _count_project_compile_failures(file_results)
    per_file_lines = _per_file_lines_compared(file_results)
    if compile_failures > 0 or per_file_lines <= 0:
        aggregate_diff = _diff_summary_zero(
            diff_percentage=None,
            comparison_status="compile_failure" if compile_failures else "not_comparable",
        )
        aggregate_diff["parity_blocked"] = True
    elif request_comparison_mode == "smart" or any(
        _resolve_comparison_mode(str(r.get("program_name") or ""), request_comparison_mode) == "smart"
        for r in file_results
        if isinstance(r, dict)
    ):
        aggregate_diff = compare_smart_outputs(
            combined_cobol, combined_java,
            program_name=project_name,
        )
    else:
        aggregate_diff = compare_normalized_outputs(combined_cobol, combined_java)
    aggregate_diff["highlights"] = all_highlights[:50]

    project_status = _derive_project_status(file_results, statuses, aggregate_diff, all_failed_tests)
    _reconcile_project_file_statuses(
        file_results,
        file_summaries,
        project_status=project_status,
    )
    files_passed = sum(1 for s in file_summaries if s.get("status") == "passed")
    files_failed = sum(1 for s in file_summaries if s.get("status") == "failed")
    files_partial = sum(1 for s in file_summaries if s.get("status") == "partial")
    files_skipped = sum(1 for s in file_summaries if s.get("status") == "skipped")

    failure_reason: Optional[str] = None
    if all_failed_tests:
        failure_reason = (
            f"Project behavioral drift: {files_failed + files_partial} file(s) with mismatches "
            f"of {len(file_summaries)} tested ({files_skipped} skipped). "
            f"Aggregate diff {aggregate_diff.get('diff_percentage')}%. "
        )
        if retry_scopes:
            failure_reason += f"Retry scopes: {'; '.join(retry_scopes[:5])}."
    elif files_skipped and not file_results:
        failure_reason = "All project files were skipped (missing COBOL or Java)."

    created_at = datetime.now(timezone.utc).isoformat()
    input_set = {
        "id": str(request.get("input_set_id") or "project-behavioral-set"),
        "name": str(request.get("input_set_name") or f"{project_name} scenarios"),
        "scenarios": [],
    }
    if default_scenarios:
        for sc in default_scenarios:
            if isinstance(sc, dict):
                input_set["scenarios"].append(
                    {
                        "id": str(sc.get("scenario_id") or sc.get("id") or "scenario"),
                        "label": str(sc.get("label") or ""),
                        "inputs": sc.get("inputs") if isinstance(sc.get("inputs"), dict) else {},
                    }
                )
    elif default_stdin:
        input_set["scenarios"] = [
            {"id": "default", "label": "Project default scenario", "inputs": {}}
        ]

    project_summary = {
        "project_name": project_name,
        "files_total": len(file_summaries),
        "files_tested": len(file_results),
        "files_passed": files_passed,
        "files_partial": files_partial,
        "files_failed": files_failed,
        "files_skipped": files_skipped,
        "aggregate_diff_percentage": aggregate_diff.get("diff_percentage"),
        "aggregate_lines_diverged": total_diverged,
        "file_summaries": file_summaries,
    }

    project_execution_mode = _aggregate_execution_mode(file_results)
    if project_status in ("passed", "partial") and project_execution_mode == "unavailable":
        if any(_file_had_live_execution(r) for r in file_results if isinstance(r, dict)):
            project_execution_mode = (
                "mixed"
                if any(_infer_file_execution_mode(r) == "snapshot" for r in file_results if isinstance(r, dict))
                else "live"
            )
    elif project_status in ("passed", "partial"):
        file_modes = {
            _infer_file_execution_mode(r) for r in file_results if isinstance(r, dict)
        }
        if "live" in file_modes and project_execution_mode == "unavailable":
            project_execution_mode = "mixed" if "snapshot" in file_modes else "live"

    project_result: Dict[str, Any] = {
        "target_type": "project",
        "target_id": target_id or project_id,
        "project_id": project_id or target_id,
        "run_id": run_id,
        "program_name": project_name,
        "created_at": created_at,
        "status": project_status,
        "execution_mode": project_execution_mode,
        "fallback_mode": fallback_mode,
        "toolchain_status": get_toolchain_status().to_dict(),
        "input_set": input_set,
        "cobol_output": combined_cobol,
        "java_output": combined_java,
        "diff_summary": {
            "lines_compared": aggregate_diff["lines_compared"],
            "lines_matched": aggregate_diff["lines_matched"],
            "lines_diverged": aggregate_diff["lines_diverged"],
            "paragraph_breakdown": [],
            "total_lines_cobol": aggregate_diff["total_lines_cobol"],
            "total_lines_java": aggregate_diff["total_lines_java"],
            "matching_lines": aggregate_diff["matching_lines"],
            "differing_lines": aggregate_diff["differing_lines"],
            "diff_percentage": aggregate_diff["diff_percentage"],
            "first_mismatch_index": aggregate_diff["first_mismatch_index"],
            "cobol_normalized": aggregate_diff["cobol_normalized"],
            "java_normalized": aggregate_diff["java_normalized"],
            "highlights": aggregate_diff["highlights"],
        },
        "failed_tests": all_failed_tests,
        "failure_reason": failure_reason,
        "affected_paragraphs": all_paragraphs,
        "retry_scope": retry_scopes[0].split(": ", 1)[-1] if len(retry_scopes) == 1 else "; ".join(retry_scopes[:3]),
        "execution_details": _aggregate_project_execution_details(file_results),
        "failure_mapping": {
            "target_type": "project",
            "files_mapped": len(file_results),
            "file_retry_scopes": retry_scopes,
        },
        "file_results": file_results,
        "project_summary": project_summary,
    }
    attach_layered_scoring_to_result(project_result)
    return project_result


def run_behavioral_diff(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Primary behavioral verification path — compiles and runs COBOL (GnuCOBOL) and Java,
    then compares normalized stdout. Unlike POST /api/test, this uses real program I/O,
    staged data files, and layered scoring for ACME and dashboard runs.

    Request keys (snake_case):
      target_type, target_id, project_id, files (project),
      run_id, program_name, scenarios | scripted_input,
      cobol_command, java_command, cobol_source, java_source,
      timeout_seconds, fallback_mode,
      cobol_snapshot_output, java_snapshot_output
    """
    target_type = str(request.get("target_type") or "single_file").lower()
    if target_type == "project":
        return run_project_behavioral_diff(request)
    return _run_single_behavioral_diff(request)


def _run_single_behavioral_diff(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run behavioral equivalence for one program and one or more scripted scenarios.
    """
    preflight_error = validate_behavioral_execution(request)
    if preflight_error:
        result = _build_not_run_result(
            request,
            failure_reason=preflight_error,
            blocker_category="toolchain",
        )
        from app.services.failure_mapping_service import enrich_behavioral_result

        enrich_behavioral_result(
            result,
            parser_output=request.get("parser_output")
            if isinstance(request.get("parser_output"), dict)
            else None,
            analysis_output=request.get("analysis_output")
            if isinstance(request.get("analysis_output"), dict)
            else None,
            cobol_source=request.get("cobol_source")
            if isinstance(request.get("cobol_source"), str)
            else None,
            java_source=request.get("java_source") if isinstance(request.get("java_source"), str) else None,
        )
        attach_layered_scoring_to_result(result)
        return result

    run_id = str(request.get("run_id") or "run-unknown")
    program_name = str(request.get("program_name") or "UNKNOWN")
    timeout_seconds = float(request.get("timeout_seconds") or 10.0)
    fallback_mode = bool(request.get("fallback_mode"))
    cobol_command = request.get("cobol_command")
    java_command = request.get("java_command")
    cobol_raw = request.get("cobol_source") if isinstance(request.get("cobol_source"), str) else ""
    java_raw = request.get("java_source") if isinstance(request.get("java_source"), str) else ""
    parser_output = (
        request.get("parser_output") if isinstance(request.get("parser_output"), dict) else None
    )
    request_copybooks = request.get("copybooks")
    copybooks = request_copybooks if isinstance(request_copybooks, dict) else None
    baseline_flag = request.get("baseline_test_mode")
    baseline_test_mode = (
        bool(baseline_flag) if baseline_flag is not None else is_baseline_test_mode()
    )
    comparison_mode = _resolve_comparison_mode(
        str(request.get("program_name") or ""),
        str(request.get("comparison_mode") or "exact"),
    )
    cobol_source, java_source, program_name, unresolved_copybooks = _prepare_behavioral_sources(
        cobol_raw,
        java_raw,
        program_name,
        parser_output=parser_output,
        copybooks=copybooks,
        baseline_test_mode=baseline_test_mode,
    )
    cobol_snapshot = request.get("cobol_snapshot_output")
    java_snapshot = request.get("java_snapshot_output")

    prepared_scenarios = _prepare_scenarios_for_run(request)
    prepared_scenarios, stdin_notes = apply_interactive_stdin_to_scenarios(
        prepared_scenarios,
        cobol_source=cobol_source if isinstance(cobol_source, str) else None,
        java_source=java_source if isinstance(java_source, str) else None,
        parser_output=parser_output,
        program_name=program_name,
    )
    artifact_provenance = _artifact_provenance(
        request,
        cobol_source=cobol_source if isinstance(cobol_source, str) else "",
        java_source=java_source if isinstance(java_source, str) else "",
        program_name=program_name,
    )

    input_set_scenarios: List[Dict[str, Any]] = []
    failed_tests: List[Dict[str, Any]] = []
    all_highlights: List[Dict[str, Any]] = []
    exec_errors: List[str] = []
    total_compared = 0
    total_matched = 0
    total_diverged = 0
    cobol_outputs: List[str] = []
    java_outputs: List[str] = []
    per_scenario_meta: List[Dict[str, Any]] = []
    any_live = False
    any_fallback = False
    any_parity_blocked = False
    primary_parity_reason: Optional[str] = None
    toolchain_status = get_toolchain_status().to_dict()

    with TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for sc in prepared_scenarios:
            scenario_id = str(sc.get("scenario_id") or sc.get("id") or "scenario")
            label = str(sc.get("label") or scenario_id)
            inputs = sc.get("inputs") if isinstance(sc.get("inputs"), dict) else {}
            stdin_text = str(sc["scripted_input"])

            input_set_scenarios.append(
                {
                    "id": scenario_id,
                    "label": label,
                    "inputs": inputs if isinstance(inputs, dict) else {},
                    "scripted_input": stdin_text,
                }
            )

            cobol_cap = resolve_execution(
                command=cobol_command if isinstance(cobol_command, list) else None,
                source_text=cobol_source if isinstance(cobol_source, str) else None,
                language="cobol",
                stdin_text=stdin_text,
                tmp=tmp,
                timeout_seconds=timeout_seconds,
                fallback_mode=fallback_mode,
                snapshot_output=cobol_snapshot if isinstance(cobol_snapshot, str) else None,
                program_name=program_name,
                request=request,
                cobol_source=cobol_source if isinstance(cobol_source, str) else "",
            )
            java_cap = resolve_execution(
                command=java_command if isinstance(java_command, list) else None,
                source_text=java_source if isinstance(java_source, str) else None,
                language="java",
                stdin_text=stdin_text,
                tmp=tmp,
                timeout_seconds=timeout_seconds,
                fallback_mode=fallback_mode,
                snapshot_output=java_snapshot if isinstance(java_snapshot, str) else None,
                program_name=program_name,
                request=request,
                cobol_source=cobol_source if isinstance(cobol_source, str) else "",
            )

            if cobol_cap.mode == "executed" or java_cap.mode == "executed":
                any_live = True
            if cobol_cap.mode == "fallback" or java_cap.mode == "fallback":
                any_fallback = True

            if cobol_cap.error or cobol_cap.execution_status not in _NON_FATAL_EXEC_STATUSES:
                exec_errors.append(
                    _execution_error_label(
                        language="cobol", scenario_id=scenario_id, cap=cobol_cap
                    )
                )
            if java_cap.error or java_cap.execution_status not in _NON_FATAL_EXEC_STATUSES:
                exec_errors.append(
                    _execution_error_label(
                        language="java", scenario_id=scenario_id, cap=java_cap
                    )
                )

            test_status = compute_test_status(
                side_from_capture(cobol_cap),
                side_from_capture(java_cap),
                program_name=program_name,
                comparison_mode=comparison_mode,
            )
            comparable = not test_status.get("blocked")
            if comparable:
                diff = test_status["diff"]
            else:
                any_parity_blocked = True
                block_reason = str(test_status.get("reason") or "not_comparable")
                if not primary_parity_reason:
                    primary_parity_reason = str(test_status.get("detail") or "")
                diff = _diff_summary_zero(
                    diff_percentage=None,
                    comparison_status=block_reason
                    if block_reason in _BLOCKED_COMPARISON_REASONS
                    else (
                        "execution_failed"
                        if exec_errors
                        else "not_comparable"
                    ),
                )
                if block_reason in _BLOCKED_COMPARISON_REASONS:
                    failed_tests.append(
                        {
                            "id": f"BEH_{scenario_id}_{block_reason}",
                            "scenario_id": scenario_id,
                            "description": str(test_status.get("detail") or block_reason),
                            "severity": "critical",
                        }
                    )
            total_compared += diff["lines_compared"]
            total_matched += diff["matching_lines"]
            total_diverged += diff["differing_lines"]
            if comparable:
                all_highlights.extend(diff["highlights"])
            cobol_outputs.append(cobol_cap.stdout)
            java_outputs.append(java_cap.stdout)

            per_scenario_meta.append(
                {
                    "scenario_id": scenario_id,
                    "scripted_input": stdin_text,
                    "cobol_execution": asdict(cobol_cap),
                    "java_execution": asdict(java_cap),
                    "diff": diff,
                    "parity_comparable": comparable,
                }
            )

            if comparable and diff["differing_lines"] > 0:
                failed_tests.append(
                    {
                        "id": f"BEH_{scenario_id}",
                        "scenario_id": scenario_id,
                        "description": (
                            f"Stdout mismatch for scenario '{label}' "
                            f"({diff['differing_lines']} line(s) differ, "
                            f"first at index {diff['first_mismatch_index']})"
                        ),
                        "severity": "critical" if diff["matching_lines"] == 0 else "high",
                    }
                )

    combined_cobol = "\n---\n".join(cobol_outputs)
    combined_java = "\n---\n".join(java_outputs)
    sub_program_only = (
        str(program_name or "").strip().upper() in SUB_PROGRAMS
        and not exec_errors
        and per_scenario_meta
        and all(
            str(m.get("diff", {}).get("comparison_status") or "") == "sub_program"
            for m in per_scenario_meta
            if isinstance(m, dict)
        )
    )
    if sub_program_only:
        aggregate_diff = _diff_summary_zero(
            diff_percentage=None,
            comparison_status="sub_program",
        )
        aggregate_diff["note"] = "sub-program — compile verification only"
    elif any_parity_blocked or exec_errors:
        aggregate_comparison_status = "execution_failed" if exec_errors else "not_comparable"
        if any_parity_blocked and failed_tests:
            first_desc = str(failed_tests[0].get("description") or "")
            if "COBOL compile:" in first_desc and "Java compile:" in first_desc:
                aggregate_comparison_status = "compile_failure"
            elif "produced no output" in first_desc.lower():
                aggregate_comparison_status = "both_empty_stdout"
            elif "one side produced output" in first_desc.lower():
                aggregate_comparison_status = "output_asymmetry"
        aggregate_diff = _diff_summary_zero(
            diff_percentage=None,
            comparison_status=aggregate_comparison_status,
        )
    else:
        if comparison_mode == "smart":
            aggregate_diff = compare_smart_outputs(
                combined_cobol, combined_java,
                program_name=program_name,
            )
        else:
            aggregate_diff = compare_normalized_outputs(combined_cobol, combined_java)
        aggregate_diff["highlights"] = all_highlights[:50]

    lines_compared = int(aggregate_diff.get("lines_compared") or 0)
    aggregate_comparison_status = str(aggregate_diff.get("comparison_status") or "")
    status = _derive_status(
        total_matched,
        total_diverged,
        exec_errors,
        lines_compared=lines_compared,
        comparison_status=aggregate_comparison_status,
    )
    failure_reason: Optional[str] = None
    blocker_category = "none"
    blocked_reason: Optional[str] = None
    if any_parity_blocked:
        blocked_reason = str(
            aggregate_diff.get("comparison_status")
            or (per_scenario_meta[0]["diff"].get("comparison_status") if per_scenario_meta else "")
            or "not_comparable"
        )
        if blocked_reason in _BLOCKED_COMPARISON_REASONS or failed_tests:
            status = "failed"
            blocker_category = "conversion_runtime"
            failure_reason = primary_parity_reason or (
                failed_tests[0]["description"] if failed_tests else _parity_block_reason(
                    ExecutionCapture(stdout="", stderr="", exit_code=1, duration_ms=0.0, mode="skipped"),
                    ExecutionCapture(stdout="", stderr="", exit_code=1, duration_ms=0.0, mode="skipped"),
                )
            )
        else:
            status = "not_run"
            failure_reason = primary_parity_reason or _parity_block_reason(
                ExecutionCapture(stdout="", stderr="", exit_code=1, duration_ms=0.0, mode="skipped"),
                ExecutionCapture(stdout="", stderr="", exit_code=1, duration_ms=0.0, mode="skipped"),
            )
            blocker_category = "conversion_runtime"
            failed_tests = []
        lines_compared = 0
        aggregate_diff["lines_compared"] = 0
        aggregate_diff["diff_percentage"] = None
        aggregate_diff["parity_blocked"] = True
    if status == "not_run" and not failure_reason:
        toolchain = get_toolchain_status()
        if exec_errors and not toolchain.live_ready:
            failure_reason = build_toolchain_unavailable_reason(toolchain)
            blocker_category = "toolchain"
        elif exec_errors:
            failure_reason = (
                "Behavioral comparison did not run: COBOL/Java compile or execution failed. "
                + "; ".join(exec_errors[:3])
            )
            blocker_category = "conversion_runtime"
        else:
            failure_reason = "Behavioral comparison did not run: no stdout lines to compare."
            blocker_category = "testing_layer"
    elif failed_tests and not (any_parity_blocked and failure_reason):
        first = per_scenario_meta[0]["diff"] if per_scenario_meta else aggregate_diff
        idx = first.get("first_mismatch_index")
        failure_reason = (
            f"Behavioral stdout drift across {len(failed_tests)} scenario(s). "
            f"Aggregate diff {aggregate_diff['diff_percentage']}%. "
            f"First mismatch line index: {idx}."
        )
        blocker_category = "behavioral_drift"
    elif exec_errors and status not in ("passed", "partial") and not any_parity_blocked:
        failure_reason = "Execution error(s): " + "; ".join(exec_errors[:3])
        blocker_category = "conversion_runtime"
    if unresolved_copybooks:
        copy_msg = format_copybook_prep_failure(
            unresolved_copybooks, _default_copybook_search_dirs()
        )
        if failure_reason:
            failure_reason = f"{failure_reason} {copy_msg}"
        elif status != "passed":
            failure_reason = copy_msg

    if status == "not_run":
        aggregate_diff["diff_percentage"] = None

    if status == "not_run":
        execution_mode = "unavailable"
    elif any_fallback and not any_live:
        execution_mode = "snapshot"
    elif any_live and any_fallback:
        execution_mode = "mixed"
    else:
        execution_mode = "live"

    if status in ("passed", "partial") and execution_mode == "unavailable" and lines_compared > 0:
        execution_mode = "live"

    created_at = datetime.now(timezone.utc).isoformat()

    target_id = str(request.get("target_id") or request.get("project_id") or "")
    result: Dict[str, Any] = {
        "target_type": "single_file",
        "target_id": target_id or run_id,
        "project_id": request.get("project_id"),
        "run_id": run_id,
        "program_name": program_name,
        "created_at": created_at,
        "status": status,
        "execution_mode": execution_mode,
        "fallback_mode": fallback_mode,
        "toolchain_status": toolchain_status,
        "input_set": {
            "id": str(request.get("input_set_id") or "behavioral-set"),
            "name": str(request.get("input_set_name") or "Behavioral scenarios"),
            "scenarios": input_set_scenarios,
        },
        "cobol_output": combined_cobol,
        "java_output": combined_java,
        "diff_summary": {
            "lines_compared": aggregate_diff["lines_compared"],
            "lines_matched": aggregate_diff["lines_matched"],
            "lines_diverged": aggregate_diff["lines_diverged"],
            "paragraph_breakdown": [],
            "total_lines_cobol": aggregate_diff["total_lines_cobol"],
            "total_lines_java": aggregate_diff["total_lines_java"],
            "matching_lines": aggregate_diff["matching_lines"],
            "differing_lines": aggregate_diff["differing_lines"],
            "diff_percentage": aggregate_diff["diff_percentage"],
            "first_mismatch_index": aggregate_diff["first_mismatch_index"],
            "cobol_normalized": aggregate_diff["cobol_normalized"],
            "java_normalized": aggregate_diff["java_normalized"],
            "highlights": aggregate_diff["highlights"],
        },
        "failed_tests": failed_tests,
        "failure_reason": failure_reason,
        "testing_blocker_category": blocker_category,
        "affected_paragraphs": [],
        "retry_scope": "",
        "execution_details": per_scenario_meta,
        "file_results": None,
        "project_summary": None,
        "artifact_provenance": artifact_provenance,
        "stdin_resolution_notes": stdin_notes,
        "comparison_status": str(aggregate_diff.get("comparison_status") or "comparable"),
        "parity_blocked": bool(aggregate_diff.get("parity_blocked")),
    }

    from app.services.failure_mapping_service import enrich_behavioral_result

    enrich_behavioral_result(
        result,
        parser_output=request.get("parser_output") if isinstance(request.get("parser_output"), dict) else None,
        analysis_output=request.get("analysis_output") if isinstance(request.get("analysis_output"), dict) else None,
        cobol_source=cobol_source if isinstance(cobol_source, str) else None,
        java_source=java_source if isinstance(java_source, str) else None,
    )
    if any_parity_blocked and failure_reason:
        result["failure_reason"] = failure_reason
        if status == "not_run":
            result["failed_tests"] = []
        if isinstance(result.get("diff_summary"), dict):
            result["diff_summary"]["diff_percentage"] = None
            result["diff_summary"]["lines_compared"] = 0
            result["diff_summary"]["parity_blocked"] = True
    attach_layered_scoring_to_result(result)
    return result
