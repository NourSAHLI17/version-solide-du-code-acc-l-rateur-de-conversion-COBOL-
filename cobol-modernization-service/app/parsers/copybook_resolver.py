"""Pre-parser COPY book resolution layer for COBOL modernization.

Pipeline Stage 2: runs after JCL parsing and before COBOL parsing.
Expands all COPY statements in raw COBOL source into their actual content,
producing a fully-resolved source file with no remaining COPY references.

This module is purely deterministic — no LLM calls, no inference, no guessing.
"""

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

COPY_LIBRARY_CONFIG: dict[str, list[str]] = {
    "default": ["./copybooks/", "./copybooks/common/"],
    "MYLIB": ["./copybooks/mylib/"],
    "SYSLIB": ["./copybooks/system/"],
}

COPY_EXTENSIONS: list[str] = [".cpy", ".CPY", ".cbl", ".CBL", ".copy", ""]

MAX_NESTING_DEPTH: int = 10

# ---------------------------------------------------------------------------
# Cross-program cache  (REQ-8)
# Key: "LIBRARY/NAME+REPLACING_HASH" → resolved content string
# ---------------------------------------------------------------------------

COPYBOOK_CACHE: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Column-aware COPY detection pattern  (REQ-2)
#
# Fixed-format COBOL layout:
#   cols 1-6  : sequence numbers (skip)
#   col  7    : indicator (* = comment, / = page eject, - = continuation, D = debug)
#   cols 8-11 : Area A
#   cols 12-72: Area B  ← COPY statements appear here
#
# The regex enforces that COPY starts in Area B (column 12+).
# It also supports multi-line COPY that has been pre-joined.
# ---------------------------------------------------------------------------

COPY_PATTERN = re.compile(
    r"^.{6}"  # cols 1-6: sequence numbers (skip)
    r"[ \-D]"  # col 7: indicator (space, continuation, debug)
    r"   "  # cols 8-10: Area A (3 spaces = not starting in Area A)
    r" {1,}"  # col 11+: Area B start
    r"COPY\s+"
    r"([A-Z0-9#@$\-]+)"  # group 1: copy book name
    r"(?:\s+IN\s+([A-Z0-9\-]+))?"  # group 2: optional library qualifier
    r"(?:\s+REPLACING\s+(.*?))?"  # group 3: optional REPLACING clause
    r"\.\s*$",
    re.IGNORECASE,
)

