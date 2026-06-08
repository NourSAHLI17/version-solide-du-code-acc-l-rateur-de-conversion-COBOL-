#!/usr/bin/env python3
"""Re-analyze ACME programs via API and report UI complexity tiers."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:8010/api"
ROOT = Path(__file__).resolve().parents[2] / "acme-bank-v3" / "src"
PROGRAMS = ("CALCFEE", "CHKAML", "RISKSCOR", "RECOVRY", "RPTMONTH", "LOANEVAL")


def post(path: str, body: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ui_tier(analysis: dict) -> str:
    ct = analysis.get("complexity_tier") or {}
    if isinstance(ct, dict) and ct.get("tier"):
        return str(ct["tier"])
    legacy = str(analysis.get("complexity") or "").lower()
    if legacy in {"low", "simple"}:
        return "Standard (legacy fallback)"
    if legacy in {"medium", "mixed"}:
        return "Complex (legacy fallback)"
    if legacy == "high":
        return "Enterprise (legacy fallback)"
    return "Unknown"


def main() -> int:
    print(f"API: {API}\n")
    for prog in PROGRAMS:
        src = (ROOT / f"{prog}.cbl").read_text(encoding="utf-8")
        parser_output = post("/parse", {"source_code": src})
        analysis = post(
            "/analyze",
            {"source_code": src, "parser_output": parser_output},
            timeout=600,
        )
        ct = analysis.get("complexity_tier") or {}
        print(f"{prog}:")
        print(f"  complexity_tier={json.dumps(ct)}")
        print(f"  legacy complexity={analysis.get('complexity')!r}")
        print(f"  UI tier → {ui_tier(analysis)}")
        print()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as exc:
        print(f"Backend not reachable at {API}: {exc}")
        raise SystemExit(2)
