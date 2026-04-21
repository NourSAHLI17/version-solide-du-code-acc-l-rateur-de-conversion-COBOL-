"""Pydantic request schemas used by the public modernization API."""

from pydantic import BaseModel, Field


class CobolRequest(BaseModel):
    """
    Request body for deterministic COBOL parsing.

    Example:
        Input:
            {"source_code": "PROCEDURE DIVISION."}
        Output:
            Valid request model with `source_code` populated.
    """

    source_code: str = Field(..., description="Raw COBOL program text.")


class AnalyzeRequest(BaseModel):
    """
    Request body for semantic analysis.

    Example:
        Input:
            {"source_code": "PROCEDURE DIVISION.", "parser_output": {}}
        Output:
            Valid request model for analysis.
    """

    source_code: str = Field(..., description="Raw COBOL program text.")
    parser_output: dict = Field(..., description="Parser-layer structured output.")


class ConvertRequest(BaseModel):
    """
    Request body for Java conversion.

    Example:
        Input:
            {
              "source_code": "PROCEDURE DIVISION.",
              "parser_output": {},
              "analysis_output": "{}"
            }
        Output:
            Valid request model for the conversion agent.
    """

    source_code: str = Field(..., description="Raw COBOL program text.")
    parser_output: dict = Field(..., description="Parser-layer structured output.")
    analysis_output: str = Field(..., description="Analysis-agent JSON output.")


class ValidateRequest(BaseModel):
    """
    Request body for lightweight validation comparisons.

    Example:
        Input:
            {"expected_output": "A", "actual_output": "A"}
        Output:
            Valid validation request model.
    """

    expected_output: str = Field(..., description="Reference output from COBOL or golden tests.")
    actual_output: str = Field(..., description="Observed output from converted code.")
