"""Post-generation Java field-name reconciliation against parser symbol tables."""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from app.converters.cobol_name_converter import CobolNameConverter
from app.converters.rewrite_record import LOAN_RECORD_FIELD_ALIASES
from app.services.symbol_table import SymbolTable, resolve_symbol_entries

_LOG = logging.getLogger(__name__)

# RISKSCOR LoanRecord fields the pipeline expects (canonical Java names).
RISKSCOR_LOAN_RECORD_JAVA_FIELDS: frozenset[str] = frozenset(
    {
        "loanId",
        "loanCustId",
        "loanStatus",
        "loanClass",
        "loanOutstanding",
        "loanDaysPastDue",
        "loanProvisionRate",
        "loanProvisionAmt",
    }
)

# Extra legacy spellings beyond LOAN_RECORD_FIELD_ALIASES (RISKSCOR / LLM drift).
_EXTRA_FIELD_ALIASES: Dict[str, str] = {
    "classNum": "loanClass",
    "loan_status": "loanStatus",
    "loanStat": "loanStatus",
    "loan_outstanding": "loanOutstanding",
    "loan_id": "loanId",
    "cust_id": "loanCustId",
}

_LOAN_RECORD_RECEIVERS = r"(?:currentLoan(?:Record)?|rec|loanRecord|loan)"

_BUILTIN_FIELD_REFS = frozenset(
    {
        "length",
        "class",
        "values",
        "name",
        "size",
        "isEmpty",
        "getClass",
        "out",
        "err",
        "in",
        # Common package segments from ``java.math.BigDecimal`` etc. (not fields).
        "math",
        "util",
        "nio",
        "time",
        "lang",
        "io",
        "awt",
        "sql",
        "net",
        "text",
        "beans",
        "security",
        "concurrent",
        "function",
        "stream",
        "channels",
        "regex",
    }
)

_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_STRING_LITERAL_RE = re.compile(
    r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
    re.DOTALL,
)
# Mask out the entire ``package`` / ``import`` line: their dotted segments are
# package names, not field references. Reconciling them rewrites valid imports
# (e.g. ``java.time.LocalDate`` → ``java.recActionTime.LocalDate``).
_PACKAGE_OR_IMPORT_LINE_RE = re.compile(
    r"^[ \t]*(?:package|import)\b[^\n]*$",
    re.MULTILINE,
)
_FIELD_DECL_RE = re.compile(
    r"^\s*(?:(?:public|private|protected)\s+)?"
    r"(?:(?:static|final)\s+)*"
    r"(?:static|final\s+)*"
    r"([\w.<>,\s\[\]]+?)\s+(\w+)\s*(?:=|;)",
    re.MULTILINE,
)
_FIELD_REF_RE = re.compile(r"\.(\w+)(?!\w|\s*[\.(])")
_TODO_HEADER_MARKER = "// TODO: Resolve these name mismatches manually:"


def _strip_comments_and_strings(source: str) -> str:
    text = _BLOCK_COMMENT_RE.sub(" ", source)
    text = _LINE_COMMENT_RE.sub(" ", text)
    text = _STRING_LITERAL_RE.sub('""', text)
    return _PACKAGE_OR_IMPORT_LINE_RE.sub(lambda m: " " * len(m.group(0)), text)


def extract_declared_fields(java_source: str) -> Set[str]:
    """Field and local variable names declared in the compilation unit."""
    stripped = _strip_comments_and_strings(java_source)
    fields: Set[str] = set()
    for match in _FIELD_DECL_RE.finditer(stripped):
        if "(" in match.group(1):
            continue
        fields.add(match.group(2))
    for match in re.finditer(
        r"(?:^|[;\{\(]\s*)(?:final\s+)?[\w.<>,\[\]]+\s+(\w+)\s*=",
        stripped,
        re.MULTILINE,
    ):
        fields.add(match.group(1))
    return fields


def extract_class_declared_fields(java_source: str, class_name: str) -> Set[str]:
    """Fields declared on a named inner/top-level class."""
    match = re.search(rf"\bclass\s+{re.escape(class_name)}\s*\{{", java_source)
    if not match:
        return set()
    start = match.end()
    depth = 1
    i = start
    while i < len(java_source) and depth > 0:
        ch = java_source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    body = java_source[start : i - 1]
    fields: Set[str] = set()
    for decl in _FIELD_DECL_RE.finditer(body):
        if "(" not in decl.group(1):
            fields.add(decl.group(2))
    return fields


def extract_field_references(java_source: str) -> Set[str]:
    """Member names used after '.' (field access, not method calls)."""
    stripped = _strip_comments_and_strings(java_source)
    return {m.group(1) for m in _FIELD_REF_RE.finditer(stripped)}


