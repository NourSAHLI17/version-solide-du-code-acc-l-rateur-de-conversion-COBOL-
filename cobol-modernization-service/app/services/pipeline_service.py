"""Service orchestration for parser, analysis, conversion, and validation layers."""

from typing import Dict

from app.agents.facade import ModernizationAgents
from app.core.config import load_config
from app.parsers.base import CobolParser
from app.parsers.factory import create_parser
from app.validation.service import ValidationService


class PipelineService:
    """
    High-level service orchestrating the COBOL modernization pipeline.

    Example:
        Input:
            source_code="PROCEDURE DIVISION."
        Output:
            parse_cobol(...) -> parser JSON dictionary
    """

    def __init__(
        self,
        parser: CobolParser | None = None,
        agents: ModernizationAgents | None = None,
        validator: ValidationService | None = None,
    ):
        self.parser = parser or create_parser(load_config())
        self.agents = agents or ModernizationAgents()
        self.validator = validator or ValidationService()

    def parse_cobol(self, source_code: str) -> Dict[str, object]:
        """
        Parse raw COBOL source code into deterministic structure.

        Args:
            source_code: Raw COBOL source.

        Returns:
            Parser-layer JSON output.

        Example:
            Input:
                "PROCEDURE DIVISION."
            Output:
                {"program_name": None, "divisions": ["PROCEDURE DIVISION"], ...}
        """

        return self.parser.parse(source_code)

    def analyze_cobol(self, source_code: str, parser_output: dict) -> Dict[str, object]:
        """
        Run semantic analysis using raw COBOL and parser outputs.

        Args:
            source_code: Raw COBOL source.
            parser_output: Structured parser-layer JSON.

        Returns:
            Analysis-agent semantic JSON.

        Example:
            Input:
                source_code="PROCEDURE DIVISION.", parser_output={}
            Output:
                {"global_purpose": "...", "complexity": "simple", ...}
        """

        return self.agents.analyze(source_code, parser_output)

    def convert_cobol(self, source_code: str, parser_output: dict, analysis_output: str) -> Dict[str, str]:
        """
        Run the conversion agent and wrap the Java output for the API.

        Args:
            source_code: Raw COBOL source.
            parser_output: Structured parser-layer JSON.
            analysis_output: Analysis-agent output as JSON string.

        Returns:
            Dictionary with generated Java code.

        Example:
            Input:
                source_code="...", parser_output={}, analysis_output="{}"
            Output:
                {"java_code": "public class ..."}
        """

        return {"java_code": self.agents.convert(source_code, parser_output, analysis_output)}

    def validate_conversion(self, expected_output: str, actual_output: str) -> Dict[str, object]:
        """
        Compare expected and actual outputs for quick validation feedback.

        Args:
            expected_output: Golden output from the legacy system.
            actual_output: Output from the converted system.

        Returns:
            A validation report with equivalence and differences.

        Example:
            Input:
                expected_output="OK", actual_output="OK"
            Output:
                {"is_equivalent": True, "differences": [], "warnings": []}
        """

        return self.validator.validate_outputs(expected_output, actual_output)

    def get_runtime_status(self) -> Dict[str, object]:
        """
        Report backend runtime status for frontend health and cockpit pages.

        Returns:
            A backend status object covering parser, analysis, conversion, and validation readiness.

        Example:
            Input:
                get_runtime_status()
            Output:
                {
                  "api_healthy": True,
                  "parser_backend": "heuristic",
                  "llm_configured": True,
                  "conversion_available": True
                }
        """

        conversion_status = self.agents.get_runtime_status()
        return {
            "api_healthy": True,
            "parser_backend": self.parser.__class__.__name__,
            "analysis_available": True,
            "validation_available": True,
            "llm_configured": conversion_status["llm_configured"],
            "conversion_available": (
                conversion_status["llm_configured"]
                and conversion_status["prompt_template_available"]
            ),
            "llm_model": conversion_status["model_name"],
            "prompt_template_available": conversion_status["prompt_template_available"],
        }
