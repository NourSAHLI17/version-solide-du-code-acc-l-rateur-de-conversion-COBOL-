"""Smoke test runner for converted Java programs.

Compiles generated Java, stages .dat data files, runs the program,
captures exit code + stdout, and optionally compares against a saved baseline.
"""

from __future__ import annotations

import difflib
import logging
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from app.env_bootstrap import SERVICE_ROOT
from app.services.behavioral_java_launcher import build_behavioral_java_compile_unit
from app.services.unit_test_generator import extract_java_class_name

logger = logging.getLogger(__name__)

_BASELINES_DIR = SERVICE_ROOT / "smoke_baselines"
_DATA_SEARCH_ROOTS = [
    SERVICE_ROOT.parent / "acme-bank-v3" / "data",
    SERVICE_ROOT.parent / "acme-bank-v3",
    SERVICE_ROOT / "java_test",
]
_MAX_STDOUT_BYTES = 64 * 1024
_DEFAULT_TIMEOUT = 15.0


@dataclass
class SmokeTestCase:
    name: str
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    baseline_compared: bool = False
    baseline_match: bool = False
    diff: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SmokeTestResult:
    program_name: str
    passed: bool
    compiled: bool
    compile_stderr: str = ""
    test_cases: List[SmokeTestCase] = field(default_factory=list)
    data_files_staged: List[str] = field(default_factory=list)
    wrapper_generated: bool = False
    error: Optional[str] = None

    @property
    def pass_count(self) -> int:
        return sum(1 for t in self.test_cases if t.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for t in self.test_cases if not t.passed)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["pass_count"] = self.pass_count
        d["fail_count"] = self.fail_count
        return d


def _find_data_files(file_names: Sequence[str]) -> Dict[str, Path]:
    """Locate .dat files from known project data directories."""
    found: Dict[str, Path] = {}
    for name in file_names:
        if name in found:
            continue
        candidates = [
            f"{name}.dat", f"{name.upper()}.dat", f"{name.lower()}.dat",
            name, name.upper(), name.lower(),
        ]
        for root in _DATA_SEARCH_ROOTS:
            if not root.is_dir():
                continue
            for candidate in candidates:
                p = root / candidate
                if p.is_file():
                    found[name] = p
                    break
            if name in found:
                break
            for child in root.iterdir():
                if child.is_dir():
                    for candidate in candidates:
                        p = child / candidate
                        if p.is_file():
                            found[name] = p
                            break
                    if name in found:
                        break
    return found


def _extract_file_control_names(parser_output: Mapping[str, Any]) -> List[str]:
    """Extract assigned file names from parser FILE-CONTROL / files output."""
    names: List[str] = []
    files = parser_output.get("files") or []
    if isinstance(files, list):
        for f in files:
            if isinstance(f, Mapping):
                assign = f.get("assign") or f.get("assigned_to") or ""
                if isinstance(assign, str) and assign.strip():
                    clean = assign.strip().strip("'\"")
                    names.append(clean)
                name = f.get("name") or ""
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
    deps = parser_output.get("dependencies") or {}
    if isinstance(deps, Mapping):
        for f in deps.get("files") or []:
            if isinstance(f, str) and f.strip():
                names.append(f.strip())
        file_kinds = deps.get("file_kinds") or {}
        if isinstance(file_kinds, Mapping):
            names.extend(str(k) for k in file_kinds.keys())
    return list(dict.fromkeys(names))


def _stage_data_files(work_dir: Path, data_files: Dict[str, Path]) -> List[str]:
    """Copy data files into the working directory. Returns list of staged names."""
    staged: List[str] = []
    for name, src in data_files.items():
        dst = work_dir / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
        staged.append(src.name)
        alt = work_dir / name
        if not alt.exists() and alt.name != dst.name:
            shutil.copy2(src, alt)
            staged.append(name)
    return staged


