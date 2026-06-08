import type {
  DiffLine,
  DiffSummary,
  ExecutionCaptureView,
  FailedTest,
  LayerScores,
  ProjectFileSummary,
  ProjectFileTestResult,
  ProjectTestSummary,
  RunDiagnostics,
  ScenarioExecutionDetail,
  TestInputSet,
  ExecutionMode,
  RecommendedAction,
  TestingAgentRunResult,
  ToolchainBannerTone,
  ToolchainGuidance,
  TestingRunListItem,
  TestingRunStatus,
  TestingTargetType,
  ToolchainStatusMeta,
} from "./testingAgentTypes";

function num(v: unknown, fallback = 0): number {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function str(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}

function asStatus(v: unknown): TestingRunStatus {
  const s = str(v, "failed").toLowerCase();
  if (s === "passed" || s === "partial" || s === "failed" || s === "not_run") return s;
  return "failed";
}

function asTargetType(v: unknown): TestingTargetType {
  const t = str(v, "single_file").toLowerCase();
  return t === "project" ? "project" : "single_file";
}

function asExecutionMode(v: unknown): ExecutionMode | undefined {
  const m = str(v, "").toLowerCase();
  if (m === "live" || m === "snapshot" || m === "mixed" || m === "unavailable") return m;
  return undefined;
}

function mapToolProbe(v: unknown): ToolchainStatusMeta["cobc"] {
  if (!v || typeof v !== "object") return { available: false };
  const o = v as Record<string, unknown>;
  return {
    available: Boolean(o.available),
    detail: o.detail != null ? str(o.detail) : undefined,
    error: o.error != null ? str(o.error) : null,
  };
}

function asRecommendedAction(v: unknown): RecommendedAction {
  const a = str(v, "none").toLowerCase();
  if (
    a === "run_live" ||
    a === "use_snapshot" ||
    a === "install_toolchain" ||
    a === "contact_admin" ||
    a === "review_mixed" ||
    a === "none"
  ) {
    return a;
  }
  return "none";
}

function asBannerTone(v: unknown): ToolchainBannerTone {
  const t = str(v, "neutral").toLowerCase();
  if (t === "success" || t === "info" || t === "warning") return t;
  return "neutral";
}

/** Map GET /testing/toolchain-status payload for the banner. */
export function normalizeToolchainGuidance(raw: Record<string, unknown>): ToolchainGuidance {
  const missing = Array.isArray(raw.missing_tools)
    ? raw.missing_tools.map((t) => str(t)).filter(Boolean)
    : [];
  return {
    cobc_available: Boolean(raw.cobc_available ?? (raw.cobc as Record<string, unknown>)?.available),
    javac_available: Boolean(raw.javac_available ?? (raw.javac as Record<string, unknown>)?.available),
    java_available: Boolean(raw.java_available ?? (raw.java as Record<string, unknown>)?.available),
    live_execution_available: Boolean(raw.live_execution_available ?? raw.live_ready),
    fallback_mode: Boolean(raw.fallback_mode),
    snapshots_available: Boolean(raw.snapshots_available),
    missing_tools: missing,
    recommended_action: asRecommendedAction(raw.recommended_action),
    banner_tone: asBannerTone(raw.banner_tone),
    banner_title: str(raw.banner_title, "Execution environment"),
    banner_subtext: str(raw.banner_subtext),
    action_label: str(raw.action_label),
  };
}

function mapToolchainStatus(raw: unknown): ToolchainStatusMeta | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const o = raw as Record<string, unknown>;
  const missing = Array.isArray(o.missing_tools) ? o.missing_tools.map((t) => str(t)).filter(Boolean) : [];
  return {
    cobc: mapToolProbe(o.cobc),
    javac: mapToolProbe(o.javac),
    java: mapToolProbe(o.java),
    live_ready: Boolean(o.live_ready),
    missing_tools: missing,
  };
}

