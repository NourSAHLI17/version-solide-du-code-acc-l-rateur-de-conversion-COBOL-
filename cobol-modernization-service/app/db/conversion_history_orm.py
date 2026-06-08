"""ORM model for conversion run history."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConversionHistoryRecord(Base):
    """One saved conversion run (single file or project), full payload as JSON."""

    __tablename__ = "conversion_history"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entry_type: Mapped[str] = mapped_column(String(16), index=True)
    program_name: Mapped[str] = mapped_column(String(512), index=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    analysis_engine: Mapped[str | None] = mapped_column(String(64), nullable=True)
    complexity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    payload_json: Mapped[str] = mapped_column(Text)

    def to_dict(self) -> dict[str, Any]:
        """Return API shape (camelCase keys for frontend)."""

        return json.loads(self.payload_json)