def _compile_java(files: Dict[str, str], work_dir: Path) -> tuple[bool, str, Dict[str, Path]]:
    """Write Java files to disk, compile with javac. Returns (success, stderr, file_paths)."""
    from app.services.java_pre_write_validator import JavaPreWriteValidationError, write_java_file

    java_paths: Dict[str, Path] = {}
    for filename, source in files.items():
        path = work_dir / filename
        try:
            write_java_file(path, source)
        except JavaPreWriteValidationError as exc:
            return False, f"validation: {'; '.join(exc.errors[:5])}", {}
        java_paths[filename] = path

    try:
        proc = subprocess.run(
            ["javac", "-encoding", "UTF-8", *[str(p) for p in java_paths.values()]],
            capture_output=True,
            cwd=str(work_dir),
            timeout=30,
        )
    except FileNotFoundError:
        return False, "javac not found on PATH", java_paths
    except subprocess.TimeoutExpired:
        return False, "javac compilation timed out", java_paths

    stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
    if proc.stdout:
        stderr = (proc.stdout or b"").decode("utf-8", errors="replace") + "\n" + stderr
    return proc.returncode == 0, stderr.strip(), java_paths


def _run_java(
    entry_class: str,
    work_dir: Path,
    *,
    stdin_text: str = "",
    timeout: float = _DEFAULT_TIMEOUT,
) -> SmokeTestCase:
    """Run a Java class and capture output."""
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            ["java", "-cp", str(work_dir), entry_class],
            capture_output=True,
            cwd=str(work_dir),
            timeout=timeout,
            input=stdin_text.encode("utf-8") if stdin_text else None,
        )
    except FileNotFoundError:
        return SmokeTestCase(
            name="main", passed=False, exit_code=-1,
            stdout="", stderr="java not found on PATH",
            duration_ms=0, error="java not found",
        )
    except subprocess.TimeoutExpired:
        elapsed = (time.perf_counter() - t0) * 1000
        return SmokeTestCase(
            name="main", passed=False, exit_code=-1,
            stdout="", stderr=f"timed out after {timeout}s",
            duration_ms=elapsed, error="timeout",
        )

    elapsed = (time.perf_counter() - t0) * 1000
    stdout = (proc.stdout or b"")[:_MAX_STDOUT_BYTES].decode("utf-8", errors="replace")
    stderr = (proc.stderr or b"")[:_MAX_STDOUT_BYTES].decode("utf-8", errors="replace")

    return SmokeTestCase(
        name="main",
        passed=proc.returncode == 0,
        exit_code=proc.returncode,
        stdout=stdout,
        stderr=stderr,
        duration_ms=round(elapsed, 1),
    )


def _load_baseline(program_name: str) -> Optional[str]:
    """Load saved baseline output for a program."""
    for ext in (".txt", ".out", ".baseline"):
        path = _BASELINES_DIR / f"{program_name}{ext}"
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")
    path = _BASELINES_DIR / program_name / "expected_output.txt"
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    return None


def _compare_baseline(actual: str, expected: str) -> tuple[bool, str]:
    """Compare actual output against baseline. Returns (match, diff_text)."""
    actual_lines = actual.strip().splitlines(keepends=True)
    expected_lines = expected.strip().splitlines(keepends=True)

    if actual.strip() == expected.strip():
        return True, ""

    diff = difflib.unified_diff(
        expected_lines, actual_lines,
        fromfile="expected", tofile="actual",
        lineterm="",
    )
    diff_text = "\n".join(list(diff)[:100])
    return False, diff_text


def save_baseline(program_name: str, output: str) -> Path:
    """Save a program's smoke test output as the new baseline."""
    _BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    path = _BASELINES_DIR / f"{program_name}.txt"
    path.write_text(output, encoding="utf-8")
    logger.info("Saved smoke baseline for %s at %s", program_name, path)
    return path


def _generate_wrapper_source(
    java_source: str,
    target_class: str,
    program_name: str,
) -> Optional[str]:
    """
    Generate a simple wrapper with main() for sub-programs that lack one.
    Detects public methods and generates basic invocations.
    """
    if re.search(r"public\s+static\s+void\s+main\s*\(", java_source):
        return None

    method_pattern = re.compile(
        r"public\s+(?:static\s+)?(\w+)\s+(\w+)\s*\(([^)]*)\)",
    )
    methods = method_pattern.findall(java_source)
    if not methods:
        return None

    wrapper_class = f"{target_class}SmokeTest"
    lines = [
        f"public class {wrapper_class} {{",
        "  public static void main(String[] args) {",
        "    try {",
        f"      {target_class} instance = new {target_class}();",
    ]

    for ret_type, method_name, params in methods:
        if method_name in ("toString", "hashCode", "equals", "getClass"):
            continue
        if params.strip():
            lines.append(f'      System.out.println("[SMOKE] skipping {method_name} (needs args)");')
        elif ret_type == "void":
            lines.append(f"      instance.{method_name}();")
            lines.append(f'      System.out.println("[SMOKE] {method_name}() completed");')
        else:
            lines.append(f"      {ret_type} r = instance.{method_name}();")
            lines.append(f'      System.out.println("[SMOKE] {method_name}() = " + r);')

    lines.extend([
        '      System.out.println("[SMOKE] all methods completed successfully");',
        "      System.exit(0);",
        "    } catch (Throwable t) {",
        '      System.err.println("[SMOKE] FAILED: " + t.getMessage());',
        "      t.printStackTrace();",
        "      System.exit(1);",
        "    }",
        "  }",
        "}",
    ])
    return "\n".join(lines)


