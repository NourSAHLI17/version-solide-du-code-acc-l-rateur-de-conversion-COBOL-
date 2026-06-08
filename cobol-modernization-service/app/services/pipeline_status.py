"""Pipeline verification status model with deterministic stage tracking.

Each conversion progresses through ordered stages.  Status only advances
when the previous stage genuinely succeeded — ``Done`` requires all
verification to have passed.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class PipelineStage(str, enum.Enum):
    PARSED = "Parsed"
    ANALYZED = "Analyzed"
    CONVERTED = "Converted"
    COMPILED = "Compiled"
    REPAIRED = "Repaired"
    VERIFIED = "Verified"
    BASELINE_MATCHED = "BaselineMatched"
    DONE = "Done"


STAGE_ORDER: Dict[PipelineStage, int] = {s: i for i, s in enumerate(PipelineStage)}

_LEGACY_STATUS_MAP: Dict[str, PipelineStage] = {
    "partial": PipelineStage.CONVERTED,
    "complete": PipelineStage.COMPILED,
    "passed": PipelineStage.VERIFIED,
    "failed": PipelineStage.CONVERTED,
    "not_run": PipelineStage.PARSED,
}


@dataclass
class PipelineStatus:
    current_stage: PipelineStage = PipelineStage.PARSED
    stages_completed: List[PipelineStage] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def advance_to(self, stage: PipelineStage, *, note: str = "") -> bool:
        """Advance status if *stage* is reachable from current position.

        Returns ``True`` if the stage was reached, ``False`` if skipped
        (e.g. trying to set ``Done`` when not yet ``Verified``).
        """
        if STAGE_ORDER[stage] <= STAGE_ORDER[self.current_stage]:
            return False
        expected_prev = list(PipelineStage)[STAGE_ORDER[stage] - 1]
        if expected_prev != self.current_stage and self.current_stage != PipelineStage.PARSED:
            if expected_prev not in self.stages_completed:
                self.notes.append(
                    f"Cannot advance to {stage.value}: "
                    f"prerequisite {expected_prev.value} not completed"
                )
                return False
        self.current_stage = stage
        if stage not in self.stages_completed:
            self.stages_completed.append(stage)
        if note:
            self.notes.append(note)
        return True

    def mark_completed(self, stage: PipelineStage, *, note: str = "") -> None:
        """Mark a stage as completed (idempotent)."""
        if stage not in self.stages_completed:
            self.stages_completed.append(stage)
        if STAGE_ORDER.get(stage, -1) > STAGE_ORDER.get(self.current_stage, -1):
            self.current_stage = stage
        if note:
            self.notes.append(note)

    @property
    def is_done(self) -> bool:
        return self.current_stage == PipelineStage.DONE

    @property
    def is_verified(self) -> bool:
        return PipelineStage.VERIFIED in self.stages_completed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_stage": self.current_stage.value,
            "stages_completed": [s.value for s in self.stages_completed],
            "is_done": self.is_done,
            "is_verified": self.is_verified,
            "notes": list(self.notes),
        }

    @classmethod
    def from_legacy_status(cls, legacy: str) -> "PipelineStatus":
        """Map old-style ``conversion_status`` strings to the new model."""
        stage = _LEGACY_STATUS_MAP.get(legacy.lower(), PipelineStage.PARSED)
        ps = cls(current_stage=stage)
        for s in PipelineStage:
            if STAGE_ORDER[s] <= STAGE_ORDER[stage]:
                ps.stages_completed.append(s)
        return ps


def build_pipeline_status(
    *,
    parsed: bool = False,
    analyzed: bool = False,
    converted: bool = False,
    compiled: bool = False,
    repaired: bool = False,
    verified: bool = False,
    baseline_matched: bool = False,
) -> PipelineStatus:
    """Construct a status from boolean flags (deterministic)."""
    ps = PipelineStatus()
    stages = [
        (parsed, PipelineStage.PARSED),
        (analyzed, PipelineStage.ANALYZED),
        (converted, PipelineStage.CONVERTED),
        (compiled, PipelineStage.COMPILED),
        (repaired, PipelineStage.REPAIRED),
        (verified, PipelineStage.VERIFIED),
        (baseline_matched, PipelineStage.BASELINE_MATCHED),
    ]
    for flag, stage in stages:
        if flag:
            ps.mark_completed(stage)
        else:
            break

    if all(flag for flag, _ in stages):
        ps.mark_completed(PipelineStage.DONE)

    return ps
