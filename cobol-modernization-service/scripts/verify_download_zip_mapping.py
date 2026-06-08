#!/usr/bin/env python3
"""Verify sequential workspace zip mapping after download/storage fixes."""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import httpx

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parent
FIXTURE_DIR = SERVICE_ROOT / "tests" / "fixtures" / "acme_e2e"
ACME_SEQ = REPO_ROOT / "acme-bank-v3" / "src" / "sequential"
API = "http://127.0.0.1:8010/api"

ORDER = [
    "CALCFEE.cbl",
    "CHKAML.cbl",
    "RISKSCOR.cbl",
    "RPTMONTH.cbl",
    "RECOVRY.cbl",
    "LOANEVAL.cbl",
]


def extract_public_class(java: str) -> str | None:
    m = re.search(r"public\s+class\s+(\w+)", java)
    return m.group(1) if m else None


def expand_copybooks(source: str, lib: dict[str, str]) -> str:
    import re as _re

    pattern = _re.compile(
        r"^.{6}.\s+COPY\s+([A-Z0-9#@$\-]+).*\.\s*$",
        _re.IGNORECASE | _re.MULTILINE,
    )

    def repl(m: _re.Match) -> str:
        name = m.group(1).upper()
        return lib.get(name, m.group(0))

    return pattern.sub(repl, source)


def load_copybook_lib() -> dict[str, str]:
    lib: dict[str, str] = {}
    copy_dir = REPO_ROOT / "acme-bank-v3" / "src" / "copybooks"
    if copy_dir.is_dir():
        for p in copy_dir.glob("*.cpy"):
            lib[p.stem.upper()] = p.read_text(encoding="utf-8", errors="replace")
    return lib


def api_post(client: httpx.Client, path: str, body: dict) -> dict:
    r = client.post(f"{API}{path}", json=body, timeout=600.0)
    r.raise_for_status()
    return r.json()


def convert_program(client: httpx.Client, filename: str, copy_lib: dict[str, str]) -> dict:
    src_path = ACME_SEQ / filename
    source = expand_copybooks(src_path.read_text(encoding="utf-8", errors="replace"), copy_lib)
    parser = api_post(client, "/parse", {"source_code": source})
    analysis = api_post(
        client,
        "/analyze",
        {"source_code": source, "parser_output": parser},
    )
    analysis_str = json.dumps(analysis) if isinstance(analysis, dict) else str(analysis)
    conv = api_post(
        client,
        "/convert",
        {
            "source_code": source,
            "parser_output": parser,
            "analysis_output": analysis_str,
        },
    )
    java = conv.get("java_code") or conv.get("java_source") or ""
    requested = Path(filename).stem.upper()
    got = str(parser.get("program_name") or "").upper()
    if got and got != requested:
        print(f"WARN program mismatch: requested {requested}, parser {got}", file=sys.stderr)
    return {
        "program_key": filename,
        "java_source": java,
        "conversion_status": conv.get("conversion_status"),
        "program_name": got or requested,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reconvert-only", default="RISKSCOR.cbl")
    parser.add_argument("--skip-full-run", action="store_true", help="Only re-convert one program")
    args = parser.parse_args()

    if not ACME_SEQ.is_dir():
        print(f"Missing {ACME_SEQ}", file=sys.stderr)
        return 1

    copy_lib = load_copybook_lib()
    workspace: dict[str, dict] = {}

    with httpx.Client() as client:
        try:
            client.get(f"{API}/status", timeout=5.0)
        except Exception as exc:
            print(f"Backend not reachable at {API}: {exc}", file=sys.stderr)
            return 1

        if not args.skip_full_run:
            print("Running sequential conversions (6 programs)...")
            for name in ORDER:
                print(f"  converting {name}...")
                workspace[name] = convert_program(client, name, copy_lib)
        else:
            print("Loading baseline workspace from fixtures...")
            for name in ORDER:
                stem = Path(name).stem
                fixture = FIXTURE_DIR / f"{stem}.raw.java"
                if fixture.is_file():
                    workspace[name] = {"program_key": name, "java_source": fixture.read_text(encoding="utf-8")}
                else:
                    print(f"  missing fixture {fixture}", file=sys.stderr)

        recon = args.reconvert_only
        print(f"Re-converting {recon}...")
        workspace[recon] = convert_program(client, recon, copy_lib)

    from app.services.pipeline_service import PipelineService

    zip_bytes = PipelineService.build_download_zip(workspace)
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        print("\nZIP contents:")
        for name in sorted(zf.namelist()):
            body = zf.read(name).decode("utf-8", errors="replace")
            cls = extract_public_class(body)
            print(f"  {name}: class {cls or '(none)'}")

    for key in ("RISKSCOR.cbl", "LOANEVAL.cbl"):
        entry = workspace.get(key)
        if not entry:
            continue
        java = entry.get("java_source") or ""
        cls = extract_public_class(java)
        print(f"\nWorkspace {key} -> public class {cls or '(none)'}")

    risk_cls = extract_public_class(workspace.get("RISKSCOR.cbl", {}).get("java_source", ""))
    loan_cls = extract_public_class(workspace.get("LOANEVAL.cbl", {}).get("java_source", ""))
    ok = True
    if risk_cls and "riskscor" not in risk_cls.lower():
        print(f"FAIL: RISKSCOR.java defines {risk_cls}, expected RiskscorApplication-like", file=sys.stderr)
        ok = False
    if loan_cls and "loaneval" not in loan_cls.lower() and "recovry" in loan_cls.lower():
        print(f"FAIL: LOANEVAL.java defines {loan_cls}, looks like wrong program", file=sys.stderr)
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
