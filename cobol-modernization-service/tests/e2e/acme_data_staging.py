"""Single source of truth for staging ACME .dat files in F41 / behavioral runs."""

from __future__ import annotations

import hashlib
import shutil
from enum import Enum
from pathlib import Path
from typing import Optional

_SERVICE_ROOT = Path(__file__).resolve().parents[2]
ACME_DATA_DIR = _SERVICE_ROOT.parent / "acme-bank-v3" / "data"
FIXTURE_DIR = _SERVICE_ROOT / "tests" / "fixtures" / "acme_e2e"
LOANFILE_NAME = "LOANFILE.dat"

PLACEHOLDER_DATS = (
    "SCORFILE.dat",
    "RECVNEW.dat",
    "DECIRPT.dat",
    "EVALREJ.dat",
)


class AcmeDataProfile(str, Enum):
    """Which LOANFILE and .dat set to stage."""

    # Full acme-bank-v3/data (800-line LOANFILE) — Java behavioral / key_metrics target.
    BEHAVIORAL = "behavioral"
    # Curated 4-record LOANFILE for legacy COBOL-captured stdout text comparison only.
    LEGACY_COBL_TEXT = "legacy_cobol_text"


def loanfile_source_path(profile: AcmeDataProfile) -> Path:
    """Return the canonical LOANFILE path for a staging profile."""
    if profile == AcmeDataProfile.BEHAVIORAL:
        return ACME_DATA_DIR / LOANFILE_NAME
    e2e = FIXTURE_DIR / "LOANFILE_E2E.dat"
    if e2e.is_file():
        return e2e
    return ACME_DATA_DIR / LOANFILE_NAME


def stage_acme_data(
    work_dir: Path,
    profile: AcmeDataProfile,
    *,
    overwrite: bool = True,
) -> None:
    """Stage .dat files under *work_dir* for the given profile."""
    work_dir.mkdir(parents=True, exist_ok=True)

    if ACME_DATA_DIR.is_dir():
        for dat in ACME_DATA_DIR.glob("*.dat"):
            dst = work_dir / dat.name
            if dat.name == LOANFILE_NAME and profile == AcmeDataProfile.LEGACY_COBL_TEXT:
                continue
            if overwrite or not dst.exists():
                shutil.copy2(dat, dst)

    if profile == AcmeDataProfile.LEGACY_COBL_TEXT:
        src = loanfile_source_path(profile)
        if src.is_file():
            shutil.copy2(src, work_dir / LOANFILE_NAME)

    for placeholder in PLACEHOLDER_DATS:
        target = work_dir / placeholder
        if overwrite or not target.exists():
            target.touch()


def loanfile_md5(work_dir: Path) -> Optional[str]:
    path = work_dir / LOANFILE_NAME
    if not path.is_file():
        return None
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def loanfile_line_count(work_dir: Path) -> int:
    path = work_dir / LOANFILE_NAME
    if not path.is_file():
        return 0
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


def profiles_use_same_loanfile(profile_a: AcmeDataProfile, profile_b: AcmeDataProfile) -> bool:
    return loanfile_source_path(profile_a) == loanfile_source_path(profile_b)
