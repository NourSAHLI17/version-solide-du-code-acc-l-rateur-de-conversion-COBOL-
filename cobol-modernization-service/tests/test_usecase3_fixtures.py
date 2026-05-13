"""Phase 0 Step 0.3 — Use Case 3 fixtures: full pipeline + enrichment checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.parsers import copybook_resolver as copybook_resolver_module
from app.services.pipeline_service import PipelineService

FIX = Path(__file__).resolve().parent / "fixtures" / "usecase3"
JCL = (FIX / "jcl" / "UC3JOB.jcl").read_text(encoding="utf-8")


@pytest.fixture
def copylib_paths():
    """Point COPY resolution at tests/fixtures/usecase3/copybooks."""
    lib_dir = str(FIX / "copybooks")
    prev = copybook_resolver_module.COPY_LIBRARY_CONFIG.get("default", [])
    copybook_resolver_module.COPY_LIBRARY_CONFIG["default"] = [lib_dir] + [
        p for p in prev if p != lib_dir
    ]
    yield
    copybook_resolver_module.COPY_LIBRARY_CONFIG["default"] = prev


@pytest.fixture
def pipeline():
    return PipelineService()


def _run(pipeline: PipelineService, program: str, copylib_paths) -> dict:
    src = (FIX / f"{program}.cbl").read_text(encoding="utf-8")
    return pipeline.run_full_pipeline(src, JCL)


def test_custmgr_usecase3(pipeline: PipelineService, copylib_paths):
    out = _run(pipeline, "CUSTMGR", copylib_paths)
    ast = out["ast"]
    assert ast.get("preflight_errors") == []
    assert len(ast.get("paragraphs") or []) >= 5
    sym = ast.get("symbol_table") or []
    assert len(sym) > 20
    names = {s.get("name") for s in sym if isinstance(s, dict)}
    assert {"CUST-ID", "CUST-NAME", "CUST-BALANCE"}.issubset(names)
    dm = out.get("data_mappings") or {}
    assert dm["CUSTOMER-FILE"]["physical_dataset"] == "ACME.CUSTOMER.MASTER"
    books = ast.get("dependencies", {}).get("copybooks") or []
    assert "CUSTCOPY" in books


def test_stmtrpt_usecase3(pipeline: PipelineService, copylib_paths):
    out = _run(pipeline, "STMTRPT", copylib_paths)
    ast = out["ast"]
    assert ast.get("preflight_errors") == []
    assert len(ast.get("paragraphs") or []) >= 4
    sym = ast.get("symbol_table") or []
    assert len(sym) > 20
    names = {s.get("name") for s in sym if isinstance(s, dict)}
    assert "RPT-LINE-TEXT" in names
    ops = ast.get("operations") or []
    assert len(ops) > 0
    types = {o.get("type") for o in ops if isinstance(o, dict)}
    for t in ("READ", "WRITE", "OPEN", "CLOSE"):
        assert t in types, f"STMTRPT missing op {t}, have {sorted(types)}"
    files_hit = set()
    for o in ops:
        if not isinstance(o, dict):
            continue
        if o.get("type") == "OPEN":
            files_hit.add(o.get("target"))
        if o.get("type") in ("READ", "WRITE", "REWRITE", "CLOSE"):
            files_hit.add(o.get("target"))
    for fn in ("CUSTOMER-FILE", "REPORT-FILE"):
        assert fn in files_hit, f"expected file {fn} in ops targets, got {files_hit}"
    books = ast.get("dependencies", {}).get("copybooks") or []
    assert "CUSTCOPY" in books and "RPTCOPY" in books


def test_txnpost_usecase3(pipeline: PipelineService, copylib_paths):
    out = _run(pipeline, "TXNPOST", copylib_paths)
    ast = out["ast"]
    assert ast.get("preflight_errors") == []
    assert len(ast.get("paragraphs") or []) >= 5
    sym = ast.get("symbol_table") or []
    assert len(sym) > 20
    names = {s.get("name") for s in sym if isinstance(s, dict)}
    assert "TXN-AMOUNT" in names and "CUST-BALANCE" in names
    ops = ast.get("operations") or []
    types = {o.get("type") for o in ops if isinstance(o, dict)}
    for t in ("OPEN", "READ", "WRITE", "CLOSE", "COMPUTE", "REWRITE"):
        assert t in types, f"missing op {t}, have {sorted(types)}"
    files_hit = set()
    for o in ops:
        if not isinstance(o, dict):
            continue
        if o.get("type") == "OPEN":
            files_hit.add(o.get("target"))
        if o.get("type") in ("READ", "WRITE", "REWRITE", "CLOSE"):
            files_hit.add(o.get("target"))
        if o.get("type") == "DELETE" and o.get("target"):
            files_hit.add(o.get("target"))
    for fn in ("CUSTOMER-FILE", "TRANSACTION-FILE", "REPORT-FILE"):
        assert fn in files_hit, f"expected file {fn} in ops targets, got {files_hit}"
    books = ast.get("dependencies", {}).get("copybooks") or []
    assert "CUSTCOPY" in books and "TXNCOPY" in books
