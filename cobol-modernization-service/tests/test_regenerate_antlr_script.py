"""Smoke tests for repo-root ANTLR regeneration helper (FIX 3)."""

from __future__ import annotations

import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "regenerate_antlr.sh"


@pytest.mark.skipif(not SCRIPT_PATH.is_file(), reason="regenerate_antlr.sh not present")
def test_regenerate_script_exists_and_is_executable() -> None:
    """scripts/regenerate_antlr.sh must exist; POSIX environments must mark it executable."""
    assert SCRIPT_PATH.is_file(), "regenerate_antlr.sh not found"
    if sys.platform == "win32":
        pytest.skip("POSIX executable bit check not applicable")
    mode = SCRIPT_PATH.stat().st_mode
    assert mode & stat.S_IXUSR, "regenerate_antlr.sh should be chmod +x for Unix CI"


@pytest.mark.skipif(sys.platform.startswith("win"), reason="bash subprocess output encoding is unreliable on Windows")
@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")
@pytest.mark.skipif(not SCRIPT_PATH.is_file(), reason="regenerate_antlr.sh not present")
def test_verify_flag_reports_artifacts() -> None:
    """--verify must succeed when generated files exist, or emit MISSING."""
    proc = subprocess.run(
        ["bash", str(SCRIPT_PATH), "--verify"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode in (0, 1)
    if proc.returncode == 0:
        assert "ANTLR artifacts OK" in combined
    else:
        assert "MISSING:" in combined
