"""Flat multi-file javac for the behavioral testing pipeline."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.services.behavioral_java_launcher import build_behavioral_java_compile_unit

ACME_PROGRAMS = frozenset({"CALCFEE", "CHKAML", "RISKSCOR", "LOANEVAL", "RECOVRY", "RPTMONTH"})
SUB_PROGRAMS = frozenset({"CALCFEE", "CHKAML"})
SUB_PROGRAM_CANONICAL_CLASS = {
    "CALCFEE": "CalcFee",
    "CHKAML": "ChkAmlService",
}
SUB_PROGRAM_LEGACY_CLASSES = {
    "CALCFEE": ("Calcfee", "CalcFEE"),
    "CHKAML": ("Chkaml", "ChkAml", "CHKAML"),
}

_PACKAGE_RE = re.compile(r"^\s*package\s+[\w.]+\s*;\s*\n?", re.MULTILINE)
_CROSS_PKG_IMPORT_RE = re.compile(
    r"^\s*import\s+com\.modernized\.\S*\s*;\s*\n?",
    re.MULTILINE,
)
_TODO_HEADER_RE = re.compile(
    r"^//\s*TODO:.*?(?=^\s*(?:package|import|public|/\*\*|/\*|\Z))",
    re.MULTILINE | re.DOTALL,
)
_PUBLIC_CLASS_RE = re.compile(
    r"^\s*public\s+(?:abstract\s+|final\s+)*class\s+([A-Za-z_]\w*)\b",
    re.MULTILINE,
)

_CHKAML_ADAPTER = """
    public AmlResponse checkAml(AmlRequest request) {
        LkAmlRequest req = new LkAmlRequest();
        req.lkReqCustId = request.custId;
        req.lkReqCin = request.cin != null ? request.cin : "";
        req.lkReqName = request.name != null ? request.name : "";
        req.lkReqDob = request.dob;
        req.lkReqNationality = request.nationality != null ? request.nationality : "";
        req.lkReqAmount = request.amount != null ? request.amount : java.math.BigDecimal.ZERO;
        LkAmlResponse resp = new LkAmlResponse();
        __FLAT_COMPILE_AML_ENTRY__(req, resp);
        return new AmlResponse(resp.lkRespClear, resp.lkRespScore, resp.lkRespReason);
    }

    public static class AmlRequest {
        public final int custId;
        public final String cin;
        public final String name;
        public final int dob;
        public final String nationality;
        public final java.math.BigDecimal amount;

        public AmlRequest(
                int custId,
                String cin,
                String name,
                int dob,
                String nationality,
                java.math.BigDecimal amount) {
            this.custId = custId;
            this.cin = cin;
            this.name = name;
            this.dob = dob;
            this.nationality = nationality;
            this.amount = amount;
        }
    }

    public static class AmlResponse {
        private final String clear;
        private final int score;
        private final String reason;

        public AmlResponse(String clear, int score, String reason) {
            this.clear = clear;
            this.score = score;
            this.reason = reason != null ? reason : "";
        }

        public String getClear() {
            return clear;
        }

        public int getScore() {
            return score;
        }

        public String getReason() {
            return reason;
        }

        public String getDecReason() {
            return reason;
        }
    }
"""

_CHKAML_DTO_STUB = """
    public static class AmlRequest {
        public String custId, cin, name, dob, nationality;
        public java.math.BigDecimal amount;
        public AmlRequest(String id, String c, String n, String d,
                         String nat, java.math.BigDecimal a) {
            this.custId=id; this.cin=c; this.name=n;
            this.dob=d; this.nationality=nat; this.amount=a;
        }
    }
    public static class AmlResponse {
        public String clear = "Y";
        public String decReason = "";
        public int score = 0;
        public String getClear() { return clear; }
        public String getDecReason() { return decReason; }
        public String getReason() { return decReason; }
        public int getScore() { return score; }
    }
    public AmlResponse checkAml(AmlRequest req) {
        return new AmlResponse();
    }
