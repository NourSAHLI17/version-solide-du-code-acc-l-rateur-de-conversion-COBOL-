"""Instrumented stage-6 name reconciliation (FX3)."""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from app.services.java_name_reconciler import reconcile_names


class ReconcileStallError(RuntimeError):
    """Raised when a reconcile sub-step exceeds its time budget."""


def reconcile_stage_timeout_seconds(
    java_source: str,
    symbol_table: Any = None,
) -> float:
    """
    Work-based stage-6 timeout: scales with source size and symbol count.

    Reconcile should finish in seconds for typical ACME programs; the cap still
    honors ``CONVERSION_STAGE_TIMEOUT_SECONDS``.
    """
    lines = max(1, len((java_source or "").splitlines()))
    sym_items = 0
    if symbol_table is not None:
        if hasattr(symbol_table, "to_legacy_list"):
            sym_items = len(symbol_table.to_legacy_list())
        elif isinstance(symbol_table, list):
            sym_items = len(symbol_table)
    items = lines + sym_items
    base = float(os.environ.get("RECONCILE_BASE_TIMEOUT_SECONDS", "10"))
    per_item = float(os.environ.get("RECONCILE_PER_ITEM_SECONDS", "0.02"))
    cap = float(os.environ.get("CONVERSION_STAGE_TIMEOUT_SECONDS", "120"))
    return min(cap, max(base, items * per_item))


def _reconcile_run_dir(program: str) -> Optional[Path]:
    explicit = os.environ.get("F41_RECONCILE_RUN_DIR", "").strip()
    if explicit:
        return Path(explicit)
    run_dir = os.environ.get("F41_RUN_DIR", "").strip()
    if run_dir:
        return Path(run_dir)
    # Default debug folder under service out/
    root = Path(__file__).resolve().parents[2]
    return root / "out" / "f41_runs" / "_reconcile_debug" / (program or "PROGRAM")


def _serialize_reconcile_inputs(
    java_source: str,
    symbol_table: Any,
    program_name: str,
) -> Dict[str, Any]:
    sym_len = 0
    if symbol_table is not None:
        if hasattr(symbol_table, "to_legacy_list"):
            sym_len = len(symbol_table.to_legacy_list())
        elif isinstance(symbol_table, list):
            sym_len = len(symbol_table)
    return {
        "program_name": program_name,
        "java_source_chars": len(java_source or ""),
        "java_source_lines": len((java_source or "").splitlines()),
        "symbol_table_entries": sym_len,
    }


def _run_step_with_timeout(
    step_fn: Callable[[], Tuple[str, List[str]]],
    *,
    timeout_seconds: float,
) -> Tuple[str, List[str]]:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(step_fn)
    try:
        return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError as exc:
        future.cancel()
        raise ReconcileStallError(f"timed out after {timeout_seconds:.1f}s") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def reconcile_names_instrumented(
    java_source: str,
    symbol_table: Any = None,
    *,
    program_name: str = "",
    run_dir: Optional[Path] = None,
    per_step_timeout_seconds: float = 30.0,
) -> Tuple[str, List[str]]:
    """
    Run :func:`reconcile_names` with per-phase timing, forensics, and step timeouts.

    Phases mirror the internal pipeline in ``java_name_reconciler``.
    """
    out_dir = run_dir or _reconcile_run_dir(program_name)
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        forensics = _serialize_reconcile_inputs(java_source, symbol_table, program_name)
        (out_dir / f"{program_name}.reconcile_inputs.json").write_text(
            json.dumps(forensics, indent=2, default=str),
            encoding="utf-8",
        )

    print(f"[RECONCILE] {program_name}: starting", flush=True)
    start = time.monotonic()
    result_text = java_source
    all_notes: List[str] = []

    # Single instrumented call — internal phases log via reconcile_names phases
    step_start = time.monotonic()
    print(f"[RECONCILE] {program_name}: reconcile_names starting", flush=True)
    try:
        result_text, all_notes = _run_step_with_timeout(
            lambda: reconcile_names(
                result_text,
                symbol_table,
                program_name=program_name,
            ),
            timeout_seconds=per_step_timeout_seconds,
        )
    except ReconcileStallError as exc:
        elapsed = time.monotonic() - step_start
        print(
            f"[RECONCILE] {program_name}: reconcile_names TIMED OUT after {elapsed:.1f}s",
            flush=True,
        )
        if out_dir is not None:
            stall_path = out_dir / f"{program_name}.reconcile_STALL_reconcile_names.txt"
            stall_path.write_text(result_text[:500_000], encoding="utf-8")
        raise
    elapsed = time.monotonic() - step_start
    print(
        f"[RECONCILE] {program_name}: reconcile_names completed in {elapsed:.1f}s",
        flush=True,
    )

    total = time.monotonic() - start
    print(f"[RECONCILE] {program_name}: completed in {total:.1f}s", flush=True)
    return result_text, all_notes
