"""Baseline behavioral testing: SEQUENTIAL COBOL variants + flat .dat staging for ACME."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple

from app.core.config import load_config
from app.env_bootstrap import SERVICE_ROOT
from app.services.behavioral_file_harness import _assign_names_in_source, _service_roots
from app.services.cobol_sequential_variant import create_sequential_variant

_LOG = logging.getLogger(__name__)

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_PROGRAM_ID_RE = re.compile(r"\bPROGRAM-ID\.\s*([A-Z0-9-]+)", re.IGNORECASE)

# ACME programs that use flat .dat ASSIGN names (baseline harness).
_ACME_PROGRAMS = frozenset(
    {"LOANEVAL", "RISKSCOR", "RECOVRY", "RPTMONTH", "CHKAML", "CALCFEE"}
)


def _env_truthy(key: str, *, default: bool = False) -> bool:
    import os

    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def is_baseline_test_mode(request_flag: Optional[bool] = None) -> bool:
    """True when behavioral runs should use SEQUENTIAL COBOL variants."""
    if request_flag is not None:
        return bool(request_flag)
    cfg = load_config()
    return bool(getattr(cfg, "behavioral_baseline_test_mode", False)) or _env_truthy(
        "BEHAVIORAL_BASELINE_TEST_MODE"
    )


def acme_bank_v3_root() -> Optional[Path]:
    """Locate the ``acme-bank-v3`` dataset next to the modernization service."""
    candidates: List[Path] = []
    for root in _service_roots():
        candidates.append(root.parent / "acme-bank-v3")
    candidates.append(_PACKAGE_ROOT.parent / "acme-bank-v3")
    candidates.append(SERVICE_ROOT.parent / "acme-bank-v3")
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()).casefold()
        if key in seen:
            continue
        seen.add(key)
        if (path / "src").is_dir():
            return path
    return None


def acme_sequential_src_dir() -> Optional[Path]:
    root = acme_bank_v3_root()
    if root is None:
        return None
    seq = root / "src" / "sequential"
    return seq if seq.is_dir() else None


def _program_name_from_source(cobol_source: str, program_name: str) -> str:
    explicit = str(program_name or "").strip().upper()
    if explicit and explicit != "UNKNOWN":
        return explicit
    match = _PROGRAM_ID_RE.search(cobol_source or "")
    return match.group(1).upper() if match else explicit or "UNKNOWN"


def sequential_variant_path(program_name: str) -> Optional[Path]:
    """Path to pre-generated ``src/sequential/<PROGRAM>.cbl`` when present."""
    seq_dir = acme_sequential_src_dir()
    if seq_dir is None:
        return None
    prog = str(program_name or "").strip().upper()
    path = seq_dir / f"{prog}.cbl"
    return path if path.is_file() else None


def resolve_cobol_for_baseline(
    cobol_source: str,
    program_name: str = "",
    *,
    baseline_mode: Optional[bool] = None,
) -> Tuple[str, str]:
    """
    Return COBOL source for behavioral compile.

    Returns ``(source_text, mode_tag)`` where *mode_tag* is one of:
    ``indexed`` (unchanged), ``sequential_file``, ``sequential_transform``.
    """
    prog = _program_name_from_source(cobol_source, program_name)
    seq_path = sequential_variant_path(prog)
    if seq_path is not None:
        _LOG.info("baseline: using sequential variant file %s", seq_path)
        return seq_path.read_text(encoding="utf-8"), "sequential_file"

    if not is_baseline_test_mode(baseline_mode):
        return cobol_source, "indexed"

    if "ORGANIZATION IS INDEXED" in (cobol_source or "").upper():
        transformed = create_sequential_variant(cobol_source)
        _LOG.info("baseline: inline SEQUENTIAL transform program=%s", prog)
        return transformed, "sequential_transform"

    return cobol_source, "indexed"


def needs_acme_dat_harness(cobol_source: str, program_name: str) -> bool:
    prog = _program_name_from_source(cobol_source, program_name)
    if prog in _ACME_PROGRAMS:
        return True
    assigns = _assign_names_in_source(cobol_source)
    return any(name.lower().endswith(".dat") for name in assigns)


def stage_acme_flat_dat_files(
    tmp_dir: Path,
    *,
    program_name: str = "",
    cobol_source: str = "",
    project_data_dir: str = "",
) -> Tuple[bool, str]:
    """
    Copy flat ``.dat`` fixtures into *tmp_dir* for ACME batch programs.

    Delegates to :func:`stage_test_data` so input files and output placeholders
    are present before GnuCOBOL/Java OPEN.
    """
    if not needs_acme_dat_harness(cobol_source, program_name):
        return True, ""

    from app.services.behavioral_file_harness import resolve_project_data_dir, stage_test_data

    staged = stage_test_data(str(tmp_dir), project_data_dir)
    if staged:
        return True, ""

    if resolve_project_data_dir(project_data_dir) is None:
        return False, "acme-bank-v3 data directory not found for baseline .dat staging"
    return True, ""
