"""HTTP chat transports for OpenAI-compatible and Anthropic Messages APIs."""

from __future__ import annotations

import logging
import os
import time
from typing import Dict, List, Optional

import httpx

from app.services.llm_config import resolve_openai_fallback_model
from app.services.llm_streaming import LLMStallError, call_llm_with_retry, save_stream_debug
from app.services.llm_timeout import compute_timeout, run_with_timeout_logging

_STREAM_STALL_SECONDS = float(os.getenv("LLM_STREAM_STALL_SECONDS", "60"))

_LOG = logging.getLogger(__name__)

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = os.getenv("ANTHROPIC_API_VERSION", "2023-06-01")

_RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504, 529}
_MAX_RETRIES = int(os.getenv("LLM_HTTP_MAX_RETRIES", "4"))
_DEFAULT_BACKOFF_SECONDS = float(os.getenv("LLM_HTTP_BACKOFF_SECONDS", "60"))
_HTTP_READ_TIMEOUT_SECONDS = float(os.getenv("LLM_HTTP_READ_TIMEOUT_SECONDS", "180"))
_HTTP_CONNECT_TIMEOUT_SECONDS = float(os.getenv("LLM_HTTP_CONNECT_TIMEOUT_SECONDS", "30"))


def _httpx_timeout(read_seconds: Optional[float] = None) -> "httpx.Timeout":
    read = read_seconds if read_seconds is not None else _HTTP_READ_TIMEOUT_SECONDS
    return httpx.Timeout(read, connect=_HTTP_CONNECT_TIMEOUT_SECONDS)


def _resolve_read_timeout(
    read_timeout_seconds: Optional[float],
    cobol_source: Optional[str],
    model: str,
) -> float:
    if read_timeout_seconds is not None:
        return float(read_timeout_seconds)
    if cobol_source:
        return float(compute_timeout(cobol_source, model))
    return _HTTP_READ_TIMEOUT_SECONDS


def _retry_after_seconds(response: httpx.Response, attempt: int) -> float:
    raw = response.headers.get("retry-after") or response.headers.get("Retry-After")
    if raw:
        try:
            return max(1.0, float(raw))
        except (TypeError, ValueError):
            pass
    # exponential backoff with floor; default is generous because Anthropic
    # quota windows are per-minute.
    return min(180.0, _DEFAULT_BACKOFF_SECONDS * (1.5 ** max(0, attempt - 1)))


def _looks_like_transient_403(response: httpx.Response) -> bool:
    if response.status_code != 403:
        return False
    body = (response.text or "").lower()
    return "internal server error" in body and "access_denied" in body


def _post_with_retry(
    client: httpx.Client,
    url: str,
    *,
    headers: Dict[str, str],
    json: Dict[str, object],
    provider_label: str,
) -> httpx.Response:
    last_response: Optional[httpx.Response] = None
    for attempt in range(1, _MAX_RETRIES + 1):
        response = client.post(url, headers=headers, json=json)
        if response.status_code not in _RETRY_STATUSES and not _looks_like_transient_403(response):
            return response
        last_response = response
        if attempt >= _MAX_RETRIES:
            return response
        wait = _retry_after_seconds(response, attempt)
        print(
            f"[LLM_TRANSPORT] {provider_label} HTTP {response.status_code}; "
            f"retry {attempt}/{_MAX_RETRIES - 1} after {wait:.1f}s",
            flush=True,
        )
        time.sleep(wait)
    assert last_response is not None
    return last_response

_STUB_MESSAGE = (
    "// Conversion agent is not configured.\n"
    "// Provide ANTHROPIC_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY.\n"
)


def _split_system_messages(messages: List[Dict[str, str]]) -> tuple[str, List[Dict[str, str]]]:
    system_parts: List[str] = []
    rest: List[Dict[str, str]] = []
    for msg in messages:
        role = str(msg.get("role") or "user")
        content = str(msg.get("content") or "")
        if role == "system":
            if content:
                system_parts.append(content)
        elif role == "assistant":
            rest.append({"role": "assistant", "content": content})
        else:
            rest.append({"role": "user", "content": content})
    if not rest and system_parts:
        rest = [{"role": "user", "content": "Continue."}]
    return "\n\n".join(system_parts), rest


