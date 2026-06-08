#!/usr/bin/env python3
"""Report complexity tiers for ACME programs (parse + classify path used by /analyze)."""
from __future__ import annotations

from pathlib import Path

from app.services.complexity_classifier import classify_complexity_tier
from app.services.pipeline_service import PipelineService

ROOT = Path(__file__).resolve().parents[2] / "acme-bank-v3" / "src"
PROGRAMS = ("CALCFEE", "CHKAML", "RISKSCOR", "RECOVRY", "RPTMONTH", "LOANEVAL")


def main() -> None:
    svc = PipelineService()
    print("Program     Score  UI Tier")
    print("-" * 36)
    for prog in PROGRAMS:
        src = (ROOT / f"{prog}.cbl").read_text(encoding="utf-8")
        po = svc.parse_cobol(src)
        tier = classify_complexity_tier(po, source_code=src)
        print(f"{prog:<11} {tier['score']:>5}  {tier['tier']}")


if __name__ == "__main__":
    main()
