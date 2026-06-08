/** Contract for the dedicated Testing Agent UI and backend integration. */

import type { ReliabilityBadgeTone } from "@/lib/reliabilityBadge";

export type TestingRunStatus = "passed" | "partial" | "failed" | "not_run";

export type ExecutionMode = "live" | "snapshot" | "mixed" | "unavailable";

export type RecommendedAction =
  | "run_live"
  | "use_snapshot"
  | "install_toolchain"
  | "contact_admin"
  | "review_mixed"
  | "none";

export type ToolchainBannerTone = "success" | "info" | "warning" | "neutral";

export interface ToolchainGuidance {
  cobc_available: boolean;
  javac_available: boolean;
  java_available: boolean;
  live_execution_available: boolean;
  fallback_mode: boolean;
  snapshots_available: boolean;
  missing_tools: string[];
  recommended_action: RecommendedAction;
  banner_tone: ToolchainBannerTone;
  banner_title: string;
  banner_subtext: string;
  action_label: string;
}

export type TestingTargetType = "single_file" | "project";

export interface ToolProbeStatus {
  available: boolean;
  detail?: string;
  error?: string | null;
}

export interface ToolchainStatusMeta {
  cobc: ToolProbeStatus;
  javac: ToolProbeStatus;
  java: ToolProbeStatus;
  live_ready: boolean;
  missing_tools: string[];
}

export interface ProjectFileSummary {
  path: string;
  filename: string;
  program_name: string;
  status: TestingRunStatus | "skipped";
  diff_percentage?: number;
  lines_diverged?: number;
  failed_scenarios?: number;
  retry_scope?: string;
  reason?: string;
}

export interface ProjectTestSummary {
  project_name: string;
  files_total: number;
  files_tested: number;
  files_passed: number;
  files_partial: number;
  files_failed: number;
  files_skipped: number;
  aggregate_diff_percentage?: number;
  aggregate_lines_diverged?: number;
  file_summaries: ProjectFileSummary[];
}

/** Per-file result nested under a project run. */
export interface ProjectFileTestResult extends TestingAgentRunResult {
  path: string;
  filename: string;
}

export interface TestInputScenario {
  id: string;
  label: string;
  /** Scripted inputs keyed by field name (e.g. MENU-CHOICE, AMOUNT). */
  inputs: Record<string, string>;
}

export interface TestInputSet {
  id: string;
  name: string;
  scenarios: TestInputScenario[];
}

export interface DiffLine {
  line: number;
  cobol: string;
  java: string;
  /** Set by failure-mapping service when available */
  failure_kind?: string;
  likely_paragraph?: string | null;
  attribution_method?: string;
}

export interface DiffSummary {
  lines_compared: number;
  lines_matched: number;
  lines_diverged: number;
  highlights: DiffLine[];
  diff_percentage?: number | null;
  first_mismatch_index?: number | null;
  comparison_status?: "comparable" | "not_comparable" | "execution_failed" | "blocked";
  parity_blocked?: boolean;
}

export interface ArtifactProvenance {
  program_name?: string;
  target_id?: string;
  target_type?: string;
  workspace_updated_at?: string;
  cobol_source_chars?: number;
  java_source_chars?: number;
  cobol_source_sha256?: string;
  java_source_sha256?: string;
}

/** Per-layer diagnostic scores (0–100) from behavioral layered scoring. */
export interface LayerScores {
  compile_health: number | null;
  runtime_health: number | null;
  behavioral_parity: number | null;
  retry_stability: number | null;
  attribution_confidence: number | null;
}

