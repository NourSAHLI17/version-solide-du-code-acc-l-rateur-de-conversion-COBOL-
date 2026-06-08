"""Pydantic request schemas used by the public modernization API."""

import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class CobolRequest(BaseModel):
    """Request body for deterministic COBOL parsing."""
    source_code: str = Field(..., description="Raw COBOL program text.")


class AnalyzeRequest(BaseModel):
    """Request body for semantic analysis."""

    source_code: str = Field(..., description="Raw COBOL program text.")
    parser_output: dict = Field(default_factory=dict, description="Parser-layer structured output.")
    force_refresh: bool = Field(
        False,
        description="When true, bypass file-based analysis cache and re-run the analyzer.",
    )

    @field_validator("parser_output", mode="before")
    @classmethod
    def _coerce_parser_output(cls, v: Any) -> dict:
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            text = v.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}


class ConvertRequest(BaseModel):
    """Request body for Java conversion."""
    source_code: str = Field(..., description="Raw COBOL program text.")
    parser_output: dict = Field(..., description="Parser-layer structured output.")
    analysis_output: str = Field(..., description="Analysis-agent JSON output.")
    java_profile: Optional[str] = Field(
        None,
        description="Target Java runtime: plain_java | spring_boot | java_ee | quarkus (default plain_java).",
    )


class ValidateRequest(BaseModel):
    """Request body for lightweight validation comparisons."""
    expected_output: str = Field(..., description="Reference output from COBOL or golden tests.")
    actual_output: str = Field(..., description="Observed output from converted code.")


class SegmentRequest(BaseModel):
    """Request body for source segmentation."""
    parser_output: dict = Field(..., description="Parser-layer structured output.")
    analysis_output: dict = Field(default_factory=dict, description="Analysis-agent output (optional).")


class AggregateRequest(BaseModel):
    """Request body for Java class aggregation."""
    converted_segments: list[dict] = Field(..., description="List of converted segment data.")
    parser_output: dict = Field(..., description="Original parser-layer structured output.")
    segment_manifest: dict = Field(default_factory=dict, description="Segmenter manifest for shared state.")


class TestRequest(BaseModel):
    """Request body for Stage 9 pipeline testing."""
    parser_output: dict = Field(default_factory=dict)
    analysis_output: dict = Field(default_factory=dict)
    java_source: str = Field(default="")
    cobol_source: str = Field(default="")


class SmartConvertRequest(BaseModel):
    """Unified request for conversion with optional pre-computed stages."""
    source_code: str = Field(..., description="Raw COBOL program text.")
    parser_output: Optional[dict] = Field(None, description="Optional pre-computed parser output.")
    analysis_output: Optional[str] = Field(None, description="Optional pre-computed analysis output.")
    java_profile: Optional[str] = Field(None, description="Target Java runtime profile.")


class PipelineModeRequest(BaseModel):
    """Unified endpoint for all pipeline modes."""
    cobol_source: str = Field(..., description="Raw COBOL program text.")
    mode: str = Field("full", description="Mode: full | parse_only | parse_analyse | analyse_only | convert_only | no_parse")
    parser_output: Optional[dict] = Field(None, description="Optional pre-computed parser output.")
    analysis_output: Optional[str] = Field(None, description="Optional pre-computed analysis output.")
    java_profile: Optional[str] = Field(None, description="Target Java runtime profile.")


class ProjectFile(BaseModel):
    """Represents a single file in a COBOL project."""
    filename: str = Field(..., description="Name of the file")
    content: str = Field(..., description="Content of the file.")
    file_type: str = Field("source", description="Type: 'source', 'copybook', or 'jcl'")


class ProjectRequest(BaseModel):
    """Request body for bulk project modernization (JSON-based)."""
    project_name: str = Field(..., description="Name of the project.")
    files: List[ProjectFile] = Field(..., description="Collection of project files.")


class ProjectPipelineRequest(BaseModel):
    """Request body for running pipeline over uploaded project files."""
    files: List[dict] = Field(..., description="File tree from upload endpoint.")
    mode: str = Field("full", description="Mode: full | parse_only | parse_analyse | analyse_only | convert_only | no_parse")
    java_profile: Optional[str] = Field(None, description="Target Java runtime profile for all conversions.")


class DownloadJavaRequest(BaseModel):
    """Request body for single Java file download."""
    java_source: str = Field(...)
    class_name: str = Field(default="Output")


class DownloadProjectRequest(BaseModel):
    """Request body for project ZIP download."""
    results: List[dict] = Field(...)
