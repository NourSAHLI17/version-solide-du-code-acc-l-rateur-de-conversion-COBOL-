#!/usr/bin/env python3
"""
F28 verification: corrupt generated Java and confirm the pipeline rejects it.

Usage (from cobol-modernization-service):
  python scripts/verify_f28_reject_broken_java.py

Requires no LLM — stubs raw conversion output with fixture Java, then applies
F28_VERIFY_CORRUPT_JAVA=1 so the pre-write validator must fail.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Enable controlled corruption before importing pipeline (conversion_agent reads env at runtime).
os.environ["F28_VERIFY_CORRUPT_JAVA"] = "1"

from app.agents.conversion_agent import ConversionAgent
from app.services.java_pre_write_validator import (
    JavaPreWriteValidationError,
    validate_java_before_write,
    write_java_file,
)
from app.services.java_output_corruptor import corrupt_java_for_f28_verify
from app.services.pipeline_service import PipelineService

_FIXTURE_JAVA = """\
package com.modernized.demo;

public class Demo {
    public static void main(String[] args) {
        System.out.println("F28 fixture");
    }
}
"""

_MINIMAL_COBOL = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. DEMO.
       PROCEDURE DIVISION.
           DISPLAY "HELLO".
           STOP RUN.
"""


def main() -> int:
    print("F28 verification — reject broken generated Java")
    print("=" * 60)

    # Step 1: corruption hook breaks valid Java
    corrupt = corrupt_java_for_f28_verify(_FIXTURE_JAVA)
    errors = validate_java_before_write(corrupt)
    if not errors:
        print("FAIL: validator did not detect corrupted Java")
        return 1
    print(f"OK  Validator detected corruption ({len(errors)} error(s)):")
    for err in errors:
        print(f"    - {err}")

    # Step 2: write_java_file must not persist broken source
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "Demo.java"
        try:
            write_java_file(out_path, corrupt)
            print("FAIL: write_java_file wrote invalid Java")
            return 1
        except JavaPreWriteValidationError:
            pass
        if out_path.exists():
            print("FAIL: invalid Java file exists on disk")
            return 1
    print("OK  write_java_file refused to write invalid Java")

    # Step 3: full pipeline convert_cobol (no LLM)
    agent = ConversionAgent()
    with patch.object(agent, "_convert_raw", return_value=_FIXTURE_JAVA), patch.object(
        agent, "_convert_raw_regeneration", return_value=_FIXTURE_JAVA
    ):
        svc = PipelineService()
        svc.agents.conversion_agent = agent
        result = svc.convert_cobol(
            _MINIMAL_COBOL,
            {"program_name": "DEMO"},
            "{}",
        )

    if not result.get("conversion_failed"):
        print("FAIL: pipeline did not set conversion_failed=true")
        print("       java_code length:", len(result.get("java_code") or ""))
        return 1
    if not result.get("validation_errors"):
        print("FAIL: pipeline missing validation_errors")
        return 1
    if result.get("java_code"):
        print("FAIL: pipeline returned non-empty java_code for failed conversion")
        return 1

    print("OK  pipeline conversion_failed=true")
    print(f"    error: {result.get('error')}")
    print("    validation_errors:")
    for err in result.get("validation_errors") or []:
        print(f"      - {err}")

    # Step 4: pipeline output dir must stay empty when using write_java_file on result
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "Demo.java"
        try:
            write_java_file(out_path, result.get("java_code") or corrupt)
        except JavaPreWriteValidationError:
            pass
        if out_path.exists():
            print("FAIL: pipeline path left invalid Java on disk")
            return 1
    print("OK  no invalid Java file written from pipeline result")

    print("=" * 60)
    print("F28 verification PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