/** Flat diagnostic snapshot from layered scoring (optional on behavioral diff). */
export interface RunDiagnostics {
  target_type?: string;
  program_name?: string;
  run_id?: string;
  created_at?: string;
  behavioral_status?: string;
  execution_mode?: string;
  cobol_execution_status?: string;
  java_execution_status?: string;
  cobol_compile_status?: string;
  java_compile_status?: string;
  cobol_runtime_status?: string;
  java_runtime_status?: string;
  stdout_diff_percentage?: number | null;
  first_mismatch_line?: number | null;
  lines_compared?: number;
  lines_matched?: number;
  lines_diverged?: number;
  failure_reason?: string | null;
  affected_paragraphs?: string[];
  retry_scope?: string;
  infrastructure_blocker?: boolean;
  layers_applicable?: Record<string, boolean>;
}

export type FailedTestSeverity = "critical" | "high" | "medium" | "low";

export interface FailedTest {
  id: string;
  scenario_id: string;
  description: string;
  severity: FailedTestSeverity;
  failure_kind?: string;
  likely_paragraph?: string | null;
}

/**
 * Full result payload returned by the future testing engine for one run.
 */
export type SaveCandidateState = "ready_to_save" | "needs_more_validation" | "retry_recommended";

export interface RetryScopeMeta {
  scope_type: string;
  scope_id: string;
  scope_name: string;
  reason: string;
  affected_methods: string[];
  affected_paragraphs: string[];
  confidence: string;
  fallback_scope: string;
}

export interface SaveGateMeta {
  save_state: SaveCandidateState;
  ready_to_save: boolean;
  score_threshold: number;
  diff_threshold_percent: number;
  reasons: string[];
  blockers: string[];
  conversion_decision: string;
}

export interface ScoreBreakdown {
  behavioral_diff?: number;
  business_rules?: number;
  edge_cases?: number;
  unit_tests?: number;
  retry_stability?: number;
  conversion_layer?: number;
  [key: string]: number | undefined;
}

/** Generated-test bucket: pass = tests generated; ready = workspace artifacts exist; unavailable = cannot run. */
export type ValidationBucketStatus = "pass" | "ready" | "unavailable";

export interface TestSummaryMeta {
  behavioral_pass: boolean;
  business_rules_pass: boolean;
  edge_cases_pass: boolean;
  unit_tests_pass: boolean;
  business_rules_status?: ValidationBucketStatus;
  edge_cases_status?: ValidationBucketStatus;
  unit_tests_status?: ValidationBucketStatus;
}

/** Normalized diff view from final-decision API. */
export interface DiffSummaryMeta {
  match_rate: number;
  mismatch_count: number;
  diff_percentage?: number;
}

export interface TestingFinalDecisionResult {
  program_name: string;
  reliability_score: number;
  decision_state: SaveCandidateState;
  save_eligible: boolean;
  score_breakdown?: ScoreBreakdown;
  reason_summary?: string;
  blockers: string[];
  diff_summary?: DiffSummaryMeta;
  test_summary?: TestSummaryMeta;
  retry_scope?: RetryScopeMeta | null;
  /** True when score was estimated locally (API unavailable). */
  is_local_estimate?: boolean;
}

export interface TestingRetryResult {
  program_name: string;
  retry_scope: RetryScopeMeta;
  requested_scope?: string;
  actual_scope?: string;
  scope_widened?: boolean;
  widen_reason?: string | null;
  included_paragraphs?: string[];
  excluded_paragraphs?: string[];
  retry_summary?: string;
  reliability_score?: number;
  decision_state?: SaveCandidateState;
  save_eligible?: boolean;
  score_breakdown?: ScoreBreakdown;
  reason_summary?: string;
  blockers?: string[];
  score: number | null;
  score_before: number | null;
  score_delta: number | null;
  ready_to_save: boolean;
  save_state: SaveCandidateState;
  save_gate: SaveGateMeta;
  retried_at: string;
  test_result?: TestingAgentRunResult;
}

export interface ExecutionCaptureView {
  stdout?: string;
  stderr?: string;
  execution_status?: string;
  error?: string | null;
  compile_stdout?: string;
  compile_stderr?: string;
  mode?: string;
  exit_code?: number;
}

