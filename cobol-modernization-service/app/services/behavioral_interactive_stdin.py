"""Interactive program detection and safe stdin defaults for behavioral runs."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

_ACCEPT_RE = re.compile(r"\bACCEPT\b", re.IGNORECASE)
_JAVA_INTERACTIVE_RE = re.compile(
    r"\b(Scanner|readLine|BufferedReader|read\s*\(\s*\))",
    re.IGNORECASE,
)
_MENU_EXIT_STDIN = "0\n"


def detect_interactive_program(
    *,
    cobol_source: Optional[str] = None,
    java_source: Optional[str] = None,
    parser_output: Optional[Mapping[str, Any]] = None,
) -> bool:
    """True when COBOL/Java sources look menu- or stdin-driven."""
    if parser_output:
        for op in parser_output.get("operations") or []:
            if isinstance(op, dict) and str(op.get("type") or "").upper() == "ACCEPT":
                return True
    if cobol_source and _ACCEPT_RE.search(cobol_source):
        return True
    if java_source and _JAVA_INTERACTIVE_RE.search(java_source):
        return True
    return False


def resolve_interactive_stdin(
    stdin_text: str,
    *,
    interactive: bool,
    program_name: str = "",
) -> Tuple[str, List[str]]:
    """
    When stdin is empty and the program is interactive, inject a minimal menu-exit script.

    Returns (resolved_stdin, operator_notes).
    """
    if not interactive or stdin_text.strip():
        return stdin_text, []
    notes = [
        f"Auto-injected menu-exit stdin ({_MENU_EXIT_STDIN.strip()!r}) for interactive program "
        f"{program_name or 'unknown'} because scripted stdin was empty."
    ]
    return _MENU_EXIT_STDIN, notes


def apply_interactive_stdin_to_scenarios(
    scenarios: List[Dict[str, Any]],
    *,
    cobol_source: Optional[str] = None,
    java_source: Optional[str] = None,
    parser_output: Optional[Mapping[str, Any]] = None,
    program_name: str = "",
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Return scenarios with resolved stdin and any operator notes."""
    interactive = detect_interactive_program(
        cobol_source=cobol_source,
        java_source=java_source,
        parser_output=parser_output,
    )
    if not interactive:
        return scenarios, []

    notes: List[str] = []
    out: List[Dict[str, Any]] = []
    for sc in scenarios:
        row = dict(sc)
        resolved, sc_notes = resolve_interactive_stdin(
            str(row.get("scripted_input") or ""),
            interactive=True,
            program_name=program_name,
        )
        row["scripted_input"] = resolved
        notes.extend(sc_notes)
        out.append(row)
    return out, notes
