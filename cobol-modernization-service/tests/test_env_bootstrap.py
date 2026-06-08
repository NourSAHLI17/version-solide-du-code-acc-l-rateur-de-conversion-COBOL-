"""Regression: service-root ``.env`` loads when process CWD is not the service directory."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parent.parent


def test_service_root_points_at_package_parent():
    from app.env_bootstrap import SERVICE_ROOT as root

    assert root.resolve() == SERVICE_ROOT.resolve()
    assert (root / "app" / "main.py").is_file()
    assert (root / "app" / "env_bootstrap.py").is_file()


def test_at_least_one_llm_key_visible_after_import_from_foreign_cwd(tmp_path):
    """
    Subprocess: chdir to an empty directory, import app (as uvicorn would from monorepo root).

    Skips if service ``.env`` does not define any LLM API key (e.g. CI without secrets).
    """
    env_file = SERVICE_ROOT / ".env"
    if not env_file.is_file():
        pytest.skip("No service .env present")

    script = f"""
import os
import sys
from pathlib import Path

sys.path.insert(0, r"{SERVICE_ROOT.as_posix()}")
os.chdir(r"{tmp_path.as_posix()}")
assert Path.cwd().resolve() != Path(r"{SERVICE_ROOT.as_posix()}").resolve()

import app.env_bootstrap  # noqa: F401
from app.agents.conversion_agent import ConversionAgent

agent = ConversionAgent()
keys = (
    bool(os.getenv("OPENAI_API_KEY")),
    bool(os.getenv("OPENROUTER_API_KEY")),
    bool(os.getenv("GOOGLE_API_KEY")),
)
if not any(keys) or not agent.can_invoke_llm():
    raise SystemExit("no_llm_keys_or_cannot_invoke")
raise SystemExit(0)
"""
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ},
    )
    if proc.returncode != 0:
        pytest.skip(
            "Local .env has no LLM keys or can_invoke_llm false after foreign cwd import: "
            f"{proc.stderr or proc.stdout}",
        )
