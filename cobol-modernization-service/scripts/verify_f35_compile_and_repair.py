#!/usr/bin/env python3
"""F35 verification: compile-and-repair after Java generation."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.converters.cobol_name_converter import enrich_symbol_table_java_names
from app.services.java_compile_repair import JavacResult, compile_and_repair

_BROKEN = """
public class Test {
    private static class LoanRecord { private String loanStatus; }
    void foo() { LoanRecord r = new LoanRecord(); r.status = "AC"; }
}
"""

_JAVAC_FAIL = """Test.java:4: error: cannot find symbol
  symbol:   variable status
  location: variable r of type LoanRecord
"""


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def _ok(msg: str) -> None:
    print(f"OK  {msg}")


def main() -> int:
    print("F35 — compile-and-repair")
    sym = enrich_symbol_table_java_names(
        [{"name": "LOAN-STATUS", "pic": "X(2)", "java_field": "loanStatus"}]
    )
    calls = 0

    def fake_javac(_files, *, work_dir):
        nonlocal calls
        calls += 1
        if calls == 1:
            return JavacResult(success=False, returncode=1, stdout="", stderr=_JAVAC_FAIL)
        return JavacResult(success=True, returncode=0, stdout="", stderr="")

    with patch("app.services.java_compile_repair.run_javac", side_effect=fake_javac):
        result = compile_and_repair({"Test.java": _BROKEN}, symbol_table=sym, program_name="TEST")

    if not result.success:
        return _fail(f"expected compile success after repair, stderr={result.stderr}")
    fixed = result.java_files.get("Test.java", "")
    if "r.loanStatus" not in fixed or "r.status" in fixed:
        return _fail("symbol repair did not apply in compile loop")
    _ok("cannot_find_symbol → reconcile_names → javac success")

    from app.services.pipeline_service import PipelineService

    svc = PipelineService()
    with patch.object(
        svc.agents.conversion_agent,
        "convert_with_metadata",
        return_value=(_BROKEN, ""),
    ):
        with patch(
            "app.agents.conversion_agent.compile_and_repair",
            side_effect=compile_and_repair,
        ):
            with patch("app.services.java_compile_repair.run_javac", side_effect=fake_javac):
                out = svc.convert_cobol("x", {"program_name": "TEST", "symbol_table": sym}, "{}")

    if out.get("conversion_status") != "complete":
        return _fail(f"expected complete after repair, got {out.get('conversion_status')}")
    _ok("pipeline convert_cobol uses postprocess compile_and_repair metadata")

    print("\n=== F35 PASSED ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
