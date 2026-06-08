"""IBM-aligned program complexity tier classification."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Union

_LOG = logging.getLogger(__name__)

_COPYBOOK_RE = re.compile(r"(?im)^\s*COPY\s+([\w-]+)")


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _file_entries(parser_output: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return unique FD/select file metadata without double-counting parser mirrors."""
    deps = _as_dict(parser_output.get("dependencies"))
    raw = deps.get("file_entries") or parser_output.get("files") or []
    entries: List[Dict[str, Any]] = []
    seen: set[str] = set()
    if isinstance(raw, dict):
        candidates = [v for v in raw.values() if isinstance(v, dict)]
    elif isinstance(raw, list):
        candidates = [item for item in raw if isinstance(item, dict)]
    else:
        candidates = []
    for entry in candidates:
        key = str(entry.get("name") or entry.get("file") or "").strip().upper()
        dedupe_key = key or str(id(entry))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        entries.append(entry)
    return entries


def _copybook_count(parser_output: Dict[str, Any], source_code: str) -> int:
    """Count COPY dependencies from parser JSON, falling back to source scan."""
    source_count = 0
    if source_code:
        source_count = len(set(_COPYBOOK_RE.findall(source_code)))
    deps = _as_dict(parser_output.get("dependencies"))
    copybooks = deps.get("copybooks") or []
    if isinstance(copybooks, list) and copybooks:
        dep_count = len(
            {
                str(name).strip().upper()
                for name in copybooks
                if str(name).strip()
            }
        )
        if source_count:
            return min(dep_count, source_count)
        return dep_count
    return source_count


def _line_count(parser_output: Dict[str, Any], source_code: str = "") -> int:
    """Prefer original source line counts over expanded COPY-inlined totals."""
    po = _as_dict(parser_output)
    for attr in ("original_lines", "source_lines"):
        val = po.get(attr)
        if val is not None:
            if isinstance(val, list):
                return len(val)
            if isinstance(val, int):
                return val
    source = po.get("raw_source") or po.get("source") or source_code or ""
    if source:
        return source.count("\n") + (1 if source.strip() else 0)
    for attr in ("total_lines", "line_count"):
        val = po.get(attr)
        if val is not None:
            if isinstance(val, list):
                return len(val)
            if isinstance(val, int):
                return val
    return 0


def classify_complexity_tier(
    parser_output: Union[Dict[str, Any], Any],
    *,
    source_code: str = "",
) -> Dict[str, Any]:
    """Score a COBOL program and return Standard / Complex / Enterprise tier metadata."""
    po = _as_dict(parser_output)
    deps = _as_dict(po.get("dependencies"))

    score = 0
    drivers: List[str] = []

    source_upper = (source_code or "").upper()
    lines = _line_count(po, source_code)

    file_entries = _file_entries(po)
    file_count = len(file_entries)

    copybook_count = _copybook_count(po, source_code)

    sorts = po.get("sorts") or []
    operations = po.get("operations") or []
    has_sort = bool(sorts) or any(
        str(op.get("type", "")).upper() == "SORT" for op in operations if isinstance(op, dict)
    )
    has_sql = bool(po.get("has_exec_sql")) or "EXEC SQL" in source_upper

    external_calls = deps.get("external_calls") or []
    sub_program_count = len(external_calls) if isinstance(external_calls, list) else 0

    has_indexed = any(
        str(entry.get("organization", "")).upper() == "INDEXED" for entry in file_entries
    )

    if lines > 1000:
        score += 3
        drivers.append(f"{lines} lines")
    elif lines > 500:
        score += 2
        drivers.append(f"{lines} lines")

    if file_count >= 6:
        score += 3
        drivers.append(f"{file_count} files")
    elif file_count >= 3:
        score += 2
        drivers.append(f"{file_count} files")

    if copybook_count >= 10:
        score += 5
        drivers.append(f"{copybook_count} copybooks")
    elif copybook_count >= 5:
        score += 2
        drivers.append(f"{copybook_count} copybooks")

    if has_sql:
        score += 4
        drivers.append("EXEC SQL")

    if has_sort:
        score += 3
        drivers.append("internal SORT")

    if sub_program_count > 0:
        score += 3
        drivers.append(f"{sub_program_count} sub-programs")

    if has_indexed:
        score += 3
        drivers.append("indexed files")

    if (
        lines < 400
        and not has_sql
        and not has_sort
        and not has_indexed
        and sub_program_count == 0
        and file_count <= 2
    ):
        score = min(score, 4)

    if score <= 4:
        tier, ibm, method = "Standard", "0-3", "Direct generation"
    elif score <= 12:
        tier, ibm, method = "Complex", "4-6", "Constrained generation + repair"
    else:
        tier, ibm, method = "Enterprise", "7-9", "Constrained generation + behavioral verification"

    program = str(po.get("program_name") or po.get("program_id") or "unknown").strip().upper()
    complexity_log = (
        f"[COMPLEXITY] {program}: lines={lines}, "
        f"files={file_count}, copybooks={copybook_count}, "
        f"sql={has_sql}, sort={has_sort}, "
        f"subprogs={sub_program_count}, "
        f"indexed={has_indexed}, score={score} -> {tier}"
    )
    print(complexity_log, flush=True)
    _LOG.info(complexity_log)

    return {
        "tier": tier,
        "ibm_rating_equivalent": ibm,
        "score": score,
        "drivers": drivers,
        "conversion_method": method,
    }