def _symbol_table_canonical_fields(symbol_table: Sequence[Mapping[str, Any]] | None) -> Set[str]:
    names: Set[str] = set()
    if not symbol_table:
        return names
    for sym in symbol_table:
        if not isinstance(sym, dict):
            continue
        cobol = str(sym.get("name") or "").strip()
        if not cobol or cobol == "FILLER":
            continue
        if sym.get("pic") or sym.get("java_field"):
            names.add(
                str(sym.get("java_field") or sym.get("java_name") or "")
                or CobolNameConverter.to_java_field(cobol)
            )
    return {n for n in names if n}


def _merged_alias_map() -> Dict[str, str]:
    merged = dict(LOAN_RECORD_FIELD_ALIASES)
    merged.update(_EXTRA_FIELD_ALIASES)
    return merged


def _build_dynamic_alias_map(
    symbol_table: Sequence[Mapping[str, Any]] | None,
) -> Dict[str, str]:
    """Derive alias → canonical mapping from the symbol table.

    For every symbol with a multi-segment COBOL name (e.g. LOAN-STATUS),
    the canonical Java name is ``loanStatus``.  Common LLM shortenings
    (dropping the prefix, snake_case variants) are generated as aliases
    that map back to the canonical name.
    """
    aliases: Dict[str, str] = {}
    if not symbol_table:
        return aliases

    for sym in symbol_table:
        if not isinstance(sym, dict):
            continue
        cobol = str(sym.get("name") or "").strip()
        if not cobol or cobol == "FILLER":
            continue
        if not (sym.get("pic") or sym.get("java_field")):
            continue
        canonical = (
            str(sym.get("java_field") or sym.get("java_name") or "")
            or CobolNameConverter.to_java_field(cobol)
        )
        if not canonical:
            continue

        parts = cobol.split("-")
        if len(parts) >= 2:
            short_cobol = "-".join(parts[1:])
            short_java = CobolNameConverter.to_java_field(short_cobol)
            if short_java and short_java != canonical:
                aliases.setdefault(short_java, canonical)

            snake = "_".join(p.lower() for p in parts)
            if snake != canonical:
                aliases.setdefault(snake, canonical)

            short_snake = "_".join(p.lower() for p in parts[1:])
            if short_snake != canonical and short_snake != short_java:
                aliases.setdefault(short_snake, canonical)

    return aliases


def _fuzzy_candidates(ref: str, declared_fields: Set[str]) -> List[str]:
    """Return possible declared names for *ref* (small candidate sets only)."""
    ref_lower = ref.lower()
    if ref in declared_fields:
        return [ref]
    candidates: List[str] = []
    for d in declared_fields:
        d_lower = d.lower()
        if d_lower == ref_lower:
            candidates.append(d)
        elif d.endswith(ref) or ref.endswith(d):
            candidates.append(d)
        elif len(ref_lower) >= 3 and d_lower.endswith(ref_lower):
            candidates.append(d)
        elif len(ref_lower) >= 3 and ref_lower in d_lower:
            candidates.append(d)
    return sorted(set(candidates))


def _replace_field_reference(
    text: str,
    old: str,
    new: str,
    *,
    receivers: Optional[str] = None,
) -> Tuple[str, int]:
    """Rename field references line-by-line, skipping import/package lines.

    Uses a single-pass line edit (no per-line javalang re-parse). Previously
    ``ScopeSafeSourceModifier.replace_line`` re-parsed the full compilation unit
    on every changed line, which caused multi-minute stalls on large programs.
    """
    if old == new:
        return text, 0

    lines = text.split("\n")
    total_count = 0

    if receivers:
        pattern = re.compile(rf"\b({receivers})\.{re.escape(old)}\b")
        repl = rf"\1.{new}"
    else:
        pattern = re.compile(rf"\.{re.escape(old)}(?!\w|\s*[\.(])")
        repl = f".{new}"

    for i, line in enumerate(lines):
        if _PACKAGE_OR_IMPORT_LINE_RE.match(line):
            continue
        new_line, count = pattern.subn(repl, line)
        if count:
            total_count += count
            lines[i] = new_line

    if not total_count:
        return text, 0
    return "\n".join(lines), total_count


def _canonical_targets(
    declared_fields: Set[str],
    symbol_table: Sequence[Mapping[str, Any]] | None,
    loan_record_fields: Set[str],
) -> Set[str]:
    return declared_fields | _symbol_table_canonical_fields(symbol_table) | loan_record_fields


def _reconcile_log(program_name: str, step: str, elapsed: float) -> None:
    prefix = f"[RECONCILE] {program_name}: " if program_name else "[RECONCILE] "
    print(f"{prefix}{step} completed in {elapsed:.1f}s", flush=True)


