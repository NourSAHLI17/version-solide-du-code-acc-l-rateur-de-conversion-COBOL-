"""File-based analysis result cache keyed by program name + COBOL source hash."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from app.env_bootstrap import SERVICE_ROOT

CACHE_DIR = SERVICE_ROOT / ".analysis_cache"
CACHE_VERSION = "v4"


def get_analysis_cache_key(program_name: str, source: str) -> str:
    source_hash = hashlib.md5(source.encode("utf-8", errors="replace")).hexdigest()[:12]
    safe_name = (program_name or "unknown").strip().upper() or "UNKNOWN"
    return f"{CACHE_VERSION}_{safe_name}_{source_hash}"


def _cache_path(cache_key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{cache_key}.json"


def load_analysis_cache(cache_key: str) -> Optional[Dict[str, Any]]:
    path = _cache_path(cache_key)
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def save_analysis_cache(cache_key: str, result: Dict[str, Any]) -> None:
    path = _cache_path(cache_key)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(result, handle)
    os.replace(tmp, path)