def _extract_openai_style_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        if parts:
            return "\n".join(parts)
    raise ValueError("Chat completion content format was not recognized.")


def _extract_anthropic_content(body: dict) -> str:
    blocks = body.get("content")
    if not isinstance(blocks, list):
        raise ValueError("Anthropic response did not include content blocks.")
    parts: List[str] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    if not parts:
        raise ValueError("Anthropic response contained no text blocks.")
    return "\n".join(parts)


def _is_openai_model_error(exc: BaseException) -> bool:
    """True when the failure is likely due to model/deployment availability."""
    text = str(exc).lower()
    markers = (
        "deploymentnotfound",
        "deployment not found",
        "model_not_found",
        "model not found",
        "does not exist",
        "unknown model",
        "invalid model",
        "model is not available",
        "resource not found",
    )
    if any(m in text for m in markers):
        return True
    status = getattr(exc, "status_code", None)
    if status is None and hasattr(exc, "response"):
        try:
            status = exc.response.status_code  # type: ignore[union-attr]
        except Exception:
            status = None
    return status in (404, 400)


def _complete_openai_with_fallback(
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_output_tokens: Optional[int],
    temperature: float,
    read_timeout_seconds: float,
    program_name: str,
) -> str:
    fallback = resolve_openai_fallback_model()
    try:
        return _complete_openai(
            model=model,
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            read_timeout_seconds=read_timeout_seconds,
        )
    except Exception as exc:
        if not fallback or fallback == model or not _is_openai_model_error(exc):
            raise
        print(
            f"[LLM_TRANSPORT] {program_name}: primary model {model!r} failed "
            f"({exc}); retrying with fallback {fallback!r}",
            flush=True,
        )
        _LOG.warning(
            "OpenAI primary model %s failed; falling back to %s: %s",
            model,
            fallback,
            exc,
        )
        return _complete_openai(
            model=fallback,
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            read_timeout_seconds=read_timeout_seconds,
        )


def _stream_openai_with_fallback(
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_output_tokens: Optional[int],
    temperature: float,
    timeout_seconds: int,
    program_name: str,
) -> str:
    fallback = resolve_openai_fallback_model()
    try:
        return _stream_openai(
            model=model,
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            program_name=program_name,
        )
    except Exception as exc:
        if not fallback or fallback == model or not _is_openai_model_error(exc):
            raise
        print(
            f"[STREAM] {program_name}: primary model {model!r} failed "
            f"({exc}); retrying with fallback {fallback!r}",
            flush=True,
        )
        _LOG.warning(
            "OpenAI stream primary model %s failed; falling back to %s: %s",
            model,
            fallback,
            exc,
        )
        return _stream_openai(
            model=fallback,
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            program_name=program_name,
        )


def complete_chat(
    *,
    provider: str,
    model: str,
    messages: List[Dict[str, str]],
    max_output_tokens: Optional[int] = None,
    temperature: float = 0.0,
    read_timeout_seconds: Optional[float] = None,
    program_name: Optional[str] = None,
    cobol_source: Optional[str] = None,
    call_kind: str = "llm",
) -> str:
    """
    Run a single chat completion for the given provider.

    ``messages`` uses OpenAI-style roles (system, user, assistant).
    Pass ``read_timeout_seconds`` or ``cobol_source`` for adaptive timeouts (F46).
    """
    timeout = _resolve_read_timeout(read_timeout_seconds, cobol_source, model)
    pname = program_name or "PROGRAM"

    def _dispatch() -> str:
        if provider == "anthropic":
            return _complete_anthropic(
                model=model,
                messages=messages,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                read_timeout_seconds=timeout,
            )
        if provider == "openai":
            return _complete_openai_with_fallback(
                model=model,
                messages=messages,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                read_timeout_seconds=timeout,
                program_name=pname,
            )
        if provider == "openrouter":
            return _complete_openrouter(
                model=model,
                messages=messages,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                read_timeout_seconds=timeout,
            )
        return _STUB_MESSAGE

    if program_name or cobol_source or read_timeout_seconds is not None:
        return run_with_timeout_logging(pname, model, int(timeout), _dispatch, call_kind=call_kind)
    return _dispatch()


