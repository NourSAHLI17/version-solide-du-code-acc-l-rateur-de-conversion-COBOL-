#!/usr/bin/env python3
"""Mirror Project page 'Run All' against the FastAPI backend (same as dashboard UI)."""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

import urllib.error
import urllib.request

API = "http://127.0.0.1:8010/api"
ROOT = Path(__file__).resolve().parents[2]
ZIP_PATH = ROOT / "acme-bank-v3.zip"
COPY_RE = re.compile(r"^(\s*)COPY\s+([A-Z0-9-]+)(\s+REPLACING[\s\S]*?)?\s*\.?\s*$", re.I | re.M)


def http_json(method: str, path: str, body: dict | None = None, timeout: int = 600) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_zip_files(zip_path: Path) -> Dict[str, str]:
    files: Dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            if not info.filename.lower().endswith((".cbl", ".cpy", ".jcl")):
                continue
            posix = info.filename.replace("\\", "/")
            files[posix] = zf.read(info.filename).decode("utf-8", errors="replace")
            base = posix.split("/")[-1]
            files[base] = files[posix]
    return files


def normalize_map(raw: Dict[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for path, content in raw.items():
        base = path.split("/")[-1]
        out[base.upper()] = content
        out[base] = content
        out[path.replace("\\", "/").upper()] = content
    return out


def resolve_copy(name: str, amap: Dict[str, str], stack: set[str]) -> str:
    keys = [f"{name.upper()}.CPY", f"{name}.cpy", name.upper(), name]
    body = None
    for k in keys:
        if k in amap:
            body = amap[k]
            break
    if body is None:
        return f"      *> COPY {name} (unresolved — file not in project ZIP)\n"
    sig = name.upper()
    if sig in stack:
        return f"      *> COPY {name} (circular)\n"
    stack.add(sig)
    try:
        return expand_source(body, amap, stack)
    finally:
        stack.discard(sig)


def expand_source(source: str, raw: Dict[str, str], stack: set[str] | None = None) -> str:
    stack = stack or set()
    amap = normalize_map(raw)

    def repl(m: re.Match[str]) -> str:
        indent, name = m.group(1), m.group(2)
        expanded = resolve_copy(name, amap, stack)
        lines = expanded.splitlines()
        return "\n".join(f"{indent}{line}" for line in lines)

    return COPY_RE.sub(repl, source)


def topological_order(cbl_paths: List[str], files: Dict[str, str]) -> List[str]:
    by_stem = {Path(p).stem.upper(): p for p in cbl_paths}
    copy_dep = re.compile(r"^\s*COPY\s+([A-Z0-9-]+)", re.I | re.M)
    referenced: set[str] = set()
    for path in cbl_paths:
        for m in copy_dep.finditer(files[path]):
            dep = m.group(1).upper()
            if dep in by_stem:
                referenced.add(Path(by_stem[dep]).name.upper())

    def sort_key(p: str) -> tuple[int, str]:
        fn = Path(p).name.upper()
        return (1 if fn in referenced else 0, fn)

    return sorted(cbl_paths, key=sort_key)


def parser_ok(parser_output: dict) -> bool:
    errs = parser_output.get("preflight_errors")
    return isinstance(errs, list) and len(errs) == 0


def score_total(conversion_score: Any) -> int | None:
    if not isinstance(conversion_score, dict):
        return None
    total = conversion_score.get("total")
    if total is None:
        total = conversion_score.get("overall_score")
    try:
        n = float(total)
    except (TypeError, ValueError):
        return None
    if not (n == n):  # NaN
        return None
    return int(round(n))


def stage_label(status: str) -> str:
    return {
        "done": "Done",
        "error": "Failed",
        "partial": "Partial",
        "running": "Running",
        "idle": "Idle",
    }.get(status, status)


def run_program(path: str, source: str) -> dict:
    row = {
        "program": Path(path).stem.upper(),
        "path": path,
        "parse": "Failed",
        "analyze": "Failed",
        "java": "Failed",
        "quality": "—",
        "error": "",
    }
    try:
        parser_output = http_json("POST", "/parse", {"source_code": source})
        if not parser_ok(parser_output):
            errs = parser_output.get("preflight_errors") or []
            row["error"] = "; ".join(str(e) for e in errs) or "parse preflight failed"
            return row
        row["parse"] = "Done"

        analysis_output = http_json(
            "POST",
            "/analyze",
            {"source_code": source, "parser_output": parser_output},
        )
        if (
            isinstance(analysis_output, dict)
            and analysis_output.get("analysis_engine") == "n/a"
        ):
            row["error"] = "Analysis halted"
            return row
        row["analyze"] = "Done"

        convert_payload = http_json(
            "POST",
            "/convert",
            {
                "source_code": source,
                "parser_output": parser_output,
                "analysis_output": json.dumps(analysis_output),
            },
            timeout=900,
        )
        if convert_payload.get("conversion_failed"):
            row["error"] = convert_payload.get("error") or "conversion failed"
            return row

        status = convert_payload.get("conversion_status")
        if status == "partial":
            row["java"] = "Partial"
            errs = convert_payload.get("compile_errors") or []
            stderr = convert_payload.get("compile_stderr") or ""
            row["error"] = "\n".join(errs) if errs else stderr[:500]
        else:
            row["java"] = "Done"

        total = score_total(convert_payload.get("conversion_score"))
        if total is not None:
            row["quality"] = f"{total}/100"
        return row
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        row["error"] = body[:500] or str(exc)
        return row
    except Exception as exc:
        row["error"] = str(exc)
        return row


def run_via_project_pipeline(cbl_paths: List[str], files: Dict[str, str]) -> List[dict]:
    """Run all programs through POST /project/pipeline (server-side parallel conversion)."""
    pipeline_files: List[dict] = []
    for path in sorted(files):
        if path.lower().endswith(".cpy"):
            pipeline_files.append(
                {"path": path.replace("\\", "/"), "type": "copybook", "content": files[path]}
            )
    for path in cbl_paths:
        pipeline_files.append(
            {
                "path": path.replace("\\", "/"),
                "type": "cobol",
                "content": files[path],
            }
        )

    payload = http_json(
        "POST",
        "/project/pipeline",
        {"files": pipeline_files, "mode": "convert_only"},
        timeout=3600,
    )

    by_path = {r.get("file", ""): r for r in payload.get("results", [])}
    results: List[dict] = []
    for path in cbl_paths:
        norm = path.replace("\\", "/")
        r = by_path.get(norm) or by_path.get(path) or {}
        prog = Path(path).stem.upper()
        row = {
            "program": prog,
            "path": path,
            "parse": "Failed",
            "analyze": "Failed",
            "java": "Failed",
            "quality": "—",
            "error": "",
        }
        errs = r.get("errors") or []
        if errs and not r.get("parser_output"):
            row["error"] = "; ".join(str(e) for e in errs)
            results.append(row)
            continue

        parser_output = r.get("parser_output") or {}
        if parser_ok(parser_output):
            row["parse"] = "Done"
        else:
            pre = parser_output.get("preflight_errors") or errs
            row["error"] = "; ".join(str(e) for e in pre) or "parse preflight failed"
            results.append(row)
            continue

        analysis_output = r.get("analysis_output")
        if (
            isinstance(analysis_output, dict)
            and analysis_output.get("analysis_engine") == "n/a"
        ):
            row["error"] = "Analysis halted"
            results.append(row)
            continue
        row["analyze"] = "Done"

        if r.get("conversion_failed"):
            row["error"] = r.get("error") or "conversion failed"
            results.append(row)
            continue

        status = r.get("conversion_status")
        if status == "partial":
            row["java"] = "Partial"
            compile_errs = r.get("compile_errors") or []
            stderr = r.get("compile_stderr") or ""
            row["error"] = "\n".join(compile_errs) if compile_errs else stderr[:500]
        elif r.get("java_source"):
            row["java"] = "Done"
        else:
            row["error"] = "; ".join(str(e) for e in errs) or "no java output"

        total = score_total(r.get("conversion_score"))
        if total is not None:
            row["quality"] = f"{total}/100"
        results.append(row)
    return results


def main() -> int:
    if not ZIP_PATH.is_file():
        print(f"ZIP not found: {ZIP_PATH}", file=sys.stderr)
        return 2
    try:
        status = http_json("GET", "/status")
    except Exception as exc:
        print(f"Backend not reachable at {API}: {exc}", file=sys.stderr)
        return 2

    print(f"Backend: {API}  LLM={status.get('llm_model')}  conversion={status.get('conversion_available')}")
    print(f"ZIP: {ZIP_PATH}")
    print()

    files = load_zip_files(ZIP_PATH)
    cbl_paths = sorted(
        p for p in files
        if p.replace("\\", "/").lower().startswith("src/")
        and p.lower().endswith(".cbl")
    )
    cbl_paths = topological_order(cbl_paths, files)

    results = run_via_project_pipeline(cbl_paths, files)

    for row in results:
        prog = row["program"]
        print(f"--- {prog} ---", flush=True)
        print(
            f"  Parse: {row['parse']}  Analyze: {row['analyze']}  Java: {row['java']}  Quality: {row['quality']}",
            flush=True,
        )
        if row["error"]:
            print(f"  Error: {row['error'][:300]}", flush=True)
        print(flush=True)

    print("=" * 72)
    print(f"{'PROGRAM':<12} {'PARSE':<8} {'ANALYZE':<8} {'JAVA':<8} {'QUALITY':<10} ERROR")
    print("-" * 72)
    for r in results:
        err = (r["error"] or "")[:40].replace("\n", " ")
        print(
            f"{r['program']:<12} {r['parse']:<8} {r['analyze']:<8} {r['java']:<8} {r['quality']:<10} {err}"
        )
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
