"""Stage disk files for live behavioral COBOL runs (batch programs with ASSIGN names)."""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from app.env_bootstrap import SERVICE_ROOT

_LOG = logging.getLogger(__name__)

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]

# Output .dat files programs create at runtime (must exist before OPEN on GnuCOBOL).
_OUTPUT_PLACEHOLDER_DATS = (
    "SCORFILE.dat",
    "BCTSUBM.dat",
    "RECVNEW.dat",
    "LETTERS.dat",
    "MONTHRPT.dat",
    "ESCARPT.dat",
    "SORTWK2.dat",
    "SORTWRK.dat",
    "RISKRPT.dat",
    "DECIRPT.dat",
    "EVALREJ.dat",
)

# ASSIGN literals used by tests/fixtures/usecase3/TXNPOST.cbl
_TXNPOST_ASSIGN_FILES = (
    "ACME.CUSTOMER.MASTER",
    "ACME.TRANSACTIONS",
)

_STMTRPT_ASSIGN_FILES = ("ACME.CUSTOMER.MASTER",)

_ASSIGN_LITERAL_RE = re.compile(
    r"ASSIGN\s+TO\s+['\"](?P<name>[^'\"]+)['\"]",
    re.IGNORECASE,
)


def _service_roots() -> List[Path]:
    roots: List[Path] = []
    for candidate in (SERVICE_ROOT, _PACKAGE_ROOT):
        key = str(candidate.resolve()).casefold()
        if key not in {str(r.resolve()).casefold() for r in roots} and candidate.is_dir():
            roots.append(candidate)
    return roots or [_PACKAGE_ROOT]


def resolve_project_data_dir(project_data_dir: str = "") -> Optional[Path]:
    """Locate the ACME/project data directory containing input ``.dat`` fixtures."""
    explicit = str(project_data_dir or "").strip()
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            for root in _service_roots():
                candidate = root / path
                if candidate.is_dir():
                    return candidate
            parent_candidate = _PACKAGE_ROOT.parent / path
            if parent_candidate.is_dir():
                return parent_candidate
        elif path.is_dir():
            return path

    from app.services.behavioral_baseline import acme_bank_v3_root

    acme_root = acme_bank_v3_root()
    if acme_root is not None:
        data_dir = acme_root / "data"
        if data_dir.is_dir():
            return data_dir

    for root in _service_roots():
        for relative in ("acme-bank-v3/data", "data", "tests/fixtures/data"):
            candidate = root / relative
            if not candidate.is_dir() and root != _PACKAGE_ROOT:
                candidate = _PACKAGE_ROOT.parent / relative
            if candidate.is_dir():
                return candidate
    return None


# Fixed record lengths for GnuCOBOL SEQUENTIAL reads (strip line terminators on staging).
_COBOL_FLAT_RECORD_LENS: dict[str, int] = {
    "custfile.dat": 434,
    "colfile.dat": 253,
    "guarfile.dat": 130,
    "sancfile.dat": 80,
}


def _copy_dat_for_cobol_sequential(src: Path, dest: Path) -> None:
    """
    Copy a ``.dat`` fixture for GnuCOBOL fixed-length SEQUENTIAL READ.

    Line-delimited fixtures (434-byte rows + newline) misalign after the first
    READ when RECORD CONTAINS matches row length only. Concatenate rows without
    terminators and pad to the configured record length.
    """
    record_len = _COBOL_FLAT_RECORD_LENS.get(src.name.casefold())
    raw = src.read_bytes()
    if record_len is None or b"\n" not in raw:
        shutil.copy2(src, dest)
        return

    out = bytearray()
    for line in raw.splitlines():
        chunk = line[:record_len]
        if len(chunk) < record_len:
            chunk = chunk + b" " * (record_len - len(chunk))
        out.extend(chunk)
    dest.write_bytes(out)


def normalize_acme_dat_files_for_cobol(
    work_dir: Path,
    project_data_dir: str = "",
) -> None:
    """Rewrite line-delimited CUST/COL/GUAR fixtures for GnuCOBOL fixed-length READ."""
    data_root = resolve_project_data_dir(project_data_dir)
    if data_root is None:
        return
    work_dir.mkdir(parents=True, exist_ok=True)
    for fname in _COBOL_FLAT_RECORD_LENS:
        src = data_root / fname
        if src.is_file():
            _copy_dat_for_cobol_sequential(src, work_dir / fname)


