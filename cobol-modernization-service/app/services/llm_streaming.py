"""F47 — Streaming LLM calls for conversion (stall detection + retry)."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, List, Optional, TypeVar

import httpx

_LOG = logging.getLogger(__name__)
_SERVICE_ROOT = Path(__file__).resolve().parents[2]
_STREAM_DEBUG_DIR = _SERVICE_ROOT / "out" / "stream_debug"

_STALL_GAP_SECONDS = float(__import__("os").getenv("LLM_STREAM_STALL_SECONDS", "60"))
_DEFAULT_MAX_RETRIES = int(__import__("os").getenv("LLM_STREAM_MAX_RETRIES", "3"))

T = TypeVar("T")


class LLMStallError(Exception):
    """Raised when streaming stalls or exceeds total timeout."""


def save_stream_debug(filename: str, content: str) -> None:
    """Persist partial stream output for debugging."""
    _STREAM_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    path = _STREAM_DEBUG_DIR / Path(filename).name
    path.write_text(content, encoding="utf-8")
    _LOG.info("[STREAM] saved partial debug: %s", path)


def collect_stream_with_watchdog(
    iterator: Callable[[], None],
    *,
    timeout_seconds: int,
    program_name: str = "PROGRAM",
    stall_gap_seconds: float = _STALL_GAP_SECONDS,
) -> str:
    """
    Run a streaming iterator that appends text via ``iterator`` side effect.

    The iterator should call ``on_text(str)`` for each piece — we pass a list collector.
    """
    chunks: List[str] = []
    last_chunk_time = time.time()
    start = time.time()

    def on_text(text: str) -> None:
        nonlocal last_chunk_time
        if text:
            chunks.append(text)
            last_chunk_time = time.time()

    try:
        iterator(on_text)
        now = time.time()
        if chunks and now - last_chunk_time > stall_gap_seconds:
            raise LLMStallError(
                f"No chunks for {stall_gap_seconds:.0f}s, had {len(chunks)} chunks so far"
            )
        elapsed = time.time() - start
        total_chars = sum(len(c) for c in chunks)
        msg = (
            f"[STREAM] {program_name}: completed in {elapsed:.1f}s, "
            f"{len(chunks)} chunks, {total_chars} chars"
        )
        _LOG.info(msg)
        print(msg, flush=True)
    except Exception as exc:
        elapsed = time.time() - start
        partial = "".join(chunks)
        msg = (
            f"[STREAM] {program_name}: failed after {elapsed:.1f}s: {exc}, "
            f"partial chunks: {len(chunks)}"
        )
        _LOG.error(msg)
        print(msg, flush=True)
        if partial:
            safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in program_name)
            save_stream_debug(f"{safe_name}_partial_response.txt", partial)
        raise

    return "".join(chunks)


def _check_stream_limits(
    *,
    start: float,
    last_chunk_time: float,
    chunk_count: int,
    timeout_seconds: int,
    stall_gap_seconds: float,
) -> None:
    now = time.time()
    if chunk_count > 0 and now - last_chunk_time > stall_gap_seconds:
        raise LLMStallError(
            f"No chunks for {stall_gap_seconds:.0f}s, had {chunk_count} chunks so far"
        )
    if now - start > timeout_seconds:
        raise LLMStallError(f"Total streaming exceeded timeout ({timeout_seconds}s)")


def call_llm_with_retry(
    fn: Callable[[], str],
    *,
    program_name: str = "PROGRAM",
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> str:
    """Retry streaming LLM calls with exponential backoff."""
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return fn()
        except (LLMStallError, ConnectionError, TimeoutError, httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            _LOG.warning(
                "LLM stream failed (attempt %d/%d): %s",
                attempt + 1,
                max_retries,
                exc,
            )
            print(
                f"[STREAM] {program_name}: LLM call failed "
                f"(attempt {attempt + 1}/{max_retries}): {exc}",
                flush=True,
            )
            if attempt == max_retries - 1:
                raise
            sleep_time = 2 ** attempt
            print(f"[STREAM] {program_name}: retrying in {sleep_time}s", flush=True)
            time.sleep(sleep_time)
    raise last_exc  # pragma: no cover
