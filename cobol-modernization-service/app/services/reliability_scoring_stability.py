"""Canonical inputs and drift detection for stable reliability scoring."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

# In-process canonical scores keyed by stable behavioral fingerprint (per process).
_CANONICAL_SCORE_CACHE: Dict[str, Tuple[int, Dict[str, int]]] = {}
_CANONICAL_CACHE_MAX = 256


def _stable_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _stable_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def canonical_diff_summary(diff_summary: Dict[str, Any]) -> Dict[str, int]:
    """Normalize diff counters so equivalent stdout comparisons share one view."""
    compared = _stable_int(diff_summary.get("lines_compared"))
    matched = _stable_int(diff_summary.get("lines_matched"))
    diverged = _stable_int(
        diff_summary.get("lines_diverged") or diff_summary.get("differing_lines")
    )
    if compared > 0 and diverged == 0 and matched <= 0:
        matched = compared
    if compared > 0 and matched > compared:
        matched = compared
    diff_pct = _stable_float(diff_summary.get("diff_percentage"))
    if compared > 0 and matched >= compared:
        diff_pct = 0
    return {
        "lines_compared": compared,
        "lines_matched": matched,
        "lines_diverged": diverged,
        "diff_percentage_milli": int(round(diff_pct * 1000)),
    }


def canonical_test_bucket(result: Optional[Dict[str, Any]], artifacts_ready: bool) -> Dict[str, Any]:
    """Stable generated-test signal: artifact readiness OR sorted test count tier."""
    count = 0
    if result and isinstance(result, dict):
        count = max(0, _stable_int(result.get("test_count")))
    return {
        "artifacts_ready": bool(artifacts_ready),
        "test_count": count,
        "tier": "ready" if artifacts_ready else ("run" if count > 0 else "none"),
    }


def is_perfect_behavioral_pass(
    behavioral_status: str,
    failed_tests: List[Dict[str, Any]],
    diff_summary: Dict[str, Any],
) -> bool:
    status = str(behavioral_status or "").lower()
    if status != "passed" or len(failed_tests or []) > 0:
        return False
    canon = canonical_diff_summary(diff_summary)
    compared = canon["lines_compared"]
    if compared <= 0:
        return False
    return canon["lines_matched"] >= compared and canon["lines_diverged"] == 0


def canonical_conversion_points(conversion_score: Any) -> Optional[int]:
    """Map structural conversion score to reliability points (deterministic)."""
    if conversion_score is None:
        return None
    total: Optional[int] = None
    if isinstance(conversion_score, dict):
        for key in ("total_score", "total", "score"):
            if conversion_score.get(key) is not None:
                try:
                    total = int(conversion_score[key])
                    break
                except (TypeError, ValueError):
                    pass
    else:
        try:
            total = int(conversion_score)
        except (TypeError, ValueError):
            return None
    if total is None:
        return None
    return max(0, min(10, total // 10))


def build_reliability_fingerprint(payload: Dict[str, Any]) -> str:
    """
    Hash stable validation facts (not timestamps, ordering noise, or advisory scope).
    """
    diff = canonical_diff_summary(dict(payload.get("diff_summary") or {}))
    failed = payload.get("failed_tests") or []
    failed_ids = sorted(
        {
            str(
                ft.get("id")
                or ft.get("scenario_id")
                or ft.get("description")
                or ""
            ).strip()
            for ft in failed
            if isinstance(ft, dict)
        }
    )
    artifacts = payload.get("validation_artifacts") or {}
    br_ready = bool(
        payload.get("business_rules_artifacts_ready")
        or artifacts.get("business_rules_ready")
    )
    ec_ready = bool(
        payload.get("edge_cases_artifacts_ready") or artifacts.get("edge_cases_ready")
    )
    unit_ready = bool(
        payload.get("unit_tests_artifacts_ready") or artifacts.get("unit_tests_ready")
    )
    body = {
        "program_name": str(payload.get("program_name") or "").upper(),
        "behavioral_status": str(payload.get("behavioral_status") or "").lower(),
        "diff": diff,
        "failed_ids": failed_ids,
        "business_rules": canonical_test_bucket(
            payload.get("business_rules_test_result"), br_ready
        ),
        "edge_cases": canonical_test_bucket(payload.get("edge_case_test_result"), ec_ready),
        "unit_tests": canonical_test_bucket(payload.get("unit_test_result"), unit_ready),
        "conversion_points": canonical_conversion_points(payload.get("conversion_score")),
    }
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def register_canonical_score(
    fingerprint: str,
    score: int,
    breakdown: Dict[str, int],
) -> None:
    if not fingerprint:
        return
    if len(_CANONICAL_SCORE_CACHE) >= _CANONICAL_CACHE_MAX:
        _CANONICAL_SCORE_CACHE.pop(next(iter(_CANONICAL_SCORE_CACHE)))
    _CANONICAL_SCORE_CACHE[fingerprint] = (score, dict(breakdown))


def detect_score_drift(
    fingerprint: str,
    score: int,
    breakdown: Dict[str, int],
) -> Optional[Dict[str, Any]]:
    """
    If the same canonical fingerprint was scored before with a different total, report drift.
    """
    if not fingerprint:
        return None
    prev = _CANONICAL_SCORE_CACHE.get(fingerprint)
    if prev is None:
        register_canonical_score(fingerprint, score, breakdown)
        return None
    prev_score, prev_breakdown = prev
    if prev_score == score:
        return None
    differing = sorted(
        k
        for k in set(prev_breakdown) | set(breakdown)
        if prev_breakdown.get(k) != breakdown.get(k)
    )
    return {
        "fingerprint": fingerprint,
        "canonical_reference_score": prev_score,
        "current_score": score,
        "score_delta": score - prev_score,
        "differing_buckets": differing,
        "canonical_breakdown": prev_breakdown,
        "current_breakdown": breakdown,
        "message": (
            f"Reliability score drifted from {prev_score} to {score} for identical "
            f"behavioral inputs (buckets: {', '.join(differing) or 'unknown'})."
        ),
    }


def normalize_program_name(name: str) -> str:
    return re.sub(r"[^\w]+", "", (name or "").upper())