function mapProjectSummary(raw: unknown): ProjectTestSummary | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const o = raw as Record<string, unknown>;
  const summariesRaw = o.file_summaries;
  const file_summaries: ProjectFileSummary[] = [];
  if (Array.isArray(summariesRaw)) {
    for (const row of summariesRaw) {
      if (!row || typeof row !== "object") continue;
      const s = row as Record<string, unknown>;
      const st = str(s.status, "failed").toLowerCase();
      file_summaries.push({
        path: str(s.path),
        filename: str(s.filename),
        program_name: str(s.program_name),
        status: st === "passed" || st === "partial" || st === "failed" ? st : "skipped",
        diff_percentage: s.diff_percentage != null ? num(s.diff_percentage) : undefined,
        lines_diverged: s.lines_diverged != null ? num(s.lines_diverged) : undefined,
        failed_scenarios: s.failed_scenarios != null ? num(s.failed_scenarios) : undefined,
        retry_scope: s.retry_scope != null ? str(s.retry_scope) : undefined,
        reason: s.reason != null ? str(s.reason) : undefined,
      });
    }
  }
  return {
    project_name: str(o.project_name),
    files_total: num(o.files_total),
    files_tested: num(o.files_tested),
    files_passed: num(o.files_passed),
    files_partial: num(o.files_partial),
    files_failed: num(o.files_failed),
    files_skipped: num(o.files_skipped),
    aggregate_diff_percentage:
      o.aggregate_diff_percentage != null ? num(o.aggregate_diff_percentage) : undefined,
    aggregate_lines_diverged:
      o.aggregate_lines_diverged != null ? num(o.aggregate_lines_diverged) : undefined,
    file_summaries,
  };
}

function mapFileResults(raw: unknown): ProjectFileTestResult[] | undefined {
  if (!Array.isArray(raw) || raw.length === 0) return undefined;
  const out: ProjectFileTestResult[] = [];
  for (const row of raw) {
    if (!row || typeof row !== "object") continue;
    const r = row as Record<string, unknown>;
    const mapped = normalizeBehavioralDiffResponse(r);
    out.push({
      ...mapped,
      path: str(r.path),
      filename: str(r.filename),
    });
  }
  return out.length ? out : undefined;
}

function mapHighlight(row: unknown): DiffLine | null {
  if (!row || typeof row !== "object") return null;
  const r = row as Record<string, unknown>;
  return {
    line: num(r.line, 0),
    cobol: str(r.cobol),
    java: str(r.java),
    failure_kind: r.failure_kind != null ? str(r.failure_kind) : undefined,
    likely_paragraph: r.likely_paragraph != null ? str(r.likely_paragraph) : null,
    attribution_method: r.attribution_method != null ? str(r.attribution_method) : undefined,
  };
}

function mapDiffSummary(raw: unknown): DiffSummary {
  const o = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const highlights: DiffLine[] = [];
  if (Array.isArray(o.highlights)) {
    for (const h of o.highlights) {
      const mapped = mapHighlight(h);
      if (mapped) highlights.push(mapped);
    }
  }
  const firstIdx = o.first_mismatch_index;
  const comparison_status = str(o.comparison_status);
  const validComparison =
    comparison_status === "comparable" ||
    comparison_status === "not_comparable" ||
    comparison_status === "execution_failed" ||
    comparison_status === "blocked"
      ? comparison_status
      : undefined;
  return {
    lines_compared: num(o.lines_compared),
    lines_matched: num(o.lines_matched),
    lines_diverged: num(o.lines_diverged),
    highlights,
    diff_percentage:
      o.diff_percentage === null ? null : o.diff_percentage != null ? num(o.diff_percentage) : undefined,
    comparison_status: validComparison,
    parity_blocked: o.parity_blocked != null ? Boolean(o.parity_blocked) : undefined,
    first_mismatch_index:
      firstIdx === null || firstIdx === undefined
        ? null
        : Number.isFinite(Number(firstIdx))
          ? Number(firstIdx)
          : null,
  };
}

function mapInputSet(raw: unknown): TestInputSet {
  const o = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const scenariosRaw = o.scenarios;
  const scenarios: TestInputSet["scenarios"] = [];
  if (Array.isArray(scenariosRaw)) {
    for (const s of scenariosRaw) {
      if (!s || typeof s !== "object") continue;
      const row = s as Record<string, unknown>;
      scenarios.push({
        id: str(row.id ?? row.scenario_id, "scenario"),
        label: str(row.label, str(row.id)),
        inputs:
          row.inputs && typeof row.inputs === "object" && !Array.isArray(row.inputs)
            ? (row.inputs as Record<string, string>)
            : {},
      });
    }
  }
  return {
    id: str(o.id, "behavioral-set"),
    name: str(o.name, "Behavioral scenarios"),
    scenarios,
  };
}

