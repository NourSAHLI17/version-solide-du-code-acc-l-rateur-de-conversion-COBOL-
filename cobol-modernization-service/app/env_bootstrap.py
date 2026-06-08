"""
Load ``cobol-modernization-service/.env`` before any code reads API keys.

``uvicorn app.main:app`` may use a current working directory outside this tree;
dotenv's default load-from-CWD would miss the file. This module resolves the
service root from ``__file__`` and loads ``{service_root}/.env`` explicitly.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# app/env_bootstrap.py -> app/ -> cobol-modernization-service/
SERVICE_ROOT = Path(__file__).resolve().parent.parent

SERVICE_ENV_FILE = SERVICE_ROOT / ".env"
load_dotenv(SERVICE_ENV_FILE)
load_dotenv()  # optional: CWD can override for local experiments

__all__ = ["SERVICE_ENV_FILE", "SERVICE_ROOT"]
