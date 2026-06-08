"""Cross-platform baseline capture for sequential COBOL variants.

Equivalent to ``capture_baseline.sh`` but uses Python + ``subprocess``
so it works on both Linux/macOS and Windows (with GnuCOBOL installed).

After COBOL run artifacts are captured, writes ``<PROGRAM>_baseline.json``
for main programs and sub-program test-case JSON (F62).

Usage::

    python tests/e2e/capture_baseline.py
    python tests/e2e/capture_baseline.py --json-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))

from tests.e2e.baseline_metrics import (
    GENERATED_FILE_RECORD_LEN,
    KEY_METRICS,
    SUB_PROGRAM_BASELINES,
)

MAIN_PROGS = ["LOANEVAL", "RECOVRY", "RISKSCOR", "RPTMONTH"]
SUB_PROGS = ["CALCFEE", "CHKAML"]
INPUT_DATS = {"LOANFILE.dat", "CUSTFILE.dat", "COLFILE.dat", "GUARFILE.dat", "SANCFILE.dat"}
PLACEHOLDER_DATS = ["SCORFILE.dat", "RECVNEW.dat"]


def find_cobc() -> Optional[str]:
    return shutil.which("cobc")


def cobol_compiler_version(cobc: str) -> str:
    try:
        proc = subprocess.run(
            [cobc, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        first = (proc.stdout or proc.stderr or "").strip().splitlines()
        if first:
            return first[0].strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "GnuCOBOL (unknown)"


def resolve_paths(
    service_root: Path,
    *,
    seq_dir: Optional[Path] = None,
    cpy_dir: Optional[Path] = None,
    data_dir: Optional[Path] = None,
    baseline_dir: Optional[Path] = None,
) -> dict:
    acme = service_root.parent / "acme-bank-v3"
    return {
        "seq_dir": seq_dir or acme / "src" / "sequential",
        "cpy_dir": cpy_dir or acme / "copybooks",
        "data_dir": data_dir or acme / "data",
        "baseline_dir": baseline_dir or service_root / "tests" / "e2e" / "baseline",
    }


def stage_work_dir(work: Path, seq_dir: Path, data_dir: Path) -> None:
    for f in seq_dir.glob("*.cbl"):
        shutil.copy2(f, work / f.name)
    for f in data_dir.glob("*.dat"):
        shutil.copy2(f, work / f.name)
    for ph in PLACEHOLDER_DATS:
        target = work / ph
        if not target.exists():
            target.touch()


def compile_sub_programs(
    work: Path,
    cpy_dir: Path,
    baseline_dir: Path,
    cobc: str,
) -> List[str]:
    notes: List[str] = []
    for sub in SUB_PROGS:
        src = work / f"{sub}.cbl"
        if not src.exists():
            notes.append(f"SKIP {sub}: source not found")
            continue
        log_path = baseline_dir / f"{sub}_compile.log"
        result = subprocess.run(
            [cobc, "-m", "-std=ibm-strict", "-I", str(cpy_dir), str(src)],
            cwd=str(work),
            capture_output=True,
            text=True,
        )
        log_path.write_text(result.stderr + result.stdout, encoding="utf-8")
        if result.returncode != 0:
            notes.append(f"WARNING: {sub} compile failed (rc={result.returncode})")
        else:
            notes.append(f"OK: {sub} compiled")
    return notes


def run_main_programs(
    work: Path,
    cpy_dir: Path,
    baseline_dir: Path,
    cobc: str,
) -> dict:
    results = {"passed": 0, "failed": 0, "programs": {}}
    for prog in MAIN_PROGS:
        src = work / f"{prog}.cbl"
        if not src.exists():
            results["programs"][prog] = {"status": "skipped", "reason": "source not found"}
            continue

        compile_log = baseline_dir / f"{prog}_compile.log"
        cr = subprocess.run(
            [cobc, "-x", "-std=ibm-strict", "-I", str(cpy_dir), str(src)],
            cwd=str(work),
            capture_output=True,
            text=True,
        )
        compile_log.write_text(cr.stderr + cr.stdout, encoding="utf-8")
        if cr.returncode != 0:
            results["failed"] += 1
            results["programs"][prog] = {"status": "compile_failed"}
            continue

        exe = work / prog
        if sys.platform == "win32":
            exe = work / f"{prog}.exe"

        rr = subprocess.run(
            [str(exe)],
            cwd=str(work),
            capture_output=True,
            text=True,
            timeout=60,
        )
        combined = (rr.stdout or "") + (rr.stderr or "")
        (baseline_dir / f"{prog}_stdout.txt").write_text(combined, encoding="utf-8")
        (baseline_dir / f"{prog}_exitcode.txt").write_text(str(rr.returncode), encoding="utf-8")

        for dat in work.glob("*.dat"):
            if dat.name not in INPUT_DATS:
                shutil.copy2(dat, baseline_dir / f"{prog}_{dat.name}")

        results["passed"] += 1
        results["programs"][prog] = {"status": "captured", "exitcode": rr.returncode}

    return results


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def record_count_for_dat(filename: str, size: int) -> Optional[int]:
    if size == 0:
        return 0
    rec_len = GENERATED_FILE_RECORD_LEN.get(filename)
    if rec_len and size % rec_len == 0:
        return size // rec_len
    return None


def collect_generated_files(baseline_dir: Path, program: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    prefix = f"{program}_"
    for path in sorted(baseline_dir.glob(f"{prefix}*.dat")):
        name = path.name[len(prefix) :]
        if name in INPUT_DATS:
            continue
        size = path.stat().st_size
        entry: Dict[str, Any] = {
            "md5": md5_file(path),
            "size_bytes": size,
        }
        rc = record_count_for_dat(name, size)
        if rc is not None:
            entry["record_count"] = rc
        out[name] = entry
    return out


def build_main_program_baseline(
    baseline_dir: Path,
    program: str,
    *,
    cobol_compiler: str,
    captured_at: Optional[str] = None,
) -> Dict[str, Any]:
    stdout_path = baseline_dir / f"{program}_stdout.txt"
    exit_path = baseline_dir / f"{program}_exitcode.txt"
    if not stdout_path.is_file():
        raise FileNotFoundError(f"missing stdout capture: {stdout_path}")

    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
    exit_code = 0
    if exit_path.is_file():
        try:
            exit_code = int(exit_path.read_text(encoding="utf-8").strip())
        except ValueError:
            exit_code = -1

    return {
        "program": program,
        "stdout_md5": hashlib.md5(stdout_text.encode("utf-8")).hexdigest(),
        "stdout_lines": len(stdout_text.splitlines()),
        "exit_code": exit_code,
        "generated_files": collect_generated_files(baseline_dir, program),
        "key_metrics": dict(KEY_METRICS[program]),
        "cobol_compiler": cobol_compiler,
        "captured_at": captured_at or datetime.now(timezone.utc).isoformat(),
    }


def write_baseline_json_files(
    baseline_dir: Path,
    *,
    cobol_compiler: str,
    programs: Optional[List[str]] = None,
) -> List[Path]:
    """Write ``<PROGRAM>_baseline.json`` for mains and sub-program test cases."""
    baseline_dir.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(timezone.utc).isoformat()
    written: List[Path] = []

    for prog in programs or MAIN_PROGS:
        doc = build_main_program_baseline(
            baseline_dir,
            prog,
            cobol_compiler=cobol_compiler,
            captured_at=captured_at,
        )
        path = baseline_dir / f"{prog}_baseline.json"
        path.write_text(json.dumps(doc, indent=4) + "\n", encoding="utf-8")
        written.append(path)

    for sub, doc in SUB_PROGRAM_BASELINES.items():
        path = baseline_dir / f"{sub}_baseline.json"
        path.write_text(json.dumps(doc, indent=4) + "\n", encoding="utf-8")
        written.append(path)

    return written


def capture_baseline(
    service_root: Path,
    *,
    seq_dir: Optional[Path] = None,
    cpy_dir: Optional[Path] = None,
    data_dir: Optional[Path] = None,
    baseline_dir: Optional[Path] = None,
    cobc_path: Optional[str] = None,
    skip_cobol_run: bool = False,
    skip_json: bool = False,
) -> dict:
    """Run baseline capture and return a summary dict."""
    cobc = cobc_path or find_cobc()
    if not cobc and not skip_cobol_run:
        raise RuntimeError("cobc (GnuCOBOL) not found in PATH")

    paths = resolve_paths(
        service_root,
        seq_dir=seq_dir,
        cpy_dir=cpy_dir,
        data_dir=data_dir,
        baseline_dir=baseline_dir,
    )
    if not skip_cobol_run and not paths["seq_dir"].is_dir():
        raise RuntimeError(f"Sequential variant directory not found: {paths['seq_dir']}")

    paths["baseline_dir"].mkdir(parents=True, exist_ok=True)
    compiler_label = cobol_compiler_version(cobc) if cobc else "GnuCOBOL (not run)"

    sub_notes: List[str] = []
    prog_results = {"passed": 0, "failed": 0, "programs": {}}

    if not skip_cobol_run:
        with tempfile.TemporaryDirectory(prefix="cobol_baseline_") as tmpdir:
            work = Path(tmpdir)
            stage_work_dir(work, paths["seq_dir"], paths["data_dir"])
            sub_notes = compile_sub_programs(work, paths["cpy_dir"], paths["baseline_dir"], cobc)
            prog_results = run_main_programs(work, paths["cpy_dir"], paths["baseline_dir"], cobc)

    json_paths: List[str] = []
    if not skip_json:
        for p in write_baseline_json_files(
            paths["baseline_dir"],
            cobol_compiler=compiler_label,
        ):
            json_paths.append(str(p))

    return {
        "baseline_dir": str(paths["baseline_dir"]),
        "cobol_compiler": compiler_label,
        "sub_program_notes": sub_notes,
        "json_files": json_paths,
        **prog_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture COBOL baseline outputs")
    parser.add_argument("--seq-dir", type=Path, default=None)
    parser.add_argument("--cpy-dir", type=Path, default=None)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--baseline-dir", type=Path, default=None)
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Only refresh *_baseline.json from existing stdout/dat captures",
    )
    args = parser.parse_args()

    service_root = Path(__file__).resolve().parents[2]
    if str(service_root) not in sys.path:
        sys.path.insert(0, str(service_root))

    try:
        result = capture_baseline(
            service_root,
            seq_dir=args.seq_dir,
            cpy_dir=args.cpy_dir,
            data_dir=args.data_dir,
            baseline_dir=args.baseline_dir,
            skip_cobol_run=args.json_only,
        )
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n=== Baseline Capture Complete ===")
    if not args.json_only:
        print(f"  Passed: {result['passed']} / {len(MAIN_PROGS)}")
        if result["failed"]:
            print(f"  Failed: {result['failed']}")
    print(f"  Compiler: {result['cobol_compiler']}")
    print(f"  Output: {result['baseline_dir']}")
    if not args.json_only:
        for name, info in result["programs"].items():
            print(f"  {name}: {info['status']}")
    for jp in result.get("json_files", []):
        print(f"  JSON: {Path(jp).name}")


if __name__ == "__main__":
    main()
