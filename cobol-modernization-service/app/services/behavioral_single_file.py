"""Single-file behavioral run preparation (copybook expansion + standalone Java)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.services.behavioral_copybook_prep import expand_cobol_copybooks_for_behavioral
from app.services.cobol_conversion_symbol_repair import repair_cobol_conversion_symbols
from app.services.java_output_sanitizer import prepare_java_for_behavioral_compile

_LOG = logging.getLogger(__name__)


@dataclass
class PreparedSingleFileBehavioralSources:
    """COBOL/Java sources ready for live compile in behavioral diff."""

    cobol_source: str
    java_source: str
    program_name: str
    unresolved_copybooks: List[str]


def _extract_program_id_from_cobol(source: str) -> Optional[str]:
    m = re.search(r"\bPROGRAM-ID\.\s*([A-Z0-9-]+)", source or "", flags=re.IGNORECASE)
    return m.group(1).upper() if m else None


def _strip_markdown_code_fence(text: str) -> str:
    """Fallback when sanitizer returns empty Java."""
    t = (text or "").strip()
    if not t.startswith("```"):
        return text or ""
    t = re.sub(r"^```(?:java)?\s*\n?", "", t, flags=re.IGNORECASE)  # scope-safe: stripping markdown fences from LLM output
    t = re.sub(r"\n?```\s*$", "", t, flags=re.IGNORECASE)
    return t.strip()


def prepare_single_file_behavioral_sources(
    cobol_source: str,
    java_source: str,
    program_name: str,
    *,
    parser_output: Optional[Dict[str, Any]] = None,
    copybooks: Optional[Dict[str, str]] = None,
    skip_cobol_copybook_expansion: bool = False,
) -> PreparedSingleFileBehavioralSources:
    """
    Prepare workspace COBOL/Java for live behavioral compile.

    - Expands COPY books (request copybooks, parser dependencies, host search paths).
    - Sanitizes Java (markdown/mapping notes removed; Spring stripped for plain javac).
    """
    cobol, repair_notes = repair_cobol_conversion_symbols(cobol_source or "")
    if repair_notes:
        _LOG.info("cobol symbol repair program=%s notes=%s", program_name, repair_notes)
    if skip_cobol_copybook_expansion:
        unresolved: List[str] = []
    else:
        cobol, unresolved = expand_cobol_copybooks_for_behavioral(
            cobol,
            copybooks=copybooks,
            parser_output=parser_output,
        )
    prog = str(program_name or "").strip() or None
    java, _notes = prepare_java_for_behavioral_compile(java_source or "", program_name=prog)
    if not java.strip():
        java = prepare_java_for_behavioral_compile(
            _strip_markdown_code_fence(java_source or ""),
            program_name=prog,
        )[0]
    resolved_name = _extract_program_id_from_cobol(cobol) or str(program_name or "UNKNOWN").strip() or "UNKNOWN"
    _LOG.info(
        "single_file behavioral prep program=%s cobol_chars=%d java_chars=%d unresolved_copybooks=%s",
        resolved_name,
        len(cobol),
        len(java),
        unresolved or "none",
    )
    return PreparedSingleFileBehavioralSources(
        cobol_source=cobol,
        java_source=java,
        program_name=resolved_name,
        unresolved_copybooks=unresolved,
    )


def apply_single_file_prep_to_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mutate a single_file behavioral-diff request in place with prepared sources.

    Used by the dedicated testing API path before compile/run.
    """
    if str(request.get("target_type") or "single_file").lower() != "single_file":
        return request
    cobol_raw = request.get("cobol_source") if isinstance(request.get("cobol_source"), str) else ""
    java_raw = request.get("java_source") if isinstance(request.get("java_source"), str) else ""
    program_name = str(request.get("program_name") or "UNKNOWN")
    parser_output = (
        request.get("parser_output") if isinstance(request.get("parser_output"), dict) else None
    )
    copybooks_raw = request.get("copybooks")
    copybooks = copybooks_raw if isinstance(copybooks_raw, dict) else None
    prepared = prepare_single_file_behavioral_sources(
        cobol_raw,
        java_raw,
        program_name,
        parser_output=parser_output,
        copybooks=copybooks,
    )
    request["cobol_source"] = prepared.cobol_source
    request["java_source"] = prepared.java_source
    request["program_name"] = prepared.program_name
    request["_prepared_unresolved_copybooks"] = prepared.unresolved_copybooks
    return request
