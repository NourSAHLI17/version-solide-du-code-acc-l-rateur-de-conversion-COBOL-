"""F52 — Lenient parse and validate LLM analysis JSON."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import ValidationError

from app.models.analysis import AnalysisOutput, BusinessRule, Section

_LOG = logging.getLogger(__name__)

_SERVICE_ROOT = Path(__file__).resolve().parents[2]
_DEBUG_DIR = _SERVICE_ROOT / "out" / "analyzer_debug"

VALID_FALLBACK_REASONS = {
    "no_chunks": "Segmenter produced no usable chunks",
    "llm_timeout": "LLM call timed out",
    "llm_transport_error": "LLM transport failed",
    "schema_validation_failed": "LLM output failed schema validation",
    "invalid_json": "LLM produced invalid JSON",
    "intentional_skip": "ANALYSIS_ENGINE=deterministic set explicitly",
    "llm_not_configured": "LLM provider not configured",
    "llm_unreachable_or_unusable_response": "LLM returned no usable analysis",
    "all_chunks_rejected": "All analysis chunks rejected",
    "empty_cobol_excerpt": "Chunk had empty COBOL excerpt",
}


class AnalysisFallback(Exception):
    """Raised when LLM analysis cannot be validated and caller should fall back."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Analysis fallback: {reason}")


def save_debug(path: Union[str, Path], content: Union[str, dict]) -> None:
    """Write analyzer debug artifacts under out/analyzer_debug/."""
    target = Path(path)
    if not target.is_absolute():
        target = _DEBUG_DIR / target.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, dict):
        target.write_text(json.dumps(content, indent=2, default=str), encoding="utf-8")
    else:
        target.write_text(str(content), encoding="utf-8")


def lenient_repair(llm_output: dict, *, program_name: str = "") -> dict:
    """Auto-fix common LLM mistakes before schema validation."""
    data = dict(llm_output)

    if not data.get("program_name") and program_name:
        data["program_name"] = program_name

    if isinstance(data.get("sections"), dict):
        data["sections"] = [data["sections"]]

    if "paragraph_analyses" in data and not data.get("sections"):
        pa = data["paragraph_analyses"]
        data["sections"] = [pa] if isinstance(pa, dict) else pa

    if "complexity" in data and isinstance(data["complexity"], str):
        data["complexity"] = data["complexity"].lower()

    rules = data.get("business_rules") or []
    if isinstance(rules, list):
        repaired_rules: List[Any] = []
        for rule in rules:
            if isinstance(rule, str):
                repaired_rules.append({"description": rule})
                continue
            if isinstance(rule, dict):
                r = dict(rule)
                if "rule" in r and "description" not in r:
                    r["description"] = r.pop("rule")
                if "rule_description" in r and "description" not in r:
                    r["description"] = r.pop("rule_description")
                if not r.get("description"):
                    r["description"] = str(r.get("text") or r.get("name") or "unspecified rule")
                repaired_rules.append(r)
                continue
            repaired_rules.append(rule)
        data["business_rules"] = repaired_rules

    if isinstance(data.get("complexity_drivers"), str):
        data["complexity_drivers"] = [data["complexity_drivers"]]

    sections = data.get("sections")
    if isinstance(sections, list):
        fixed_sections: List[dict] = []
        for sec in sections:
            if isinstance(sec, str):
                fixed_sections.append({"name": sec, "role": ""})
                continue
            if isinstance(sec, dict):
                s = dict(sec)
                if "paragraph_name" in s and "name" not in s:
                    s["name"] = s.pop("paragraph_name")
                if "purpose" in s and "role" not in s:
                    s["role"] = s["purpose"]
                br = s.get("business_rules") or []
                if isinstance(br, list):
                    s["business_rules"] = [
                        {"description": x} if isinstance(x, str) else x for x in br
                    ]
                fixed_sections.append(s)
        data["sections"] = fixed_sections

    return data


def analysis_output_to_dict(output: AnalysisOutput) -> Dict[str, Any]:
    """Serialize validated output for downstream aggregation."""
    return output.model_dump(mode="python")


def section_to_paragraph_dict(section: Section) -> Dict[str, Any]:
    """Convert a Section model to analysis_agent paragraph overlay shape."""
    d = section.model_dump(mode="python")
    extra = getattr(section, "__pydantic_extra__", None) or {}
    if isinstance(extra, dict):
        d.update(extra)
    if not d.get("role") and d.get("purpose"):
        d["role"] = d["purpose"]
    br_out: List[Any] = []
    for item in d.get("business_rules") or []:
        if isinstance(item, BusinessRule):
            br_out.append(item.description or item.model_dump())
        elif isinstance(item, dict):
            br_out.append(item.get("description") or str(item))
        else:
            br_out.append(str(item))
    d["business_rules"] = br_out
    return d


