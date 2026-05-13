"""ANTLR parser integration layer for future grammar-based COBOL parsing."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Dict, List


class AntlrCobolParser:
    """
    Integration scaffold for an ANTLR-backed COBOL parser.

    This class provides the stable entrypoint and diagnostics for the grammar-
    based parser path. It is intentionally strict: if the ANTLR runtime,
    grammar artifacts, or adapter logic are missing, it raises a clear error
    instead of silently falling back.

    Example:
        Input:
            AntlrCobolParser().parse("PROCEDURE DIVISION.")
        Output:
            RuntimeError explaining which ANTLR setup steps are still missing.
    """

    grammar_root = Path(__file__).resolve().parents[1] / "grammars" / "cobol85"
    generated_root = Path(__file__).resolve().parent / "generated"

    def parse_and_validate(self, source_code: str) -> Dict[str, object]:
        """Alias for :meth:`parse` — run ANTLR lexer/parser validation + heuristic JSON."""
        return self.parse(source_code)

    def parse(self, source_code: str) -> Dict[str, object]:
        """
        Parse COBOL using an ANTLR-generated grammar backend.

        Args:
            source_code: Raw COBOL source code.

        Returns:
            Structured parser JSON once ANTLR integration is completed.

        Example:
            Input:
                "PROCEDURE DIVISION."
            Output:
                RuntimeError with setup guidance when ANTLR pieces are missing.
        """

        missing_requirements = self.missing_requirements()
        if missing_requirements:
            bullet_list = "; ".join(missing_requirements)
            raise RuntimeError(
                "ANTLR parser backend is scaffolded but not ready: "
                f"{bullet_list}. "
                "Generate parser artifacts from app/grammars/cobol85/Cobol85.g4, install the "
                "Python ANTLR runtime, and implement the parse-tree adapter before "
                "selecting PARSER_BACKEND=antlr."
            )

        from app.parsers.generated.parse_tree_adapter import parse_with_generated_antlr

        return parse_with_generated_antlr(source_code)

    def missing_requirements(self) -> List[str]:
        """
        List ANTLR integration requirements that are not satisfied yet.

        Returns:
            A list of human-readable missing setup items.

        Example:
            Input:
                AntlrCobolParser().missing_requirements()
            Output:
                ["missing grammar file Cobol85.g4", ...]
        """

        missing: List[str] = []

        if importlib.util.find_spec("antlr4") is None:
            missing.append("missing Python ANTLR runtime package 'antlr4'")

        # grammars-v4 cobol85 ships as a combined grammar (lexer + parser in Cobol85.g4).
        required_grammar_files = [
            self.grammar_root / "Cobol85.g4",
        ]
        for grammar_file in required_grammar_files:
            if not grammar_file.exists():
                missing.append(f"missing grammar file {grammar_file.name}")

        required_generated_files = [
            self.generated_root / "Cobol85Lexer.py",
            self.generated_root / "Cobol85Parser.py",
            self.generated_root / "Cobol85Visitor.py",
            self.generated_root / "parse_tree_adapter.py",
        ]
        for generated_file in required_generated_files:
            if not generated_file.exists():
                missing.append(f"missing generated file {generated_file.name}")

        return missing
