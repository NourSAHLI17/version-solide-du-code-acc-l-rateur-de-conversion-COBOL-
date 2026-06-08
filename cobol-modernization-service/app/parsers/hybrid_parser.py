"""Backend: ANTLR validation + visitor merge + heuristic :class:`ParserLayer` contract."""

from __future__ import annotations

from typing import Dict, List

from app.parsers.antlr_parser import AntlrCobolParser


class HybridCobolParser:
    """
    Production parser backend.

    Heuristic ParserLayer owns the JSON contract; ANTLR adds grammar-backed operations
    and control-flow when the Cobol85 runtime is provisioned. Degrades to heuristic-only
    rather than failing the request when ANTLR artifacts are missing.
    """

    def missing_requirements(self) -> List[str]:
        return AntlrCobolParser().missing_requirements()

    def parse(self, source_code: str) -> Dict[str, object]:
        from app.parsers.generated.parse_tree_adapter import parse_with_hybrid

        return parse_with_hybrid(source_code)