function mapExecutionCapture(raw: unknown): ExecutionCaptureView | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const o = raw as Record<string, unknown>;
  return {
    stdout: o.stdout != null ? str(o.stdout) : undefined,
    stderr: o.stderr != null ? str(o.stderr) : undefined,
    execution_status: o.execution_status != null ? str(o.execution_status) : undefined,
    error: o.error != null ? str(o.error) : null,
    compile_stdout: o.compile_stdout != null ? str(o.compile_stdout) : undefined,
    compile_stderr: o.compile_stderr != null ? str(o.compile_stderr) : undefined,
    mode: o.mode != null ? str(o.mode) : undefined,
    exit_code: o.exit_code != null ? num(o.exit_code) : undefined,
  };
}

function mapExecutionDetails(raw: unknown): ScenarioExecutionDetail[] | undefined {
  if (!Array.isArray(raw) || raw.length === 0) return undefined;
  const out: ScenarioExecutionDetail[] = [];
  for (const row of raw) {
    if (!row || typeof row !== "object") continue;
    const r = row as Record<string, unknown>;
    out.push({
      scenario_id: str(r.scenario_id, "default"),
      scripted_input: r.scripted_input != null ? str(r.scripted_input) : undefined,
      cobol_execution: mapExecutionCapture(r.cobol_execution),
      java_execution: mapExecutionCapture(r.java_execution),
    });
  }
  return out.length ? out : undefined;
}

function optLayerScore(v: unknown): number | null {
  if (v == null) return null;
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return null;
  return Math.max(0, Math.min(100, Math.round(n)));
}

function mapLayerScores(raw: unknown): LayerScores | null | undefined {
  if (raw == null) return undefined;
  if (typeof raw !== "object") return undefined;
  const o = raw as Record<string, unknown>;
  return {
    compile_health: optLayerScore(o.compile_health),
    runtime_health: optLayerScore(o.runtime_health),
    behavioral_parity: optLayerScore(o.behavioral_parity),
    retry_stability: optLayerScore(o.retry_stability),
    attribution_confidence: optLayerScore(o.attribution_confidence),
  };
}

function mapRunDiagnostics(raw: unknown): RunDiagnostics | null | undefined {
  if (raw == null) return undefined;
  if (typeof raw !== "object") return undefined;
  const o = raw as Record<string, unknown>;
  const affected = o.affected_paragraphs;
  const paragraphs = Array.isArray(affected) ? affected.map((p) => str(p)).filter(Boolean) : undefined;
  const layersApplicable =
    o.layers_applicable && typeof o.layers_applicable === "object"
      ? (o.layers_applicable as Record<string, boolean>)
      : undefined;
  return {
    target_type: o.target_type != null ? str(o.target_type) : undefined,
    program_name: o.program_name != null ? str(o.program_name) : undefined,
    run_id: o.run_id != null ? str(o.run_id) : undefined,
    created_at: o.created_at != null ? str(o.created_at) : undefined,
    behavioral_status: o.behavioral_status != null ? str(o.behavioral_status) : undefined,
    execution_mode: o.execution_mode != null ? str(o.execution_mode) : undefined,
    cobol_execution_status:
      o.cobol_execution_status != null ? str(o.cobol_execution_status) : undefined,
    java_execution_status: o.java_execution_status != null ? str(o.java_execution_status) : undefined,
    cobol_compile_status: o.cobol_compile_status != null ? str(o.cobol_compile_status) : undefined,
    java_compile_status: o.java_compile_status != null ? str(o.java_compile_status) : undefined,
    cobol_runtime_status: o.cobol_runtime_status != null ? str(o.cobol_runtime_status) : undefined,
    java_runtime_status: o.java_runtime_status != null ? str(o.java_runtime_status) : undefined,
    stdout_diff_percentage:
      o.stdout_diff_percentage != null ? num(o.stdout_diff_percentage) : null,
    first_mismatch_line: o.first_mismatch_line != null ? num(o.first_mismatch_line) : null,
    lines_compared: o.lines_compared != null ? num(o.lines_compared) : undefined,
    lines_matched: o.lines_matched != null ? num(o.lines_matched) : undefined,
    lines_diverged: o.lines_diverged != null ? num(o.lines_diverged) : undefined,
    failure_reason: o.failure_reason != null ? str(o.failure_reason) : null,
    affected_paragraphs: paragraphs,
    retry_scope: o.retry_scope != null ? str(o.retry_scope) : undefined,
    infrastructure_blocker:
      o.infrastructure_blocker != null ? Boolean(o.infrastructure_blocker) : undefined,
    layers_applicable: layersApplicable,
  };
}