def _should_use_streaming(call_kind: str) -> bool:
    """Conversion paths stream; analysis stays non-streaming."""
    return call_kind not in ("analysis_chunk", "analysis")


def stream_chat(
    *,
    provider: str,
    model: str,
    messages: List[Dict[str, str]],
    max_output_tokens: Optional[int] = None,
    temperature: float = 0.0,
    read_timeout_seconds: Optional[float] = None,
    program_name: Optional[str] = None,
    cobol_source: Optional[str] = None,
    call_kind: str = "conversion",
    max_retries: int = 3,
) -> str:
    """
    Streaming chat completion (F47) — keeps connection warm on large outputs.
    """
    timeout = int(_resolve_read_timeout(read_timeout_seconds, cobol_source, model))
    pname = program_name or "PROGRAM"

    def _stream_once() -> str:
        print(f"[STREAM] {pname}: LLM stream started ({call_kind})", flush=True)
        _LOG.info("[STREAM] %s: stream started (%s)", pname, call_kind)
        if provider == "anthropic":
            return _stream_anthropic(
                model=model,
                messages=messages,
                max_output_tokens=max_output_tokens,
                timeout_seconds=timeout,
                program_name=pname,
            )
        if provider == "openai":
            return _stream_openai_with_fallback(
                model=model,
                messages=messages,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                timeout_seconds=timeout,
                program_name=pname,
            )
        if provider == "openrouter":
            return _stream_openrouter(
                model=model,
                messages=messages,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                timeout_seconds=timeout,
                program_name=pname,
            )
        return _STUB_MESSAGE

    return call_llm_with_retry(_stream_once, program_name=pname, max_retries=max_retries)


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


def _stream_anthropic(
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_output_tokens: Optional[int],
    timeout_seconds: int,
    program_name: str,
) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return _STUB_MESSAGE

    from anthropic import Anthropic

    system_text, api_messages = _split_system_messages(messages)
    client = Anthropic(api_key=api_key, timeout=timeout_seconds)
    kwargs: Dict[str, object] = {
        "model": model,
        "messages": api_messages,
        "max_tokens": max_output_tokens if max_output_tokens is not None else 8192,
    }
    if system_text:
        kwargs["system"] = system_text

    chunks: List[str] = []
    last_chunk_time = time.time()
    start = time.time()

    try:
        with client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                _check_stream_limits(
                    start=start,
                    last_chunk_time=last_chunk_time,
                    chunk_count=len(chunks),
                    timeout_seconds=timeout_seconds,
                    stall_gap_seconds=_STREAM_STALL_SECONDS,
                )
                if text:
                    chunks.append(text)
                    last_chunk_time = time.time()
    except Exception as exc:
        elapsed = time.time() - start
        partial = "".join(chunks)
        print(
            f"[STREAM] {program_name}: failed after {elapsed:.1f}s: {exc}, "
            f"partial chunks: {len(chunks)}",
            flush=True,
        )
        if partial:
            save_stream_debug(f"{program_name}_partial_response.txt", partial)
        raise

    elapsed = time.time() - start
    total_chars = sum(len(c) for c in chunks)
    print(
        f"[STREAM] {program_name}: completed in {elapsed:.1f}s, "
        f"{len(chunks)} chunks, {total_chars} chars",
        flush=True,
    )
    return "".join(chunks)


def _stream_openai(
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_output_tokens: Optional[int],
    temperature: float,
    timeout_seconds: int,
    program_name: str,
) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _STUB_MESSAGE

    if _azure_openai_configured():
        return _stream_openai_azure_sdk(
            model=model,
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            program_name=program_name,
        )

    return _stream_openai_http(
        model=model,
        messages=messages,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
        program_name=program_name,
    )


