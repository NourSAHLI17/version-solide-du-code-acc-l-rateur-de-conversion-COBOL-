"""Backend: ANTLR validation + visitor merge + heuristic :class:`ParserLayer` contract."""

from __future__ import annotations

from typing import Dict, List

from app.parsers.antlr_parser import AntlrCobolParser


class HybridCobolParser:
    """Parser backend that merges grammar-backed visitor output with heuristic extraction."""

    def missing_requirements(self) -> List[str]:
        return AntlrCobolParser().missing_requirements()

    def parse(self, source_code: str) -> Dict[str, object]:
        from app.parsers.generated.parse_tree_adapter import parse_with_hybrid

        return parse_with_hybrid(source_code)