function mapLayeredScoringFields(raw: Record<string, unknown>): Pick<
  TestingAgentRunResult,
  "qscore" | "layer_scores" | "primary_failure_layer" | "run_diagnostics"
> {
  const qscoreRaw = raw.qscore;
  const qscore =
    qscoreRaw == null
      ? qscoreRaw === null
        ? null
        : undefined
      : optLayerScore(qscoreRaw);
  const layer_scores = mapLayerScores(raw.layer_scores);
  const primary_failure_layer =
    raw.primary_failure_layer != null ? str(raw.primary_failure_layer) : raw.primary_failure_layer === null ? null : undefined;
  const run_diagnostics = mapRunDiagnostics(raw.run_diagnostics);
  return { qscore, layer_scores, primary_failure_layer, run_diagnostics };
}

function mapFailedTests(raw: unknown): FailedTest[] {
  if (!Array.isArray(raw)) return [];
  const out: FailedTest[] = [];
  for (const t of raw) {
    if (!t || typeof t !== "object") continue;
    const row = t as Record<string, unknown>;
    const sev = str(row.severity, "high");
    out.push({
      id: str(row.id, "BEH_UNKNOWN"),
      scenario_id: str(row.scenario_id, "default"),
      description: str(row.description),
      severity: sev === "critical" || sev === "medium" || sev === "low" ? sev : "high",
      failure_kind: row.failure_kind != null ? str(row.failure_kind) : undefined,
      likely_paragraph: row.likely_paragraph != null ? str(row.likely_paragraph) : null,
    });
  }
  return out;
}

/** Map backend snake_case payload → UI TestingAgentRunResult. */
export function normalizeBehavioralDiffResponse(raw: Record<string, unknown>): TestingAgentRunResult {
  const affected = raw.affected_paragraphs;
  const paragraphs = Array.isArray(affected) ? affected.map((p) => str(p)).filter(Boolean) : [];

  const failureMapping =
    raw.failure_mapping && typeof raw.failure_mapping === "object"
      ? (raw.failure_mapping as TestingAgentRunResult["failure_mapping"])
      : undefined;

  const fileResults = mapFileResults(raw.file_results);
  const projectSummary = mapProjectSummary(raw.project_summary);

  const base: TestingAgentRunResult = {
    target_type: asTargetType(raw.target_type ?? (fileResults ? "project" : "single_file")),
    target_id: raw.target_id != null ? str(raw.target_id) : undefined,
    project_id: raw.project_id != null ? str(raw.project_id) : undefined,
    run_id: str(raw.run_id, "run-unknown"),
    program_name: str(raw.program_name, "UNKNOWN"),
    created_at: str(raw.created_at, new Date().toISOString()),
    status: asStatus(raw.status),
    execution_mode: asExecutionMode(raw.execution_mode),
    fallback_mode: raw.fallback_mode != null ? Boolean(raw.fallback_mode) : undefined,
    toolchain_status: mapToolchainStatus(raw.toolchain_status),
    input_set: mapInputSet(raw.input_set),
    cobol_output: str(raw.cobol_output),
    java_output: str(raw.java_output),
    diff_summary: mapDiffSummary(raw.diff_summary),
    failed_tests: mapFailedTests(raw.failed_tests),
    failure_reason: raw.failure_reason != null ? str(raw.failure_reason) : null,
    comparison_status:
      raw.comparison_status != null ? (str(raw.comparison_status) as TestingAgentRunResult["comparison_status"]) : undefined,
    parity_blocked: raw.parity_blocked != null ? Boolean(raw.parity_blocked) : undefined,
    artifact_provenance:
      raw.artifact_provenance && typeof raw.artifact_provenance === "object"
        ? (raw.artifact_provenance as TestingAgentRunResult["artifact_provenance"])
        : undefined,
    stdin_resolution_notes: Array.isArray(raw.stdin_resolution_notes)
      ? raw.stdin_resolution_notes.map((n) => str(n)).filter(Boolean)
      : undefined,
    execution_details: mapExecutionDetails(raw.execution_details),
    affected_paragraphs: paragraphs,
    retry_scope: str(raw.retry_scope),
    failure_mapping: failureMapping,
    file_results: fileResults,
    project_summary: projectSummary,
    ...mapLayeredScoringFields(raw),
  };
  return hydrateRunForDisplay(base);
}

