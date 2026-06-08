"""Expand COPY books before live COBOL compile in behavioral testing."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from app.env_bootstrap import SERVICE_ROOT
from app.parsers.copybook_resolver import COPY_LIBRARY_CONFIG, find_copy_book

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_COPY_EXTENSIONS = ("", ".cpy", ".CPY", ".copy", ".cbl", ".CBL")
_MAX_EXPAND_PASSES = 12

# Alternate on-disk names for the same layout (use case 3 renames).
_COPYBOOK_ALIASES: Dict[str, List[str]] = {
    "RPTHDCPY": ["RPTCOPY"],
    "RPTCOPY": ["RPTHDCPY"],
}

# COPY directive line (period optional — editor/free-format often omits it).
_COPY_LINE = re.compile(
    r"^(?P<indent>\s*)COPY\s+(?P<name>[A-Z0-9#@$\-]+)"
    r"(?:\s+IN\s+(?P<lib>[A-Z0-9\-]+))?"
    r"(?:\s*\.)?"
    r"(?:\s+.*)?\s*$",
    re.IGNORECASE,
)


def _service_roots() -> List[Path]:
    roots: List[Path] = []
    for candidate in (SERVICE_ROOT, _PACKAGE_ROOT):
        key = str(candidate.resolve()).casefold()
        if key not in {str(r.resolve()).casefold() for r in roots} and candidate.is_dir():
            roots.append(candidate)
    return roots or [_PACKAGE_ROOT]


_LEVEL_PREFIX = re.compile(
    r"^(?P<lvl>FD|01|77|05|\d{2})\s+",
    re.IGNORECASE,
)


def _flatten_copybook_for_subgroup(copybook_text: str, *, base_indent: str = "          ") -> str:
    """
    When a copybook starts with 01 but is inlined under an existing 01 group (COPY at level 05),
    emit only the elementary 05 items to avoid invalid duplicate level-01 records.
    """
    lines = [ln for ln in copybook_text.splitlines() if ln.strip()]
    if not lines:
        return copybook_text
    first = lines[0].lstrip().upper()
    if not re.match(r"01\s+", first):
        return copybook_text
    body: List[str] = []
    for ln in lines[1:]:
        stripped = ln.lstrip()
        if re.match(r"05\s+", stripped, flags=re.IGNORECASE):
            body.append(f"{base_indent}{stripped}")
        elif re.match(r"\d{2}\s+", stripped):
            body.append(f"{base_indent}{re.sub(r'^\d{2}', '05', stripped, count=1)}")
    if body:
        return "\n".join(body) + "\n"
    return copybook_text


def _placement_before_copy(lines: List[str], copy_index: int) -> str:
    """
    Classify COPY insertion context from preceding lines.

    Returns:
        under_01 — COPY nested under an existing 01/77 group
        under_fd — COPY immediately under FD (no 01 wrapper in host)
        under_other — working-storage, section-level, or unknown
    """
    for i in range(copy_index - 1, -1, -1):
        raw = lines[i]
        if not raw.strip() or _is_fixed_format_comment(raw):
            continue
        if _COPY_LINE.match(raw.rstrip("\r\n")):
            return "under_other"
        stripped = raw.lstrip()
        if re.search(r"\bSECTION\b", stripped, flags=re.IGNORECASE):
            return "under_other"
        level_match = _LEVEL_PREFIX.match(stripped)
        if level_match:
            lvl = level_match.group("lvl").upper()
            if lvl == "FD":
                return "under_fd"
            if lvl in ("01", "77"):
                return "under_01"
            return "under_other"
    return "under_other"


def _normalize_copybook_lib(lib: Optional[Mapping[str, str]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key, value in (lib or {}).items():
        name = str(key or "").strip().upper()
        text = str(value or "").replace("\ufeff", "").replace("\r\n", "\n")
        if name and text.strip():
            out[name] = text
    return out


def _default_copybook_search_dirs(extra: Optional[Iterable[str]] = None) -> List[Path]:
    dirs: List[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = str(path.resolve()).casefold()
        if key in seen or not path.is_dir():
            return
        seen.add(key)
        dirs.append(path)

    try:
        from app.services.behavioral_baseline import acme_bank_v3_root

        acme = acme_bank_v3_root()
        if acme is not None:
            add(acme / "copybooks")
    except Exception:
        pass

    for root in _service_roots():
        for rel in (
            "tests/fixtures/usecase3/copybooks",
            "copybooks",
            "tests/fixtures/copybooks",
        ):
            add(root / rel)

    env_dirs = os.environ.get("COBOL_COPYBOOK_DIRS", "")
    for part in re.split(r"[;:,]", env_dirs):
        part = part.strip()
        if part:
            add(Path(part))

    if extra:
        for part in extra:
            part = str(part).strip()
            if part:
                add(Path(part))

    for lib_paths in COPY_LIBRARY_CONFIG.values():
        if isinstance(lib_paths, list):
            for part in lib_paths:
                part = str(part).strip()
                if part:
                    add(Path(part))

    return dirs


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_copybook_file(name: str, search_dirs: List[Path]) -> Optional[str]:
    base_name = name.strip().upper()
    if not base_name:
        return None

    def read_from_dirs(copy_name: str) -> Optional[str]:
        for directory in search_dirs:
            for ext in _COPY_EXTENSIONS:
                candidate = directory / f"{copy_name}{ext}"
                if candidate.is_file():
                    return _read_text_file(candidate)
        return None

    content = read_from_dirs(base_name)
    if content:
        return content

    resolved_path = find_copy_book(base_name)
    if resolved_path:
        path = Path(resolved_path)
        if path.is_file():
            return _read_text_file(path)

    for alias in _COPYBOOK_ALIASES.get(base_name, []):
        content = read_from_dirs(alias.upper())
        if content:
            return content
        resolved_path = find_copy_book(alias)
        if resolved_path:
            path = Path(resolved_path)
            if path.is_file():
                return _read_text_file(path)

    return None


def _unwrap_parser_output(parser_output: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not parser_output:
        return {}
    if isinstance(parser_output.get("dependencies"), dict):
        return dict(parser_output)
    ast = parser_output.get("ast")
    if isinstance(ast, dict):
        return dict(ast)
    return dict(parser_output)


def _copybook_names_from_source(source: str) -> List[str]:
    names: List[str] = []
    for line in source.splitlines():
        if _is_fixed_format_comment(line):
            continue
        match = _COPY_LINE.match(line.rstrip("\r\n"))
        if match:
            text = match.group("name").strip().upper()
            if text and text not in names:
                names.append(text)
    return names


def _copybook_names_from_parser(parser_output: Optional[Mapping[str, Any]]) -> List[str]:
    unwrapped = _unwrap_parser_output(parser_output)
    deps = unwrapped.get("dependencies")
    if not isinstance(deps, dict):
        return []
    names: List[str] = []
    for item in deps.get("copybooks") or []:
        text = str(item or "").strip().upper()
        if text and text not in names:
            names.append(text)
    for item in unwrapped.get("unresolved_copybooks") or []:
        text = str(item or "").strip().upper()
        if text and text not in names:
            names.append(text)
    return names


def _is_fixed_format_comment(line: str) -> bool:
    """True when line is a fixed-format comment (area A * or / in column 7)."""
    raw = line.rstrip("\r\n")
    if not raw.strip():
        return False
    if len(raw) >= 7 and raw[6] in ("*", "/"):
        return True
    stripped = raw.lstrip()
    return stripped.startswith("*>")


def _line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return "\n"


def _copy_indent_for_inlining(indent: str) -> str:
    """Indent for 05 fields nested under an 01 record (COPY already at subordinate level)."""
    return indent if indent else "          "


def _field_indent_under_fd(copy_indent: str) -> str:
    """Indent for 05 fields under a copybook 01 emitted directly below FD."""
    base = copy_indent if copy_indent else "       "
    if len(base) >= 11:
        return base
    return base + "   "


def _logical_copybook_lines(body: str) -> List[str]:
    return [ln.lstrip() for ln in (body or "").splitlines() if ln.strip()]


def _adapt_copybook_body(body: str, *, placement: str) -> List[str]:
    """
    Return logical COBOL lines to emit for this COPY site (no indentation yet).

    under_01: drop leading 01/77 from copybook, keep subordinate fields only.
    under_fd: keep full 01/77 record + children.
    """
    lines = _logical_copybook_lines(body)
    if not lines:
        return []
    first = lines[0].upper()
    if placement == "under_01" and re.match(r"01\s+", first):
        return lines[1:] or lines
    if placement == "under_01" and re.match(r"77\s+", first):
        return lines[1:] or lines
    return lines


def _emit_inlined_lines(
    logical_lines: List[str],
    *,
    copy_indent: str,
    placement: str,
    nl: str,
) -> str:
    """Apply COPY-site indentation so 01/77 never sit directly under FD without a record level."""
    if not logical_lines:
        return ""
    field_indent = (
        _field_indent_under_fd(copy_indent)
        if placement in ("under_fd", "under_other")
        else _copy_indent_for_inlining(copy_indent)
    )
    out: List[str] = []
    for stripped in logical_lines:
        if placement == "under_fd" or (
            placement == "under_other"
            and re.match(r"01\s+", stripped, flags=re.IGNORECASE)
        ) or (
            placement == "under_other"
            and re.match(r"77\s+", stripped, flags=re.IGNORECASE)
        ):
            if re.match(r"01\s+", stripped, flags=re.IGNORECASE) or re.match(
                r"77\s+", stripped, flags=re.IGNORECASE
            ):
                out.append(f"{copy_indent}{stripped}{nl}")
            elif re.match(r"05\s+", stripped, flags=re.IGNORECASE):
                out.append(f"{field_indent}{stripped}{nl}")
            elif re.match(r"\d{2}\s+", stripped):
                out.append(
                    f"{field_indent}{re.sub(r'^\d{2}', '05', stripped, count=1)}{nl}"
                )
            else:
                out.append(f"{field_indent}{stripped}{nl}")
        else:
            if re.match(r"05\s+", stripped, flags=re.IGNORECASE):
                out.append(f"{field_indent}{stripped}{nl}")
            elif re.match(r"\d{2}\s+", stripped):
                out.append(
                    f"{field_indent}{re.sub(r'^\d{2}', '05', stripped, count=1)}{nl}"
                )
            else:
                out.append(f"{copy_indent}{stripped}{nl}")
    return "".join(out)


def _inline_copy_line(line: str, lib: Dict[str, str], *, placement: str = "under_other") -> str:
    """Expand one COPY directive line to valid COBOL only (no debug markers)."""
    raw = line.rstrip("\r\n")
    match = _COPY_LINE.match(raw)
    if not match:
        return line
    name = match.group("name").upper()
    indent = match.group("indent") or ""
    nl = _line_ending(line)
    if name not in lib:
        return line
    logical = _adapt_copybook_body(lib[name], placement=placement)
    emitted = _emit_inlined_lines(logical, copy_indent=indent, placement=placement, nl=nl)
    return emitted if emitted else line


def _ensure_trailing_newline(source: str) -> str:
    if not source:
        return "\n"
    if source.endswith("\n"):
        return source
    return source + "\n"


def _expand_copy_lines(source: str, lib: Dict[str, str]) -> str:
    """Primary expansion: line-by-line COPY detection (fixed and editor layouts)."""
    if not lib:
        return _ensure_trailing_newline(source)
    lines = source.splitlines(keepends=True)
    logical: List[str] = [ln.rstrip("\r\n") for ln in lines]
    parts: List[str] = []
    for idx, line in enumerate(lines):
        if _is_fixed_format_comment(line):
            parts.append(line)
            continue
        placement = _placement_before_copy(logical, idx)
        parts.append(_inline_copy_line(line, lib, placement=placement))
    return _ensure_trailing_newline("".join(parts))


def _find_remaining_copy_directives(source: str) -> List[str]:
    """COPY statements still present (would make cobc look for .cpy files on disk)."""
    names: List[str] = []
    for line in source.splitlines():
        if _is_fixed_format_comment(line):
            continue
        match = _COPY_LINE.match(line.rstrip("\r\n"))
        if match:
            name = match.group("name").upper()
            if name not in names:
                names.append(name)
    return names


def _load_lib_for_names(names: Iterable[str], lib: Dict[str, str], search_dirs: List[Path]) -> None:
    for name in names:
        key = name.strip().upper()
        if not key or key in lib:
            continue
        content = _read_copybook_file(key, search_dirs)
        if content:
            lib[key] = content.replace("\ufeff", "").replace("\r\n", "\n")


def expand_cobol_copybooks_for_behavioral(
    cobol_source: str,
    *,
    copybooks: Optional[Mapping[str, str]] = None,
    parser_output: Optional[Mapping[str, Any]] = None,
    extra_search_dirs: Optional[Iterable[str]] = None,
) -> Tuple[str, List[str]]:
    """
    Inline COPY statements using request copybooks, parser metadata, and disk search paths.

    Returns:
        (expanded_source, unresolved_copybook_names)
    """
    source = (cobol_source or "").replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    if not source.strip():
        return source, []

    lib = _normalize_copybook_lib(copybooks)
    search_dirs = _default_copybook_search_dirs(extra_search_dirs)

    needed: List[str] = []
    for name in _copybook_names_from_source(source):
        if name not in needed:
            needed.append(name)
    for name in _copybook_names_from_parser(parser_output):
        if name not in needed:
            needed.append(name)

    _load_lib_for_names(needed, lib, search_dirs)

    expanded = source
    for _ in range(_MAX_EXPAND_PASSES):
        _load_lib_for_names(_copybook_names_from_source(expanded), lib, search_dirs)
        next_source = _expand_copy_lines(expanded, lib)
        if next_source == expanded:
            break
        expanded = next_source

    unresolved = _find_remaining_copy_directives(expanded)
    return _ensure_trailing_newline(expanded), unresolved


def format_copybook_prep_failure(unresolved: List[str], search_dirs: List[Path]) -> str:
    """Human-readable message when COPY books are not inlined before cobc."""
    if not unresolved:
        return ""
    dirs = "; ".join(str(d) for d in search_dirs[:3]) or "(no copybook directories configured)"
    names = ", ".join(unresolved[:8])
    return (
        f"COBOL COPY book(s) not expanded before compile: {names}. "
        f"Searched: {dirs}. "
        "Provide copybooks in the behavioral request or place .cpy files on the API host."
    )
