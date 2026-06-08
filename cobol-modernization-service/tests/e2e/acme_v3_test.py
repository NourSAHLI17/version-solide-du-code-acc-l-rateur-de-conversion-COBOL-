"""ACME v3 end-to-end test: pipeline -> Java compile -> smoke run -> baseline compare.

Exercises the full modernization pipeline against all 6 ACME Bank v3 programs:
  LOANEVAL, RISKSCOR, RECOVRY, RPTMONTH (main programs)
  CALCFEE, CHKAML (sub-programs)

Acceptance criteria:
  1. All 6 COBOL programs parse without errors
  2. All 6 Java files compile cleanly with javac
  3. RISKSCOR.java output matches COBOL baseline (CLASS counts exact, TOTAL PROV within tolerance)
  4. BCTSUBM.dat output matches baseline byte-for-byte (except date field)

Usage:
    python tests/e2e/acme_v3_test.py                     # against running API
    python tests/e2e/acme_v3_test.py --api http://host:8000/api
    python tests/e2e/acme_v3_test.py --offline             # skip API, use cached Java
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAIN_PROGS = ["LOANEVAL", "RISKSCOR", "RECOVRY", "RPTMONTH"]
SUB_PROGS = ["CALCFEE", "CHKAML"]
ALL_PROGS = MAIN_PROGS + SUB_PROGS

_SCRIPT_DIR = Path(__file__).resolve().parent
_SERVICE_ROOT = _SCRIPT_DIR.parents[1]
_ACME_ROOT = _SERVICE_ROOT.parent / "acme-bank-v3"
_SRC_DIR = _ACME_ROOT / "src"
_DATA_DIR = _ACME_ROOT / "data"
_EXPECTED_DIR = _SCRIPT_DIR / "expected_output"
_BASELINE_DIR = _SCRIPT_DIR / "baseline"

INPUT_DATS = {"LOANFILE.dat", "CUSTFILE.dat", "COLFILE.dat", "GUARFILE.dat", "SANCFILE.dat"}
PLACEHOLDER_DATS = ["SCORFILE.dat", "RECVNEW.dat", "RISKRPT.dat", "BCTSUBM.dat",
                    "EVALREJ.dat", "DECIRPT.dat", "ESCARPT.dat", "LETTERS.dat",
                    "MONTHRPT.dat"]

_DATE_RE = re.compile(r"\b20\d{6}(?:-\d{6})?\b")

DEFAULT_API = "http://127.0.0.1:8000/api"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    name: str
    passed: bool
    message: str
    detail: str = ""

    def __str__(self) -> str:
        icon = "PASS" if self.passed else "FAIL"
        s = f"  [{icon}] {self.name}: {self.message}"
        if self.detail and not self.passed:
            for line in self.detail.strip().splitlines()[:20]:
                s += f"\n      {line}"
        return s


@dataclass
class E2EReport:
    tests: List[TestResult] = field(default_factory=list)
    java_files: Dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> int:
        return sum(1 for t in self.tests if t.passed)

    @property
    def failed(self) -> int:
        return sum(1 for t in self.tests if not t.passed)

    @property
    def all_passed(self) -> bool:
        return all(t.passed for t in self.tests)

    def add(self, name: str, passed: bool, message: str, detail: str = "") -> None:
        self.tests.append(TestResult(name, passed, message, detail))

    def print_summary(self) -> None:
        print("\n" + "=" * 70)
        print("ACME v3 End-to-End Test Report")
        print("=" * 70)
        for t in self.tests:
            print(str(t))
        print("-" * 70)
        total = len(self.tests)
        status = "PASS" if self.all_passed else "FAIL"
        print(f"  Result: {status} ({self.passed}/{total} passed, {self.failed} failed)")
        print("=" * 70)


# ---------------------------------------------------------------------------
# 1. Upload & pipeline
# ---------------------------------------------------------------------------

def _api_request(api_base: str, endpoint: str, payload: dict, *, timeout: int = 120) -> dict:
    """Make an API request using urllib (no external deps)."""
    import urllib.request
    import urllib.error

    url = f"{api_base}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"API {endpoint} returned {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"API {endpoint} connection failed: {exc.reason}") from exc


def run_pipeline_for_program(
    api_base: str, program: str, source_code: str, report: E2EReport
) -> Optional[Dict[str, Any]]:
    """Run parse -> analyze -> convert pipeline for a single program."""
    try:
        result = _api_request(api_base, "/smart-convert", {
            "source_code": source_code,
        }, timeout=180)
    except RuntimeError as exc:
        report.add(f"{program}/pipeline", False, f"API error: {exc}")
        return None

    if result.get("conversion_failed"):
        report.add(f"{program}/pipeline", False, f"Conversion failed: {result.get('error', 'unknown')}")
        return result

    parser_output = result.get("parser_output") or {}
    errors = parser_output.get("preflight_errors") or parser_output.get("errors") or []
    if errors:
        report.add(f"{program}/parse", False, f"{len(errors)} parse error(s)", "\n".join(str(e) for e in errors[:5]))
    else:
        report.add(f"{program}/parse", True, "parsed without errors")

    java_code = result.get("java_code") or ""
    if not java_code.strip():
        report.add(f"{program}/convert", False, "no Java code produced")
        return result

    report.java_files[program] = java_code

    score = result.get("conversion_score") or {}
    total = score.get("total_score", "?")
    report.add(f"{program}/convert", True, f"Java produced (score={total}/100)")

    return result


def upload_all_programs(api_base: str, report: E2EReport) -> None:
    """Upload all 6 ACME programs to the pipeline."""
    for prog in ALL_PROGS:
        src_path = _SRC_DIR / f"{prog}.cbl"
        if not src_path.is_file():
            report.add(f"{prog}/source", False, f"source file not found: {src_path}")
            continue

        source_code = src_path.read_text(encoding="utf-8", errors="replace")
        print(f"  [{prog}] Running pipeline...", flush=True)
        t0 = time.time()
        run_pipeline_for_program(api_base, prog, source_code, report)
        elapsed = time.time() - t0
        print(f"  [{prog}] Done in {elapsed:.1f}s", flush=True)


# ---------------------------------------------------------------------------
# 2. Compile all Java files with javac
# ---------------------------------------------------------------------------

def compile_java_files(report: E2EReport, work_dir: Path) -> bool:
    """Write all Java files and compile with javac. Returns True if all compile."""
    if not report.java_files:
        report.add("javac/compile", False, "no Java files to compile")
        return False

    javac = shutil.which("javac")
    if not javac:
        report.add("javac/compile", False, "javac not found on PATH")
        return False

    java_paths: List[Path] = []
    for prog, code in report.java_files.items():
        class_match = re.search(r"public\s+class\s+(\w+)", code)
        class_name = class_match.group(1) if class_match else prog
        path = work_dir / f"{class_name}.java"
        path.write_text(code, encoding="utf-8")
        java_paths.append(path)

    proc = subprocess.run(
        [javac, "-encoding", "UTF-8", *[str(p) for p in java_paths]],
        capture_output=True,
        cwd=str(work_dir),
        timeout=60,
    )

    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
        errors_by_file: Dict[str, List[str]] = {}
        for line in stderr.splitlines():
            for prog in report.java_files:
                if prog.lower() in line.lower() or prog in line:
                    errors_by_file.setdefault(prog, []).append(line)
                    break

        all_compiled = True
        for prog in report.java_files:
            if prog in errors_by_file:
                report.add(f"javac/{prog}", False, f"{len(errors_by_file[prog])} error(s)",
                           "\n".join(errors_by_file[prog][:10]))
                all_compiled = False
            else:
                report.add(f"javac/{prog}", True, "compiled cleanly")

        if not errors_by_file:
            report.add("javac/compile", False, f"javac failed (rc={proc.returncode})", stderr[:2000])
            return False
        return all_compiled

    for prog in report.java_files:
        report.add(f"javac/{prog}", True, "compiled cleanly")
    return True


# ---------------------------------------------------------------------------
# 3. Stage data files & run RISKSCOR
# ---------------------------------------------------------------------------

def stage_data_files(work_dir: Path) -> List[str]:
    """Copy .dat files into the working directory."""
    staged: List[str] = []
    for dat in _DATA_DIR.glob("*.dat"):
        dst = work_dir / dat.name
        if not dst.exists():
            shutil.copy2(dat, dst)
        staged.append(dat.name)

    for root_dat in _ACME_ROOT.glob("*.dat"):
        dst = work_dir / root_dat.name
        if not dst.exists():
            shutil.copy2(root_dat, dst)
            staged.append(root_dat.name)

    for ph in PLACEHOLDER_DATS:
        target = work_dir / ph
        if not target.exists():
            target.touch()
            staged.append(f"{ph} (placeholder)")

    return staged


def run_java_program(
    entry_class: str, work_dir: Path, *, timeout: float = 30.0
) -> Tuple[int, str, str]:
    """Run a Java program and return (exit_code, stdout, stderr)."""
    java = shutil.which("java")
    if not java:
        return -1, "", "java not found on PATH"

    try:
        proc = subprocess.run(
            [java, "-cp", str(work_dir), entry_class],
            capture_output=True,
            cwd=str(work_dir),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return -1, "", f"timed out after {timeout}s"

    stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
    stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
    return proc.returncode, stdout, stderr


def find_entry_class(java_code: str, program_name: str) -> str:
    """Extract the public class name from Java source."""
    m = re.search(r"public\s+class\s+(\w+)", java_code)
    return m.group(1) if m else program_name


# ---------------------------------------------------------------------------
# 4. Compare against baseline
# ---------------------------------------------------------------------------

def _extract_class_counts(text: str) -> Dict[str, int]:
    """Extract CLASS N: NNNNNN counts from RISKSCOR output."""
    counts: Dict[str, int] = {}
    for m in re.finditer(r"CLASS\s+(\d+):\s*(\d+)", text):
        counts[f"CLASS_{m.group(1)}"] = int(m.group(2))
    return counts


def _extract_total_prov(text: str) -> Optional[int]:
    """Extract TOTAL PROV value from RISKSCOR output."""
    m = re.search(r"TOTAL\s+PROV:\s*(\d+)", text)
    return int(m.group(1)) if m else None


def compare_riskscor_stdout(actual: str, expected: str, report: E2EReport) -> None:
    """Compare RISKSCOR stdout against baseline with acceptance criteria."""
    actual_classes = _extract_class_counts(actual)
    expected_classes = _extract_class_counts(expected)

    for class_key in ["CLASS_1", "CLASS_2", "CLASS_3", "CLASS_4"]:
        exp = expected_classes.get(class_key)
        act = actual_classes.get(class_key)
        if exp is None:
            report.add(f"riskscor/{class_key}", False, f"not found in baseline")
            continue
        if act is None:
            report.add(f"riskscor/{class_key}", False, f"not found in actual output")
            continue
        if act == exp:
            report.add(f"riskscor/{class_key}", True, f"count={act} (exact match)")
        else:
            report.add(f"riskscor/{class_key}", False,
                        f"expected={exp}, actual={act} (diff={act - exp})")

    exp_prov = _extract_total_prov(expected)
    act_prov = _extract_total_prov(actual)
    if exp_prov is not None and act_prov is not None:
        tolerance = max(1, abs(exp_prov) // 1000)
        if abs(act_prov - exp_prov) <= tolerance:
            report.add("riskscor/TOTAL_PROV", True,
                        f"value={act_prov} (within rounding tolerance of {tolerance})")
        else:
            report.add("riskscor/TOTAL_PROV", False,
                        f"expected={exp_prov}, actual={act_prov} (tolerance={tolerance})")
    elif exp_prov is not None:
        report.add("riskscor/TOTAL_PROV", False, "TOTAL PROV not found in actual output")
    else:
        report.add("riskscor/TOTAL_PROV", False, "TOTAL PROV not found in baseline")

    actual_clean = actual.strip()
    expected_clean = expected.strip()
    if actual_clean != expected_clean:
        diff_lines = list(difflib.unified_diff(
            expected_clean.splitlines(keepends=True),
            actual_clean.splitlines(keepends=True),
            fromfile="expected", tofile="actual",
        ))
        diff_text = "".join(diff_lines[:30])
        report.add("riskscor/full_diff", False, "stdout differs from baseline", diff_text)
    else:
        report.add("riskscor/full_diff", True, "stdout matches baseline exactly")


def compare_bctsubm(actual_path: Path, expected_path: Path, report: E2EReport) -> None:
    """Compare BCTSUBM.dat output, allowing date field differences."""
    if not expected_path.is_file():
        report.add("riskscor/BCTSUBM.dat", False, f"baseline not found: {expected_path}")
        return
    if not actual_path.is_file():
        report.add("riskscor/BCTSUBM.dat", False, "BCTSUBM.dat not produced by Java run")
        return

    expected_bytes = expected_path.read_bytes()
    actual_bytes = actual_path.read_bytes()

    if expected_bytes == actual_bytes:
        report.add("riskscor/BCTSUBM.dat", True, "byte-for-byte match")
        return

    expected_text = expected_bytes.decode("latin-1")
    actual_text = actual_bytes.decode("latin-1")

    expected_masked = _DATE_RE.sub("XXXXXXXX", expected_text)
    actual_masked = _DATE_RE.sub("XXXXXXXX", actual_text)

    if expected_masked == actual_masked:
        report.add("riskscor/BCTSUBM.dat", True, "matches (date fields excluded)")
        return

    if len(expected_bytes) != len(actual_bytes):
        report.add("riskscor/BCTSUBM.dat", False,
                    f"size mismatch: expected={len(expected_bytes)}, actual={len(actual_bytes)}")
        return

    diffs: List[str] = []
    for i in range(len(expected_bytes)):
        if expected_bytes[i] != actual_bytes[i]:
            diffs.append(f"  offset {i}: expected=0x{expected_bytes[i]:02X} actual=0x{actual_bytes[i]:02X}")
    report.add("riskscor/BCTSUBM.dat", False,
                f"{len(diffs)} byte(s) differ", "\n".join(diffs[:20]))


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_e2e_test(
    api_base: str = DEFAULT_API,
    *,
    offline: bool = False,
    java_dir: Optional[Path] = None,
) -> E2EReport:
    """Run the full ACME v3 end-to-end test."""
    report = E2EReport()

    print("\n--- ACME v3 E2E Test ---")
    print(f"  API: {api_base}")
    print(f"  Source: {_SRC_DIR}")
    print(f"  Data: {_DATA_DIR}")
    print(f"  Baselines: {_EXPECTED_DIR}")

    # Step 1: Run pipeline
    if offline and java_dir and java_dir.is_dir():
        print("\n[Step 1] OFFLINE mode — loading cached Java files...")
        for jf in java_dir.glob("*.java"):
            prog = jf.stem.upper()
            report.java_files[prog] = jf.read_text(encoding="utf-8")
            report.add(f"{prog}/parse", True, "(offline — skipped)")
            report.add(f"{prog}/convert", True, "(offline — loaded from cache)")
    else:
        print("\n[Step 1] Running pipeline for all 6 programs...")
        upload_all_programs(api_base, report)

    if not report.java_files:
        report.add("overall", False, "no Java files produced — cannot continue")
        report.print_summary()
        return report

    print(f"\n  Java files produced: {len(report.java_files)} / {len(ALL_PROGS)}")

    with tempfile.TemporaryDirectory(prefix="acme_e2e_") as tmp_str:
        work = Path(tmp_str)

        # Step 2: Compile all Java
        print("\n[Step 2] Compiling all Java files with javac...")
        compiled = compile_java_files(report, work)

        # Step 3: Stage data files
        print("\n[Step 3] Staging data files...")
        staged = stage_data_files(work)
        print(f"  Staged {len(staged)} files")

        # Step 4: Run RISKSCOR
        if "RISKSCOR" in report.java_files and compiled:
            print("\n[Step 4] Running RISKSCOR.java...")
            entry = find_entry_class(report.java_files["RISKSCOR"], "RISKSCOR")
            exit_code, stdout, stderr = run_java_program(entry, work)

            if exit_code == 0:
                report.add("riskscor/run", True, f"exit code 0")
            elif exit_code == -1:
                report.add("riskscor/run", False, f"failed to run: {stderr[:200]}")
            else:
                report.add("riskscor/run", False,
                            f"exit code {exit_code}", stderr[:500])

            # Step 5: Compare stdout
            print("\n[Step 5] Comparing RISKSCOR output against baseline...")
            expected_stdout_path = _EXPECTED_DIR / "acme_v3_riskscor.txt"
            if expected_stdout_path.is_file():
                expected_stdout = expected_stdout_path.read_text(encoding="utf-8")
                compare_riskscor_stdout(stdout, expected_stdout, report)
            else:
                report.add("riskscor/baseline", False,
                            f"baseline file not found: {expected_stdout_path}")

            # Step 6: Compare BCTSUBM.dat
            print("\n[Step 6] Comparing BCTSUBM.dat output...")
            bctsubm_actual = work / "BCTSUBM.dat"
            bctsubm_expected = _EXPECTED_DIR / "acme_v3_riskscor_BCTSUBM.dat"
            compare_bctsubm(bctsubm_actual, bctsubm_expected, report)

            # Save actual output for debugging
            output_dir = _SCRIPT_DIR / "actual_output"
            output_dir.mkdir(exist_ok=True)
            (output_dir / "RISKSCOR_stdout.txt").write_text(stdout, encoding="utf-8")
            if bctsubm_actual.is_file():
                shutil.copy2(bctsubm_actual, output_dir / "RISKSCOR_BCTSUBM.dat")
        elif "RISKSCOR" not in report.java_files:
            report.add("riskscor/run", False, "RISKSCOR Java not produced — skipping")
        else:
            report.add("riskscor/run", False, "compilation failed — skipping runtime tests")

        # Run other main programs if available
        for prog in ["LOANEVAL", "RECOVRY", "RPTMONTH"]:
            if prog in report.java_files and compiled:
                entry = find_entry_class(report.java_files[prog], prog)
                ec, stdout, stderr = run_java_program(entry, work)
                if ec == 0:
                    report.add(f"{prog}/run", True, "exit code 0")
                elif ec == -1:
                    report.add(f"{prog}/run", False, f"failed: {stderr[:200]}")
                else:
                    report.add(f"{prog}/run", False, f"exit code {ec}", stderr[:300])

                expected_path = _EXPECTED_DIR / f"acme_v3_{prog}.txt"
                if expected_path.is_file() and stdout.strip():
                    expected = expected_path.read_text(encoding="utf-8")
                    exp_masked = _DATE_RE.sub("DATE", expected.strip())
                    act_masked = _DATE_RE.sub("DATE", stdout.strip())
                    if exp_masked == act_masked:
                        report.add(f"{prog}/baseline", True, "output matches baseline")
                    else:
                        diff = "\n".join(difflib.unified_diff(
                            exp_masked.splitlines(keepends=True),
                            act_masked.splitlines(keepends=True),
                            fromfile="expected", tofile="actual",
                        )[:20])
                        report.add(f"{prog}/baseline", False, "output differs", diff)

    report.print_summary()
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="ACME v3 end-to-end pipeline test")
    parser.add_argument("--api", default=DEFAULT_API, help="API base URL")
    parser.add_argument("--offline", action="store_true", help="Skip API, use cached Java")
    parser.add_argument("--java-dir", type=Path, default=None,
                        help="Directory with cached .java files (for --offline)")
    args = parser.parse_args()

    report = run_e2e_test(args.api, offline=args.offline, java_dir=args.java_dir)
    sys.exit(0 if report.all_passed else 1)


if __name__ == "__main__":
    main()
