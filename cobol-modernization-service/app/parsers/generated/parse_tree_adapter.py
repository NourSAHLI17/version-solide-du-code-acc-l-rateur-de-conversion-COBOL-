"""Adapter stub that will translate generated ANTLR parse trees into parser JSON."""

from __future__ import annotations

from typing import Dict


def parse_with_generated_antlr(source_code: str) -> Dict[str, object]:
    """
    Convert COBOL source into parser JSON using generated ANTLR artifacts.

    Args:
        source_code: Raw COBOL source code.

    Returns:
        Parser-layer JSON once the generated lexer/parser and tree visitor are wired.

    Example:
        Input:
            "PROCEDURE DIVISION."
        Output:
            RuntimeError indicating the adapter still needs implementation.
    """

    raise RuntimeError(
        "ANTLR parse-tree adapter is scaffolded but not implemented yet. "
        "Wire generated lexer/parser classes and translate the parse tree into the "
        "project parser JSON contract."
    )