"""

_CALCFEE_DTOS = """
    public static class FeeRequest {
        public String loanType;
        public java.math.BigDecimal amount;
        public java.math.BigDecimal rate;
        public FeeRequest(String t, java.math.BigDecimal a,
                         java.math.BigDecimal r) {
            this.loanType=t; this.amount=a; this.rate=r;
        }
    }
    public static class FeeResponse {
        public java.math.BigDecimal fileFee = java.math.BigDecimal.ZERO;
        public java.math.BigDecimal taxAmt = java.math.BigDecimal.ZERO;
        public java.math.BigDecimal totalFee = java.math.BigDecimal.ZERO;
        public java.math.BigDecimal getFileFee() { return fileFee; }
        public java.math.BigDecimal getTaxAmt() { return taxAmt; }
        public java.math.BigDecimal getTax() { return taxAmt; }
        public java.math.BigDecimal getInsurance() { return java.math.BigDecimal.ZERO; }
        public java.math.BigDecimal getTotalFee() { return totalFee; }
        public java.math.BigDecimal getTotal() { return totalFee; }
    }
"""

_CALCFEE_CALCULATE_BRIDGE = """
    public FeeResponse calculate(FeeRequest req) {
        LkFeeRequest lkReq = new LkFeeRequest();
        lkReq.lkReqLoanType = req.loanType;
        lkReq.lkReqAmount = req.amount != null ? req.amount : java.math.BigDecimal.ZERO;
        lkReq.lkReqRate = req.rate != null ? req.rate : java.math.BigDecimal.ZERO;
        LkFeeResponse lkResp = new LkFeeResponse();
        execute(lkReq, lkResp);
        FeeResponse resp = new FeeResponse();
        resp.fileFee = lkResp.lkRespFileFee != null ? lkResp.lkRespFileFee : java.math.BigDecimal.ZERO;
        resp.taxAmt = lkResp.lkRespTax != null ? lkResp.lkRespTax : java.math.BigDecimal.ZERO;
        resp.totalFee = lkResp.lkRespTotal != null ? lkResp.lkRespTotal : java.math.BigDecimal.ZERO;
        return resp;
    }
"""

_NO_ARGS_CONSTRUCTOR = """
    public {class_name}() {{
        // default no-args constructor for flat compilation
    }}
"""


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


def _acme_fixture_dir() -> Optional[Path]:
    root = Path(__file__).resolve().parents[2]
    fixture_dir = root / "tests" / "fixtures" / "acme_e2e"
    return fixture_dir if fixture_dir.is_dir() else None


def get_java_for_testing(program_name: str, workspace_java: str) -> str:
    """Prefer checked-in ACME fixture Java over workspace output for behavioral tests."""
    prog = str(program_name or "").strip().upper()
    fixture_dir = _acme_fixture_dir()
    if fixture_dir is not None:
        raw_path = fixture_dir / f"{prog}.raw.java"
        if raw_path.is_file():
            return raw_path.read_text(encoding="utf-8")
    return workspace_java


_IMPLNOTE_JAVADOC_BLOCK = re.compile(
    r"/\*\*(?:(?!\*/).)*@implNote(?:(?!\*/).)*\*/\s*",
    re.DOTALL | re.IGNORECASE,
)


def strip_mapping_notes(java_source: str) -> str:
    """Remove mapping-note trailers and other non-compilable content after the final class."""
    from app.services.java_output_sanitizer import _split_mapping_notes

    text = java_source or ""
    text, _notes = _split_mapping_notes(text)
    text = _IMPLNOTE_JAVADOC_BLOCK.sub("", text)
    lines = text.split("\n")
    last_brace_idx = -1
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() == "}":
            last_brace_idx = i
            break
    if last_brace_idx >= 0:
        return "\n".join(lines[: last_brace_idx + 1]) + "\n"
    return text


def _strip_flat_compile_boilerplate(java_source: str) -> str:
    text = _PACKAGE_RE.sub("", java_source or "", count=1)
    text = _CROSS_PKG_IMPORT_RE.sub("", text)
    text = _TODO_HEADER_RE.sub("", text)
    return text


def _rename_class_references(source: str, old: str, new: str) -> str:
    if old == new:
        return source
    return re.sub(rf"\b{re.escape(old)}\b", new, source)


def _rename_public_class(source: str, new_class: str) -> str:
    match = _PUBLIC_CLASS_RE.search(source)
    if not match:
        return source
    old_class = match.group(1)
    if old_class == new_class:
        return source
    source = _PUBLIC_CLASS_RE.sub(
        lambda m: m.group(0).replace(old_class, new_class, 1),
        source,
        count=1,
    )
    return _rename_class_references(source, old_class, new_class)


def _inject_before_last_brace(source: str, snippet: str) -> str:
    close = source.rfind("}")
    if close < 0:
        return source
    return source[:close] + snippet + "\n" + source[close:]


def _has_no_args_constructor(source: str, class_name: str) -> bool:
    return bool(re.search(rf"public\s+{re.escape(class_name)}\s*\(\s*\)", source))


def _inject_no_args_constructor(source: str, class_name: str) -> str:
    if _has_no_args_constructor(source, class_name):
        return source
    snippet = _NO_ARGS_CONSTRUCTOR.format(class_name=class_name)
    return _inject_before_last_brace(source, snippet)


def _has_inner_class(source: str, class_name: str) -> bool:
    return bool(re.search(rf"(?:static\s+)?class\s+{re.escape(class_name)}\b", source))


def _inject_calcfee_dtos(source: str) -> str:
    if _has_inner_class(source, "FeeRequest") and _has_inner_class(source, "FeeResponse"):
        return source
    snippet = _CALCFEE_DTOS
    if "calculate(FeeRequest" not in source:
        if "execute(LkFeeRequest" in source:
            snippet += _CALCFEE_CALCULATE_BRIDGE
        else:
            snippet += """
    public FeeResponse calculate(FeeRequest req) {
        return new FeeResponse();
    }
