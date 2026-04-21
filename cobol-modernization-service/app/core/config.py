"""Configuration helpers for the COBOL modernization backend."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


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
    llm_provider: str = "auto"
    openai_model: str = "gpt-4.1-mini"
    openrouter_model: str = "openai/gpt-4o-mini"
    parser_backend: str = "heuristic"


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
        llm_provider=os.getenv("LLM_PROVIDER", "auto").lower(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
        parser_backend=os.getenv("PARSER_BACKEND", "heuristic"),
    )