def reconcile_names(
    java_source: str,
    symbol_table: Sequence[Mapping[str, Any]] | SymbolTable | None = None,
    *,
    program_name: str = "",
) -> Tuple[str, List[str]]:
    """
    Fix field references that do not match declarations.

    1. Auto-rename when an alias or fuzzy match is unambiguous.
    2. Prepend TODO comments for ambiguous unresolved references.
    """
    text = java_source or ""
    if not text.strip():
        return text, []

    prog = program_name or "PROGRAM"
    print(f"[RECONCILE] {prog}: starting", flush=True)
    total_start = time.monotonic()

    symbol_entries: Sequence[Mapping[str, Any]] | None
    if isinstance(symbol_table, SymbolTable):
        symbol_entries = symbol_table.to_legacy_list()
        allowed_java = symbol_table.all_java_names()
    else:
        symbol_entries = symbol_table
        allowed_java = None

    notes: List[str] = []

    t0 = time.monotonic()
    static_aliases = _merged_alias_map()
    dynamic_aliases = _build_dynamic_alias_map(symbol_entries)
    alias_map = {**dynamic_aliases, **static_aliases}
    loan_fields = extract_class_declared_fields(text, "LoanRecord")
    if not loan_fields:
        loan_fields = set(RISKSCOR_LOAN_RECORD_JAVA_FIELDS)

    declared = extract_declared_fields(text)
    targets = _canonical_targets(declared, symbol_entries, loan_fields)
    if allowed_java:
        targets |= allowed_java
    _reconcile_log(prog, "prepare_aliases_and_extract", time.monotonic() - t0)

    # Phase 1: known aliases on loan-record receivers (RISKSCOR path).
    t0 = time.monotonic()
    phase1_count = 0
    for legacy, canonical in alias_map.items():
        if legacy == canonical or canonical not in targets:
            continue
        text, count = _replace_field_reference(
            text, legacy, canonical, receivers=_LOAN_RECORD_RECEIVERS
        )
        if count:
            phase1_count += count
            msg = f"Auto-renamed reference {legacy} → {canonical} ({count} on loan receiver)"
            notes.append(msg)
            _LOG.info("%s%s", f"[{program_name}] " if program_name else "", msg)
    _reconcile_log(prog, f"phase1_loan_receiver_aliases ({phase1_count} replacements)", time.monotonic() - t0)

    t0 = time.monotonic()
    declared = extract_declared_fields(text)
    targets = _canonical_targets(declared, symbol_entries, loan_fields)
    if allowed_java:
        targets |= allowed_java
    _reconcile_log(prog, "refresh_declared_after_phase1", time.monotonic() - t0)

    # Phase 2: global alias replace when canonical exists but reference is still dangling.
    t0 = time.monotonic()
    phase2_count = 0
    declared_set = declared
    for legacy, canonical in alias_map.items():
        if legacy == canonical or canonical not in targets:
            continue
        if legacy in declared_set:
            continue
        text, count = _replace_field_reference(text, legacy, canonical)
        if count:
            phase2_count += count
            msg = f"Auto-renamed reference {legacy} → {canonical} ({count} occurrence(s))"
            notes.append(msg)
            _LOG.info("%s%s", f"[{program_name}] " if program_name else "", msg)
    _reconcile_log(prog, f"phase2_global_aliases ({phase2_count} replacements)", time.monotonic() - t0)

    t0 = time.monotonic()
    declared = extract_declared_fields(text)
    refs = extract_field_references(text)
    sym_field_names = (
        _symbol_table_canonical_fields(symbol_entries) if symbol_entries else set()
    )
    _reconcile_log(
        prog,
        f"extract_refs ({len(refs)} refs, {len(declared)} declared)",
        time.monotonic() - t0,
    )

    t0 = time.monotonic()
    mismatches: List[Tuple[str, List[str]]] = []
    fuzzy_renames = 0
    declared_set = declared

    for ref in sorted(refs):
        if ref in _BUILTIN_FIELD_REFS or ref in declared_set:
            continue
        if ref and ref[0].isupper():
            continue
        if ref in alias_map and alias_map[ref] in declared_set:
            continue

        candidates = _fuzzy_candidates(ref, declared_set)
        if not candidates and sym_field_names:
            candidates = _fuzzy_candidates(ref, sym_field_names)

        if len(candidates) == 1:
            text, count = _replace_field_reference(text, ref, candidates[0])
            if count:
                fuzzy_renames += count
                msg = f"Auto-renamed reference {ref} → {candidates[0]} ({count} occurrence(s))"
                notes.append(msg)
                _LOG.info("%s%s", f"[{program_name}] " if program_name else "", msg)
            continue

        mismatches.append((ref, candidates))

    _reconcile_log(
        prog,
        f"phase3_fuzzy_resolve ({fuzzy_renames} renames, {len(mismatches)} mismatches)",
        time.monotonic() - t0,
    )

    if mismatches:
        _LOG.warning(
            "%sUnresolvable name mismatches: %s",
            f"[{program_name}] " if program_name else "",
            mismatches,
        )
        if _TODO_HEADER_MARKER not in text:
            todo_lines = [_TODO_HEADER_MARKER]
            for ref, cands in mismatches:
                todo_lines.append(f"//   - '{ref}' has candidates: {cands}")
            text = "\n".join(todo_lines) + "\n" + text

    print(
        f"[RECONCILE] {prog}: completed in {time.monotonic() - total_start:.1f}s",
        flush=True,
    )
    return text, notes
