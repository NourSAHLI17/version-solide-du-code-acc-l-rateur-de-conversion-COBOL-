"""Engine and session lifecycle for conversion history (SQLite)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Generator, Optional

from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import app.env_bootstrap  # noqa: F401
from app.db.base import Base
from app.db.conversion_history_orm import ConversionHistoryRecord
from app.env_bootstrap import SERVICE_ROOT

MAX_HISTORY_ROWS = int(os.getenv("CONVERSION_HISTORY_MAX", "50"))

_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker[Session]] = None


def _default_db_path() -> Path:
    override = os.getenv("CONVERSION_HISTORY_DB_PATH")
    if override:
        return Path(override)
    data = SERVICE_ROOT / "data"
    data.mkdir(parents=True, exist_ok=True)
    return data / "conversion_history.db"


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        path = _default_db_path()
        _engine = create_engine(
            f"sqlite:///{path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        _session_factory = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def reset_engine_for_tests() -> None:
    """Clear cached engine (pytest / alternate DB path)."""

    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def init_history_db() -> None:
    """Create tables if missing."""

    engine = get_engine()
    Base.metadata.create_all(engine)


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _extract_metadata(entry: dict[str, Any]) -> dict[str, Any]:
    analysis = entry.get("analysisOutput")
    eng = None
    complexity = None
    if isinstance(analysis, dict):
        eng = analysis.get("analysis_engine")
        if isinstance(eng, str):
            eng = eng[:64]
        c = analysis.get("complexity")
        if isinstance(c, str):
            complexity = c[:32]
    src = entry.get("sourceCode")
    if isinstance(src, str) and src:
        h = hashlib.sha256(src.encode("utf-8", errors="replace")).hexdigest()[:16]
    else:
        h = None
    return {"analysis_engine": eng, "complexity": complexity, "source_hash": h}


def save_entry(session: Session, entry: dict[str, Any]) -> None:
    """Insert or replace one history row and enforce max count."""

    eid = str(entry.get("id") or "")
    if not eid:
        raise ValueError("history entry missing id")
    etype = str(entry.get("type") or "single")
    program = str(entry.get("programName") or "unknown")
    meta = _extract_metadata(entry)
    payload = json.dumps(entry, separators=(",", ":"), default=str)
    row = ConversionHistoryRecord(
        id=eid,
        entry_type=etype,
        program_name=program,
        source_hash=meta["source_hash"],
        analysis_engine=meta["analysis_engine"],
        complexity=meta["complexity"],
        payload_json=payload,
    )
    session.merge(row)
    session.flush()

    count = session.scalar(select(func.count()).select_from(ConversionHistoryRecord)) or 0
    if count > MAX_HISTORY_ROWS:
        over = count - MAX_HISTORY_ROWS
        ids = session.scalars(
            select(ConversionHistoryRecord.id).order_by(ConversionHistoryRecord.created_at.asc()).limit(over),
        ).all()
        for oid in ids:
            session.execute(delete(ConversionHistoryRecord).where(ConversionHistoryRecord.id == oid))


def list_entries(session: Session, limit: int = MAX_HISTORY_ROWS) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(ConversionHistoryRecord).order_by(ConversionHistoryRecord.created_at.desc()).limit(limit),
    ).all()
    return [r.to_dict() for r in rows]


def get_entry(session: Session, eid: str) -> Optional[dict[str, Any]]:
    row = session.get(ConversionHistoryRecord, eid)
    return row.to_dict() if row else None


def delete_entry(session: Session, eid: str) -> bool:
    row = session.get(ConversionHistoryRecord, eid)
    if not row:
        return False
    session.delete(row)
    return True


def clear_all(session: Session) -> int:
    before = session.scalar(select(func.count()).select_from(ConversionHistoryRecord)) or 0
    session.execute(delete(ConversionHistoryRecord))
    return int(before)
