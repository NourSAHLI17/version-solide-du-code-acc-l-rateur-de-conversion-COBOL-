"""Render repair history into display-ready structures for UI consumption.

Produces structured data with status badges, categorized auto-repairs,
and prominently flagged manual-review TODO items.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


STATUS_BADGES = {
    "converted": {"label": "Converted", "color": "blue", "icon": "code"},
    "compiled": {"label": "Compiled", "color": "green", "icon": "check"},
    "repaired": {"label": "Repaired", "color": "yellow", "icon": "wrench"},
    "verified": {"label": "Verified", "color": "emerald", "icon": "shield-check"},
    "baseline_matched": {"label": "Baseline Matched", "color": "teal", "icon": "scale"},
    "partial": {"label": "Partial", "color": "orange", "icon": "alert-triangle"},
    "failed": {"label": "Failed", "color": "red", "icon": "x-circle"},
}


def derive_conversion_status(
    *,
    converted: bool = False,
    compiled: bool = False,
    repaired: bool = False,
    verified: bool = False,
    baseline_matched: bool = False,
    has_manual_todos: bool = False,
) -> str:
    if baseline_matched:
        return "baseline_matched"
    if verified:
        return "verified"
    if has_manual_todos and compiled:
        return "repaired"
    if compiled:
        return "compiled"
    if converted:
        return "converted"
    return "failed"


def render_status_badge(status: str) -> Dict[str, str]:
    badge = STATUS_BADGES.get(status, STATUS_BADGES["failed"])
    return dict(badge)


def categorize_repairs(auto_repairs: Sequence[str]) -> Dict[str, List[str]]:
    """Group auto-repairs by category for compact display."""
    categories: Dict[str, List[str]] = {
        "imports": [],
        "naming": [],
        "syntax": [],
        "structure": [],
        "other": [],
    }
    for repair in auto_repairs:
        lower = repair.lower()
        if "import" in lower or "annotation" in lower or "spring" in lower:
            categories["imports"].append(repair)
        elif "renamed" in lower or "name" in lower:
            categories["naming"].append(repair)
        elif "semicolon" in lower or "brace" in lower or "comment" in lower:
            categories["syntax"].append(repair)
        elif "closing" in lower or "class" in lower or "visibility" in lower:
            categories["structure"].append(repair)
        else:
            categories["other"].append(repair)
    return {k: v for k, v in categories.items() if v}


def render_repair_history(
    repair_summary: Dict[str, Any],
    *,
    converted: bool = True,
    compiled: bool = False,
    verified: bool = False,
    baseline_matched: bool = False,
) -> Dict[str, Any]:
    """Build a display-ready repair history payload.

    Parameters
    ----------
    repair_summary
        Output of ``format_repair_notes_for_ui`` with keys
        ``auto_repairs`` and ``manual_review``.
    converted, compiled, verified, baseline_matched
        Pipeline stage flags.

    Returns
    -------
    dict
        ``status``, ``status_badge``, ``auto_repairs_categorized``,
        ``auto_repair_count``, ``manual_review``, ``manual_review_count``,
        ``has_unresolved_todos``.
    """
    auto_repairs = list(repair_summary.get("auto_repairs") or [])
    manual_review = list(repair_summary.get("manual_review") or [])
    has_todos = len(manual_review) > 0

    status = derive_conversion_status(
        converted=converted,
        compiled=compiled,
        repaired=compiled and len(auto_repairs) > 0,
        verified=verified,
        baseline_matched=baseline_matched,
        has_manual_todos=has_todos,
    )

    return {
        "status": status,
        "status_badge": render_status_badge(status),
        "auto_repairs_categorized": categorize_repairs(auto_repairs),
        "auto_repair_count": len(auto_repairs),
        "auto_repairs": auto_repairs,
        "manual_review": manual_review,
        "manual_review_count": len(manual_review),
        "has_unresolved_todos": has_todos,
    }