def _stream_openai_azure_sdk(
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_output_tokens: Optional[int],
    temperature: float,
    timeout_seconds: int,
    program_name: str,
) -> str:
    from openai import AzureOpenAI

    client = AzureOpenAI(
        azure_endpoint=os.environ["OPENAI_ENDPOINT"].strip().rstrip("/"),
        api_version=os.environ["OPENAI_API_VERSION"].strip(),
        api_key=os.environ["OPENAI_API_KEY"].strip(),
    )
    deployment = _openai_deployment_name(model)
    kwargs: Dict[str, object] = {
        "model": deployment,
        "messages": messages,
        "temperature": temperature,
        "timeout": timeout_seconds,
        "stream": True,
    }
    if max_output_tokens is not None:
        tok_key = "max_completion_tokens" if _uses_max_completion_tokens(model) else "max_tokens"
        kwargs[tok_key] = max_output_tokens

    chunks: List[str] = []
    last_chunk_time = time.time()
    start = time.time()

    try:
        stream = client.chat.completions.create(**kwargs)
        for chunk in stream:
            _check_stream_limits(
                start=start,
                last_chunk_time=last_chunk_time,
                chunk_count=len(chunks),
                timeout_seconds=timeout_seconds,
                stall_gap_seconds=_STREAM_STALL_SECONDS,
            )
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None) if delta else None
            if content:
                chunks.append(content)
                last_chunk_time = time.time()
    except Exception as exc:
        elapsed = time.time() - start
        partial = "".join(chunks)
        print(
            f"[STREAM] {program_name}: failed after {elapsed:.1f}s: {exc}, "
            f"partial chunks: {len(chunks)}",
            flush=True,
        )
        if partial:
            save_stream_debug(f"{program_name}_partial_response.txt", partial)
        raise

    elapsed = time.time() - start
    total_chars = sum(len(c) for c in chunks)
    print(
        f"[STREAM] {program_name}: completed in {elapsed:.1f}s, "
        f"{len(chunks)} chunks, {total_chars} chars",
        flush=True,
    )
    return "".join(chunks)


