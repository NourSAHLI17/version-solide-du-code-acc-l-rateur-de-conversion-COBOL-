"""Scoped retry and save-gating endpoints for the testing agent."""

import logging
import traceback

from fastapi import APIRouter, HTTPException

from app.api.schemas.testing import LayerScores, RunDiagnostics
from app.api.schemas.testing_retry import (
    DeriveRetryScopeRequest,
    DeriveRetryScopeResponse,
    FinalDecisionRequest,
    FinalDecisionResponse,
    RetryConversionScopeRequest,
    RetryConversionScopeResponse,
    RetryScopeMeta,
    SaveGateMeta,
    TestSummaryMeta,
    DiffSummaryView,
)
from app.services.testing_retry_service import (
    build_final_decision,
    derive_scope_only,
    retry_conversion_scope,
)

router = APIRouter(prefix="/api/testing", tags=["testing"])
logger = logging.getLogger(__name__)


def _optional_layer_scores(raw: dict) -> LayerScores | None:
    layer_raw = raw.get("layer_scores")
    if not isinstance(layer_raw, dict):
        return None
    return LayerScores(**layer_raw)


def _optional_run_diagnostics(raw: dict) -> RunDiagnostics | None:
    diag_raw = raw.get("run_diagnostics")
    if not isinstance(diag_raw, dict):
        return None
    return RunDiagnostics(**diag_raw)


def _layered_fields_from_raw(raw: dict) -> dict:
    """Map optional layered behavioral fields for FinalDecisionResponse."""
    out: dict = {}
    if "qscore" in raw:
        q = raw.get("qscore")
        out["qscore"] = int(q) if q is not None else None
    if "primary_failure_layer" in raw:
        out["primary_failure_layer"] = raw.get("primary_failure_layer")
    layer_scores = _optional_layer_scores(raw)
    if layer_scores is not None:
        out["layer_scores"] = layer_scores
    run_diagnostics = _optional_run_diagnostics(raw)
    if run_diagnostics is not None:
        out["run_diagnostics"] = run_diagnostics
    return out


@router.post("/final-decision", response_model=FinalDecisionResponse)
async def final_decision_endpoint(request: FinalDecisionRequest):
    """Compute reliability score and trust decision from validation outputs."""
    try:
        raw = build_final_decision(request.model_dump())
        return FinalDecisionResponse(
            program_name=raw["program_name"],
            reliability_score=int(raw["reliability_score"]),
            decision_state=str(raw["decision_state"]),
            save_eligible=bool(raw["save_eligible"]),
            score_breakdown=raw.get("score_breakdown"),
            reason_summary=raw.get("reason_summary"),
            blockers=list(raw.get("blockers") or []),
            diff_summary=DiffSummaryView(**raw["diff_summary"])
            if raw.get("diff_summary")
            else None,
            test_summary=TestSummaryMeta(**raw["test_summary"])
            if raw.get("test_summary")
            else None,
            retry_scope=raw.get("retry_scope"),
            save_gate=SaveGateMeta(**raw["save_gate"]),
            **_layered_fields_from_raw(raw),
        )
    except Exception as exc:
        logger.error("final-decision failed: %s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/derive-retry-scope", response_model=DeriveRetryScopeResponse)
async def derive_retry_scope_endpoint(request: DeriveRetryScopeRequest):
    """Return the smallest safe retry scope without re-running conversion."""
    try:
        payload = derive_scope_only(request.model_dump())
        return {"retry_scope": payload["retry_scope"]}
    except Exception as exc:
        logger.error("derive-retry-scope failed: %s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/retry-conversion-scope", response_model=RetryConversionScopeResponse)
async def retry_conversion_scope_endpoint(request: RetryConversionScopeRequest):
    """Re-convert a narrowed scope, re-run behavioral diff, and evaluate save readiness."""
    try:
        raw = retry_conversion_scope(request.model_dump())
        return RetryConversionScopeResponse(
            program_name=raw["program_name"],
            retry_scope=RetryScopeMeta(**raw["retry_scope"]),
            requested_scope=raw.get("requested_scope"),
            actual_scope=raw.get("actual_scope"),
            scope_widened=bool(raw.get("scope_widened")),
            widen_reason=raw.get("widen_reason"),
            included_paragraphs=list(raw.get("included_paragraphs") or []),
            excluded_paragraphs=list(raw.get("excluded_paragraphs") or []),
            retry_summary=raw.get("retry_summary"),
            conversion_result=raw["conversion_result"],
            test_result=raw["test_result"],
            diff_summary=raw["diff_summary"],
            failed_tests=raw["failed_tests"],
            score=raw.get("score"),
            reliability_score=raw.get("reliability_score"),
            decision_state=raw.get("decision_state"),
            save_eligible=bool(raw.get("save_eligible")),
            score_breakdown=raw.get("score_breakdown"),
            reason_summary=raw.get("reason_summary"),
            blockers=list(raw.get("blockers") or []),
            score_before=raw.get("score_before"),
            score_delta=raw.get("score_delta"),
            ready_to_save=raw["ready_to_save"],
            save_state=raw["save_state"],
            save_gate=SaveGateMeta(**raw["save_gate"]),
            unit_test_result=raw.get("unit_test_result"),
            edge_test_result=raw.get("edge_test_result"),
            business_rules_test_result=raw.get("business_rules_test_result"),
            retried_at=raw["retried_at"],
        )
    except Exception as exc:
        logger.error("retry-conversion-scope failed: %s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc)) from exc