def extract_sections_lenient(data: dict) -> List[Dict[str, Any]]:
    """Last-resort section extraction when full AnalysisOutput validation fails."""
    rows = data.get("sections") or data.get("paragraph_analyses") or []
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in rows:
        if isinstance(item, dict):
            try:
                sec = Section(**lenient_repair({"sections": [item], "program_name": data.get("program_name", "P")})["sections"][0])
                out.append(section_to_paragraph_dict(sec))
            except ValidationError:
                name = str(item.get("name") or item.get("paragraph_name") or "").strip()
                if name:
                    out.append(item)
    return out


def parse_llm_analysis(raw_output: str, program_name: str) -> AnalysisOutput:
    """Parse and validate full-program LLM analysis JSON."""
    try:
        data = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        _LOG.warning("[ANALYZER] LLM produced invalid JSON: %s", exc)
        save_debug(f"{program_name}_invalid_json.txt", raw_output)
        raise AnalysisFallback("invalid_json") from exc

    if not isinstance(data, dict):
        save_debug(f"{program_name}_invalid_json.txt", raw_output)
        raise AnalysisFallback("invalid_json")

    data = lenient_repair(data, program_name=program_name)

    try:
        return AnalysisOutput(**data)
    except ValidationError as exc:
        _LOG.warning("[ANALYZER] schema validation failed: %s", exc)
        save_debug(f"{program_name}_failed_validation.json", data)

        try:
            minimal = {
                "program_name": data.get("program_name", program_name),
                "complexity": str(data.get("complexity", "medium")).lower(),
                "sections": data.get("sections") or [],
                "global_purpose": data.get("global_purpose"),
            }
            return AnalysisOutput(**lenient_repair(minimal, program_name=program_name))
        except Exception as exc2:
            _LOG.warning("[ANALYZER] even minimal schema failed: %s", exc2)
            raise AnalysisFallback("schema_validation_failed") from exc2


def parse_llm_chunk_from_data(
    data: dict,
    program_name: str,
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str], Optional[str]]:
    """Validate already-parsed chunk JSON dict."""
    data = lenient_repair(data, program_name=program_name)
    gp_raw = data.get("global_purpose")
    gp: Optional[str] = gp_raw.strip() if isinstance(gp_raw, str) and gp_raw.strip() else None

    try:
        output = AnalysisOutput(**data)
    except ValidationError as exc:
        _LOG.warning("[ANALYZER] chunk schema validation failed: %s", exc)
        save_debug(f"{program_name}_failed_validation.json", data)
        sections = extract_sections_lenient(data)
        if sections:
            return sections, gp, None
        return None, gp, "schema_validation_failed"

    sections = [section_to_paragraph_dict(s) for s in output.sections]
    if not sections:
        sections = extract_sections_lenient(data)
    if not sections:
        return None, gp or output.global_purpose, "schema_validation_failed"
    return sections, gp or output.global_purpose, None


def parse_llm_chunk_response(
    raw_output: str,
    program_name: str,
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str], Optional[str]]:
    """
    Parse LLM chunk analysis JSON.

    Returns (section_rows, global_purpose, fallback_reason).
    fallback_reason is None on success.
    """
    cleaned = (raw_output or "").strip()
    if not cleaned:
        return None, None, "invalid_json"

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        _LOG.warning("[ANALYZER] LLM produced invalid JSON: %s", exc)
        save_debug(f"{program_name}_invalid_json.txt", raw_output)
        return None, None, "invalid_json"

    if not isinstance(data, dict):
        save_debug(f"{program_name}_invalid_json.txt", raw_output)
        return None, None, "invalid_json"

    return parse_llm_chunk_from_data(data, program_name)


def normalize_fallback_reason(reason: Optional[str]) -> Optional[str]:
    """Map internal failure tokens to VALID_FALLBACK_REASONS keys."""
    if not reason:
        return None
    key = reason.strip().lower()
    aliases = {
        "no_chunks_attempted": "no_chunks",
        "invalid_json": "invalid_json",
        "timeout": "llm_timeout",
        "rate_limit": "llm_transport_error",
        "transport_error": "llm_transport_error",
        "empty_response": "llm_transport_error",
        "llm_unreachable_or_unusable_response": "llm_unreachable_or_unusable_response",
    }
    if key in VALID_FALLBACK_REASONS:
        return key
    return aliases.get(key, reason)