def _stream_openai_http(
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_output_tokens: Optional[int],
    temperature: float,
    timeout_seconds: int,
    program_name: str,
) -> str:
    """SSE streaming for standard OpenAI-compatible HTTP endpoints."""
    import json as _json

    api_key = os.getenv("OPENAI_API_KEY", "")
    url, headers = _resolve_openai_url_and_headers(model, api_key)
    payload: Dict[str, object] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    if max_output_tokens is not None:
        tok_key = "max_completion_tokens" if _uses_max_completion_tokens(model) else "max_tokens"
        payload[tok_key] = max_output_tokens

    chunks: List[str] = []
    last_chunk_time = time.time()
    start = time.time()

    try:
        with httpx.Client(timeout=_httpx_timeout(timeout_seconds)) as client:
            with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    _check_stream_limits(
                        start=start,
                        last_chunk_time=last_chunk_time,
                        chunk_count=len(chunks),
                        timeout_seconds=timeout_seconds,
                        stall_gap_seconds=_STREAM_STALL_SECONDS,
                    )
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        body = _json.loads(data)
                        delta = body["choices"][0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            chunks.append(content)
                            last_chunk_time = time.time()
                    except (_json.JSONDecodeError, KeyError, IndexError, TypeError):
                        continue
    except Exception as exc:
        elapsed = time.time() - start
        partial = "".join(chunks)
        print(
            f"[STREAM] {program_name}: failed after {elapsed:.1f}s: {exc}, "
            f"partial chunks: {len(chunks)}",
            flush=True,
        )
        if partial:
            save_stream_debug(f"{program_name}_partial_response.txt", partial)
        raise

    elapsed = time.time() - start
    total_chars = sum(len(c) for c in chunks)
    print(
        f"[STREAM] {program_name}: completed in {elapsed:.1f}s, "
        f"{len(chunks)} chunks, {total_chars} chars",
        flush=True,
    )
    return "".join(chunks)


def _stream_openrouter(
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_output_tokens: Optional[int],
    temperature: float,
    timeout_seconds: int,
    program_name: str,
) -> str:
    import json as _json

    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return _STUB_MESSAGE

    payload: Dict[str, object] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    if max_output_tokens is not None:
        payload["max_tokens"] = max_output_tokens

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "http://localhost"),
        "X-Title": os.getenv("OPENROUTER_APP_NAME", "cobol-modernization-service"),
    }

    chunks: List[str] = []
    last_chunk_time = time.time()
    start = time.time()

    try:
        with httpx.Client(timeout=_httpx_timeout(timeout_seconds)) as client:
            with client.stream("POST", _OPENROUTER_URL, headers=headers, json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    _check_stream_limits(
                        start=start,
                        last_chunk_time=last_chunk_time,
                        chunk_count=len(chunks),
                        timeout_seconds=timeout_seconds,
                        stall_gap_seconds=_STREAM_STALL_SECONDS,
                    )
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        body = _json.loads(data)
                        delta = body["choices"][0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            chunks.append(content)
                            last_chunk_time = time.time()
                    except (_json.JSONDecodeError, KeyError, IndexError, TypeError):
                        continue
    except Exception as exc:
        elapsed = time.time() - start
        partial = "".join(chunks)
        print(
            f"[STREAM] {program_name}: failed after {elapsed:.1f}s: {exc}, "
            f"partial chunks: {len(chunks)}",
            flush=True,
        )
        if partial:
            save_stream_debug(f"{program_name}_partial_response.txt", partial)
        raise

    elapsed = time.time() - start
    total_chars = sum(len(c) for c in chunks)
    print(
        f"[STREAM] {program_name}: completed in {elapsed:.1f}s, "
        f"{len(chunks)} chunks, {total_chars} chars",
        flush=True,
    )
    return "".join(chunks)


def _complete_anthropic(
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_output_tokens: Optional[int],
    temperature: float,
    read_timeout_seconds: float = _HTTP_READ_TIMEOUT_SECONDS,
) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return _STUB_MESSAGE

    system_text, api_messages = _split_system_messages(messages)
    payload: Dict[str, object] = {
        "model": model,
        "messages": api_messages,
        "max_tokens": max_output_tokens if max_output_tokens is not None else 8192,
    }
    # Recent Claude models reject ``temperature`` on the Messages API (omit for compatibility).
    if system_text:
        payload["system"] = system_text

    headers = {
        "x-api-key": api_key,
        "anthropic-version": _ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    with httpx.Client(timeout=_httpx_timeout(read_timeout_seconds)) as client:
        response = _post_with_retry(
            client, _ANTHROPIC_URL, headers=headers, json=payload, provider_label="anthropic"
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text.strip()
            raise RuntimeError(
                f"Anthropic request failed with status {response.status_code}: {detail}"
            ) from exc
        body = response.json()

    return _extract_anthropic_content(body)


def _azure_openai_configured() -> bool:
    return bool(
        os.getenv("OPENAI_API_KEY", "").strip()
        and os.getenv("OPENAI_ENDPOINT", "").strip()
        and os.getenv("OPENAI_API_VERSION", "").strip()
    )


def _openai_deployment_name(model: str) -> str:
    """Azure deployment name (may differ from logical model id)."""
    return os.getenv("OPENAI_DEPLOYMENT_NAME", "").strip() or model


def _uses_max_completion_tokens(model: str) -> bool:
    lowered = model.lower()
    return any(tag in lowered for tag in ("gpt-4o", "gpt-4.1", "gpt-5", "o1", "o3", "o4"))


def _resolve_openai_url_and_headers(model: str, api_key: str) -> tuple[str, Dict[str, str]]:
    """Build the URL and auth headers, supporting both standard OpenAI and Azure-style endpoints."""
    custom_endpoint = os.getenv("OPENAI_ENDPOINT", "").strip().rstrip("/")
    api_version = os.getenv("OPENAI_API_VERSION", "").strip()
    deployment = _openai_deployment_name(model)

    if custom_endpoint and api_version:
        url = (
            f"{custom_endpoint}/openai/deployments/{deployment}"
            f"/chat/completions?api-version={api_version}"
        )
        headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
        }
    elif custom_endpoint:
        url = f"{custom_endpoint}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    else:
        url = _OPENAI_URL
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    return url, headers


def _complete_openai_via_azure_sdk(
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_output_tokens: Optional[int],
    temperature: float,
    read_timeout_seconds: float = _HTTP_READ_TIMEOUT_SECONDS,
) -> str:
    """EY / Azure OpenAI via official SDK (same path as standalone connection tests)."""
    from openai import AzureOpenAI

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    endpoint = os.getenv("OPENAI_ENDPOINT", "").strip().rstrip("/")
    api_version = os.getenv("OPENAI_API_VERSION", "").strip()
    deployment = _openai_deployment_name(model)

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_version=api_version,
        api_key=api_key,
    )
    kwargs: Dict[str, object] = {
        "model": deployment,
        "messages": messages,
        "temperature": temperature,
        "timeout": read_timeout_seconds,
    }
    if max_output_tokens is not None:
        tok_key = "max_completion_tokens" if _uses_max_completion_tokens(model) else "max_tokens"
        kwargs[tok_key] = max_output_tokens

    completion = client.chat.completions.create(**kwargs)
    content = completion.choices[0].message.content
    return _extract_openai_style_content(content)


def _complete_openai(
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_output_tokens: Optional[int],
    temperature: float,
    read_timeout_seconds: float = _HTTP_READ_TIMEOUT_SECONDS,
) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _STUB_MESSAGE

    if _azure_openai_configured():
        return _complete_openai_via_azure_sdk(
            model=model,
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            read_timeout_seconds=read_timeout_seconds,
        )

    url, headers = _resolve_openai_url_and_headers(model, api_key)
    deployment = _openai_deployment_name(model)
    is_azure = bool(os.getenv("OPENAI_ENDPOINT", "").strip() and os.getenv("OPENAI_API_VERSION", "").strip())

    payload: Dict[str, object] = {
        "messages": messages,
    }
    # Azure deployment URL embeds the model; omit body model when using deployments API.
    if not is_azure:
        payload["model"] = model
    elif deployment != model:
        payload["model"] = deployment

    payload["temperature"] = temperature

    if max_output_tokens is not None:
        tok_key = "max_completion_tokens" if _uses_max_completion_tokens(model) else "max_tokens"
        payload[tok_key] = max_output_tokens

    with httpx.Client(timeout=_httpx_timeout(read_timeout_seconds)) as client:
        response = _post_with_retry(
            client, url, headers=headers, json=payload, provider_label="openai"
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text.strip()
            raise RuntimeError(
                f"OpenAI request failed with status {response.status_code}: {detail}"
            ) from exc
        body = response.json()

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("OpenAI response did not include a chat completion payload.") from exc

    return _extract_openai_style_content(content)


def _complete_openrouter(
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_output_tokens: Optional[int],
    temperature: float,
    read_timeout_seconds: float = _HTTP_READ_TIMEOUT_SECONDS,
) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return _STUB_MESSAGE

    payload: Dict[str, object] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_output_tokens is not None:
        payload["max_tokens"] = max_output_tokens

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "http://localhost"),
        "X-Title": os.getenv("OPENROUTER_APP_NAME", "cobol-modernization-service"),
    }

    with httpx.Client(timeout=_httpx_timeout(read_timeout_seconds)) as client:
        response = _post_with_retry(
            client, _OPENROUTER_URL, headers=headers, json=payload, provider_label="openrouter"
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text.strip()
            raise RuntimeError(
                f"OpenRouter request failed with status {response.status_code}: {detail}"
            ) from exc
        body = response.json()

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("OpenRouter response did not include a chat completion payload.") from exc

    return _extract_openai_style_content(content)
