"""Resolve LLM provider and per-agent model names from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import app.env_bootstrap  # noqa: F401

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:  # pragma: no cover
    ChatGoogleGenerativeAI = None


# Single source of truth for Anthropic model IDs in this project (Sonnet 4.5).
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5"

# EY Azure OpenAI Fabric defaults (when OPENAI_ENDPOINT + OPENAI_API_VERSION set).
DEFAULT_AZURE_OPENAI_MODEL = "gpt-4o"
DEFAULT_AZURE_OPENAI_FALLBACK_MODEL = "gpt-4.1-mini"
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"


@dataclass(frozen=True)
class LlmRuntimeConfig:
    """Resolved LLM settings for conversion + analysis (shared transport)."""

    provider: str  # google | openai | openrouter | anthropic | stub
    model_conversion: str
    model_analysis: str
    google_llm: object | None = None


def resolve_anthropic_analysis_model() -> str:
    """Analysis, structural review, business-rule extraction, and chunked LLM analysis."""
    return (
        os.getenv("ANTHROPIC_MODEL_ANALYSIS")
        or os.getenv("ANTHROPIC_MODEL")
        or DEFAULT_ANTHROPIC_MODEL
    )


def _azure_openai_configured() -> bool:
    return bool(
        os.getenv("OPENAI_ENDPOINT", "").strip()
        and os.getenv("OPENAI_API_VERSION", "").strip()
    )


def resolve_openai_model() -> str:
    """Primary OpenAI / Azure deployment for analysis and conversion."""
    explicit = os.getenv("OPENAI_MODEL", "").strip()
    if explicit:
        return explicit
    if _azure_openai_configured():
        return DEFAULT_AZURE_OPENAI_MODEL
    return DEFAULT_OPENAI_MODEL


def resolve_openai_fallback_model() -> str:
    """Fallback deployment when primary model is unavailable (EY Azure)."""
    explicit = os.getenv("OPENAI_MODEL_FALLBACK", "").strip()
    if explicit:
        return explicit
    if _azure_openai_configured():
        return DEFAULT_AZURE_OPENAI_FALLBACK_MODEL
    return ""


def resolve_openai_analysis_model() -> str:
    return os.getenv("OPENAI_MODEL_ANALYSIS", "").strip() or resolve_openai_model()


def resolve_openai_conversion_model() -> str:
    return os.getenv("OPENAI_MODEL_CONVERSION", "").strip() or resolve_openai_model()


def resolve_anthropic_conversion_model() -> str:
    """COBOL→Java conversion and scoped retry conversion (via PipelineService)."""
    return (
        os.getenv("ANTHROPIC_MODEL_CONVERSION")
        or os.getenv("ANTHROPIC_MODEL")
        or resolve_anthropic_analysis_model()
    )


def resolve_llm_runtime() -> LlmRuntimeConfig:
    """
    Pick provider from LLM_PROVIDER (auto | anthropic | openai | openrouter | google).

    Anthropic defaults to DEFAULT_ANTHROPIC_MODEL (claude-sonnet-4-5) unless overridden:
      - ANTHROPIC_MODEL — project-wide override for both roles
      - ANTHROPIC_MODEL_ANALYSIS — analysis / validation LLM stages
      - ANTHROPIC_MODEL_CONVERSION — conversion (falls back to analysis model)
    """
    preference = os.getenv("LLM_PROVIDER", "auto").lower()
    google_key = os.getenv("GOOGLE_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    def _google() -> LlmRuntimeConfig:
        model = os.getenv("GOOGLE_MODEL", "gemini-2.0-flash")
        llm = None
        if ChatGoogleGenerativeAI and google_key:
            llm = ChatGoogleGenerativeAI(model=model, temperature=0, google_api_key=google_key)
        return LlmRuntimeConfig(
            provider="google",
            model_conversion=model,
            model_analysis=model,
            google_llm=llm,
        )

    def _openai() -> LlmRuntimeConfig:
        return LlmRuntimeConfig(
            provider="openai",
            model_conversion=resolve_openai_conversion_model(),
            model_analysis=resolve_openai_analysis_model(),
        )

    def _openrouter() -> LlmRuntimeConfig:
        model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        return LlmRuntimeConfig(provider="openrouter", model_conversion=model, model_analysis=model)

    def _anthropic() -> LlmRuntimeConfig:
        return LlmRuntimeConfig(
            provider="anthropic",
            model_conversion=resolve_anthropic_conversion_model(),
            model_analysis=resolve_anthropic_analysis_model(),
        )

    if preference == "anthropic" and anthropic_key:
        return _anthropic()
    if preference == "openai" and openai_key:
        return _openai()
    if preference == "openrouter" and openrouter_key:
        return _openrouter()
    if preference == "google" and google_key:
        return _google()

    if preference == "auto":
        if anthropic_key:
            return _anthropic()
        if ChatGoogleGenerativeAI and google_key:
            return _google()
        if openai_key:
            return _openai()
        if openrouter_key:
            return _openrouter()

    # Explicit provider without key, or auto with no keys: try any available credential.
    if anthropic_key:
        return _anthropic()
    if ChatGoogleGenerativeAI and google_key:
        return _google()
    if openai_key:
        return _openai()
    if openrouter_key:
        return _openrouter()

    return LlmRuntimeConfig(provider="stub", model_conversion="", model_analysis="")


def provider_has_credentials(provider: str) -> bool:
    """True when the named provider has an API key in the environment."""
    if provider == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    if provider == "openai":
        return bool(os.getenv("OPENAI_API_KEY")) and (
            not _azure_openai_configured()
            or bool(os.getenv("OPENAI_ENDPOINT", "").strip())
        )
    if provider == "openrouter":
        return bool(os.getenv("OPENROUTER_API_KEY"))
    if provider == "google":
        return bool(os.getenv("GOOGLE_API_KEY"))
    return False
