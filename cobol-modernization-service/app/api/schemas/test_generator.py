"""Schemas for business-rules JUnit test generation."""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class BusinessRuleInput(BaseModel):
    """Single business rule (string fields or free-form dict)."""

    id: Optional[str] = None
    text: Optional[str] = None
    rule: Optional[str] = None
    description: Optional[str] = None


class GenerateBusinessRulesTestsRequest(BaseModel):
    program_name: str = Field(..., description="PROGRAM-ID or Java class base name.")
    business_rules: List[Union[str, Dict[str, Any], BusinessRuleInput]] = Field(
        default_factory=list,
        description="Rules from analysis_output.business_rules or sections.",
    )
    java_source: str = Field(default="", description="Converted Java source for the program.")


class BoundaryInputMeta(BaseModel):
    rule: str
    pattern: str
    values: List[Union[int, str]]


class GenerateBusinessRulesTestsResponse(BaseModel):
    program_name: str
    test_class_name: str
    test_source: str
    test_count: int
    rules_covered: int
    rules_total: int
    boundary_inputs: List[BoundaryInputMeta]


class GenerateEdgeCaseTestsRequest(BaseModel):
    program_name: str = Field(..., description="PROGRAM-ID or Java class base name.")
    parser_json: Dict[str, Any] = Field(default_factory=dict, description="Parser-layer JSON.")
    java_source: str = Field(default="", description="Converted Java source for the program.")


class EdgeCaseMeta(BaseModel):
    type: str
    paragraph: Optional[str] = None
    field: Optional[str] = None
    values: List[Union[int, str]] = Field(default_factory=list)
    detail: Optional[str] = None


class GenerateEdgeCaseTestsResponse(BaseModel):
    program_name: str
    test_class_name: str
    test_source: str
    test_count: int
    edge_cases: List[EdgeCaseMeta]


class MethodCoverageMeta(BaseModel):
    name: str
    test_count: int


class GenerateUnitTestsRequest(BaseModel):
    program_name: str = Field(..., description="PROGRAM-ID or Java class base name.")
    parser_json: Dict[str, Any] = Field(default_factory=dict, description="Parser-layer JSON.")
    analysis_json: Dict[str, Any] = Field(default_factory=dict, description="Analysis JSON for paragraph roles.")
    java_source: str = Field(default="", description="Converted Java source for the program.")


class GenerateUnitTestsResponse(BaseModel):
    program_name: str
    test_class_name: str
    test_source: str
    test_count: int
    methods_covered: List[MethodCoverageMeta]
    coverage_strategy: str = "public methods with deterministic branch/value assertions"
