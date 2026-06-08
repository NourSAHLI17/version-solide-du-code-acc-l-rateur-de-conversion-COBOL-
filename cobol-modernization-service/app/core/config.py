"""Configuration helpers for the COBOL modernization backend."""

import os
from dataclasses import dataclass

import app.env_bootstrap  # noqa: F401 — ensure service .env loaded (idempotent)
from app.services.llm_config import (
    DEFAULT_ANTHROPIC_MODEL,
    resolve_anthropic_analysis_model,
    resolve_anthropic_conversion_model,
    resolve_openai_model,
)


def _env_truthy(key: str, *, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class AppConfig:
    """
    Runtime configuration for API and agent wiring.

    Returns:
        An immutable configuration object with API host, port, and LLM settings.

    Example:
        Input:
            Environment contains HOST=0.0.0.0 and PORT=8000
        Output:
            AppConfig(host="0.0.0.0", port=8000, google_api_key="...", llm_provider="google")
    """

    host: str = "0.0.0.0"
    port: int = 8000
    google_api_key: str | None = None
    openai_api_key: str | None = None
    openrouter_api_key: str | None = None
    anthropic_api_key: str | None = None
    llm_provider: str = "auto"
    openai_model: str = "gpt-4.1-mini"
    openrouter_model: str = "openai/gpt-4o-mini"
    anthropic_model_analysis: str = DEFAULT_ANTHROPIC_MODEL
    anthropic_model_conversion: str = DEFAULT_ANTHROPIC_MODEL
    parser_backend: str = "hybrid"
    analysis_engine: str = "llm"
    analysis_use_column_paragraph_sources: bool = False
    java_project_profile: str = "plain_java"
    behavioral_baseline_test_mode: bool = False


def load_config() -> AppConfig:
    """
    Load runtime configuration from environment variables.

    Returns:
        AppConfig populated from `.env` and process environment variables.

    Example:
        Input:
            HOST=127.0.0.1, PORT=9000
        Output:
            AppConfig(host="127.0.0.1", port=9000, google_api_key=None, llm_provider="auto")
    """

    return AppConfig(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        llm_provider=os.getenv("LLM_PROVIDER", "auto").lower(),
        openai_model=resolve_openai_model(),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
        anthropic_model_analysis=resolve_anthropic_analysis_model(),
        anthropic_model_conversion=resolve_anthropic_conversion_model(),
        parser_backend=os.getenv("PARSER_BACKEND", "hybrid"),
        analysis_engine=os.getenv("ANALYSIS_ENGINE", "llm").strip().lower(),
        analysis_use_column_paragraph_sources=_env_truthy("ANALYSIS_USE_COLUMN_PARAGRAPH_SOURCES"),
        java_project_profile=os.getenv("JAVA_PROJECT_PROFILE", "plain_java").strip().lower() or "plain_java",
        behavioral_baseline_test_mode=_env_truthy("BEHAVIORAL_BASELINE_TEST_MODE"),
    )
