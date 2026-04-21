"""Factory for selecting the active COBOL parser backend."""

from app.core.config import AppConfig
from app.parsers.antlr_parser import AntlrCobolParser
from app.parsers.base import CobolParser
from app.parsers.cobol_parser import ParserLayer


def create_parser(config: AppConfig) -> CobolParser:
    """
    Create the configured parser backend.

    Args:
        config: Application configuration containing the parser backend name.

    Returns:
        A parser implementation matching the selected backend.

    Example:
        Input:
            AppConfig(parser_backend="heuristic")
        Output:
            ParserLayer()
    """

    backend = config.parser_backend.lower()
    if backend == "heuristic":
        return ParserLayer()
    if backend == "antlr":
        return AntlrCobolParser()
    raise ValueError(f"Unsupported parser backend: {config.parser_backend}")

