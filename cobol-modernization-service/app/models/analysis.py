"""Pydantic models for LLM analysis output (F52 — lenient validation)."""

from __future__ import annotations

from typing import List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class BusinessRule(BaseModel):
    model_config = ConfigDict(extra="allow")

    description: str = ""
    source_paragraph: Optional[str] = None
    rule_type: Optional[str] = None
    confidence: Optional[str] = "medium"


class RiskPoint(BaseModel):
    model_config = ConfigDict(extra="allow")

    description: str = ""
    severity: Optional[str] = "low"


class Section(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    purpose: Optional[str] = None
    role: Optional[str] = None
    paragraphs: List[str] = Field(default_factory=list)
    business_rules: List[Union[str, BusinessRule, dict]] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ComplexityTierInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    tier: str = "Standard"
    ibm_rating_equivalent: str = "0-3"
    score: int = 0
    drivers: List[str] = Field(default_factory=list)
    conversion_method: str = ""


class AnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    program_name: str
    complexity: str = "medium"
    complexity_tier: Optional[ComplexityTierInfo] = None
    business_rules: List[Union[str, BusinessRule, dict]] = Field(default_factory=list)
    complexity_drivers: List[str] = Field(default_factory=list)
    risk_points: List[RiskPoint] = Field(default_factory=list)
    sections: List[Section] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    global_purpose: Optional[str] = None