/**
 * Map API status to a score/label status when stdout was compared via snapshot or live
 * but the raw status is still `not_run` (e.g. execution_mode forced unavailable).
 */
export function resolveEffectiveBehavioralStatus(
  status: string | undefined,
  opts: {
    execution_mode?: ExecutionMode;
    fallback_mode?: boolean;
    lines_compared?: number;
    lines_diverged?: number;
    failed_count?: number;
    parity_blocked?: boolean;
    comparison_status?: string;
  },
): TestingRunStatus {
  const raw = String(status ?? "failed").toLowerCase();
  if (raw === "passed" || raw === "partial" || raw === "failed") {
    return raw;
  }
  const compared = Number(opts.lines_compared) || 0;
  const comparisonStatus = String(opts.comparison_status ?? "").toLowerCase();
  if (
    opts.parity_blocked ||
    comparisonStatus === "compile_failure" ||
    comparisonStatus === "both_empty_stdout" ||
    comparisonStatus === "output_asymmetry" ||
    comparisonStatus === "execution_failed"
  ) {
    return "failed";
  }
  if (raw !== "not_run" || compared <= 0) {
    return raw === "not_run" ? "not_run" : "failed";
  }
  const failed = Number(opts.failed_count) || 0;
  const diverged = Number(opts.lines_diverged) || 0;
  if (failed > 0) return "failed";
  if (diverged > 0) return "partial";
  return "passed";
}

/** Infer live vs snapshot when API left execution_mode unavailable but stdout was compared. */
export function resolveEffectiveExecutionMode(
  mode: ExecutionMode | undefined,
  opts: {
    effectiveStatus?: TestingRunStatus;
    fallback_mode?: boolean;
    lines_compared?: number;
  },
): ExecutionMode | undefined {
  if (mode && mode !== "unavailable") return mode;
  const compared = Number(opts.lines_compared) || 0;
  const st = opts.effectiveStatus;
  if (compared <= 0 || !st || st === "not_run") return mode;
  if (mode === "live" || mode === "snapshot" || mode === "mixed") return mode;
  if (opts.fallback_mode) return "snapshot";
  return "live";
}

/** Status / execution / diff lines used for the reliability decision panel (project overview uses root). */
export function getBehavioralDisplayFields(
  run: TestingAgentRunResult | null,
  displayRun: TestingAgentRunResult | null,
  selectedFilePath: string | null,
): {
  status?: TestingRunStatus;
  execution_mode?: ExecutionMode;
  lines_compared?: number;
  fallback_mode?: boolean;
} {
  if (!run || !displayRun) {
    return {};
  }
  const source =
    run.target_type === "project" && !selectedFilePath ? run : displayRun;
  const linesCompared = source.diff_summary?.lines_compared;
  const effective = resolveEffectiveBehavioralStatus(source.status, {
    execution_mode: source.execution_mode,
    fallback_mode: source.fallback_mode,
    lines_compared: linesCompared,
    lines_diverged: source.diff_summary?.lines_diverged,
    failed_count: source.failed_tests?.length ?? 0,
    parity_blocked: source.diff_summary?.parity_blocked ?? source.parity_blocked,
    comparison_status: source.diff_summary?.comparison_status ?? source.comparison_status,
  });
  const execution_mode = resolveEffectiveExecutionMode(source.execution_mode, {
    effectiveStatus: effective,
    fallback_mode: source.fallback_mode,
    lines_compared: linesCompared,
  });
  return {
    status: effective,
    execution_mode,
    lines_compared: linesCompared,
    fallback_mode: source.fallback_mode,
  };
}

