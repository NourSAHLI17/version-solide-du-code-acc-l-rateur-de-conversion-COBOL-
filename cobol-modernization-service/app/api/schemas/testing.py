"""Request/response schemas for the dedicated behavioral diff testing API."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

TestingTargetType = Literal["single_file", "project"]


class BehavioralScenarioInput(BaseModel):
    scenario_id: str = Field(..., description="Unique scenario id within the run.")
    label: str = Field(default="", description="Human-readable scenario label.")
    scripted_input: str = Field(default="", description="Stdin payload sent to both executables.")
    inputs: Dict[str, str] = Field(default_factory=dict, description="Optional keyed inputs (serialized if stdin empty).")


class ProjectFileArtifact(BaseModel):
    """Per-program artifacts when target_type is project."""

    path: str = Field(..., description="Relative path within the project tree.")
    filename: str = Field(default="", description="Base filename.")
    program_name: str = Field(default="", description="PROGRAM-ID or display name for this file.")
    cobol_source: str = Field(default="", description="COBOL source for this program.")
    java_source: Optional[str] = Field(default=None, description="Converted Java for this program.")
    parser_output: Optional[Dict[str, Any]] = Field(default=None, description="Parser JSON for attribution.")
    analysis_output: Optional[Dict[str, Any]] = Field(default=None, description="Analysis JSON for attribution.")
    scripted_input: str = Field(default="", description="Optional per-file stdin override.")
    cobol_snapshot_output: Optional[str] = Field(default=None, description="Per-file COBOL stdout fallback.")
    java_snapshot_output: Optional[str] = Field(default=None, description="Per-file Java stdout fallback.")


class BehavioralDiffRequest(BaseModel):
    """Run COBOL and Java with the same scripted input and diff stdout."""

    target_type: TestingTargetType = Field(
        default="single_file",
        description="single_file: one program; project: batch over files[].",
    )
    target_id: Optional[str] = Field(
        default=None,
        description="Workspace or project id from the client.",
    )
    project_id: Optional[str] = Field(
        default=None,
        description="Project id when target_type is project (alias for target_id).",
    )
    run_id: str = Field(..., description="Correlation id for the test run.")
    program_name: str = Field(..., description="PROGRAM-ID or display name.")
    files: List[ProjectFileArtifact] = Field(
        default_factory=list,
        description="Per-file artifacts when target_type is project.",
    )
    scenarios: List[BehavioralScenarioInput] = Field(
        default_factory=list,
        description="One or more scripted scenarios; if empty, scripted_input is used alone.",
    )
    scripted_input: str = Field(default="", description="Default stdin when scenarios is empty.")
    workspace_updated_at: Optional[str] = Field(
        default=None,
        description="ISO timestamp of the conversion workspace used for this run (artifact freshness).",
    )
    cobol_command: Optional[List[str]] = Field(
        default=None,
        description="Executable + args for COBOL (e.g. compiled binary path).",
    )
    java_command: Optional[List[str]] = Field(
        default=None,
        description="Executable + args for Java (e.g. java -cp . Main).",
    )
    cobol_source: Optional[str] = Field(default=None, description="COBOL source to compile with cobc when no command.")
    java_source: Optional[str] = Field(default=None, description="Java source to compile when no command.")
    copybooks: Optional[Dict[str, str]] = Field(
        default=None,
        description="Optional COPY book name → source text for live COBOL compile (single_file).",
    )
    timeout_seconds: float = Field(default=10.0, ge=0.1, le=120.0)
    fallback_mode: bool = Field(
        default=False,
        description="When true, use snapshot outputs if execution is unavailable or fails.",
    )
    baseline_test_mode: Optional[bool] = Field(
        default=None,
        description=(
            "When true, compile/run SEQUENTIAL COBOL variants for GnuCOBOL baseline testing "
            "(flat .dat files). Defaults from BEHAVIORAL_BASELINE_TEST_MODE env when omitted."
        ),
    )
    cobol_snapshot_output: Optional[str] = Field(
        default=None,
        description="Manual/reference COBOL stdout for fallback mode.",
    )
    java_snapshot_output: Optional[str] = Field(
        default=None,
        description="Manual/reference Java stdout for fallback mode.",
    )
    input_set_id: Optional[str] = None
    input_set_name: Optional[str] = None
    parser_output: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional parser JSON for paragraph-level failure attribution.",
    )
    analysis_output: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional analysis JSON (sections/roles) for attribution.",
    )


class LayerScores(BaseModel):
    """Per-layer diagnostic scores (0–100). Null when a layer does not apply."""

    compile_health: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="COBOL/Java compile and copybook/symbol readiness.",
    )
    runtime_health: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="Execution success after compile (no timeout/runtime failure).",
    )
    behavioral_parity: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="Stdout diff alignment; omitted when compile/runtime blocked.",
    )
    retry_stability: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="Consistency of outcomes and retry scope narrowness.",
    )
    attribution_confidence: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="Quality of failure mapping to paragraphs/methods.",
    )


class RunDiagnostics(BaseModel):
    """Flat diagnostic snapshot captured for a behavioral run."""

    target_type: str = "single_file"
    program_name: str = ""
    run_id: str = ""
    created_at: str = ""
    behavioral_status: str = ""
    execution_mode: str = ""
    cobol_execution_status: str = ""
    java_execution_status: str = ""
    cobol_compile_status: str = ""
    java_compile_status: str = ""
    cobol_runtime_status: str = ""
    java_runtime_status: str = ""
    stdout_diff_percentage: Optional[float] = None
    first_mismatch_line: Optional[int] = None
    lines_compared: int = 0
    lines_matched: int = 0
    lines_diverged: int = 0
    failure_reason: Optional[str] = None
    affected_paragraphs: List[str] = Field(default_factory=list)
    retry_scope: str = ""
    infrastructure_blocker: bool = False
    testing_blocker_category: Optional[str] = Field(
        default=None,
        description="Dominant blocker: toolchain | conversion_runtime | testing_layer | behavioral_drift | none",
    )
    layers_applicable: Optional[Dict[str, bool]] = None


class BehavioralLayerScoreResult(BaseModel):
    """Layered scoring output (Phase 1 contract; wired in Phase 2)."""

    qscore: int = Field(ge=0, le=100, description="Weighted diagnostic score across applicable layers.")
    layer_scores: LayerScores
    primary_failure_layer: Optional[str] = Field(
        default=None,
        description="Layer that best explains the failure (compile_health, runtime_health, etc.).",
    )
    run_diagnostics: RunDiagnostics
    layers_applicable: Dict[str, bool] = Field(default_factory=dict)


class ToolchainStatusResponse(BaseModel):
    """Toolchain probe plus banner copy for the Testing page."""

    cobc: Dict[str, Any]
    javac: Dict[str, Any]
    java: Dict[str, Any]
    live_ready: bool
    missing_tools: List[str]
    cobc_available: bool
    javac_available: bool
    java_available: bool
    live_execution_available: bool
    fallback_mode: bool = False
    snapshots_available: bool = False
    recommended_action: str = Field(
        description="run_live | use_snapshot | install_toolchain | contact_admin | review_mixed | none",
    )
    banner_tone: str = Field(description="success | info | warning | neutral")
    banner_title: str
    banner_subtext: str
    action_label: str = ""


class BehavioralDiffResponse(BaseModel):
    """TestingAgentRunResult-compatible payload."""

    target_type: str = "single_file"
    target_id: Optional[str] = None
    project_id: Optional[str] = None
    run_id: str
    program_name: str
    created_at: str
    status: str
    execution_mode: Optional[str] = Field(
        default=None,
        description="live | snapshot | mixed | unavailable — how stdout was produced.",
    )
    fallback_mode: Optional[bool] = Field(
        default=None,
        description="True when the client requested snapshot fallback.",
    )
    toolchain_status: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Probe results for cobc, javac, and java on the API host.",
    )
    input_set: Dict[str, Any]
    cobol_output: str
    java_output: str
    diff_summary: Dict[str, Any]
    failed_tests: List[Dict[str, Any]]
    failure_reason: Optional[str]
    affected_paragraphs: List[str]
    retry_scope: str
    execution_details: Optional[List[Dict[str, Any]]] = None
    failure_mapping: Optional[Dict[str, Any]] = None
    file_results: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Per-file behavioral diff results when target_type is project.",
    )
    project_summary: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Aggregate counts and per-file diff summaries for project runs.",
    )
    qscore: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="Layered diagnostic score (Phase 2+). Not populated until diff runner wiring.",
    )
    layer_scores: Optional[LayerScores] = Field(
        default=None,
        description="Per-layer sub-scores for compile, runtime, parity, retry, attribution.",
    )
    primary_failure_layer: Optional[str] = Field(
        default=None,
        description="Dominant failure layer for this run.",
    )
    run_diagnostics: Optional[RunDiagnostics] = Field(
        default=None,
        description="Captured signals used to compute layered scores.",
    )
