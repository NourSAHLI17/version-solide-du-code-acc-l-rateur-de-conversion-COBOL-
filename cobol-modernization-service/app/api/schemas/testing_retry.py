"""Schemas for scoped testing retry and save gating."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.api.schemas.testing import BehavioralScenarioInput, LayerScores, RunDiagnostics


class RetryScopeMeta(BaseModel):
    scope_type: str
    scope_id: str
    scope_name: str
    reason: str
    affected_methods: List[str] = Field(default_factory=list)
    affected_paragraphs: List[str] = Field(default_factory=list)
    confidence: str = "medium"
    fallback_scope: str = "program"


class DeriveRetryScopeRequest(BaseModel):
    program_name: str = ""
    parser_json: Dict[str, Any] = Field(default_factory=dict)
    analysis_json: Dict[str, Any] = Field(default_factory=dict)
    java_source: str = ""
    failed_tests: List[Dict[str, Any]] = Field(default_factory=list)
    diff_summary: Dict[str, Any] = Field(default_factory=dict)
    scope_type: Optional[str] = None
    scope_id: Optional[str] = None


class DeriveRetryScopeResponse(BaseModel):
    retry_scope: RetryScopeMeta


class RetryConversionScopeRequest(BaseModel):
    program_name: str
    cobol_source: str = Field(default="", description="COBOL source for scoped re-conversion.")
    parser_json: Dict[str, Any] = Field(default_factory=dict)
    analysis_json: Dict[str, Any] = Field(default_factory=dict)
    java_source: str = ""
    failed_tests: List[Dict[str, Any]] = Field(default_factory=list)
    diff_summary: Dict[str, Any] = Field(default_factory=dict)
    scope_type: Optional[str] = None
    scope_id: Optional[str] = None
    previous_score: Optional[int] = None
    run_id: Optional[str] = None
    scripted_input: str = ""
    scenarios: List[BehavioralScenarioInput] = Field(default_factory=list)
    fallback_mode: bool = False
    cobol_snapshot_output: Optional[str] = None
    java_snapshot_output: Optional[str] = None
    run_validation_loop: bool = Field(
        default=False,
        description="When true, also regenerate unit/edge/business-rules tests.",
    )


class SaveGateMeta(BaseModel):
    save_state: str
    ready_to_save: bool
    score_threshold: int
    diff_threshold_percent: float
    reasons: List[str] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
    conversion_decision: str = ""


class ScoreBreakdown(BaseModel):
    behavioral_diff: int = 0
    business_rules: int = 0
    edge_cases: int = 0
    unit_tests: int = 0
    retry_stability: int = 0
    conversion_layer: Optional[int] = None


class TestSummaryMeta(BaseModel):
    behavioral_pass: bool = False
    business_rules_pass: bool = False
    edge_cases_pass: bool = False
    unit_tests_pass: bool = False
    business_rules_status: Optional[str] = None
    edge_cases_status: Optional[str] = None
    unit_tests_status: Optional[str] = None


class DiffSummaryView(BaseModel):
    match_rate: float = 0
    mismatch_count: int = 0
    diff_percentage: float = 0


class FinalDecisionRequest(BaseModel):
    program_name: str
    diff_summary: Dict[str, Any] = Field(default_factory=dict)
    failed_tests: List[Dict[str, Any]] = Field(default_factory=list)
    behavioral_status: str = "failed"
    parser_json: Dict[str, Any] = Field(default_factory=dict)
    analysis_json: Dict[str, Any] = Field(default_factory=dict)
    java_source: str = ""
    conversion_score: Optional[Any] = None
    retry_scope: Optional[Dict[str, Any]] = None
    derive_retry_scope: bool = True
    business_rules_test_result: Optional[Dict[str, Any]] = None
    edge_case_test_result: Optional[Dict[str, Any]] = None
    unit_test_result: Optional[Dict[str, Any]] = None
    validation_artifacts: Optional[Dict[str, Any]] = None
    qscore: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="Optional layered behavioral qscore from the latest diff run.",
    )
    layer_scores: Optional[LayerScores] = Field(
        default=None,
        description="Optional per-layer scores from behavioral layered scoring.",
    )
    primary_failure_layer: Optional[str] = Field(
        default=None,
        description="Dominant failure layer from layered scoring (informational).",
    )
    run_diagnostics: Optional[RunDiagnostics] = Field(
        default=None,
        description="Optional flat diagnostics snapshot from layered scoring.",
    )
    behavioral_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional full behavioral diff payload; layered fields are read when top-level fields are omitted.",
    )
    test_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional behavioral diff result (e.g. from retry); layered fields extracted when present.",
    )


class FinalDecisionResponse(BaseModel):
    program_name: str
    reliability_score: int
    decision_state: str
    save_eligible: bool
    score_breakdown: Optional[Dict[str, Any]] = None
    reason_summary: Optional[str] = None
    blockers: List[str] = Field(default_factory=list)
    diff_summary: Optional[DiffSummaryView] = None
    test_summary: Optional[TestSummaryMeta] = None
    retry_scope: Optional[Dict[str, Any]] = None
    save_gate: SaveGateMeta
    qscore: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="Layered behavioral qscore when supplied with the diff run (informational; save gate uses reliability_score).",
    )
    layer_scores: Optional[LayerScores] = Field(
        default=None,
        description="Per-layer behavioral diagnostic scores when available.",
    )
    primary_failure_layer: Optional[str] = Field(
        default=None,
        description="Primary failure layer from layered scoring when available.",
    )
    run_diagnostics: Optional[RunDiagnostics] = Field(
        default=None,
        description="Flat run diagnostics from layered scoring when available.",
    )


class ReliabilityScoreResponse(BaseModel):
    program_name: str
    reliability_score: int
    decision_state: str
    save_eligible: bool
    score_breakdown: Optional[Dict[str, Any]] = None
    reason_summary: Optional[str] = None
    blockers: List[str] = Field(default_factory=list)


class RetryConversionScopeResponse(BaseModel):
    program_name: str
    retry_scope: RetryScopeMeta
    requested_scope: Optional[str] = None
    actual_scope: Optional[str] = None
    scope_widened: bool = False
    widen_reason: Optional[str] = None
    included_paragraphs: List[str] = Field(default_factory=list)
    excluded_paragraphs: List[str] = Field(default_factory=list)
    retry_summary: Optional[str] = None
    conversion_result: Dict[str, Any]
    test_result: Dict[str, Any]
    diff_summary: Dict[str, Any]
    failed_tests: List[Dict[str, Any]]
    score: Optional[int] = None
    reliability_score: Optional[int] = None
    decision_state: Optional[str] = None
    save_eligible: bool = False
    score_breakdown: Optional[Dict[str, Any]] = None
    reason_summary: Optional[str] = None
    blockers: List[str] = Field(default_factory=list)
    score_before: Optional[int] = None
    score_delta: Optional[int] = None
    ready_to_save: bool
    save_state: str
    save_gate: SaveGateMeta
    unit_test_result: Optional[Dict[str, Any]] = None
    edge_test_result: Optional[Dict[str, Any]] = None
    business_rules_test_result: Optional[Dict[str, Any]] = None
    retried_at: str
