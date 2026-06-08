"""ANTLR Cobol85 pass + optional hybrid merge with :class:`ParserLayer`.

``run_antlr_pass`` runs lexer/parser and returns the ``startRule`` context (or ``None``).

``parse_with_hybrid`` merges ANTLR visitor facts with heuristic parser JSON.

``parse_with_generated_antlr`` validates with ANTLR but keeps heuristic operations-only
(legacy ``antlr`` backend — no ANTLR operation merge).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener
from antlr4.tree.Tree import ParseTree

from app.parsers.cobol_parser import ParserLayer
from app.parsers.cobol_tree_adapter import CobolTreeAdapter
from app.parsers.hybrid_merger import HybridMerger


def grammar_source_metadata() -> Dict[str, str]:
    """Authoritative grammar layout (local clones; do not substitute remote ZIPs silently)."""

    return {
        "authoritative_reference_tree": "grammars_v4_master/cobol85",
        "service_generation_tree": "cobol-modernization-service/app/grammars/cobol85",
        "generated_python_target": "cobol-modernization-service/app/parsers/generated",
        "antlr_runtime_note": (
            "Python runtime uses the antlr4 pip package; a checked-in antlr4/ tool folder "
            "may be used for regeneration when present."
        ),
    }


class _SyntaxErrors(ErrorListener):
    """Collect ANTLR syntax error messages (lexer + parser)."""

    def __init__(self) -> None:
        self.messages: List[str] = []

    def syntaxError(
        self,
        recognizer: Any,
        offendingSymbol: Any,
        line: int,
        column: int,
        msg: str,
        e: Any,
    ) -> None:
        who = getattr(recognizer, "__class__", type(recognizer)).__name__
        self.messages.append(f"{who} line {line}:{column} {msg}")


def run_antlr_pass(source_code: str) -> Tuple[Optional[ParseTree], List[str], bool, Optional[str]]:
    """
    Run generated Cobol85 lexer/parser; returns parse tree, errors, success flag, exception text.

    Returns:
        (tree_or_none, error_messages, syntax_ok_no_listener_errors, parse_exception_or_none)
    """

    from app.parsers.generated.Cobol85Lexer import Cobol85Lexer
    from app.parsers.generated.Cobol85Parser import Cobol85Parser

    err = _SyntaxErrors()
    lexer = Cobol85Lexer(InputStream(source_code))
    lexer.removeErrorListeners()
    lexer.addErrorListener(err)

    tokens = CommonTokenStream(lexer)
    parser = Cobol85Parser(tokens)
    parser.removeErrorListeners()
    parser.addErrorListener(err)

    parse_exception: Optional[str] = None
    tree: Optional[ParseTree] = None
    try:
        tree = parser.startRule()
    except Exception as exc:  # pragma: no cover
        parse_exception = str(exc)

    ok = len(err.messages) == 0 and parse_exception is None
    return tree, list(err.messages), ok, parse_exception


def parse_with_hybrid(source_code: str) -> Dict[str, object]:
    """Hybrid backend: ANTLR syntax + tree visitor merge + heuristic JSON contract."""

    from app.parsers.antlr_parser import AntlrCobolParser

    missing = AntlrCobolParser().missing_requirements()
    # Heuristic parse always runs first — downstream stages need a stable contract even when ANTLR is absent.
    heuristic = ParserLayer().parse(source_code)

    if missing:
        # Degraded: same heuristic JSON, flagged so callers know ANTLR enrichment did not run.
        out = dict(heuristic)
        out["parser_backend"] = "hybrid_degraded"
        out["hybrid_degraded_reason"] = "; ".join(missing)
        out["antlr_syntax_ok"] = False
        out["antlr_errors"] = list(missing)
        out["antlr_adapter_revision"] = "2026-05-10"
        out["grammar_metadata"] = grammar_source_metadata()
        return out

    tree, messages, ok, parse_exc = run_antlr_pass(source_code)
    # Low-confidence ANTLR (syntax errors) still returns heuristic output; antlr_syntax_ok signals trust level.
    partial: Dict[str, Any] = {}
    if ok and tree is not None:
        adapter = CobolTreeAdapter()
        adapter.visit(tree)
        partial = adapter.as_partial_parser_dict()

    merged = HybridMerger().merge(heuristic, partial, antlr_syntax_ok=ok)
    out = dict(merged)
    out["parser_backend"] = "hybrid"
    out["antlr_errors"] = list(messages)
    if parse_exc:
        out["antlr_errors"].append(parse_exc)
    out["antlr_adapter_revision"] = "2026-05-10"
    out["grammar_metadata"] = grammar_source_metadata()
    return out


def parse_with_generated_antlr(source_code: str) -> Dict[str, object]:
    """
    ANTLR backend: grammar validation + heuristic structural JSON (no ANTLR operation merge).
    """

    from app.parsers.antlr_parser import AntlrCobolParser

    if AntlrCobolParser().missing_requirements():
        raise RuntimeError(
            "ANTLR parser backend is not provisioned. "
            + "; ".join(AntlrCobolParser().missing_requirements())
        )

    tree, messages, ok, parse_exc = run_antlr_pass(source_code)
    layer = ParserLayer()
    result = dict(layer.parse(source_code))

    result["parser_backend"] = "antlr"
    result["antlr_syntax_ok"] = ok
    result["antlr_errors"] = list(messages)
    if parse_exc:
        result["antlr_errors"].append(parse_exc)
    result["antlr_adapter_revision"] = "2026-05-10"
    result["grammar_metadata"] = grammar_source_metadata()
    _ = tree
    return result