export interface ScenarioExecutionDetail {
  scenario_id: string;
  scripted_input?: string;
  cobol_execution?: ExecutionCaptureView;
  java_execution?: ExecutionCaptureView;
}

export interface TestingAgentRunResult {
  target_type?: TestingTargetType;
  target_id?: string;
  project_id?: string;
  run_id: string;
  program_name: string;
  created_at: string;
  status: TestingRunStatus;
  execution_mode?: ExecutionMode;
  fallback_mode?: boolean;
  toolchain_status?: ToolchainStatusMeta;
  input_set: TestInputSet;
  cobol_output: string;
  java_output: string;
  diff_summary: DiffSummary;
  failed_tests: FailedTest[];
  failure_reason: string | null;
  comparison_status?: DiffSummary["comparison_status"];
  parity_blocked?: boolean;
  artifact_provenance?: ArtifactProvenance;
  stdin_resolution_notes?: string[];
  /** Per-scenario live compile/run diagnostics from the behavioral runner. */
  execution_details?: ScenarioExecutionDetail[];
  affected_paragraphs: string[];
  /** Paragraph slice or stage hint for a future targeted retry (e.g. "3000-ADD-CUSTOMER"). */
  retry_scope: string;
  failure_mapping?: {
    scenarios_mapped?: number;
    primary_retry_scope?: string;
    attribution?: string;
    target_type?: string;
    files_mapped?: number;
    file_retry_scopes?: string[];
  };
  file_results?: ProjectFileTestResult[];
  project_summary?: ProjectTestSummary;
  /** Layered diagnostic score (0–100) when the API computed layered scoring. */
  qscore?: number | null;
  layer_scores?: LayerScores | null;
  primary_failure_layer?: string | null;
  run_diagnostics?: RunDiagnostics | null;
}

export function formatFailureLayer(layer: string | null | undefined): string {
  if (!layer) return "";
  const labels: Record<string, string> = {
    compile_health: "Compile health",
    runtime_health: "Runtime health",
    behavioral_parity: "Behavioral parity",
    retry_stability: "Retry stability",
    attribution_confidence: "Attribution confidence",
  };
  return labels[layer] ?? layer.replace(/_/g, " ");
}

export function hasLayeredScoring(
  run: Pick<TestingAgentRunResult, "qscore" | "layer_scores" | "primary_failure_layer" | "run_diagnostics">,
): boolean {
  return (
    run.qscore != null ||
    run.layer_scores != null ||
    run.primary_failure_layer != null ||
    run.run_diagnostics != null
  );
}

export function targetModeLabel(mode: TestingTargetType): string {
  return mode === "project" ? "Project" : "Single File";
}

/** List item for run history / selector (subset of a full run). */
export interface TestingRunListItem {
  run_id: string;
  program_name: string;
  created_at: string;
  status: TestingRunStatus;
  scenario_count: number;
  failed_count: number;
  target_type?: TestingTargetType;
  reliability_score?: number | null;
  force_save?: boolean;
  persistence_state?: "session" | "stable_saved" | "saved";
  persistence_label?: string;
  badge_label?: string;
  badge_display?: string;
  badge_tone?: ReliabilityBadgeTone;
}

export function statusLabel(status: TestingRunStatus): string {
  if (status === "passed") return "Passed";
  if (status === "partial") return "Partial";
  if (status === "not_run") return "Not run";
  return "Failed";
}

export function statusTone(status: TestingRunStatus): "success" | "running" | "error" {
  if (status === "passed") return "success";
  if (status === "partial") return "running";
  if (status === "not_run") return "running";
  return "error";
}

export function executionModeLabel(mode: ExecutionMode | undefined): string {
  if (mode === "live") return "Live execution";
  if (mode === "snapshot") return "Snapshot fallback";
  if (mode === "mixed") return "Mixed (live + snapshot)";
  return "Execution unavailable";
}