def restore_acme_line_delimited_dat_files(
    work_dir: Path,
    project_data_dir: str = "",
) -> None:
    """Restore Java-friendly line-delimited fixtures after a COBOL run."""
    data_root = resolve_project_data_dir(project_data_dir)
    if data_root is None:
        return
    work_dir.mkdir(parents=True, exist_ok=True)
    for fname in _COBOL_FLAT_RECORD_LENS:
        src = data_root / fname
        if src.is_file():
            shutil.copy2(src, work_dir / fname)


def stage_test_data(work_dir: str, project_data_dir: str = "") -> List[str]:
    """Copy all input ``.dat`` files to the test working directory."""
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    staged: List[str] = []

    data_root = resolve_project_data_dir(project_data_dir)
    if data_root is not None:
        for entry in sorted(data_root.iterdir()):
            if not entry.is_file() or not entry.name.lower().endswith(".dat"):
                continue
            dest = work / entry.name
            shutil.copy2(entry, dest)
            staged.append(entry.name)

    for fname in _OUTPUT_PLACEHOLDER_DATS:
        path = work / fname
        if not path.exists():
            path.touch()

    if staged:
        _LOG.info(
            "staged behavioral .dat files work_dir=%s data_dir=%s files=%s",
            work,
            data_root,
            ",".join(staged),
        )
    return staged


def txnpost_behavioral_data_dir() -> Optional[Path]:
    for root in _service_roots():
        directory = root / "tests" / "fixtures" / "usecase3" / "behavioral_data"
        if directory.is_dir():
            return directory
    return None


def _assign_names_in_source(cobol_source: str) -> List[str]:
    names: List[str] = []
    for match in _ASSIGN_LITERAL_RE.finditer(cobol_source or ""):
        text = match.group("name").strip()
        if text and text not in names:
            names.append(text)
    return names


def needs_stmtrpt_file_harness(cobol_source: str, program_name: str) -> bool:
    if str(program_name or "").strip().upper() == "STMTRPT":
        return True
    assigns = set(_assign_names_in_source(cobol_source))
    return "ACME.STMT.REPORT" in assigns or assigns >= set(_STMTRPT_ASSIGN_FILES)


def needs_txnpost_file_harness(cobol_source: str, program_name: str) -> bool:
    """True when the program expects TXNPOST-style ACME dataset files on disk."""
    if str(program_name or "").strip().upper() == "TXNPOST":
        return True
    assigns = set(_assign_names_in_source(cobol_source))
    return all(name in assigns for name in _TXNPOST_ASSIGN_FILES)


def stage_txnpost_behavioral_files(
    tmp_dir: Path,
    *,
    program_name: str = "",
    cobol_source: str = "",
    project_data_dir: str = "",
) -> Tuple[bool, str]:
    """
    Copy indexed/sequential fixture files into the behavioral run directory.

    Files are placed using the same ASSIGN literals the COBOL program references
    (relative to tmp_dir, which is the subprocess cwd for program.exe).
    """
    if not needs_txnpost_file_harness(cobol_source, program_name):
        return True, ""

    fixture_dir = txnpost_behavioral_data_dir()
    if fixture_dir is None:
        return False, "TXNPOST behavioral data directory not found on API host"

    tmp_dir.mkdir(parents=True, exist_ok=True)
    copied: List[str] = []
    for assign_name in _TXNPOST_ASSIGN_FILES:
        src = fixture_dir / assign_name
        if not src.is_file():
            return (
                False,
                f"Missing behavioral fixture {assign_name} under {fixture_dir}. "
                "Run scripts/build_txnpost_behavioral_data.py on the API host.",
            )
        dest = tmp_dir / assign_name
        shutil.copy2(src, dest)
        copied.append(assign_name)

    _LOG.info(
        "staged TXNPOST behavioral files program=%s tmp=%s files=%s",
        program_name or "unknown",
        tmp_dir,
        ",".join(copied),
    )
    return True, ""


