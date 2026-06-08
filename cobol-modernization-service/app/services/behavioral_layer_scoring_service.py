"""Layered diagnostic scoring for behavioral testing runs (Phase 1 — isolated service)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Tuple

_LOG = logging.getLogger(__name__)

# Fields exposed on RunDiagnostics API schema (exclude heavy nested blobs).
_RUN_DIAGNOSTICS_API_KEYS = (
    "target_type",
    "program_name",
    "run_id",
    "created_at",
    "behavioral_status",
    "execution_mode",
    "cobol_execution_status",
    "java_execution_status",
    "cobol_compile_status",
    "java_compile_status",
    "cobol_runtime_status",
    "java_runtime_status",
    "stdout_diff_percentage",
    "first_mismatch_line",
    "lines_compared",
    "lines_matched",
    "lines_diverged",
    "failure_reason",
    "affected_paragraphs",
    "retry_scope",
    "infrastructure_blocker",
    "testing_blocker_category",
    "layers_applicable",
)

# Suggested weights (percent); renormalized when a layer is not applicable.
WEIGHT_COMPILE_HEALTH = 30
WEIGHT_RUNTIME_HEALTH = 30
WEIGHT_BEHAVIORAL_PARITY = 25
WEIGHT_RETRY_STABILITY = 10
WEIGHT_ATTRIBUTION_CONFIDENCE = 5

LAYER_COMPILE = "compile_health"
LAYER_RUNTIME = "runtime_health"
LAYER_PARITY = "behavioral_parity"
LAYER_RETRY = "retry_stability"
LAYER_ATTRIBUTION = "attribution_confidence"

_LAYER_WEIGHTS: Dict[str, int] = {
    LAYER_COMPILE: WEIGHT_COMPILE_HEALTH,
    LAYER_RUNTIME: WEIGHT_RUNTIME_HEALTH,
    LAYER_PARITY: WEIGHT_BEHAVIORAL_PARITY,
    LAYER_RETRY: WEIGHT_RETRY_STABILITY,
    LAYER_ATTRIBUTION: WEIGHT_ATTRIBUTION_CONFIDENCE,
}

_INFRA_BLOCKER_PATTERNS = re.compile(
    r"copybook|copy\s+book|unresolved\s+copy|symbol[\s_-]?repair|"
    r"expansion\s+incomplete|gmp\.h|toolchain|not\s+expanded\s+before\s+compile|"
    r"cobc\s+unavailable|javac\s+unavailable|sanitizer",
    re.IGNORECASE,
)

_COMPILE_FAILURE_STATUSES = frozenset({"compile_failure"})
_RUNTIME_FAILURE_STATUSES = frozenset({"runtime_failure", "timeout"})
_SUCCESS_RUNTIME_STATUSES = frozenset({"success", "no_stdout", "fallback"})


@dataclass
class LayerScoreResult:
    """Outcome of layered scoring for one behavioral run."""

    qscore: int
    layer_scores: Dict[str, Optional[int]]
    primary_failure_layer: Optional[str]
    run_diagnostics: Dict[str, Any]
    layers_applicable: Dict[str, bool] = field(default_factory=dict)


def score_behavioral_run(snapshot: Mapping[str, Any]) -> LayerScoreResult:
    """
    Compute layered diagnostic scores from a behavioral run snapshot.

    This service is intentionally isolated from the diff runner and API routes
    (Phase 1). Callers pass a dict with execution, diff, attribution, and metadata fields.
    """
    diagnostics = build_run_diagnostics(snapshot)
    infra_blocker = bool(diagnostics.get("infrastructure_blocker"))
    cobol_status = str(diagnostics.get("cobol_execution_status") or "")
    java_status = str(diagnostics.get("java_execution_status") or "")

    compile_score, compile_ok = _score_compile_health(
        cobol_status=cobol_status,
        java_status=java_status,
        infrastructure_blocker=infra_blocker,
        behavioral_status=str(diagnostics.get("behavioral_status") or ""),
    )
    runtime_score, runtime_ok = _score_runtime_health(
        cobol_status=cobol_status,
        java_status=java_status,
        behavioral_status=str(diagnostics.get("behavioral_status") or ""),
        execution_mode=str(diagnostics.get("execution_mode") or ""),
        lines_compared=int(diagnostics.get("lines_compared") or 0),
    )
    parity_applicable = compile_ok and runtime_ok and not infra_blocker
    parity_score: Optional[int] = None
    if parity_applicable:
        parity_score = _score_behavioral_parity(
            diff_summary=diagnostics.get("diff_summary") or {},
            behavioral_status=str(diagnostics.get("behavioral_status") or ""),
            failed_tests=diagnostics.get("failed_tests") or [],
        )

    retry_score = _score_retry_stability(
        behavioral_status=str(diagnostics.get("behavioral_status") or ""),
        failed_tests=diagnostics.get("failed_tests") or [],
        retry_scope=str(diagnostics.get("retry_scope") or ""),
    )
    attribution_score = _score_attribution_confidence(
        failure_mapping=diagnostics.get("failure_mapping"),
        affected_paragraphs=diagnostics.get("affected_paragraphs") or [],
        retry_scope=str(diagnostics.get("retry_scope") or ""),
        failure_reason=diagnostics.get("failure_reason"),
        behavioral_status=str(diagnostics.get("behavioral_status") or ""),
    )

    layer_scores: Dict[str, Optional[int]] = {
        LAYER_COMPILE: compile_score,
        LAYER_RUNTIME: runtime_score,
        LAYER_PARITY: parity_score,
        LAYER_RETRY: retry_score,
        LAYER_ATTRIBUTION: attribution_score,
    }
    layers_applicable = {
        LAYER_COMPILE: True,
        LAYER_RUNTIME: True,
        LAYER_PARITY: parity_applicable,
        LAYER_RETRY: True,
        LAYER_ATTRIBUTION: True,
    }

    qscore = _weighted_qscore(layer_scores, layers_applicable)
    primary = _primary_failure_layer(
        layer_scores=layer_scores,
        layers_applicable=layers_applicable,
        infrastructure_blocker=infra_blocker,
        cobol_status=cobol_status,
        java_status=java_status,
    )

    diagnostics["layers_applicable"] = layers_applicable
    diagnostics["qscore_weights"] = dict(_LAYER_WEIGHTS)

    return LayerScoreResult(
        qscore=qscore,
        layer_scores=layer_scores,
        primary_failure_layer=primary,
        run_diagnostics=diagnostics,
        layers_applicable=layers_applicable,
    )


def _execution_details_for_scoring(snapshot: Mapping[str, Any]) -> List[Any]:
    """Return execution_details, aggregating from project file_results when the top level is empty."""
    raw = snapshot.get("execution_details")
    if isinstance(raw, list) and raw:
        return raw
    if str(snapshot.get("target_type") or "").lower() != "project":
        return []
    file_results = snapshot.get("file_results")
    if not isinstance(file_results, list):
        return []
    merged: List[Any] = []
    for row in file_results:
        if not isinstance(row, dict):
            continue
        details = row.get("execution_details")
        if isinstance(details, list):
            merged.extend(details)
    return merged


def _infer_missing_stage_statuses(
    cobol_status: str,
    java_status: str,
    *,
    behavioral_status: str,
    lines_compared: int,
    execution_mode: str,
) -> Tuple[str, str]:
    """When a live run passed but capture metadata was sparse, assume compile+run succeeded."""
    if behavioral_status not in ("passed", "partial") or lines_compared <= 0:
        return cobol_status, java_status
    if execution_mode in ("unavailable", ""):
        return cobol_status, java_status
    cobol = cobol_status
    java = java_status
    if not cobol:
        cobol = "success"
    if not java:
        java = "success"
    return cobol, java


def build_run_diagnostics(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize a behavioral run snapshot into flat diagnostic fields."""
    diff_summary = dict(snapshot.get("diff_summary") or {})
    execution_details = _execution_details_for_scoring(snapshot)
    failure_mapping = snapshot.get("failure_mapping")
    if failure_mapping is not None and not isinstance(failure_mapping, dict):
        failure_mapping = None

    behavioral_status = str(snapshot.get("status") or snapshot.get("behavioral_status") or "")
    execution_mode = str(snapshot.get("execution_mode") or "")
    lines_compared = int(diff_summary.get("lines_compared") or 0)

    cobol_status, java_status = _aggregate_execution_statuses(execution_details)
    cobol_status, java_status = _infer_missing_stage_statuses(
        cobol_status,
        java_status,
        behavioral_status=behavioral_status,
        lines_compared=lines_compared,
        execution_mode=execution_mode,
    )
    failure_reason = snapshot.get("failure_reason")
    failure_text = str(failure_reason or "")
    infrastructure_blocker = _is_infrastructure_blocker(failure_text, execution_details)

    return {
        "target_type": str(snapshot.get("target_type") or "single_file"),
        "program_name": str(snapshot.get("program_name") or ""),
        "run_id": str(snapshot.get("run_id") or ""),
        "created_at": str(snapshot.get("created_at") or ""),
        "behavioral_status": behavioral_status,
        "execution_mode": execution_mode,
        "cobol_execution_status": cobol_status,
        "java_execution_status": java_status,
        "cobol_compile_status": _compile_label(cobol_status),
        "java_compile_status": _compile_label(java_status),
        "cobol_runtime_status": _runtime_label(cobol_status),
        "java_runtime_status": _runtime_label(java_status),
        "stdout_diff_percentage": diff_summary.get("diff_percentage"),
        "first_mismatch_line": diff_summary.get("first_mismatch_index"),
        "lines_compared": lines_compared,
        "lines_matched": int(diff_summary.get("lines_matched") or diff_summary.get("matching_lines") or 0),
        "lines_diverged": int(
            diff_summary.get("lines_diverged") or diff_summary.get("differing_lines") or 0
        ),
        "failure_reason": failure_reason,
        "affected_paragraphs": list(snapshot.get("affected_paragraphs") or []),
        "retry_scope": str(snapshot.get("retry_scope") or ""),
        "failed_tests": list(snapshot.get("failed_tests") or []),
        "failure_mapping": failure_mapping,
        "diff_summary": diff_summary,
        "execution_details": execution_details,
        "infrastructure_blocker": infrastructure_blocker,
        "testing_blocker_category": _classify_testing_blocker(
            behavioral_status=str(snapshot.get("status") or snapshot.get("behavioral_status") or ""),
            failure_text=failure_text,
            cobol_status=cobol_status,
            java_status=java_status,
            infrastructure_blocker=infrastructure_blocker,
            lines_compared=int(diff_summary.get("lines_compared") or 0),
            execution_mode=str(snapshot.get("execution_mode") or ""),
        ),
    }