function hydrateBehavioralSlice(
  status: TestingRunStatus,
  execution_mode: ExecutionMode | undefined,
  fallback_mode: boolean | undefined,
  diff_summary: DiffSummary | undefined,
  failed_tests: FailedTest[] | undefined,
): { status: TestingRunStatus; execution_mode?: ExecutionMode } {
  const lines_compared = diff_summary?.lines_compared;
  const effective = resolveEffectiveBehavioralStatus(status, {
    execution_mode,
    fallback_mode,
    lines_compared,
    lines_diverged: diff_summary?.lines_diverged,
    failed_count: failed_tests?.length ?? 0,
    parity_blocked: diff_summary?.parity_blocked,
    comparison_status: diff_summary?.comparison_status,
  });
  const mode = resolveEffectiveExecutionMode(execution_mode, {
    effectiveStatus: effective,
    fallback_mode,
    lines_compared,
  });
  return { status: effective, execution_mode: mode };
}

/** Normalize root + per-file status/mode so all UI paths see the same effective values. */
export function hydrateRunForDisplay(run: TestingAgentRunResult): TestingAgentRunResult {
  const root = hydrateBehavioralSlice(
    run.status,
    run.execution_mode,
    run.fallback_mode,
    run.diff_summary,
    run.failed_tests,
  );
  const file_results = run.file_results?.map((f) => {
    const slice = hydrateBehavioralSlice(
      f.status,
      f.execution_mode,
      f.fallback_mode,
      f.diff_summary,
      f.failed_tests,
    );
    return {
      ...f,
      status: slice.status,
      execution_mode: slice.execution_mode ?? f.execution_mode,
    };
  });
  return {
    ...run,
    status: root.status,
    execution_mode: root.execution_mode ?? run.execution_mode,
    file_results,
  };
}

/** Apply effective behavioral status/mode for summary bars, diff panel, and run list. */
export function withEffectiveBehavioralFields(
  run: TestingAgentRunResult,
  displayRun: TestingAgentRunResult,
  selectedFilePath: string | null,
): TestingAgentRunResult {
  const fields = getBehavioralDisplayFields(run, displayRun, selectedFilePath);
  return {
    ...displayRun,
    status: fields.status ?? displayRun.status,
    execution_mode: fields.execution_mode ?? displayRun.execution_mode,
    fallback_mode: fields.fallback_mode ?? displayRun.fallback_mode,
  };
}

/** Project runs: return per-file slice for panels when a file is selected; otherwise aggregate run. */
export function resolveDisplayRun(
  run: TestingAgentRunResult,
  selectedFilePath: string | null,
): TestingAgentRunResult {
  if (run.target_type !== "project" || !selectedFilePath || !run.file_results?.length) {
    return run;
  }
  const file = run.file_results.find((f) => f.path === selectedFilePath);
  if (!file) return run;
  return {
    ...file,
    target_type: "project",
    target_id: run.target_id,
    project_id: run.project_id,
    file_results: run.file_results,
    project_summary: run.project_summary,
    program_name: `${run.program_name} — ${file.program_name}`,
  };
}

export function runResultToListItem(run: TestingAgentRunResult): TestingRunListItem {
  const effectiveStatus = resolveEffectiveBehavioralStatus(run.status, {
    execution_mode: run.execution_mode,
    fallback_mode: run.fallback_mode,
    lines_compared: run.diff_summary?.lines_compared,
    lines_diverged: run.diff_summary?.lines_diverged,
    failed_count: run.failed_tests?.length ?? 0,
    parity_blocked: run.diff_summary?.parity_blocked ?? run.parity_blocked,
    comparison_status: run.diff_summary?.comparison_status ?? run.comparison_status,
  });
  const failed =
    run.target_type === "project" && run.project_summary
      ? run.project_summary.files_failed + run.project_summary.files_partial
      : run.failed_tests.length;
  return {
    run_id: run.run_id,
    program_name: run.program_name,
    created_at: run.created_at,
    status: effectiveStatus,
    scenario_count:
      run.target_type === "project" && run.project_summary
        ? run.project_summary.files_tested
        : run.input_set.scenarios.length,
    failed_count: failed,
    target_type: run.target_type,
  };
}

export function runsToListItems(runs: TestingAgentRunResult[]): TestingRunListItem[] {
  return runs.map(runResultToListItem);
}

export function findRunById(runs: TestingAgentRunResult[], runId: string | null): TestingAgentRunResult | null {
  if (!runId) return null;
  return runs.find((r) => r.run_id === runId) ?? null;
}

export function prependRun(runs: TestingAgentRunResult[], run: TestingAgentRunResult): TestingAgentRunResult[] {
  const filtered = runs.filter((r) => r.run_id !== run.run_id);
  return [run, ...filtered];
}
