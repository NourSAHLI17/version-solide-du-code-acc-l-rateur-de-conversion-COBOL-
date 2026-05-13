"""Facade combining semantic analysis and conversion agents."""

from typing import Dict, Tuple

from app.agents.analysis_agent import AnalysisAgent
from app.agents.conversion_agent import ConversionAgent


class ModernizationAgents:
    """
    Public façade for analysis and conversion layers.

    Example:
        Input:
            source_code="PROCEDURE DIVISION.", parser_output={}
        Output:
            analyze(...) -> semantic JSON dictionary
    """

    def __init__(
        self,
        analysis_agent: AnalysisAgent | None = None,
        conversion_agent: ConversionAgent | None = None,
    ):
        self.conversion_agent = conversion_agent or ConversionAgent()
        self.analysis_agent = analysis_agent or AnalysisAgent(
            conversion_agent=self.conversion_agent,
        )
        self.llm = self.conversion_agent.llm

    def analyze(self, source_code: str, parser_output: dict) -> Dict[str, object]:
        """Delegate semantic analysis to the dedicated analysis agent."""
        return self.analysis_agent.analyze(source_code, parser_output)

    def convert(self, source_code: str, parser_output: dict, analysis_output: str) -> str:
        """Delegate Java conversion to the dedicated conversion agent."""
        return self.conversion_agent.convert(source_code, parser_output, analysis_output)

    def build_conversion_prompt_input(
        self,
        source_code: str,
        parser_output: dict,
        analysis_output: str,
    ) -> Tuple[object, Dict[str, str]]:
        """Expose conversion prompt construction for tests and debugging."""
        return self.conversion_agent.build_conversion_prompt_input(
            source_code,
            parser_output,
            analysis_output,
        )

    def _normalize_analysis_output(self, analysis_output: str) -> Dict[str, object]:
        """Compatibility proxy for tests and existing callers."""
        return self.conversion_agent._normalize_analysis_output(analysis_output)

    def _default_conversion_config(
        self,
        parser_output: Dict[str, object],
        analysis_output: Dict[str, object],
    ) -> Dict[str, object]:
        """Compatibility proxy for tests and existing callers."""
        return self.conversion_agent._default_conversion_config(parser_output, analysis_output)

    def get_runtime_status(self) -> Dict[str, object]:
        """Expose conversion-agent runtime readiness for API status views."""
        return self.conversion_agent.get_runtime_status()