def run_smoke_test(
    java_code: str,
    *,
    program_name: str = "Program",
    parser_output: Optional[Mapping[str, Any]] = None,
    timeout: float = _DEFAULT_TIMEOUT,
    save_as_baseline: bool = False,
) -> SmokeTestResult:
    """
    Run a smoke test on converted Java code.

    1. Resolves entry class (uses existing launcher if no main())
    2. Compiles with javac
    3. Stages .dat data files from known locations
    4. Runs the program
    5. Compares output against baseline (if one exists)
    """
    if not java_code or not java_code.strip():
        return SmokeTestResult(
            program_name=program_name,
            passed=False,
            compiled=False,
            error="no Java code provided",
        )

    target_class = extract_java_class_name(java_code, program_name)
    unit = build_behavioral_java_compile_unit(java_code, program_name)
    files = dict(unit.files)

    wrapper_generated = False
    wrapper_class: Optional[str] = None
    if not unit.uses_launcher and not re.search(
        r"public\s+static\s+void\s+main\s*\(", java_code
    ):
        wrapper_src = _generate_wrapper_source(java_code, target_class, program_name)
        if wrapper_src:
            wrapper_class = f"{target_class}SmokeTest"
            files[f"{wrapper_class}.java"] = wrapper_src
            wrapper_generated = True

    entry_class = wrapper_class or unit.entry_class

    file_names = _extract_file_control_names(parser_output or {})
    data_files = _find_data_files(file_names)

    with tempfile.TemporaryDirectory(prefix="smoke_") as tmp_str:
        tmp = Path(tmp_str)

        staged = _stage_data_files(tmp, data_files)

        compiled, compile_stderr, _ = _compile_java(files, tmp)
        if not compiled:
            return SmokeTestResult(
                program_name=program_name,
                passed=False,
                compiled=False,
                compile_stderr=compile_stderr,
                data_files_staged=staged,
                wrapper_generated=wrapper_generated,
                error="compilation failed",
            )

        test_case = _run_java(entry_class, tmp, timeout=timeout)

        baseline = _load_baseline(program_name)
        if baseline is not None:
            match, diff_text = _compare_baseline(test_case.stdout, baseline)
            test_case.baseline_compared = True
            test_case.baseline_match = match
            test_case.diff = diff_text
            if not match:
                test_case.passed = False

        if save_as_baseline and test_case.exit_code == 0:
            save_baseline(program_name, test_case.stdout)

        return SmokeTestResult(
            program_name=program_name,
            passed=test_case.passed,
            compiled=True,
            test_cases=[test_case],
            data_files_staged=staged,
            wrapper_generated=wrapper_generated,
        )


def run_smoke_tests_batch(
    programs: Sequence[Dict[str, Any]],
    *,
    timeout: float = _DEFAULT_TIMEOUT,
) -> List[SmokeTestResult]:
    """
    Run smoke tests for multiple programs.

    Each item in *programs* should have:
      - java_code: str
      - program_name: str
      - parser_output: dict (optional)
    """
    results: List[SmokeTestResult] = []
    for prog in programs:
        java = prog.get("java_code") or ""
        name = prog.get("program_name") or "Program"
        parser = prog.get("parser_output") or {}
        logger.info("Running smoke test for %s", name)
        result = run_smoke_test(
            java,
            program_name=name,
            parser_output=parser,
            timeout=timeout,
        )
        results.append(result)
        logger.info(
            "Smoke test %s: %s (exit=%d)",
            name,
            "PASS" if result.passed else "FAIL",
            result.test_cases[0].exit_code if result.test_cases else -1,
        )
    return results