def layer_scores_to_dict(result: LayerScoreResult) -> Dict[str, Any]:
    """Serialize a LayerScoreResult for API payloads (Phase 2+)."""
    return {
        "qscore": result.qscore,
        "layer_scores": result.layer_scores,
        "primary_failure_layer": result.primary_failure_layer,
        "run_diagnostics": result.run_diagnostics,
        "layers_applicable": result.layers_applicable,
    }


def layer_scores_for_api(layer_scores: Mapping[str, Optional[int]]) -> Dict[str, Optional[int]]:
    """Shape layer scores for LayerScores schema (fixed field names)."""
    return {
        LAYER_COMPILE: layer_scores.get(LAYER_COMPILE),
        LAYER_RUNTIME: layer_scores.get(LAYER_RUNTIME),
        LAYER_PARITY: layer_scores.get(LAYER_PARITY),
        LAYER_RETRY: layer_scores.get(LAYER_RETRY),
        LAYER_ATTRIBUTION: layer_scores.get(LAYER_ATTRIBUTION),
    }


def run_diagnostics_for_api(diagnostics: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a flat diagnostics dict suitable for RunDiagnostics (no nested run blobs)."""
    out: Dict[str, Any] = {}
    for key in _RUN_DIAGNOSTICS_API_KEYS:
        if key in diagnostics:
            out[key] = diagnostics[key]
    return out


def attach_layered_scoring_to_result(result: MutableMapping[str, Any]) -> None:
    """
    Populate qscore, layer_scores, primary_failure_layer, and run_diagnostics on a diff result.

    Mutates ``result`` in place. On failure, sets the new fields to None without raising.
    """
    program = str(result.get("program_name") or "unknown")
    try:
        scored = score_behavioral_run(result)
        result["qscore"] = scored.qscore
        result["layer_scores"] = layer_scores_for_api(scored.layer_scores)
        result["primary_failure_layer"] = scored.primary_failure_layer
        result["run_diagnostics"] = run_diagnostics_for_api(scored.run_diagnostics)
    except Exception:
        _LOG.exception("layered scoring failed for program=%s", program)
        result["qscore"] = None
        result["layer_scores"] = None
        result["primary_failure_layer"] = None
        result["run_diagnostics"] = None


def _aggregate_execution_statuses(
    execution_details: Any,
) -> Tuple[str, str]:
    """Worst status per language across scenarios (compile_failure > runtime > success)."""
    cobol_worst = ""
    java_worst = ""
    if not isinstance(execution_details, list):
        return cobol_worst, java_worst
    for entry in execution_details:
        if not isinstance(entry, dict):
            continue
        cobol_worst = _worse_status(cobol_worst, _status_from_cap(entry.get("cobol_execution")))
        java_worst = _worse_status(java_worst, _status_from_cap(entry.get("java_execution")))
    return cobol_worst, java_worst


def _status_from_cap(cap: Any) -> str:
    if not isinstance(cap, dict):
        return ""
    explicit = str(cap.get("execution_status") or "").strip()
    if explicit:
        return explicit
    mode = str(cap.get("mode") or "").strip()
    if mode == "fallback":
        return "fallback"
    if mode == "skipped":
        return "skipped"
    if mode == "executed":
        exit_code = cap.get("exit_code")
        if exit_code not in (None, 0):
            return "runtime_failure"
        if not str(cap.get("stdout") or "").strip():
            return "no_stdout"
        return "success"
    return mode


def _worse_status(current: str, new: str) -> str:
    order = {
        "": 0,
        "skipped": 1,
        "fallback": 2,
        "no_stdout": 3,
        "success": 4,
        "runtime_failure": 5,
        "timeout": 6,
        "compile_failure": 7,
    }
    if order.get(new, 0) > order.get(current, 0):
        return new
    return current


def _is_infrastructure_blocker(failure_reason: str, execution_details: Any) -> bool:
    if failure_reason and _INFRA_BLOCKER_PATTERNS.search(failure_reason):
        return True
    if not isinstance(execution_details, list):
        return False
    for entry in execution_details:
        if not isinstance(entry, dict):
            continue
        for side in ("cobol_execution", "java_execution"):
            cap = entry.get(side)
            if not isinstance(cap, dict):
                continue
            blob = " ".join(
                str(cap.get(k) or "")
                for k in ("error", "compile_stderr", "stderr")
            )
            if _INFRA_BLOCKER_PATTERNS.search(blob):
                return True
            if "copybook" in str(cap.get("error") or "").lower():
                return True
    return False


def _compile_label(status: str) -> str:
    if status in _COMPILE_FAILURE_STATUSES:
        return "failed"
    if status == "skipped":
        return "skipped"
    if status in _SUCCESS_RUNTIME_STATUSES or status == "executed":
        return "ok"
    if not status:
        return "unknown"
    return "ok"


def _runtime_label(status: str) -> str:
    if status in _COMPILE_FAILURE_STATUSES:
        return "blocked"
    if status in _RUNTIME_FAILURE_STATUSES:
        return "failed"
    if status in _SUCCESS_RUNTIME_STATUSES or status == "executed":
        return "ok"
    if status == "skipped":
        return "skipped"
    if not status:
        return "unknown"
    return "unknown"


def _score_compile_health(
    *,
    cobol_status: str,
    java_status: str,
    infrastructure_blocker: bool,
    behavioral_status: str,
) -> Tuple[int, bool]:
    if behavioral_status == "not_run" and not cobol_status and not java_status:
        return 0, False
    if infrastructure_blocker:
        return 5, False
    if cobol_status in _COMPILE_FAILURE_STATUSES or java_status in _COMPILE_FAILURE_STATUSES:
        return 0, False
    if cobol_status in ("skipped", "") and java_status in ("skipped", ""):
        return 50, False
    return 100, True


def _classify_testing_blocker(
    *,
    behavioral_status: str,
    failure_text: str,
    cobol_status: str,
    java_status: str,
    infrastructure_blocker: bool,
    lines_compared: int,
    execution_mode: str,
) -> str:
    """
    Classify the dominant blocker for operators (does not affect qscore weights).

    Categories: toolchain | conversion_runtime | testing_layer | behavioral_drift | none
    """
    status = behavioral_status.lower()
    text = failure_text.lower()

    if infrastructure_blocker or any(
        token in text
        for token in (
            "toolchain",
            "cobc not available",
            "javac not available",
            "java runtime unavailable",
            "copy book",
            "copybook",
            "not expanded before compile",
        )
    ):
        return "toolchain"
    if status == "not_run" and execution_mode == "unavailable":
        if cobol_status in _COMPILE_FAILURE_STATUSES or java_status in _COMPILE_FAILURE_STATUSES:
            return "conversion_runtime"
        if "no cobol/java sources" in text or "snapshot fallback was requested" in text:
            return "testing_layer"
        return "toolchain"
    if cobol_status in _COMPILE_FAILURE_STATUSES or java_status in _COMPILE_FAILURE_STATUSES:
        return "conversion_runtime"
    if cobol_status in _RUNTIME_FAILURE_STATUSES or java_status in _RUNTIME_FAILURE_STATUSES:
        return "conversion_runtime"
    if status in ("failed", "partial") and lines_compared > 0:
        return "behavioral_drift"
    if status == "not_run":
        return "testing_layer"
    return "none"


def _score_runtime_health(
    *,
    cobol_status: str,
    java_status: str,
    behavioral_status: str,
    execution_mode: str,
    lines_compared: int = 0,
) -> Tuple[int, bool]:
    if behavioral_status == "not_run":
        return 0, False
    if cobol_status in _COMPILE_FAILURE_STATUSES or java_status in _COMPILE_FAILURE_STATUSES:
        return 0, False
    if cobol_status in _RUNTIME_FAILURE_STATUSES or java_status in _RUNTIME_FAILURE_STATUSES:
        return 0, False

    behavioral_ok = behavioral_status in ("passed", "partial")
    if behavioral_ok and lines_compared > 0:
        if cobol_status in _SUCCESS_RUNTIME_STATUSES and java_status in _SUCCESS_RUNTIME_STATUSES:
            return 100, True
        if behavioral_status == "passed" and (
            cobol_status in _SUCCESS_RUNTIME_STATUSES or java_status in _SUCCESS_RUNTIME_STATUSES
        ):
            other = java_status if cobol_status in _SUCCESS_RUNTIME_STATUSES else cobol_status
            if other in ("skipped", "", "no_stdout", "fallback"):
                return 100, True

    if execution_mode == "unavailable":
        if behavioral_ok and lines_compared > 0:
            return 100, True
        return 10, False
    if cobol_status in _SUCCESS_RUNTIME_STATUSES and java_status in _SUCCESS_RUNTIME_STATUSES:
        return 100, True
    return 40, False


def _score_behavioral_parity(
    *,
    diff_summary: Mapping[str, Any],
    behavioral_status: str,
    failed_tests: List[Any],
) -> int:
    compared = int(diff_summary.get("lines_compared") or 0)
    if compared <= 0:
        return 0 if behavioral_status in ("failed", "partial") else 30

    matched = int(diff_summary.get("lines_matched") or diff_summary.get("matching_lines") or 0)
    if compared > 0 and matched == compared and not failed_tests:
        return 100

    diff_pct = diff_summary.get("diff_percentage")
    if diff_pct is None:
        diverged = int(diff_summary.get("lines_diverged") or diff_summary.get("differing_lines") or 0)
        if diverged == 0:
            return 95
        ratio = max(0.0, 1.0 - (diverged / compared))
        return _clamp_int(ratio * 100)

    try:
        pct = float(diff_pct)
    except (TypeError, ValueError):
        pct = 100.0
    return _clamp_int(max(0.0, 100.0 - pct))


def _score_retry_stability(
    *,
    behavioral_status: str,
    failed_tests: List[Any],
    retry_scope: str,
) -> int:
    status = behavioral_status.lower()
    failed_count = len(failed_tests or [])
    if status == "passed" and failed_count == 0:
        return 100
    if status == "partial":
        base = 55
    elif status == "failed":
        base = 25
    elif status == "not_run":
        return 0
    else:
        base = 40

    scope = (retry_scope or "").strip()
    if not scope:
        return max(0, base - 15)
    if ":" in scope and any(ch.isdigit() for ch in scope.split(":", 1)[0]):
        return max(0, base - 5)
    return base


def _score_attribution_confidence(
    *,
    failure_mapping: Optional[Mapping[str, Any]],
    affected_paragraphs: List[Any],
    retry_scope: str,
    failure_reason: Optional[str],
    behavioral_status: str,
) -> int:
    if behavioral_status == "passed" and not failure_reason:
        return 100

    score = 20
    paragraphs = [str(p) for p in affected_paragraphs if p]
    if paragraphs:
        score += 35
    scope = (retry_scope or "").strip()
    if scope:
        score += 20

    if isinstance(failure_mapping, dict):
        primary = str(failure_mapping.get("primary_retry_scope") or failure_mapping.get("retry_scope") or "")
        if primary:
            score += 15
        method = str(failure_mapping.get("attribution_method") or "")
        if method and method not in ("none", "unknown"):
            score += 15
        highlights = failure_mapping.get("highlights") or []
        if isinstance(highlights, list):
            attributed = sum(
                1
                for h in highlights
                if isinstance(h, dict)
                and str(h.get("likely_paragraph") or h.get("attribution_method") or "") not in ("", "none")
            )
            if attributed > 0:
                score += min(10, attributed * 3)

    if not paragraphs and not scope and not failure_mapping:
        return 10

    return _clamp_int(score)


def _weighted_qscore(
    layer_scores: Dict[str, Optional[int]],
    layers_applicable: Dict[str, bool],
) -> int:
    total_weight = 0
    weighted_sum = 0.0
    for layer, weight in _LAYER_WEIGHTS.items():
        if not layers_applicable.get(layer, True):
            continue
        raw = layer_scores.get(layer)
        if raw is None:
            continue
        total_weight += weight
        weighted_sum += weight * raw
    if total_weight <= 0:
        return 0
    return _clamp_int(weighted_sum / total_weight)


def _primary_failure_layer(
    *,
    layer_scores: Dict[str, Optional[int]],
    layers_applicable: Dict[str, bool],
    infrastructure_blocker: bool,
    cobol_status: str,
    java_status: str,
) -> Optional[str]:
    if infrastructure_blocker or cobol_status in _COMPILE_FAILURE_STATUSES or java_status in _COMPILE_FAILURE_STATUSES:
        return LAYER_COMPILE
    if cobol_status in _RUNTIME_FAILURE_STATUSES or java_status in _RUNTIME_FAILURE_STATUSES:
        return LAYER_RUNTIME

    candidates: List[Tuple[str, int]] = []
    for layer in (LAYER_COMPILE, LAYER_RUNTIME, LAYER_PARITY, LAYER_RETRY, LAYER_ATTRIBUTION):
        if not layers_applicable.get(layer, True):
            continue
        raw = layer_scores.get(layer)
        if raw is None:
            continue
        candidates.append((layer, raw))

    if not candidates:
        return None

    # Lowest score among applicable layers; parity wins ties when diff failed.
    candidates.sort(key=lambda item: (item[1], 0 if item[0] == LAYER_PARITY else 1))
    lowest = candidates[0][1]
    tied = [name for name, score in candidates if score == lowest]
    priority = [LAYER_COMPILE, LAYER_RUNTIME, LAYER_PARITY, LAYER_RETRY, LAYER_ATTRIBUTION]
    for layer in priority:
        if layer in tied:
            return layer
    return tied[0]


def _clamp_int(value: float, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(round(value))))