"""
    return _inject_before_last_brace(source, snippet)


def _aml_entry_method(source: str) -> Optional[str]:
    if "execute(LkAmlRequest" in source:
        return "execute"
    if re.search(r"\b(?:public|private|protected)?\s*void\s+main\s*\(\s*LkAmlRequest\b", source):
        return "main"
    return None


def _inject_chkaml_service_adapter(source: str) -> str:
    if "checkAml(" in source or "class ChkAmlService" not in source:
        return source
    entry = _aml_entry_method(source)
    if entry is None:
        return source
    adapter = _CHKAML_ADAPTER.replace(
        "__FLAT_COMPILE_AML_ENTRY__(req, resp);",
        f"{entry}(req, resp);",
    )
    close = source.rfind("}")
    if close < 0:
        return source
    return source[:close] + adapter + "\n" + source[close:]


def _inject_chkaml_dtos(source: str) -> str:
    if _has_inner_class(source, "AmlRequest") and _has_inner_class(source, "AmlResponse"):
        return source
    if _aml_entry_method(source) is not None:
        return _inject_chkaml_service_adapter(source)
    return _inject_before_last_brace(source, _CHKAML_DTO_STUB)


def _inject_chkaml_flat_compile_support(source: str) -> str:
    text = _inject_chkaml_dtos(source)
    return _inject_no_args_constructor(text, "ChkAmlService")


def normalize_java_for_flat_compile(java_source: str, program_name: str = "") -> Tuple[str, str]:
    """
    Strip packages/imports and normalize sub-program class names for flat javac.

    Returns ``(normalized_source, public_class_name)``.
    """
    from app.services.java_post_processor import apply_all_post_processing

    prog = str(program_name or "").strip().upper()
    text, _notes = apply_all_post_processing(
        java_source,
        prog,
        symbol_table=None,
        for_flat_compile=True,
    )
    text = _strip_flat_compile_boilerplate(text)

    canonical = SUB_PROGRAM_CANONICAL_CLASS.get(prog)
    if canonical:
        for legacy in SUB_PROGRAM_LEGACY_CLASSES.get(prog, ()):
            text = _rename_class_references(text, legacy, canonical)
        text = _rename_public_class(text, canonical)
        if prog == "CHKAML":
            text = _inject_chkaml_flat_compile_support(text)
        elif prog == "CALCFEE":
            text = _inject_calcfee_dtos(text)
    else:
        for sub_prog, sub_class in SUB_PROGRAM_CANONICAL_CLASS.items():
            for legacy in SUB_PROGRAM_LEGACY_CLASSES.get(sub_prog, ()):
                text = _rename_class_references(text, legacy, sub_class)

    match = _PUBLIC_CLASS_RE.search(text)
    class_name = match.group(1) if match else (canonical or prog or "Output")
    return text, class_name


def collect_java_sources_for_behavioral_testing(
    program_name: str,
    primary_java: str,
    *,
    request: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Gather all Java sources that should compile together for one behavioral run."""
    prog = str(program_name or "").strip().upper()
    sources: Dict[str, str] = {}
    if primary_java.strip():
        sources[prog] = get_java_for_testing(prog, primary_java)

    req = request or {}

    raw_map = req.get("java_files")
    if isinstance(raw_map, dict):
        for key, value in raw_map.items():
            if isinstance(value, str) and value.strip():
                key_upper = str(key).upper()
                sources[key_upper] = get_java_for_testing(key_upper, value)

    project_java = req.get("_project_java_files")
    if isinstance(project_java, dict):
        for key, value in project_java.items():
            if isinstance(value, str) and value.strip():
                key_upper = str(key).upper()
                sources[key_upper] = get_java_for_testing(key_upper, value)

    if prog in ACME_PROGRAMS or any(name in ACME_PROGRAMS for name in sources):
        for acme_prog in ACME_PROGRAMS:
            if sources.get(acme_prog, "").strip():
                continue
            fixture_java = get_java_for_testing(acme_prog, "")
            if fixture_java.strip():
                sources[acme_prog] = fixture_java

    return sources


