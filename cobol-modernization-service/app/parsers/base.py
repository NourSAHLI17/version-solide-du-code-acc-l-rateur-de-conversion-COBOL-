"""Shared parser interfaces for COBOL parsing backends."""

from typing import Dict, Protocol


class CobolParser(Protocol):
    """
    Protocol implemented by all parser backends.

    Example:
        Input:
            parser.parse("PROCEDURE DIVISION.")
        Output:
            {"divisions": ["PROCEDURE DIVISION"], ...}
    """

    def parse(self, source_code: str) -> Dict[str, object]:
        """
        Parse COBOL source into deterministic structured output.

        Args:
            source_code: Raw COBOL program text.

        Returns:
            Parser-layer JSON.
        """