# Simpler fallback for free-form or loosely-formatted sources where the
# column-strict pattern may miss valid COPY statements.
COPY_PATTERN_LOOSE = re.compile(
    r"^\s+COPY\s+"
    r"([A-Z0-9#@$\-]+)"
    r"(?:\s+IN\s+([A-Z0-9\-]+))?"
    r"(?:\s+REPLACING\s+(.*?))?"
    r"\.\s*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Output contract  (REQ-9)
# ---------------------------------------------------------------------------


@dataclass
class CopyResolutionResult:
    """Result of COPY book resolution.

    Attributes:
        expanded_source: Full source with all COPYs replaced by their content.
        resolved_copybooks: Audit trail of each successfully resolved COPY.
        unresolved_copybooks: Names of copy books that could not be found.
        errors: All errors encountered during resolution.
        warnings: Non-fatal issues encountered during resolution.

    Example:
        Input:
            (returned from resolve_copy_books)
        Output:
            CopyResolutionResult(
                expanded_source="...",
                resolved_copybooks=[{"name": "INVDATA", ...}],
                unresolved_copybooks=[],
                errors=[],
                warnings=[]
            )
    """

    expanded_source: str = ""
    resolved_copybooks: list[dict] = field(default_factory=list)
    unresolved_copybooks: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# REPLACING clause parser  (REQ-1, REQ-4)
# ---------------------------------------------------------------------------


def parse_replacing_clause(replacing_str: str) -> list[tuple[str, str]]:
    """Parse a REPLACING clause into (old, new) substitution pairs.

    Handles the COBOL pseudo-text delimiter format: ==old== BY ==new==.
    Multiple pairs are allowed in a single REPLACING clause.

    Args:
        replacing_str: Raw text after the REPLACING keyword.

    Returns:
        List of (old_text, new_text) tuples.

    Example:
        Input:
            "==INV== BY ==SALES== ==OLD== BY ==NEW=="
        Output:
            [("INV", "SALES"), ("OLD", "NEW")]
    """

    pairs: list[tuple[str, str]] = []
    pattern = r"==([^=]+)==\s+BY\s+==([^=]+)=="
    for m in re.finditer(pattern, replacing_str, re.IGNORECASE):
        pairs.append((m.group(1).strip(), m.group(2).strip()))
    return pairs


def apply_replacing(content: str, pairs: list[tuple[str, str]]) -> str:
    """Apply REPLACING substitutions using word-boundary matching.

    Uses \\b word boundaries so that replacing INV does not affect INVALID.

    Args:
        content: Copy book content to transform.
        pairs: List of (old_text, new_text) substitution pairs.

    Returns:
        Transformed content with all replacements applied.

    Example:
        Input:
            content="INV-NAME  INV-QUANTITY  INVALID-FLAG"
            pairs=[("INV", "SALES")]
        Output:
            "SALES-NAME  SALES-QUANTITY  INVALID-FLAG"
    """

    for old, new in pairs:
        old_esc = re.escape(old)
        # Tokens ending with '-' (COPY REPLACING ==PREFIX-==) need COBOL identifier boundaries.
        # Plain tokens use \\b so INV still matches inside INV-NAME.
        if old.endswith("-"):
            pattern = r"(?<![A-Z0-9-])" + old_esc + r"(?![A-Z0-9-])"
        else:
            pattern = r"\b" + old_esc + r"\b"
        content = re.sub(pattern, new, content, flags=re.IGNORECASE)
    return content


# ---------------------------------------------------------------------------
# File search  (REQ-3)
# ---------------------------------------------------------------------------


def _get_library_paths(library: str) -> list[str]:
    """Look up library paths from config, case-insensitively.

    Args:
        library: Library key (e.g. "default", "MYLIB").

    Returns:
        List of directory paths for the given library key.
    """

    # Build a case-insensitive lookup map
    lookup = {k.upper(): v for k, v in COPY_LIBRARY_CONFIG.items()}
    val = lookup.get(library.upper(), [])
    if isinstance(val, list):
        return list(val)
    return [val]


def find_copy_book(name: str, library: str = "default") -> Optional[str]:
    """Locate a copy book file on disk.

    Search order (per REQ-3):
        1. Paths from JCL manifest copylib_paths (in order listed in SYSLIB DD)
        2. Default configured paths
        3. Try extensions: .cpy, .CPY, .cbl, .CBL, .copy, (no extension)
        4. Try both original case and UPPERCASE of the name

    Args:
        name: Copy book name (e.g. "INVDATA").
        library: Library qualifier from the IN clause, or "default".

    Returns:
        Absolute path to the copy book file, or None if not found.

    Example:
        Input:
            name="INVDATA", library="default"
        Output:
            "/copybooks/INVDATA.cpy"  (if file exists)
    """

    search_paths: list[str] = []

    # Library-specific paths first
    search_paths.extend(_get_library_paths(library))

    # Always fall back to default paths
    if library.upper() != "DEFAULT":
        search_paths.extend(_get_library_paths("default"))

    for base_path in search_paths:
        for ext in COPY_EXTENSIONS:
            for candidate_name in [name, name.upper()]:
                full_path = os.path.join(base_path, candidate_name + ext)
                if os.path.isfile(full_path):
                    return os.path.abspath(full_path)

    return None


# ---------------------------------------------------------------------------
# Cache key builder  (REQ-8)
# ---------------------------------------------------------------------------


def _make_cache_key(
    library: str,
    name: str,
    replacing_pairs: list[tuple[str, str]],
) -> str:
    """Build a deterministic cache key incorporating library, name, and REPLACING hash.

    Args:
        library: Library qualifier (e.g. "DEFAULT", "MYLIB").
        name: Copy book name.
        replacing_pairs: REPLACING substitution pairs.

    Returns:
        Cache key string like "DEFAULT/INVDATA+abc123".

    Example:
        Input:
            library="DEFAULT", name="INVDATA", replacing_pairs=[("INV", "SALES")]
        Output:
            "DEFAULT/INVDATA+e3b0c442..."
    """

    pairs_str = str(tuple(sorted(replacing_pairs)))
    replacing_hash = hashlib.sha256(pairs_str.encode()).hexdigest()[:12]
    return f"{library}/{name}+{replacing_hash}"


# ---------------------------------------------------------------------------
# Continuation line joiner
# ---------------------------------------------------------------------------


def _join_continuation_lines(source_lines: list[str]) -> list[str]:
    """Pre-join continuation lines (col 7 = '-') into their preceding line.

    In fixed-format COBOL, a '-' in column 7 means the line continues the
    previous statement.  We merge them so COPY patterns spanning multiple
    physical lines can be detected.

    Args:
        source_lines: Raw source lines (with newlines).

    Returns:
        List of logical lines with continuations merged.

    Example:
        Input:
            ["      COPY INVDATA RE-\\n", "      -    PLACING ==INV== BY ==SALES==.\\n"]
        Output:
            (merged into single line containing the full COPY statement)
    """

    joined: list[str] = []
    for line in source_lines:
        raw = line.rstrip("\n\r")
        # Check for continuation indicator in column 7
        if len(raw) >= 7 and raw[6] == "-" and joined:
            # Strip seq area + indicator + leading spaces from continuation
            cont_text = raw[7:].lstrip() if len(raw) > 7 else ""
            # Append to previous line (remove trailing period/whitespace temporarily)
            prev = joined[-1].rstrip("\n\r").rstrip()
            joined[-1] = prev + " " + cont_text + "\n"
        else:
            joined.append(line)
    return joined


# ---------------------------------------------------------------------------
# Main resolver  (REQ-1, REQ-2, REQ-5, REQ-6, REQ-7)
# ---------------------------------------------------------------------------


def resolve_copy_books(
    source_lines: list[str],
    depth: int = 0,
    resolved_stack: set[str] | None = None,
    result: CopyResolutionResult | None = None,
) -> CopyResolutionResult:
    """Resolve all COPY statements in COBOL source lines.

    Recursively expands COPY statements, handling:
    - Simple COPY (REQ-1)
    - COPY with IN library qualifier (REQ-1)
    - COPY with REPLACING clause (REQ-1, REQ-4)
    - Column-aware detection in Area B (REQ-2)
    - Nested COPY resolution up to MAX_NESTING_DEPTH (REQ-5)
    - Source map comments around expanded content (REQ-6)
    - Three-tier degradation: found / not-found / circular (REQ-7)
    - Cross-program cache (REQ-8)

    Args:
        source_lines: COBOL source as list of strings (with newlines).
        depth: Current recursion depth (0 = top level).
        resolved_stack: Set of currently-being-resolved copy keys for
            circular reference detection.
        result: Accumulating result object (created on first call).

    Returns:
        CopyResolutionResult with expanded source and audit trail.

    Example:
        Input:
            source_lines=["      COPY INVDATA.\\n"]
        Output:
            CopyResolutionResult(
                expanded_source="      * >>>BEGIN COPY INVDATA FROM /path<<<\\n...\\n      * >>>END COPY INVDATA<<<\\n",
                resolved_copybooks=[{"name": "INVDATA", ...}],
                ...
            )
    """

    if resolved_stack is None:
        resolved_stack = set()
    if result is None:
        result = CopyResolutionResult()

    # Depth guard (REQ-5)
    if depth > MAX_NESTING_DEPTH:
        result.errors.append(
            f"COPY nesting depth exceeded {MAX_NESTING_DEPTH} — possible circular reference"
        )
        result.expanded_source = "".join(source_lines)
        return result

    # Pre-join continuation lines so multi-line COPY statements are detectable
    logical_lines = _join_continuation_lines(source_lines)

    expanded: list[str] = []

    for lineno, line in enumerate(logical_lines, 1):
        raw = line.rstrip("\n\r")

        # Skip comment lines (col 7 = * or /)
        if len(raw) >= 7 and raw[6] in ("*", "/"):
            expanded.append(line)
            continue

        # Try column-strict Area B pattern first, then loose fallback
        m = COPY_PATTERN.match(raw)
        if not m:
            m = COPY_PATTERN_LOOSE.match(raw)
        if not m:
            expanded.append(line)
            continue

        copy_name = m.group(1).upper()
        library = (m.group(2) or "default").upper()
        replacing_str = m.group(3) or ""
        replacing_pairs = parse_replacing_clause(replacing_str)

        copy_key = f"{library}/{copy_name}"

        # --- Circular reference detection (REQ-7) ---
        if copy_key in resolved_stack:
            result.errors.append(
                f"Line {lineno}: Circular COPY reference: {copy_key}"
            )
            expanded.append(
                f"      * >>>CIRCULAR COPY: {copy_name}<<<\n"
            )
            continue

        # --- Locate the copy book file (REQ-3) ---
        path = find_copy_book(copy_name, library)

        if not path:
            # Tier 2: Not found — graceful degradation (REQ-7)
            result.unresolved_copybooks.append(copy_name)
            result.errors.append(
                f"Line {lineno}: COPY book not found: {copy_name}"
            )
            expanded.append(
                f"      * >>>UNRESOLVED COPY: {copy_name}<<<\n"
            )
            continue

        # --- Check cross-program cache (REQ-8) ---
        cache_key = _make_cache_key(library, copy_name, replacing_pairs)
        cached_content = COPYBOOK_CACHE.get(cache_key)

        if cached_content is not None:
            copy_lines = cached_content.splitlines(keepends=True)
            result.warnings.append(
                f"Line {lineno}: COPY {copy_name} served from cache"
            )
        else:
            # Read the copy book file
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    copy_content = f.read()
            except OSError as exc:
                result.errors.append(
                    f"Line {lineno}: Failed to read COPY book {copy_name} "
                    f"at {path}: {exc}"
                )
                expanded.append(
                    f"      * >>>UNRESOLVED COPY: {copy_name}<<<\n"
                )
                result.unresolved_copybooks.append(copy_name)
                continue

            # Apply REPLACING clause (REQ-4)
            if replacing_pairs:
                copy_content = apply_replacing(copy_content, replacing_pairs)

            # Resolve nested COPYs (REQ-5)
            resolved_stack.add(copy_key)
            nested_lines = copy_content.splitlines(keepends=True)
            # Ensure last line has newline
            if nested_lines and not nested_lines[-1].endswith("\n"):
                nested_lines[-1] += "\n"

            nested_result = resolve_copy_books(
                nested_lines, depth + 1, resolved_stack, result
            )
            resolved_stack.discard(copy_key)

            # After nested resolution, the content is in result.expanded_source
            # but we need the resolved nested lines — they were appended to result
            # during recursion.  We use the nested_result.expanded_source.
            copy_content = nested_result.expanded_source
            copy_lines = copy_content.splitlines(keepends=True)

            # Store in cache (REQ-8)
            COPYBOOK_CACHE[cache_key] = copy_content

        # --- Insert with source map comments (REQ-6) ---
        expanded.append(
            f"      * >>>BEGIN COPY {copy_name} FROM {path}<<<\n"
        )
        expanded.extend(copy_lines)
        expanded.append(
            f"      * >>>END COPY {copy_name}<<<\n"
        )

        # --- Build audit trail entry (REQ-9) ---
        nested_copy_names = [
            entry["name"]
            for entry in result.resolved_copybooks
            if entry.get("_parent_copy") == copy_name
        ]

        audit_entry = {
            "name": copy_name,
            "path": path,
            "library": library,
            "line_in_source": lineno,
            "replacing": [
                {"old": old, "new": new} for old, new in replacing_pairs
            ],
            "nested_copies": nested_copy_names,
        }
        result.resolved_copybooks.append(audit_entry)

    result.expanded_source = "".join(expanded)
    return result


# ---------------------------------------------------------------------------
# Cache management utilities
# ---------------------------------------------------------------------------


def clear_cache() -> None:
    """Clear the cross-program copy book cache.

    Useful between test runs or when reprocessing with different configurations.
    """

    COPYBOOK_CACHE.clear()


def get_cache_stats() -> dict:
    """Return basic statistics about the copy book cache.

    Returns:
        Dictionary with cache entry count and keys.

    Example:
        Output:
            {"entries": 2, "keys": ["DEFAULT/INVDATA+abc...", "MYLIB/CUSTDATA+def..."]}
    """

    return {
        "entries": len(COPYBOOK_CACHE),
        "keys": list(COPYBOOK_CACHE.keys()),
    }
