"""Persistent conversion history API (SQLite via SQLAlchemy)."""

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.db.history_session import (
    clear_all,
    delete_entry,
    get_entry,
    list_entries,
    save_entry,
    session_scope,
)

_LOG = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["history"])


@router.get("/history")
async def history_list(limit: int = 100):
    """List saved conversion runs (newest first)."""

    lim = max(1, min(limit, 200))
    with session_scope() as session:
        entries = list_entries(session, limit=lim)
    _LOG.info("[HISTORY] list_entries returned %d rows (limit=%d)", len(entries), lim)
    return {"entries": entries}


@router.get("/history/{entry_id}")
async def history_get(entry_id: str):
    """Return one history entry by id."""

    with session_scope() as session:
        data = get_entry(session, entry_id)
    if not data:
        raise HTTPException(status_code=404, detail="History entry not found")
    return data


@router.post("/history")
async def history_save(payload: dict[str, Any] = Body(...)):
    """Save or update a conversion history row (full HistoryEntry JSON from the UI)."""

    try:
        with session_scope() as session:
            save_entry(session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "id": payload.get("id")}


@router.delete("/history/{entry_id}")
async def history_delete(entry_id: str):
    with session_scope() as session:
        ok = delete_entry(session, entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail="History entry not found")
    return {"ok": True}


def _get_flexible(data: dict, *keys: str, default: Any = None) -> Any:
    """Try multiple key variants (snake_case, camelCase) and return the first hit."""
    for k in keys:
        if k in data:
            return data[k]
    return default


@router.get("/history/{entry_id}/repair-summary")
async def history_repair_summary(entry_id: str):
    """Return display-ready repair history for a conversion entry."""
    from app.services.repair_history_renderer import render_repair_history

    with session_scope() as session:
        data = get_entry(session, entry_id)
    if not data:
        raise HTTPException(status_code=404, detail="History entry not found")

    repair_data = (
        _get_flexible(data, "repair_summary", "repairSummary")
        or {"auto_repairs": [], "manual_review": []}
    )
    return render_repair_history(
        repair_data,
        converted=bool(_get_flexible(data, "java_source", "javaSource", "java_code", "javaCode")),
        compiled=_get_flexible(data, "compile_status", "compileStatus", "conversion_status", "conversionStatus") in ("success", "complete"),
        verified=_get_flexible(data, "verification_status", "verificationStatus") == "passed",
        baseline_matched=bool(_get_flexible(data, "baseline_matched", "baselineMatched", default=False)),
    )


@router.delete("/history")
async def history_clear():
    with session_scope() as session:
        removed = clear_all(session)
    return {"ok": True, "removed": removed}
