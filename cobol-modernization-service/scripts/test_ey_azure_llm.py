#!/usr/bin/env python3
"""Smoke-test EY Azure OpenAI (gpt-4o) via SDK and project llm_transport."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def _validate_env() -> None:
    missing = []
    if not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if not os.getenv("OPENAI_ENDPOINT"):
        missing.append("OPENAI_ENDPOINT")
    if not os.getenv("OPENAI_API_VERSION"):
        missing.append("OPENAI_API_VERSION")
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")


def test_sdk() -> str:
    from openai import AzureOpenAI

    client = AzureOpenAI(
        azure_endpoint=os.environ["OPENAI_ENDPOINT"].rstrip("/"),
        api_version=os.environ["OPENAI_API_VERSION"],
        api_key=os.environ["OPENAI_API_KEY"],
    )
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    print(f"[SDK] Querying {model} via AzureOpenAI...")
    completion = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Reply with exactly: hello"},
        ],
        timeout=120,
    )
    return completion.choices[0].message.content or ""


def test_transport() -> str:
    from app.services.llm_config import resolve_llm_runtime
    from app.services.llm_transport import complete_chat

    runtime = resolve_llm_runtime()
    print(
        f"[TRANSPORT] provider={runtime.provider} "
        f"model={runtime.model_analysis}"
    )
    return complete_chat(
        provider=runtime.provider,
        model=runtime.model_analysis,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Reply with exactly: hello"},
        ],
        max_output_tokens=64,
        temperature=0,
    )


def main() -> int:
    print("Testing EY Azure OpenAI connection...")
    try:
        _validate_env()
        from app.services.llm_config import resolve_llm_runtime

        runtime = resolve_llm_runtime()
        print(f"Resolved: provider={runtime.provider}, model={runtime.model_analysis}")

        sdk_text = test_sdk().strip()
        print(f"[SDK] Response: {sdk_text[:200]}")

        transport_text = test_transport().strip()
        print(f"[TRANSPORT] Response: {transport_text[:200]}")

        if not sdk_text or sdk_text.startswith("// Conversion agent"):
            print("FAIL: SDK returned empty or stub response")
            return 1
        if not transport_text or transport_text.startswith("// Conversion agent"):
            print("FAIL: transport returned empty or stub response")
            return 1

        print("OK: LLM connection successful (SDK + transport)")
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
