"""Trim and deduplicate analysis JSON before LLM conversion prompts."""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List

ANALYSIS_FIELDS_TO_STRIP = frozenset(
    {
        "all_business_rules",
        "risk_flags",
        "file_io_paragraphs",
        "loop_paragraphs",
        "paragraph_source_extraction",
        "analysis_engine",
        "analysis_revision",
        "assumptions",
    }
)


def deduplicate_rules(rules: List[str]) -> List[str]:
    """Collapse duplicate pattern rules and case-insensitive specific rules."""
    seen_patterns: set[str] = set()
    seen_specific: set[str] = set()
    result: List[str] = []

    for rule in rules:
        rule = str(rule).strip()
        if not rule:
            continue

        if rule.startswith("[pattern]"):
            key = re.sub(r"\d+", "N", rule)
            if key not in seen_patterns:
                seen_patterns.add(key)
                result.append(rule)
        else:
            key = rule.lower()
            if key not in seen_specific:
                seen_specific.add(key)
                result.append(rule)

    return result


def clean_analysis_for_prompt(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of analysis with noise fields removed for LLM prompts."""
    cleaned = {
        k: v
        for k, v in analysis.items()
        if k not in ANALYSIS_FIELDS_TO_STRIP
    }

    warnings = cleaned.get("warnings")
    if isinstance(warnings, list):
        cleaned["warnings"] = [
            str(w)
            for w in warnings
            if "line exceeds column" not in str(w).lower()
            and "exceeds column 72" not in str(w).lower()
        ]

    sections = cleaned.get("sections")
    if isinstance(sections, list):
        trimmed_sections: List[Dict[str, Any]] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            if section.get("is_dead_code"):
                continue
            sec_copy = dict(section)
            sec_rules = sec_copy.get("business_rules")
            if isinstance(sec_rules, list):
                sec_copy["business_rules"] = deduplicate_rules(
                    [str(r) for r in sec_rules],
                )
            trimmed_sections.append(sec_copy)
        cleaned["sections"] = trimmed_sections

    top_rules = cleaned.get("business_rules")
    if isinstance(top_rules, list):
        cleaned["business_rules"] = deduplicate_rules([str(r) for r in top_rules])

    return cleaned


def get_chunk_rules(
    chunk_sections: List[Dict[str, Any]],
    global_rules: List[str],
) -> List[str]:
    """
  For a conversion chunk, return section-specific rules plus capped global rules.
  """
    section_rules: List[str] = []
    for section in chunk_sections:
        if not isinstance(section, dict):
            continue
        for rule in section.get("business_rules") or []:
            section_rules.append(str(rule))

    global_specific = [
        str(r)
        for r in global_rules
        if not str(r).startswith("[pattern]")
    ][:15]

    return deduplicate_rules(section_rules + global_specific)


def prepare_analysis_for_conversion_prompt(
    analysis: Dict[str, Any],
    *,
    chunk_sections: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    Clean analysis and replace top-level business_rules with chunk-relevant rules.
    """
    cleaned = clean_analysis_for_prompt(analysis)
    sections = chunk_sections
    if sections is None:
        raw_sections = cleaned.get("sections") or []
        sections = [s for s in raw_sections if isinstance(s, dict)]
    global_rules = list(cleaned.get("business_rules") or [])
    cleaned["business_rules"] = get_chunk_rules(sections, global_rules)
    return cleaned
