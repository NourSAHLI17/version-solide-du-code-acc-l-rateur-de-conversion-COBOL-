"""GnuCOBOL compile helpers for the behavioral testing pipeline."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from app.services.behavioral_baseline import (
    acme_bank_v3_root,
    sequential_variant_path,
)
from app.services.behavioral_copybook_prep import _default_copybook_search_dirs

SUB_PROGRAMS = frozenset({"CALCFEE", "CHKAML"})
# Main programs that CALL sub-program modules — compile modules first.
MAIN_PROGRAMS_WITH_SUB_DEPS = frozenset({"LOANEVAL"})

_PROGRAM_ID_RE = re.compile(r"\bPROGRAM-ID\.\s*([A-Z0-9-]+)", re.IGNORECASE)


@dataclass
class CompileResult:
    ok: bool
    stdout: str
    stderr: str
    binary_path: Optional[str] = None
    command: Optional[List[str]] = None


def _tool_executable(name: str) -> str:
    resolved = shutil.which(name)
    return resolved if resolved else name


def _module_extension() -> str:
    if sys.platform == "win32":
        return ".dll"
    if sys.platform == "darwin":
        return ".dylib"
    return ".so"


def _remove_stale_cobol_binary(work_dir: Path, prog: str, *, is_sub_program: bool) -> None:
    """Delete prior cobc outputs so every behavioral run recompiles from source."""
    if is_sub_program:
        candidates = [work_dir / f"{prog}{_module_extension()}"]
    else:
        base = work_dir / prog
        candidates = [base, base.with_suffix(".exe")]
    for path in candidates:
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass


def _resolve_compiled_executable(out_bin: Path) -> str:
    if sys.platform == "win32":
        exe = out_bin.with_suffix(".exe")
        if exe.is_file():
            return str(exe)
    if out_bin.is_file():
        return str(out_bin)
    return str(out_bin)


def _program_name_from_path(cobol_path: Path, program_name: str = "") -> str:
    explicit = str(program_name or "").strip().upper()
    if explicit:
        return explicit
    try:
        text = cobol_path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    match = _PROGRAM_ID_RE.search(text)
    if match:
        return match.group(1).upper()
    return cobol_path.stem.upper()


def _cobol_prefers_free_format(source: str) -> bool:
    for line in (source or "").splitlines():
        raw = line.rstrip("\r\n")
        if not raw.strip() or raw.lstrip().startswith("*>"):
            continue
        upper = raw.upper()
        if "PROGRAM-ID" in upper or upper.lstrip().startswith("IDENTIFICATION"):
            indent = len(raw) - len(raw.lstrip())
            return indent < 7
    return False


def resolve_testing_project_dir(project_dir: Optional[str | Path] = None) -> Optional[Path]:
    if project_dir:
        path = Path(project_dir)
        if path.is_dir():
            return path
    return acme_bank_v3_root()


def resolve_copybook_dirs(
    project_dir: Optional[str | Path] = None,
    extra: Optional[Sequence[str]] = None,
) -> List[Path]:
    """Copybook ``-I`` paths: project ``copybooks/`` first, then defaults."""
    dirs = _default_copybook_search_dirs(extra)
    root = resolve_testing_project_dir(project_dir)
    if root is not None:
        cpy = root / "copybooks"
        if cpy.is_dir():
            key = str(cpy.resolve()).casefold()
            if not any(str(d.resolve()).casefold() == key for d in dirs):
                dirs.insert(0, cpy)
    return dirs


def find_acme_cobol_source(
    program_name: str,
    *,
    project_dir: Optional[Path] = None,
    work_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    Prefer pre-generated sequential variant, then work dir, then indexed ``src/``.
    """
    prog = str(program_name or "").strip().upper()
    if not prog:
        return None

    seq_path = sequential_variant_path(prog)
    if seq_path is not None and seq_path.is_file():
        return seq_path

    root = project_dir or acme_bank_v3_root()
    if work_dir is not None:
        staged = work_dir / f"{prog}.cbl"
        if staged.is_file():
            return staged

    if root is not None:
        seq_dir = root / "src" / "sequential"
        if seq_dir.is_dir():
            candidate = seq_dir / f"{prog}.cbl"
            if candidate.is_file():
                return candidate
        src = root / "src" / f"{prog}.cbl"
        if src.is_file():
            return src
    return None


