#!/usr/bin/env python3
"""Verify sequential Run All order (mirrors frontend handler)."""
from __future__ import annotations

import json
import time
import urllib.request
import zipfile
from pathlib import Path

API = "http://127.0.0.1:8010/api"
ZIP_PATH = Path(__file__).resolve().parents[2] / "acme-bank-v3.zip"
ORDER = [
    "CALCFEE.cbl",
    "CHKAML.cbl",
    "RISKSCOR.cbl",
    "RPTMONTH.cbl",
    "RECOVRY.cbl",
    "LOANEVAL.cbl",
]


def post(path: str, body: dict, timeout: int = 3600) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    if not ZIP_PATH.is_file():
        print(f"Missing zip: {ZIP_PATH}")
        return 1

    sources: dict[str, str] = {}
    with zipfile.ZipFile(ZIP_PATH) as zf:
        for name in zf.namelist():
            if name.lower().endswith(".cbl"):
                sources[Path(name).name] = zf.read(name).decode("utf-8", errors="replace")

    print("Sequential Run All (frontend order)\n")
    for idx, filename in enumerate(ORDER, 1):
        src = sources.get(filename)
        if not src:
            print(f"{idx}. {filename}: SKIP (not in zip)")
            continue
        t0 = time.time()
        print(f"{idx}. {filename}: started @ {time.strftime('%H:%M:%S')}", flush=True)
        po = post("/parse", {"source_code": src}, timeout=120)
        an = post("/analyze", {"source_code": src, "parser_output": po}, timeout=600)
        cv = post(
            "/convert",
            {
                "source_code": src,
                "parser_output": po,
                "analysis_output": json.dumps(an),
            },
            timeout=600,
        )
        elapsed = time.time() - t0
        status = cv.get("conversion_status", "?")
        print(
            f"   done @ {time.strftime('%H:%M:%S')} "
            f"({elapsed:.0f}s) conversion_status={status}",
            flush=True,
        )
        if idx < len(ORDER):
            time.sleep(2)

    print("\nAll programs processed one at a time.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
