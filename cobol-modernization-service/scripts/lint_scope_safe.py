#!/usr/bin/env python3
"""CI lint rule: ban raw regex mutation on Java source (F43).

Usage::

    python scripts/lint_scope_safe.py          # exit 0 if clean, exit 1 with report
    python scripts/lint_scope_safe.py --fix    # show what to fix

All Java source modification in ``app/services/`` must go through
:class:`ScopeSafeSourceModifier` (``app/services/scope_safe_modifier.py``).

Banned patterns in repair files:
    re.sub(pattern, replacement, java_source)
    re.subn(pattern, replacement, java_source)
    java_source.replace(old, new) on whole file
    java_source += new_content
    lines.insert(N, content) without scope verification

Lines containing ``# scope-safe`` are exempted (explicit opt-in after review).
The ``scope_safe_modifier.py`` file itself is always exempted.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SERVICES_DIR = Path(__file__).resolve().parents[1] / "app" / "services"

_BANNED_PATTERNS = [
    re.compile(r"^\s*java_source\s*=\s*re\.sub\s*\(.*\bjava_source\b"),
    re.compile(r"^\s*java_source\s*=\s*re\.subn\s*\(.*\bjava_source\b"),
    re.compile(r"^\s*java_source\s*=\s*java_source\.replace\s*\("),
    re.compile(r"java_source\s*\+="),
    re.compile(r"lines\.insert\s*\("),
]

_EXEMPT_FILES = {
    "scope_safe_modifier.py",
    "__pycache__",
}

_EXEMPT_COMMENT = "# scope-safe"


def _scan_file(path: Path) -> list[tuple[int, str]]:
    """Return list of (line_no, line_text) for banned patterns."""
    violations: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return violations
    for i, line in enumerate(text.splitlines(), 1):
        if _EXEMPT_COMMENT in line:
            continue
        for pat in _BANNED_PATTERNS:
            if pat.search(line):
                violations.append((i, line.rstrip()))
                break
    return violations


def main() -> int:
    if not _SERVICES_DIR.is_dir():
        print(f"WARNING: {_SERVICES_DIR} not found, skipping lint.")
        return 0

    total = 0
    for py_file in sorted(_SERVICES_DIR.rglob("*.py")):
        if py_file.name in _EXEMPT_FILES:
            continue
        hits = _scan_file(py_file)
        if hits:
            rel = py_file.relative_to(_SERVICES_DIR.parent.parent)
            for line_no, line_text in hits:
                print(f"{rel}:{line_no}: {line_text.strip()}")
                total += 1

    if total:
        print(
            f"\n{total} violation(s) found. "
            f"Use ScopeSafeSourceModifier instead of regex on Java source."
        )
        print(
            "Add '# scope-safe' comment to exempt a line after manual review."
        )
        return 1

    print("scope-safe lint: OK (0 violations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
