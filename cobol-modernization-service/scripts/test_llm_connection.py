#!/usr/bin/env python3
"""Test EY Azure OpenAI connection (gpt-4o) — mirrors your standalone test script."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AzureOpenAI

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = os.getenv("OPENAI_ENDPOINT")
OPENAI_API_VERSION = os.getenv("OPENAI_API_VERSION")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")


def _validate_env() -> None:
    missing = []
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if not OPENAI_ENDPOINT:
        missing.append("OPENAI_ENDPOINT")
    if not OPENAI_API_VERSION:
        missing.append("OPENAI_API_VERSION")
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")


def query_llm(prompt: list, *, timeout: float = 120) -> str:
    print("Querying LLM..")
    client = AzureOpenAI(
        azure_endpoint=OPENAI_ENDPOINT,
        api_version=OPENAI_API_VERSION,
        api_key=OPENAI_API_KEY,
    )
    completion = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0,
        messages=prompt,
        timeout=timeout,
    )
    return completion.choices[0].message.content or ""


def main() -> int:
    print("Testing LLM connection...")
    print(f"  endpoint: {OPENAI_ENDPOINT}")
    print(f"  model:    {OPENAI_MODEL}")
    try:
        _validate_env()
        prompt = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "hello"},
        ]
        response = query_llm(prompt)
        print(f"LLM Response: {response}")
        print("LLM connection successful!")
        return 0
    except Exception as exc:
        print(f"LLM connection failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
