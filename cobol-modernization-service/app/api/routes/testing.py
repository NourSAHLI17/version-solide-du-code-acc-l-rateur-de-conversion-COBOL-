"""Dedicated testing agent API (behavioral diff runner)."""

import logging
import traceback

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.api.schemas.testing import BehavioralDiffRequest, BehavioralDiffResponse, ToolchainStatusResponse
from app.services.behavioral_diff_runner import run_behavioral_diff
from app.services.behavioral_toolchain import build_toolchain_status_payload

router = APIRouter(prefix="/api/testing", tags=["testing"])
logger = logging.getLogger(__name__)


@router.get("/toolchain-status", response_model=ToolchainStatusResponse)
async def toolchain_status_endpoint(
    fallback_mode: bool = Query(
        default=False,
        description="Whether the client has snapshot fallback enabled for the next run.",
    ),
    snapshots_available: bool = Query(
        default=False,
        description="Whether both COBOL and Java snapshot outputs are available.",
    ),
    execution_mode: Optional[str] = Query(
        default=None,
        description="Execution mode from the latest run (live, snapshot, mixed, unavailable).",
    ),
    force_refresh: bool = Query(
        default=False,
        description="Clear cached probe results and re-check the host PATH (use after installing cobc).",
    ),
):
    """Report toolchain availability and recommended next action for the Testing page banner."""
    return build_toolchain_status_payload(
        fallback_mode=fallback_mode,
        snapshots_available=snapshots_available,
        execution_mode=execution_mode,
        force_refresh=force_refresh,
    )


@router.post("/behavioral-diff", response_model=BehavioralDiffResponse)
async def run_behavioral_diff_endpoint(request: BehavioralDiffRequest):
    """
    Production verification endpoint (dashboard Testing page, ACME regression).

    POST /api/test remains for lightweight static checks; behavioral-diff is the
    runtime equivalence gate that requires GnuCOBOL + javac on the host.
    """
    try:
        payload = run_behavioral_diff(request.model_dump())
        return payload
    except Exception as exc:
        logger.error("behavioral-diff failed: %s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc)) from exc
