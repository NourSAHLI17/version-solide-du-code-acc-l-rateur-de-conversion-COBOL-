#!/usr/bin/env python3
"""
F37 verification: repair history is exposed for the dashboard UI.

Runs a deterministic conversion with deliberately broken LLM Java so
compile-and-repair produces non-empty notes, then validates:

  - repair_summary.auto_repairs (human-readable)
  - repair_summary.manual_review (line + message)
  - compile_repair_notes (raw technical log)
  - conversion_status when repairs are insufficient

Usage (from cobol-modernization-service):
  python scripts/verify_f37_repair_history_ui.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CBL = ROOT / "tests" / "fixtures" / "TEMPCNVT.cbl"

# Deliberately broken Java: Spring imports, type mismatch, missing semicolon, typo field.
_BROKEN_JAVA = """\
package com.modernized.tempcnvt;

import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;

@Service
public class Tempcnvt {

    private int wsFahrenheit;
    private String wsCelsiu = "";

    @Autowired
    private void convert() {
        wsFahrenheit = new java.math.BigDecimal("32.0");
        rec.status = "OK"
    }
}
"""


def _install_broken_java_shim() -> None:
    from app.agents.conversion_agent import ConversionAgent

    def _broken_raw(_self, _source, parser_output, _analysis, *, java_profile=None):
        return _BROKEN_JAVA

    def _broken_regen(_self, source, parser_output, analysis, _errors, *, java_profile=None):
        return _broken_raw(_self, source, parser_output, analysis, java_profile=java_profile)

    ConversionAgent._convert_raw = _broken_raw
    ConversionAgent._convert_raw_regeneration = _broken_regen


def main() -> int:
    os.environ.setdefault("ANALYSIS_ENGINE", "deterministic")
    sys.path.insert(0, str(ROOT))

    if not FIXTURE_CBL.is_file():
        print(f"FAIL: missing fixture {FIXTURE_CBL}")
        return 1

    source = FIXTURE_CBL.read_text(encoding="utf-8")
    _install_broken_java_shim()

    from app.services.pipeline_service import PipelineService

    svc = PipelineService()
    parsed = svc.parse_cobol(source)
    analysis = svc.analyze_cobol(source, parsed)
    result = svc.convert_cobol(source, parsed, analysis, java_profile="plain_java")

    print("F37 — repair history API verification")
    print("=" * 60)

    errors: list[str] = []

    java_code = result.get("java_code") or ""
    if not java_code.strip():
        errors.append("java_code is empty")

    raw_notes = result.get("compile_repair_notes") or []
    all_notes = list(getattr(svc.agents.conversion_agent, "last_all_repair_notes", None) or raw_notes)
    summary = result.get("repair_summary") or {}

    auto = summary.get("auto_repairs") or []
    manual = summary.get("manual_review") or []
    status = result.get("conversion_status", "unknown")

    print(f"conversion_status: {status}")
    print(f"compile_repair_notes: {len(raw_notes)} item(s)")
    print(f"last_all_repair_notes: {len(all_notes)} item(s)")
    print(f"repair_summary.auto_repairs: {len(auto)} item(s)")
    print(f"repair_summary.manual_review: {len(manual)} item(s)")

    if not all_notes and not raw_notes:
        errors.append("expected non-empty compile_repair_notes from broken Java run")

    if not auto and not manual:
        errors.append(
            "expected repair_summary with auto_repairs and/or manual_review "
            "(backend summary generation)"
        )

    def _safe_print(text: str) -> None:
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode("ascii", errors="replace").decode("ascii"))

    if auto:
        print("\nAuto-repairs (UI bullets):")
        for line in auto[:12]:
            _safe_print(f"  - {line}")
        if len(auto) > 12:
            print(f"  ... +{len(auto) - 12} more")

    if manual:
        print("\nManual review (UI warnings):")
        for item in manual[:12]:
            line_no = item.get("line", "?")
            msg = item.get("message", "")
            _safe_print(f"  - Line {line_no}: {msg}")

    if raw_notes:
        print("\nTechnical log (first 5 compile_repair_notes):")
        for note in raw_notes[:5]:
            _safe_print(f"  * {note[:120]}")

    # UI contract checks
    for item in manual:
        if not isinstance(item, dict) or "line" not in item or "message" not in item:
            errors.append("manual_review items must have line and message keys")
            break

    if raw_notes and not isinstance(raw_notes, list):
        errors.append("compile_repair_notes must be a list")

    # Partial label when javac still fails after repairs
    compile_success = result.get("compile_success")
    if compile_success is False and status != "partial":
        errors.append(
            f"expected conversion_status=partial when compile_success=False, got {status!r}"
        )

    # Spot-check: broken input should have triggered at least one recognizable repair class
    joined_auto = " ".join(auto).lower()
    joined_notes = " ".join(all_notes).lower()
    triggered = any(
        kw in joined_auto or kw in joined_notes
        for kw in (
            "semicolon",
            "import",
            "spring",
            "renamed",
            "type mismatch",
            "bigdecimal",
            "incompatible",
            "annotation",
            "profile",
        )
    )
    if not triggered:
        errors.append(
            "no recognizable repair activity in summary/notes "
            "(broken Java may not have exercised the pipeline)"
        )

    print("\nAPI payload excerpt (repair_summary):")
    print(json.dumps(summary, indent=2)[:2000])

    print("\n" + "=" * 60)
    if errors:
        print("FAIL F37:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("OK F37: repair_summary and compile_repair_notes ready for dashboard UI")
    if status == "partial":
        print("  (partial status — UI should show Partial badge + manual review)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