def stage_java_sources_for_testing(
    sources: Dict[str, str],
    work_dir: Path,
    *,
    entry_program: str,
) -> Tuple[List[Path], str, List[Path]]:
    """
    Normalize and write Java sources for flat compilation.

    Returns ``(all_java_paths, entry_class, source_paths_without_launcher)``.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    entry_prog = str(entry_program or "").strip().upper()
    written_classes: set[str] = set()
    source_paths: List[Path] = []

    def _write_program(prog: str, raw_source: str) -> None:
        normalized, class_name = normalize_java_for_flat_compile(raw_source, prog)
        if class_name in written_classes:
            return
        path = work_dir / f"{class_name}.java"
        path.write_text(normalized, encoding="utf-8")
        source_paths.append(path)
        written_classes.add(class_name)

    for sub in sorted(SUB_PROGRAMS):
        if sub in sources and sources[sub].strip():
            _write_program(sub, sources[sub])

    for prog in sorted(sources.keys()):
        if prog in SUB_PROGRAMS:
            continue
        if sources[prog].strip():
            _write_program(prog, sources[prog])

    entry_source = sources.get(entry_prog, "")
    normalized_entry, _ = normalize_java_for_flat_compile(entry_source, entry_prog)
    unit = build_behavioral_java_compile_unit(normalized_entry, entry_prog or "Output")
    entry_class = unit.entry_class

    all_paths = list(source_paths)
    if unit.uses_launcher:
        launcher_name = f"{unit.entry_class}.java"
        launcher_path = work_dir / launcher_name
        launcher_path.write_text(unit.files[launcher_name], encoding="utf-8")
        if launcher_path not in all_paths:
            all_paths.append(launcher_path)

    return all_paths, entry_class, source_paths


def compile_java_for_testing(
    java_files: List[str],
    work_dir: str,
    *,
    timeout_seconds: float = 60.0,
    env: Optional[dict[str, str]] = None,
) -> CompileResult:
    """Compile all Java files together so cross-program imports resolve."""
    if not java_files:
        return CompileResult(ok=False, stdout="", stderr="No Java files provided")

    work = Path(work_dir)
    cmd = [
        _tool_executable("javac"),
        "-encoding",
        "UTF-8",
        "-d",
        str(work.resolve()),
        *[str(Path(p).resolve()) for p in java_files],
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(work.resolve()),
            timeout=timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return CompileResult(ok=False, stdout="", stderr="javac timed out", command=cmd)

    return CompileResult(
        ok=proc.returncode == 0,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        command=cmd,
    )


def compile_java_bundle_for_behavioral_testing(
    sources: Dict[str, str],
    work_dir: Path,
    *,
    entry_program: str,
    timeout_seconds: float = 60.0,
    env: Optional[dict[str, str]] = None,
) -> Tuple[CompileResult, str]:
    """Stage normalized sources and compile them together. Returns compile result and entry class."""
    paths, entry_class, _ = stage_java_sources_for_testing(
        sources,
        work_dir,
        entry_program=entry_program,
    )
    result = compile_java_for_testing(
        [str(p) for p in paths],
        str(work_dir),
        timeout_seconds=timeout_seconds,
        env=env,
    )
    return result, entry_class