def stage_stmtrpt_behavioral_files(
    tmp_dir: Path,
    *,
    program_name: str = "",
    cobol_source: str = "",
    project_data_dir: str = "",
) -> Tuple[bool, str]:
    if not needs_stmtrpt_file_harness(cobol_source, program_name):
        return True, ""
    fixture_dir = txnpost_behavioral_data_dir()
    if fixture_dir is None:
        return False, "STMTRPT behavioral data directory not found on API host"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    src = fixture_dir / "ACME.CUSTOMER.MASTER"
    if not src.is_file():
        return False, f"Missing behavioral fixture ACME.CUSTOMER.MASTER under {fixture_dir}"
    shutil.copy2(src, tmp_dir / "ACME.CUSTOMER.MASTER")
    _LOG.info("staged STMTRPT behavioral files program=%s tmp=%s", program_name or "unknown", tmp_dir)
    return True, ""


def stage_behavioral_data_files(
    tmp_dir: Path,
    *,
    program_name: str = "",
    cobol_source: str = "",
    project_data_dir: str = "",
) -> Tuple[bool, str]:
    """Entry point: stage any program-specific behavioral disk fixtures."""
    from app.services.behavioral_baseline import stage_acme_flat_dat_files

    for stage_fn in (
        stage_acme_flat_dat_files,
        stage_txnpost_behavioral_files,
        stage_stmtrpt_behavioral_files,
    ):
        ok, msg = stage_fn(
            tmp_dir,
            program_name=program_name,
            cobol_source=cobol_source,
            project_data_dir=project_data_dir,
        )
        if not ok:
            return ok, msg
    return True, ""


def read_stmtrpt_report_stdout(tmp_dir: Path) -> str:
    """STMTRPT writes ACME.STMT.REPORT (no DISPLAY) — surface key lines for behavioral diff."""
    report_path = tmp_dir / "ACME.STMT.REPORT"
    if not report_path.is_file():
        return ""
    text = report_path.read_bytes().decode("utf-8", errors="replace")
    lines: List[str] = []
    if "CUSTOMER STATEMENT REPORT" in text:
        lines.append("CUSTOMER STATEMENT REPORT")
    if "GRAND TOTAL" in text.upper():
        lines.append("GRAND TOTAL:")
    if "TOTAL RECORDS" in text.upper():
        match = re.search(r"TOTAL\s+RECORDS:\s*(\d+)", text, flags=re.IGNORECASE)
        if match:
            lines.append(f"TOTAL RECORDS: {int(match.group(1)):05d}")
        else:
            lines.append("TOTAL RECORDS:")
    if "END OF REPORT" in text.upper():
        lines.append("END OF REPORT")
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def read_txnpost_report_stdout(tmp_dir: Path) -> str:
    """
    TXNPOST writes the report to ASSIGN 'ACME.POST.REPORT' (no DISPLAY).

    For behavioral diff, surface report lines as synthetic stdout when the file exists.
    """
    report_path = tmp_dir / "ACME.POST.REPORT"
    if not report_path.is_file():
        return ""
    raw = report_path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    lines: List[str] = []
    if "TRANSACTION POSTING REPORT" in text:
        lines.append("TRANSACTION POSTING REPORT")
    posted = re.search(r"POSTED:\s+(\d+)", text, flags=re.IGNORECASE)
    if posted:
        lines.append(f"POSTED:  {int(posted.group(1)):05d}")
    failed = re.search(r"FAILED:\s+(\d+)", text, flags=re.IGNORECASE)
    if failed:
        lines.append(f"FAILED:  {int(failed.group(1)):05d}")
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def read_report_stdout_for_program(
    tmp_dir: Path,
    *,
    program_name: str = "",
    cobol_source: str = "",
) -> str:
    name = str(program_name or "").strip().upper()
    if name == "TXNPOST" or "ACME.POST.REPORT" in (cobol_source or ""):
        return read_txnpost_report_stdout(tmp_dir)
    if name == "STMTRPT" or "ACME.STMT.REPORT" in (cobol_source or ""):
        return read_stmtrpt_report_stdout(tmp_dir)
    return ""