def build_cobc_argv(
    cobol_path: Path,
    work_dir: Path,
    program_name: str,
    *,
    copybook_dirs: Sequence[Path],
    is_sub_program: bool,
    cobol_source: str = "",
) -> List[str]:
    """Build a ``cobc`` argv with ``-std=ibm-strict`` and copybook include paths."""
    cobc = _tool_executable("cobc")
    prog = program_name.upper()
    source = cobol_source or (
        cobol_path.read_text(encoding="utf-8") if cobol_path.is_file() else ""
    )

    if is_sub_program:
        mod_out = work_dir / f"{prog}{_module_extension()}"
        argv: List[str] = [cobc, "-m", "-std=ibm-strict", "-o", str(mod_out)]
    else:
        argv = [cobc, "-x", "-std=ibm-strict", "-o", str(work_dir / prog)]

    for cpy_dir in copybook_dirs:
        argv.extend(["-I", str(cpy_dir)])

    if source and _cobol_prefers_free_format(source):
        argv.insert(1, "-free")

    argv.append(str(cobol_path))
    return argv


def compile_cobol_module(
    cobol_path: Path,
    work_dir: Path,
    program_name: str,
    *,
    copybook_dirs: Sequence[Path],
    timeout_seconds: float = 60.0,
    env: Optional[dict[str, str]] = None,
    cobol_source: str = "",
) -> CompileResult:
    """Compile one COBOL program or sub-program module."""
    prog = program_name.upper()
    is_sub = prog in SUB_PROGRAMS
    _remove_stale_cobol_binary(work_dir, prog, is_sub_program=is_sub)
    cmd = build_cobc_argv(
        cobol_path,
        work_dir,
        prog,
        copybook_dirs=copybook_dirs,
        is_sub_program=is_sub,
        cobol_source=cobol_source,
    )
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            cwd=str(work_dir),
            timeout=timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace") or "compile timed out"
        return CompileResult(ok=False, stdout=stdout, stderr=stderr, command=cmd)

    stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
    stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
    if proc.returncode != 0:
        return CompileResult(ok=False, stdout=stdout, stderr=stderr, command=cmd)

    if is_sub:
        binary = str(work_dir / f"{prog}{_module_extension()}")
    else:
        binary = _resolve_compiled_executable(work_dir / prog)
    return CompileResult(ok=True, stdout=stdout, stderr=stderr, binary_path=binary, command=cmd)


def compile_sub_program_dependencies(
    work_dir: Path,
    *,
    project_dir: Optional[Path],
    copybook_dirs: Sequence[Path],
    timeout_seconds: float,
    env: Optional[dict[str, str]],
) -> Optional[CompileResult]:
    """Compile CALCFEE/CHKAML modules required by LOANEVAL-style mains."""
    for sub in sorted(SUB_PROGRAMS):
        src = find_acme_cobol_source(sub, project_dir=project_dir, work_dir=work_dir)
        if src is None:
            continue
        result = compile_cobol_module(
            src,
            work_dir,
            sub,
            copybook_dirs=copybook_dirs,
            timeout_seconds=timeout_seconds,
            env=env,
        )
        if not result.ok:
            result.stderr = f"{sub} dependency compile failed:\n{result.stderr}"
            return result
    return None


def compile_cobol_for_testing(
    cobol_path: str,
    work_dir: str,
    project_dir: str,
    *,
    program_name: str = "",
    timeout_seconds: float = 60.0,
    env: Optional[dict[str, str]] = None,
    cobol_source: str = "",
) -> CompileResult:
    """
    Compile COBOL for behavioral testing with copybook paths and IBM strict mode.

    Sub-programs (CALCFEE, CHKAML) are built as shared modules (``-m``); mains use ``-x``.
    When compiling LOANEVAL, dependency modules are compiled first.
    """
    cob_path = Path(cobol_path)
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    project = resolve_testing_project_dir(project_dir)
    prog = _program_name_from_path(cob_path, program_name)
    copybook_dirs = resolve_copybook_dirs(project)

    if prog in MAIN_PROGRAMS_WITH_SUB_DEPS:
        dep_failure = compile_sub_program_dependencies(
            work,
            project_dir=project,
            copybook_dirs=copybook_dirs,
            timeout_seconds=timeout_seconds,
            env=env,
        )
        if dep_failure is not None:
            return dep_failure

    return compile_cobol_module(
        cob_path,
        work,
        prog,
        copybook_dirs=copybook_dirs,
        timeout_seconds=timeout_seconds,
        env=env,
        cobol_source=cobol_source,
    )
