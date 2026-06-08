"""F46 — Adaptive read timeouts for LLM calls based on program size and model."""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional, TypeVar

_LOG = logging.getLogger(__name__)

T = TypeVar("T")

_MODEL_FACTORS = {
    "gpt-4.1-mini": 1.0,
    "gpt-4.1": 1.5,
    "gpt-4o": 1.5,
    "gpt-5.5": 1.5,
    "claude-sonnet-4-5": 1.5,
    "claude-sonnet-4-6": 1.5,
    "claude-opus-4-7": 3.0,
}

_TIMEOUT_FLOOR_SECONDS = 300
_TIMEOUT_CEILING_SECONDS = 900
_METHOD_BODY_FLOOR_SECONDS = 60
_METHOD_BODY_CEILING_SECONDS = 120


def _model_factor(model: str) -> float:
    if model in _MODEL_FACTORS:
        return _MODEL_FACTORS[model]
    lowered = model.lower()
    for key, factor in _MODEL_FACTORS.items():
        if key in lowered or lowered in key:
            return factor
    return 1.5


def compute_timeout(cobol_source: str, model: str) -> int:
    """Compute read timeout based on program size and model (floor 300s, ceiling 900s)."""
    lines = len((cobol_source or "").split("\n"))
    base = 60
    per_line = lines / 10
    factor = _model_factor(model)
    return max(_TIMEOUT_FLOOR_SECONDS, min(int((base + per_line) * factor), _TIMEOUT_CEILING_SECONDS))


def compute_method_body_timeout(model: str) -> int:
    """Per-method F45 conversion calls — small payloads, shorter limits (60–120s)."""
    factor = _model_factor(model)
    return max(
        _METHOD_BODY_FLOOR_SECONDS,
        min(int(90 * factor), _METHOD_BODY_CEILING_SECONDS),
    )


def log_timeout_plan(
    program_name: str,
    cobol_source: str,
    model: str,
    timeout_seconds: int,
    *,
    call_kind: str = "llm",
) -> int:
    """Log planned timeout; return line count for callers."""
    lines = len((cobol_source or "").split("\n"))
    _LOG.info(
        "[TIMEOUT] %s: %d COBOL lines, %s, %s timeout=%ds",
        program_name,
        lines,
        model,
        call_kind,
        timeout_seconds,
    )
    print(
        f"[TIMEOUT] {program_name}: {lines} COBOL lines, {model}, "
        f"{call_kind} timeout={timeout_seconds}s",
        flush=True,
    )
    return lines


def run_with_timeout_logging(
    program_name: str,
    model: str,
    timeout_seconds: int,
    fn: Callable[[], T],
    *,
    call_kind: str = "llm",
) -> T:
    """Execute *fn* with [TIMEOUT] start/complete/failure logs."""
    print(f"[TIMEOUT] {program_name}: LLM call started ({call_kind})", flush=True)
    _LOG.info("[TIMEOUT] %s: LLM call started (%s)", program_name, call_kind)
    start = time.time()
    try:
        return fn()
    except Exception as exc:
        elapsed = time.time() - start
        is_timeout = "timeout" in type(exc).__name__.lower() or "timeout" in str(exc).lower()
        if is_timeout:
            msg = (
                f"[TIMEOUT] {program_name}: FAILURE — TIMEOUT after {elapsed:.1f}s "
                f"(limit was {timeout_seconds}s, model={model}, kind={call_kind})"
            )
            _LOG.error(msg)
            print(msg, flush=True)
        raise
    finally:
        elapsed = time.time() - start
        _LOG.info(
            "[TIMEOUT] %s: LLM call completed in %.1fs (limit=%ds, kind=%s)",
            program_name,
            elapsed,
            timeout_seconds,
            call_kind,
        )
        print(
            f"[TIMEOUT] {program_name}: LLM call completed in {elapsed:.1f}s "
            f"(limit={timeout_seconds}s, kind={call_kind})",
            flush=True,
        )
