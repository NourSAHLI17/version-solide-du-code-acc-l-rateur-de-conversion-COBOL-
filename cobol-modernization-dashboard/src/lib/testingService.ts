import {
  buildFinalDecisionApi,
  deriveRetryScopeApi,
  generateBusinessRulesTestsApi,
  generateEdgeCaseTestsApi,
  generateUnitTestsApi,
  retryConversionScopeApi,
  fetchTestingToolchainStatus,
  runBehavioralDiff,
} from "@/lib/api";
import { extractProgramId } from "@/lib/programId";
import {
  loadProjectWorkspace,
  type ProjectFileEntry,
  type ProjectWorkspace,
} from "@/lib/projectWorkspace";
import { getMockTestingRunById, getMockTestingRuns } from "@/lib/testingAgentMock";
import {
  findRunById,
  getBehavioralDisplayFields,
  normalizeBehavioralDiffResponse,
  normalizeToolchainGuidance,
  prependRun,
  resolveDisplayRun,
  resolveEffectiveBehavioralStatus,
  runResultToListItem,
  runsToListItems,
  withEffectiveBehavioralFields,
  hydrateRunForDisplay,
} from "@/lib/testingResponseMapper";
import type {
  DiffSummaryMeta,
  ExecutionMode,
  RetryScopeMeta,
  SaveGateMeta,
  ScoreBreakdown,
  TestSummaryMeta,
  TestingAgentRunResult,
  TestingFinalDecisionResult,
  TestingRetryResult,
  TestingTargetType,
  ToolchainGuidance,
  ValidationBucketStatus,
} from "@/lib/testingAgentTypes";
import { loadSingleWorkspace, saveSingleWorkspace, type SingleFileWorkspace } from "@/lib/singleFileWorkspace";
import { applyTestingReplayWorkspace } from "@/lib/testingReplayHandoff";
import type { TestingRunPersistenceState } from "@/lib/testingRunPersistence";
import type { AnalysisResult, ParserResult } from "@/lib/types";

export {
  findRunById,
  getBehavioralDisplayFields,
  resolveEffectiveBehavioralStatus,
  normalizeBehavioralDiffResponse,
  prependRun,
  resolveDisplayRun,
  runResultToListItem,
  runsToListItems,
  withEffectiveBehavioralFields,
  hydrateRunForDisplay,
} from "@/lib/testingResponseMapper";

export { normalizeToolchainGuidance } from "@/lib/testingResponseMapper";

export const TESTING_RUNS_STORAGE_KEY = "cobol-testing-agent-runs";
export const TESTING_MODE_STORAGE_KEY = "cobol-testing-target-mode";
export const TESTING_FALLBACK_STORAGE_KEY = "cobol-testing-fallback-mode";
export const TESTING_VALIDATION_CACHE_KEY = "cobol-testing-validation-cache";
/** Bump when persisted run shape or live-first semantics change (invalidates sessionStorage). */
export const TESTING_RUNS_SCHEMA_VERSION = 3;
export const TESTING_VALIDATION_CACHE_SCHEMA_VERSION = 2;

type PersistedRunsEnvelope = {
  schema_version: number;
  runs: TestingAgentRunResult[];
  persistence?: Record<string, TestingRunPersistenceState>;
  reliability_by_run_id?: Record<string, number>;
};

export type PersistedTestingSession = {
  sessionRuns: TestingAgentRunResult[];
  persistence: Record<string, TestingRunPersistenceState>;
  reliabilityByRunId: Record<string, number>;
};

/** Live execution is primary; snapshot fallback only when live is unavailable on the API host. */
export function resolveRunFallbackMode(
  userFallbackEnabled: boolean,
  liveExecutionAvailable: boolean,
): boolean {
  if (liveExecutionAvailable) return false;
  return userFallbackEnabled;
}

export function loadTestingFallbackMode(): boolean {
  if (typeof window === "undefined") return false;
  return sessionStorage.getItem(TESTING_FALLBACK_STORAGE_KEY) === "true";
}

export function persistTestingFallbackMode(enabled: boolean): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(TESTING_FALLBACK_STORAGE_KEY, enabled ? "true" : "false");
}

export async function fetchToolchainGuidance(options: {
  fallbackMode?: boolean;
  snapshotsAvailable?: boolean;
  executionMode?: string;
  forceRefresh?: boolean;
} = {}): Promise<ToolchainGuidance> {
  const raw = await fetchTestingToolchainStatus({
    fallbackMode: options.fallbackMode,
    snapshotsAvailable: options.snapshotsAvailable,
    executionMode: options.executionMode,
    forceRefresh: options.forceRefresh,
  });
  return normalizeToolchainGuidance(raw);
}

export function contactAdminToolchainGuidance(detail?: string): ToolchainGuidance {
  return {
    cobc_available: false,
    javac_available: false,
    java_available: false,
    live_execution_available: false,
    fallback_mode: false,
    snapshots_available: false,
    missing_tools: [],
    recommended_action: "contact_admin",
    banner_tone: "neutral",
    banner_title: "Could not verify execution environment.",
    banner_subtext:
      detail ??
      "The testing API is unreachable. Check that the backend is running, then refresh. Contact your administrator if the problem continues.",
    action_label: "Open setup instructions",
  };
}

export interface ProjectFileArtifactPayload {
  path: string;
  filename: string;
  program_name: string;
  cobol_source: string;
  java_source?: string;
  parser_output?: ParserResult | Record<string, unknown>;
  analysis_output?: AnalysisResult | Record<string, unknown>;
  scripted_input?: string;
}

export interface BehavioralDiffRequestPayload {
  target_type: TestingTargetType;
  target_id: string;
  project_id?: string;
  run_id: string;
  program_name: string;
  files?: ProjectFileArtifactPayload[];
  scenarios?: Array<{
    scenario_id: string;
    label?: string;
    scripted_input?: string;
    inputs?: Record<string, string>;
  }>;
  scripted_input?: string;
  cobol_source?: string;
  java_source?: string;
  /** COPY book name → source; optional. Parser copybook list is used when omitted. */
  copybooks?: Record<string, string>;
  parser_output?: ParserResult | Record<string, unknown>;
  analysis_output?: AnalysisResult | Record<string, unknown>;
  timeout_seconds?: number;
  fallback_mode?: boolean;
  cobol_snapshot_output?: string;
  java_snapshot_output?: string;
}

/** COPY names from parser dependencies (for UI hints; API expands copybooks at run time). */
export function copybookNamesFromParser(parser: ParserResult | Record<string, unknown> | null): string[] {
  if (!parser || typeof parser !== "object") return [];
  const deps = (parser as { dependencies?: { copybooks?: unknown } }).dependencies;
  if (!deps || !Array.isArray(deps.copybooks)) return [];
  return deps.copybooks.map((n) => String(n).trim()).filter(Boolean);
}

export function loadTestingTargetMode(): TestingTargetType {
  if (typeof window === "undefined") return "single_file";
  const raw = sessionStorage.getItem(TESTING_MODE_STORAGE_KEY);
  return raw === "project" ? "project" : "single_file";
}

export function persistTestingTargetMode(mode: TestingTargetType): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(TESTING_MODE_STORAGE_KEY, mode);
}

export function loadPersistedRuns(): TestingAgentRunResult[] {
  return loadPersistedTestingSession().sessionRuns;
}

export function loadPersistedTestingSession(): PersistedTestingSession {
  if (typeof window === "undefined") {
    return { sessionRuns: [], persistence: {}, reliabilityByRunId: {} };
  }
  try {
    const raw = sessionStorage.getItem(TESTING_RUNS_STORAGE_KEY);
    if (!raw) {
      return { sessionRuns: [], persistence: {}, reliabilityByRunId: {} };
    }
    const parsed = JSON.parse(raw) as unknown;
    if (Array.isArray(parsed)) {
      return { sessionRuns: [], persistence: {}, reliabilityByRunId: {} };
    }
    if (!parsed || typeof parsed !== "object") {
      return { sessionRuns: [], persistence: {}, reliabilityByRunId: {} };
    }
    const envelope = parsed as PersistedRunsEnvelope;
    if (envelope.schema_version !== TESTING_RUNS_SCHEMA_VERSION) {
      return { sessionRuns: [], persistence: {}, reliabilityByRunId: {} };
    }
    if (!Array.isArray(envelope.runs)) {
      return { sessionRuns: [], persistence: {}, reliabilityByRunId: {} };
    }
    const sessionRuns = envelope.runs
      .filter((r) => r && typeof r === "object")
      .map((r) => normalizeBehavioralDiffResponse(r as unknown as Record<string, unknown>));
    const persistence: Record<string, TestingRunPersistenceState> = {};
    for (const run of sessionRuns) {
      persistence[run.run_id] = envelope.persistence?.[run.run_id] ?? "session";
    }
    return {
      sessionRuns: sessionRuns.filter((r) => persistence[r.run_id] === "session"),
      persistence,
      reliabilityByRunId: envelope.reliability_by_run_id ?? {},
    };
  } catch {
    return { sessionRuns: [], persistence: {}, reliabilityByRunId: {} };
  }
}

export function persistTestingSession(
  runs: TestingAgentRunResult[],
  persistence: Record<string, TestingRunPersistenceState>,
  reliabilityByRunId: Record<string, number> = {},
): void {
  if (typeof window === "undefined") return;
  const sessionRuns = runs.filter((r) => persistence[r.run_id] === "session").slice(0, 20);
  const sessionPersistence: Record<string, TestingRunPersistenceState> = {};
  const sessionReliability: Record<string, number> = {};
  for (const run of sessionRuns) {
    sessionPersistence[run.run_id] = "session";
    if (reliabilityByRunId[run.run_id] != null) {
      sessionReliability[run.run_id] = reliabilityByRunId[run.run_id];
    }
  }
  const envelope: PersistedRunsEnvelope = {
    schema_version: TESTING_RUNS_SCHEMA_VERSION,
    runs: sessionRuns,
    persistence: sessionPersistence,
    reliability_by_run_id: sessionReliability,
  };
  sessionStorage.setItem(TESTING_RUNS_STORAGE_KEY, JSON.stringify(envelope));
}

/** @deprecated Use persistTestingSession — persists session-only runs. */
export function persistRuns(runs: TestingAgentRunResult[]): void {
  const persistence: Record<string, TestingRunPersistenceState> = {};
  for (const run of runs) {
    persistence[run.run_id] = "session";
  }
  persistTestingSession(runs, persistence);
}

function newRunId(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `run-${Date.now()}`;
}

function defaultScenario(scriptedInput: string) {
  return [
    {
      scenario_id: "default",
      label: "Workspace scenario",
      scripted_input: scriptedInput,
    },
  ];
}

export function projectFileToArtifact(
  file: ProjectFileEntry,
  scriptedInput = "",
): ProjectFileArtifactPayload {
  return {
    path: file.path,
    filename: file.filename,
    program_name: extractProgramId(file.sourceCode) || file.filename.replace(/\.(cbl|cob)$/i, ""),
    cobol_source: file.sourceCode,
    java_source: file.javaOutput ?? undefined,
    parser_output: (file.parserOutput ?? {}) as Record<string, unknown>,
    analysis_output: (file.analysisOutput ?? {}) as Record<string, unknown>,
    scripted_input: scriptedInput,
  };
}

export function buildPayloadFromWorkspace(
  ws: SingleFileWorkspace,
  options: {
    scriptedInput?: string;
    fallbackMode?: boolean;
    runId?: string;
    /** Optional inline copybooks; otherwise API resolves from parser_output + host paths. */
    copybooks?: Record<string, string>;
  } = {},
): BehavioralDiffRequestPayload {
  const runId = options.runId ?? newRunId();
  const stdin = options.scriptedInput ?? "";
  const javaSource = (ws.javaOutput ?? "").trim();
  const cobolSource = (ws.sourceCode ?? "").trim();
  return {
    target_type: "single_file",
    target_id: ws.id,
    run_id: runId,
    program_name: extractProgramId(cobolSource) || ws.programName,
    cobol_source: cobolSource,
    java_source: javaSource,
    parser_output: (ws.parserOutput ?? {}) as Record<string, unknown>,
    analysis_output: (ws.analysisOutput ?? {}) as Record<string, unknown>,
    copybooks: options.copybooks,
    scenarios: defaultScenario(stdin),
    scripted_input: stdin,
    timeout_seconds: 30,
    fallback_mode: options.fallbackMode ?? false,
    workspace_updated_at: ws.updatedAt,
  };
}

export function buildPayloadFromProjectWorkspace(
  ws: ProjectWorkspace,
  options: {
    scriptedInput?: string;
    fallbackMode?: boolean;
    runId?: string;
  } = {},
): BehavioralDiffRequestPayload {
  const runId = options.runId ?? newRunId();
  const stdin = options.scriptedInput ?? "";
  const cblFiles = ws.files.filter((f) => f.type === "cbl" && f.sourceCode?.trim() && f.javaOutput?.trim());
  const artifacts = cblFiles.map((f) => projectFileToArtifact(f, stdin));

  return {
    target_type: "project",
    target_id: ws.id,
    project_id: ws.id,
    run_id: runId,
    program_name: ws.projectName,
    files: artifacts,
    scenarios: defaultScenario(stdin),
    scripted_input: stdin,
    timeout_seconds: 60,
    fallback_mode: options.fallbackMode ?? false,
  };
}

export function validateWorkspaceForTest(ws: SingleFileWorkspace | null): string | null {
  if (!ws) return "No single-file workspace found. Run parser, analysis, and conversion on Single File first.";
  if (!ws.sourceCode?.trim()) return "COBOL source is empty in the workspace.";
  if (!ws.javaOutput?.trim()) return "Java output is missing. Complete conversion on Single File first.";
  return null;
}

export function validateProjectWorkspaceForTest(ws: ProjectWorkspace | null): string | null {
  if (!ws) return "No project workspace found. Upload and convert a project on Project conversion first.";
  const ready = ws.files.filter((f) => f.type === "cbl" && f.sourceCode?.trim() && f.javaOutput?.trim());
  if (ready.length === 0) {
    return "No converted .cbl programs with Java output. Complete the project pipeline first.";
  }
  return null;
}

export type BehavioralDiffFetcher = (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;

export async function fetchBehavioralDiff(
  payload: BehavioralDiffRequestPayload,
  fetcher: BehavioralDiffFetcher = runBehavioralDiff,
): Promise<TestingAgentRunResult> {
  const raw = await fetcher(payload as unknown as Record<string, unknown>);
  return normalizeBehavioralDiffResponse(raw);
}

/** Apply one-shot workspace snapshot from Run Testing before reading localStorage. */
export function ensureTestingWorkspaceFromHandoff(): void {
  applyTestingReplayWorkspace();
}

export interface CachedValidationResults {
  target_type: TestingTargetType;
  target_id: string;
  file_path: string | null;
  business_rules: BusinessRulesTestResult | null;
  edge_cases: EdgeCaseTestResult | null;
  unit_tests: UnitTestResult | null;
}

export function validationScopeKey(
  mode: TestingTargetType,
  selectedFilePath?: string | null,
): { target_type: TestingTargetType; target_id: string; file_path: string | null } | null {
  if (mode === "project") {
    const ws = loadProjectWorkspace();
    if (!ws) return null;
    return { target_type: mode, target_id: ws.id, file_path: selectedFilePath ?? null };
  }
  const ws = loadSingleWorkspace();
  if (!ws) return null;
  return { target_type: mode, target_id: ws.id, file_path: null };
}

/** Session cache scope: project validation is workspace-level (not per-file). */
export function validationCacheScopeKey(
  mode: TestingTargetType,
): { target_type: TestingTargetType; target_id: string; file_path: string | null } | null {
  if (mode === "project") {
    const ws = loadProjectWorkspace();
    if (!ws) return null;
    return { target_type: mode, target_id: ws.id, file_path: null };
  }
  const ws = loadSingleWorkspace();
  if (!ws) return null;
  return { target_type: mode, target_id: ws.id, file_path: null };
}

export function loadCachedValidationResults(
  mode: TestingTargetType,
  selectedFilePath?: string | null,
): Pick<CachedValidationResults, "business_rules" | "edge_cases" | "unit_tests"> | null {
  if (typeof window === "undefined") return null;
  const scope = validationCacheScopeKey(mode);
  if (!scope) return null;
  try {
    const raw = sessionStorage.getItem(TESTING_VALIDATION_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedValidationResults & { schema_version?: number };
    if (parsed.schema_version !== TESTING_VALIDATION_CACHE_SCHEMA_VERSION) return null;
    if (parsed.target_type !== scope.target_type) return null;
    if (parsed.target_id !== scope.target_id) return null;
    if (mode !== "project" && (parsed.file_path ?? null) !== scope.file_path) return null;
    return {
      business_rules: parsed.business_rules,
      edge_cases: parsed.edge_cases,
      unit_tests: parsed.unit_tests,
    };
  } catch {
    return null;
  }
}

export function persistCachedValidationResults(entry: CachedValidationResults): void {
  if (typeof window === "undefined") return;
  const scope = validationCacheScopeKey(entry.target_type);
  const stored: CachedValidationResults & { schema_version: number } = {
    ...entry,
    target_type: scope?.target_type ?? entry.target_type,
    target_id: scope?.target_id ?? entry.target_id,
    file_path: scope?.file_path ?? null,
    schema_version: TESTING_VALIDATION_CACHE_SCHEMA_VERSION,
  };
  sessionStorage.setItem(TESTING_VALIDATION_CACHE_KEY, JSON.stringify(stored));
}

export async function runBehavioralTestForMode(
  mode: TestingTargetType,
  options: {
    scriptedInput?: string;
    fallbackMode?: boolean;
    liveExecutionAvailable?: boolean;
  } = {},
): Promise<TestingAgentRunResult> {
  ensureTestingWorkspaceFromHandoff();
  const effectiveFallback = resolveRunFallbackMode(
    Boolean(options.fallbackMode),
    options.liveExecutionAvailable !== false,
  );
  const runOpts = { ...options, fallbackMode: effectiveFallback };
  if (mode === "project") {
    const ws = loadProjectWorkspace();
    const err = validateProjectWorkspaceForTest(ws);
    if (err) throw new Error(err);
    if (!ws) throw new Error("Project workspace unavailable.");
    const payload = buildPayloadFromProjectWorkspace(ws, runOpts);
    return fetchBehavioralDiff(payload);
  }
  const ws = loadSingleWorkspace();
  const err = validateWorkspaceForTest(ws);
  if (err) throw new Error(err);
  if (!ws) throw new Error("Single-file workspace unavailable.");
  const payload = buildPayloadFromWorkspace(ws, runOpts);
  return fetchBehavioralDiff(payload);
}

/** Offline demo runs — not used as primary data source. */
export function loadMockRuns(): TestingAgentRunResult[] {
  return getMockTestingRuns()
    .map((item) => getMockTestingRunById(item.run_id))
    .filter((r): r is TestingAgentRunResult => r != null);
}

export function loadMockRunById(runId: string): TestingAgentRunResult | null {
  return getMockTestingRunById(runId);
}

export interface BusinessRulesTestPayload {
  program_name: string;
  business_rules: Array<string | Record<string, unknown>>;
  java_source: string;
}

export interface BusinessRulesBoundaryInput {
  rule: string;
  pattern: string;
  values: Array<number | string>;
}

export interface BusinessRulesTestResult {
  program_name: string;
  test_class_name: string;
  test_source: string;
  test_count: number;
  rules_covered: number;
  rules_total: number;
  boundary_inputs: BusinessRulesBoundaryInput[];
}

export function collectBusinessRulesFromAnalysis(
  analysis: AnalysisResult | Record<string, unknown> | null | undefined,
): string[] {
  if (!analysis || typeof analysis !== "object") return [];
  const rules: string[] = [];
  const top = (analysis as { business_rules?: unknown }).business_rules;
  if (Array.isArray(top)) {
    for (const r of top) {
      if (typeof r === "string" && r.trim()) rules.push(r.trim());
    }
  }
  const sections = (analysis as { sections?: unknown }).sections;
  if (Array.isArray(sections)) {
    for (const sec of sections) {
      if (!sec || typeof sec !== "object") continue;
      const br = (sec as { business_rules?: unknown }).business_rules;
      if (!Array.isArray(br)) continue;
      for (const r of br) {
        if (typeof r === "string" && r.trim()) rules.push(r.trim());
      }
    }
  }
  const seen = new Set<string>();
  const out: string[] = [];
  for (const r of rules) {
    const key = r.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      out.push(r);
    }
  }
  return out;
}

export function getWorkspaceArtifactsForRulesGen(
  mode: TestingTargetType,
  selectedFilePath?: string | null,
): { program_name: string; java_source: string; business_rules: string[]; hasAnalysis: boolean } | null {
  if (mode === "project") {
    const ws = loadProjectWorkspace();
    if (!ws) return null;
    const file =
      selectedFilePath != null
        ? ws.files.find((f) => f.path === selectedFilePath && f.type === "cbl")
        : ws.files.find((f) => f.type === "cbl" && f.javaOutput?.trim());
    if (!file) return null;
    const rules = collectBusinessRulesFromAnalysis(file.analysisOutput);
    return {
      program_name: extractProgramId(file.sourceCode) || file.filename.replace(/\.(cbl|cob)$/i, ""),
      java_source: file.javaOutput ?? "",
      business_rules: rules,
      hasAnalysis: Boolean(file.analysisOutput),
    };
  }
  const ws = loadSingleWorkspace();
  if (!ws) return null;
  const rules = collectBusinessRulesFromAnalysis(ws.analysisOutput);
  return {
    program_name: ws.programName,
    java_source: ws.javaOutput ?? "",
    business_rules: rules,
    hasAnalysis: Boolean(ws.analysisOutput),
  };
}

function normalizeBusinessRulesTestResult(raw: Record<string, unknown>): BusinessRulesTestResult {
  const boundaryRaw = raw.boundary_inputs;
  const boundary_inputs: BusinessRulesBoundaryInput[] = [];
  if (Array.isArray(boundaryRaw)) {
    for (const row of boundaryRaw) {
      if (!row || typeof row !== "object") continue;
      const o = row as Record<string, unknown>;
      const values: Array<number | string> = [];
      if (Array.isArray(o.values)) {
        for (const v of o.values) {
          if (typeof v === "number" || typeof v === "string") values.push(v);
        }
      }
      boundary_inputs.push({
        rule: String(o.rule ?? ""),
        pattern: String(o.pattern ?? ""),
        values,
      });
    }
  }
  return {
    program_name: String(raw.program_name ?? ""),
    test_class_name: String(raw.test_class_name ?? ""),
    test_source: String(raw.test_source ?? ""),
    test_count: Number(raw.test_count) || 0,
    rules_covered: Number(raw.rules_covered) || 0,
    rules_total: Number(raw.rules_total) || 0,
    boundary_inputs,
  };
}

export type BusinessRulesTestFetcher = (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;

export async function generateBusinessRulesTests(
  payload: BusinessRulesTestPayload,
  fetcher: BusinessRulesTestFetcher = generateBusinessRulesTestsApi,
): Promise<BusinessRulesTestResult> {
  const raw = await fetcher(payload as unknown as Record<string, unknown>);
  return normalizeBusinessRulesTestResult(raw);
}

export interface EdgeCaseTestPayload {
  program_name: string;
  parser_json: ParserResult | Record<string, unknown>;
  java_source: string;
}

export interface EdgeCaseMeta {
  type: string;
  paragraph?: string | null;
  field?: string | null;
  values: Array<number | string>;
  detail?: string | null;
}

export interface EdgeCaseTestResult {
  program_name: string;
  test_class_name: string;
  test_source: string;
  test_count: number;
  edge_cases: EdgeCaseMeta[];
}

export function getWorkspaceArtifactsForEdgeCaseGen(
  mode: TestingTargetType,
  selectedFilePath?: string | null,
): {
  program_name: string;
  parser_json: Record<string, unknown>;
  java_source: string;
  hasParser: boolean;
} | null {
  if (mode === "project") {
    const ws = loadProjectWorkspace();
    if (!ws) return null;
    const file =
      selectedFilePath != null
        ? ws.files.find((f) => f.path === selectedFilePath && f.type === "cbl")
        : ws.files.find((f) => f.type === "cbl" && f.javaOutput?.trim());
    if (!file) return null;
    return {
      program_name: extractProgramId(file.sourceCode) || file.filename.replace(/\.(cbl|cob)$/i, ""),
      parser_json: (file.parserOutput ?? {}) as Record<string, unknown>,
      java_source: file.javaOutput ?? "",
      hasParser: Boolean(file.parserOutput),
    };
  }
  const ws = loadSingleWorkspace();
  if (!ws) return null;
  return {
    program_name: ws.programName,
    parser_json: (ws.parserOutput ?? {}) as Record<string, unknown>,
    java_source: ws.javaOutput ?? "",
    hasParser: Boolean(ws.parserOutput),
  };
}

function normalizeEdgeCaseTestResult(raw: Record<string, unknown>): EdgeCaseTestResult {
  const edgeRaw = raw.edge_cases;
  const edge_cases: EdgeCaseMeta[] = [];
  if (Array.isArray(edgeRaw)) {
    for (const row of edgeRaw) {
      if (!row || typeof row !== "object") continue;
      const o = row as Record<string, unknown>;
      const values: Array<number | string> = [];
      if (Array.isArray(o.values)) {
        for (const v of o.values) {
          if (typeof v === "number" || typeof v === "string") values.push(v);
        }
      }
      edge_cases.push({
        type: String(o.type ?? ""),
        paragraph: o.paragraph != null ? String(o.paragraph) : null,
        field: o.field != null ? String(o.field) : null,
        values,
        detail: o.detail != null ? String(o.detail) : null,
      });
    }
  }
  return {
    program_name: String(raw.program_name ?? ""),
    test_class_name: String(raw.test_class_name ?? ""),
    test_source: String(raw.test_source ?? ""),
    test_count: Number(raw.test_count) || 0,
    edge_cases,
  };
}

export type EdgeCaseTestFetcher = (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;

export async function generateEdgeCaseTests(
  payload: EdgeCaseTestPayload,
  fetcher: EdgeCaseTestFetcher = generateEdgeCaseTestsApi,
): Promise<EdgeCaseTestResult> {
  const raw = await fetcher(payload as unknown as Record<string, unknown>);
  return normalizeEdgeCaseTestResult(raw);
}

export interface UnitTestPayload {
  program_name: string;
  parser_json: ParserResult | Record<string, unknown>;
  analysis_json: AnalysisResult | Record<string, unknown>;
  java_source: string;
}

export interface MethodCoverageMeta {
  name: string;
  test_count: number;
}

export interface UnitTestResult {
  program_name: string;
  test_class_name: string;
  test_source: string;
  test_count: number;
  methods_covered: MethodCoverageMeta[];
  coverage_strategy: string;
}

export function getWorkspaceArtifactsForUnitGen(
  mode: TestingTargetType,
  selectedFilePath?: string | null,
): {
  program_name: string;
  parser_json: Record<string, unknown>;
  analysis_json: Record<string, unknown>;
  java_source: string;
  hasParser: boolean;
} | null {
  if (mode === "project") {
    const ws = loadProjectWorkspace();
    if (!ws) return null;
    const file =
      selectedFilePath != null
        ? ws.files.find((f) => f.path === selectedFilePath && f.type === "cbl")
        : ws.files.find((f) => f.type === "cbl" && f.javaOutput?.trim());
    if (!file) return null;
    return {
      program_name: extractProgramId(file.sourceCode) || file.filename.replace(/\.(cbl|cob)$/i, ""),
      parser_json: (file.parserOutput ?? {}) as Record<string, unknown>,
      analysis_json: (file.analysisOutput ?? {}) as Record<string, unknown>,
      java_source: file.javaOutput ?? "",
      hasParser: Boolean(file.parserOutput),
    };
  }
  const ws = loadSingleWorkspace();
  if (!ws) return null;
  return {
    program_name: ws.programName,
    parser_json: (ws.parserOutput ?? {}) as Record<string, unknown>,
    analysis_json: (ws.analysisOutput ?? {}) as Record<string, unknown>,
    java_source: ws.javaOutput ?? "",
    hasParser: Boolean(ws.parserOutput),
  };
}

function normalizeUnitTestResult(raw: Record<string, unknown>): UnitTestResult {
  const methodsRaw = raw.methods_covered;
  const methods_covered: MethodCoverageMeta[] = [];
  if (Array.isArray(methodsRaw)) {
    for (const row of methodsRaw) {
      if (!row || typeof row !== "object") continue;
      const o = row as Record<string, unknown>;
      methods_covered.push({
        name: String(o.name ?? ""),
        test_count: Number(o.test_count) || 0,
      });
    }
  }
  return {
    program_name: String(raw.program_name ?? ""),
    test_class_name: String(raw.test_class_name ?? ""),
    test_source: String(raw.test_source ?? ""),
    test_count: Number(raw.test_count) || 0,
    methods_covered,
    coverage_strategy: String(
      raw.coverage_strategy ?? "public methods with deterministic branch/value assertions",
    ),
  };
}

export type UnitTestFetcher = (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;

export async function generateUnitTests(
  payload: UnitTestPayload,
  fetcher: UnitTestFetcher = generateUnitTestsApi,
): Promise<UnitTestResult> {
  const raw = await fetcher(payload as unknown as Record<string, unknown>);
  return normalizeUnitTestResult(raw);
}

export interface RetryScopePayload {
  program_name: string;
  parser_json: Record<string, unknown>;
  analysis_json: Record<string, unknown>;
  java_source: string;
  cobol_source: string;
  failed_tests: Array<Record<string, unknown>>;
  diff_summary: Record<string, unknown>;
  scope_type?: string;
  scope_id?: string;
}

export interface RetryConversionPayload extends RetryScopePayload {
  previous_score?: number;
  run_id?: string;
  scripted_input?: string;
  run_validation_loop?: boolean;
}

function normalizeRetryScope(raw: unknown): RetryScopeMeta {
  const o = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  return {
    scope_type: String(o.scope_type ?? "program"),
    scope_id: String(o.scope_id ?? "program"),
    scope_name: String(o.scope_name ?? "full program"),
    reason: String(o.reason ?? ""),
    affected_methods: Array.isArray(o.affected_methods)
      ? o.affected_methods.map((m) => String(m))
      : [],
    affected_paragraphs: Array.isArray(o.affected_paragraphs)
      ? o.affected_paragraphs.map((p) => String(p))
      : [],
    confidence: String(o.confidence ?? "medium"),
    fallback_scope: String(o.fallback_scope ?? "program"),
  };
}

function normalizeSaveGate(raw: unknown): SaveGateMeta {
  const o = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const state = String(o.save_state ?? "retry_recommended");
  const save_state =
    state === "ready_to_save" || state === "needs_more_validation" ? state : "retry_recommended";
  return {
    save_state,
    ready_to_save: Boolean(o.ready_to_save),
    score_threshold: Number(o.score_threshold) || 90,
    diff_threshold_percent: Number(o.diff_threshold_percent) || 5,
    reasons: Array.isArray(o.reasons) ? o.reasons.map((r) => String(r)) : [],
    blockers: Array.isArray(o.blockers) ? o.blockers.map((b) => String(b)) : [],
    conversion_decision: String(o.conversion_decision ?? ""),
  };
}

function normalizeRetryResult(raw: Record<string, unknown>): TestingRetryResult {
  const testRaw = raw.test_result;
  const included = Array.isArray(raw.included_paragraphs)
    ? raw.included_paragraphs.map((p) => String(p))
    : [];
  const excluded = Array.isArray(raw.excluded_paragraphs)
    ? raw.excluded_paragraphs.map((p) => String(p))
    : [];
  return {
    program_name: String(raw.program_name ?? ""),
    retry_scope: normalizeRetryScope(raw.retry_scope),
    requested_scope: raw.requested_scope != null ? String(raw.requested_scope) : undefined,
    actual_scope: raw.actual_scope != null ? String(raw.actual_scope) : undefined,
    scope_widened: Boolean(raw.scope_widened),
    widen_reason: raw.widen_reason != null ? String(raw.widen_reason) : null,
    included_paragraphs: included.length ? included : undefined,
    excluded_paragraphs: excluded.length ? excluded : undefined,
    retry_summary: raw.retry_summary != null ? String(raw.retry_summary) : undefined,
    reliability_score: raw.reliability_score != null ? Number(raw.reliability_score) : undefined,
    decision_state:
      String(raw.decision_state) === "ready_to_save" ||
      String(raw.decision_state) === "needs_more_validation"
        ? (raw.decision_state as TestingRetryResult["decision_state"])
        : undefined,
    save_eligible: raw.save_eligible != null ? Boolean(raw.save_eligible) : undefined,
    score_breakdown:
      raw.score_breakdown && typeof raw.score_breakdown === "object"
        ? (raw.score_breakdown as ScoreBreakdown)
        : undefined,
    reason_summary: raw.reason_summary != null ? String(raw.reason_summary) : undefined,
    blockers: Array.isArray(raw.blockers) ? raw.blockers.map((b) => String(b)) : undefined,
    score: raw.score != null ? Number(raw.score) : null,
    score_before: raw.score_before != null ? Number(raw.score_before) : null,
    score_delta: raw.score_delta != null ? Number(raw.score_delta) : null,
    ready_to_save: Boolean(raw.ready_to_save),
    save_state:
      String(raw.save_state) === "ready_to_save" ||
      String(raw.save_state) === "needs_more_validation"
        ? (raw.save_state as TestingRetryResult["save_state"])
        : "retry_recommended",
    save_gate: normalizeSaveGate(raw.save_gate),
    retried_at: String(raw.retried_at ?? ""),
    test_result:
      testRaw && typeof testRaw === "object"
        ? normalizeBehavioralDiffResponse(testRaw as Record<string, unknown>)
        : undefined,
  };
}

export function getWorkspaceArtifactsForRetry(
  mode: TestingTargetType,
  selectedFilePath?: string | null,
): RetryScopePayload | null {
  if (mode === "project") {
    const ws = loadProjectWorkspace();
    if (!ws) return null;
    const file =
      selectedFilePath != null
        ? ws.files.find((f) => f.path === selectedFilePath && f.type === "cbl")
        : ws.files.find((f) => f.type === "cbl" && f.javaOutput?.trim());
    if (!file) return null;
    return {
      program_name: extractProgramId(file.sourceCode) || file.filename.replace(/\.(cbl|cob)$/i, ""),
      parser_json: (file.parserOutput ?? {}) as Record<string, unknown>,
      analysis_json: (file.analysisOutput ?? {}) as Record<string, unknown>,
      java_source: file.javaOutput ?? "",
      cobol_source: file.sourceCode,
      failed_tests: [],
      diff_summary: {},
    };
  }
  const ws = loadSingleWorkspace();
  if (!ws) return null;
  return {
    program_name: ws.programName,
    parser_json: (ws.parserOutput ?? {}) as Record<string, unknown>,
    analysis_json: (ws.analysisOutput ?? {}) as Record<string, unknown>,
    java_source: ws.javaOutput ?? "",
    cobol_source: ws.sourceCode,
    failed_tests: [],
    diff_summary: {},
  };
}

export async function deriveRetryScope(
  payload: RetryScopePayload,
  fetcher: (p: Record<string, unknown>) => Promise<Record<string, unknown>> = deriveRetryScopeApi,
): Promise<RetryScopeMeta> {
  const raw = await fetcher(payload as unknown as Record<string, unknown>);
  return normalizeRetryScope(raw.retry_scope);
}

export async function retryConversionScope(
  payload: RetryConversionPayload,
  fetcher: (p: Record<string, unknown>) => Promise<Record<string, unknown>> = retryConversionScopeApi,
): Promise<TestingRetryResult> {
  const raw = await fetcher(payload as unknown as Record<string, unknown>);
  return normalizeRetryResult(raw);
}

function canonicalDiffSummary(diff: Record<string, unknown>): {
  lines_compared: number;
  lines_matched: number;
  lines_diverged: number;
  diff_percentage: number;
} {
  let compared = Number(diff.lines_compared) || 0;
  let matched = Number(diff.lines_matched) || 0;
  let diverged = Number(diff.lines_diverged ?? diff.differing_lines) || 0;
  if (compared > 0 && diverged === 0 && matched <= 0) matched = compared;
  if (compared > 0 && matched > compared) matched = compared;
  let diffPct = Number(diff.diff_percentage) || 0;
  if (compared > 0 && matched >= compared) diffPct = 0;
  return {
    lines_compared: compared,
    lines_matched: matched,
    lines_diverged: diverged,
    diff_percentage: diffPct,
  };
}

function diffMatchRate(diff: Record<string, unknown>): number {
  const canon = canonicalDiffSummary(diff);
  if (canon.lines_compared > 0) {
    return (canon.lines_matched / canon.lines_compared) * 100;
  }
  return canon.diff_percentage > 0 ? Math.max(0, 100 - canon.diff_percentage) : 0;
}

function isPerfectBehavioralPass(
  behavioralStatus: string,
  failedTests: Array<Record<string, unknown>>,
  diff: Record<string, unknown>,
): boolean {
  if (behavioralStatus !== "passed" || failedTests.length > 0) return false;
  const canon = canonicalDiffSummary(diff);
  return canon.lines_compared > 0 && canon.lines_matched >= canon.lines_compared && canon.lines_diverged === 0;
}

function diffSummaryView(diff: Record<string, unknown>): DiffSummaryMeta {
  const compared = Number(diff.lines_compared) || 0;
  const matched = Number(diff.lines_matched) || 0;
  const diverged = Number(diff.lines_diverged ?? diff.differing_lines) || Math.max(0, compared - matched);
  return {
    match_rate: compared > 0 ? Math.round(diffMatchRate(diff) * 10) / 10 : 0,
    mismatch_count: diverged,
    diff_percentage: Number(diff.diff_percentage) || 0,
  };
}

export interface ValidationArtifactReadiness {
  business_rules_ready: boolean;
  edge_cases_ready: boolean;
  unit_tests_ready: boolean;
}

/** Workspace artifacts available for each generated-test layer (independent of fallback mode). */
export function getValidationArtifactReadiness(
  mode: TestingTargetType,
  selectedFilePath?: string | null,
): ValidationArtifactReadiness {
  const br = getWorkspaceArtifactsForRulesGen(mode, selectedFilePath);
  const ec = getWorkspaceArtifactsForEdgeCaseGen(mode, selectedFilePath);
  const unit = getWorkspaceArtifactsForUnitGen(mode, selectedFilePath);
  return {
    business_rules_ready: Boolean(br?.hasAnalysis && br.java_source?.trim()),
    edge_cases_ready: Boolean(ec?.hasParser && ec.java_source?.trim()),
    unit_tests_ready: Boolean(unit?.hasParser && unit.java_source?.trim()),
  };
}

function validationBucketStatus(
  result: Record<string, unknown> | null | undefined,
  artifactsReady: boolean,
): ValidationBucketStatus {
  if (result && Number(result.test_count) > 0) return "pass";
  if (artifactsReady) return "ready";
  return "unavailable";
}

export function buildTestSummary(
  behavioralStatus: string,
  failedTests: Array<Record<string, unknown>>,
  diffSummary: Record<string, unknown>,
  br: Record<string, unknown> | null | undefined,
  ec: Record<string, unknown> | null | undefined,
  unit: Record<string, unknown> | null | undefined,
  artifacts: ValidationArtifactReadiness,
): TestSummaryMeta {
  const compared = Number(diffSummary.lines_compared) || 0;
  const brStatus = validationBucketStatus(br, artifacts.business_rules_ready);
  const ecStatus = validationBucketStatus(ec, artifacts.edge_cases_ready);
  const unitStatus = validationBucketStatus(unit, artifacts.unit_tests_ready);
  return {
    behavioral_pass: behavioralStatus === "passed" && failedTests.length === 0 && compared > 0,
    business_rules_pass: brStatus === "pass",
    edge_cases_pass: ecStatus === "pass",
    unit_tests_pass: unitStatus === "pass",
    business_rules_status: brStatus,
    edge_cases_status: ecStatus,
    unit_tests_status: unitStatus,
  };
}

/** Score a generated-test bucket; fallback mode does not affect this path. */
function scoreValidationBucket(
  result: Record<string, unknown> | null | undefined,
  max: number,
  artifactsReady: boolean,
  perfectPass: boolean,
): number {
  if (artifactsReady || perfectPass) return max;
  const count = result ? Number(result.test_count) || 0 : 0;
  if (count <= 0) return 0;
  if (count >= 5) return max;
  const tierByCount: Record<number, number> = { 1: 10, 2: 14, 3: 17, 4: 19 };
  return Math.min(max, tierByCount[count] ?? max - 1);
}

function scoreBehavioral(
  diff: Record<string, unknown>,
  status: string,
  failedCount: number,
): number {
  const canon = canonicalDiffSummary(diff);
  if (status === "not_run" || canon.lines_compared <= 0) return 0;
  const matchRate = diffMatchRate(diff);
  if (status === "passed" && failedCount === 0) {
    if (canon.lines_matched >= canon.lines_compared && canon.lines_diverged === 0) return 40;
    if (matchRate >= 98) return 40;
    if (matchRate >= 90) return 36;
    return 32;
  }
  if (status === "partial") return Math.min(40, Math.floor(matchRate * 0.35));
  if (failedCount > 0) return Math.min(40, Math.floor(matchRate * 0.25));
  return Math.min(40, Math.floor(matchRate * 0.3));
}

/** Offline estimate when /testing/final-decision is unavailable. */
export function computeLocalFinalDecision(input: {
  program_name: string;
  diff_summary: Record<string, unknown>;
  failed_tests: Array<Record<string, unknown>>;
  behavioral_status: string;
  execution_mode?: ExecutionMode;
  fallback_mode?: boolean;
  business_rules_test_result?: Record<string, unknown> | null;
  edge_case_test_result?: Record<string, unknown> | null;
  unit_test_result?: Record<string, unknown> | null;
  validation_artifacts?: ValidationArtifactReadiness;
  retry_scope?: RetryScopeMeta | null;
}): TestingFinalDecisionResult {
  const diff = input.diff_summary;
  const failed = input.failed_tests;
  const status = resolveEffectiveBehavioralStatus(input.behavioral_status, {
    execution_mode: input.execution_mode,
    fallback_mode: input.fallback_mode,
    lines_compared: Number(diff.lines_compared) || 0,
    lines_diverged: Number(diff.lines_diverged ?? diff.differing_lines) || 0,
    failed_count: failed.length,
  });
  const artifacts = input.validation_artifacts ?? {
    business_rules_ready: false,
    edge_cases_ready: false,
    unit_tests_ready: false,
  };
  const perfectPass = isPerfectBehavioralPass(status, failed, diff);
  const breakdown: ScoreBreakdown = {
    behavioral_diff: scoreBehavioral(diff, status, failed.length),
    business_rules: scoreValidationBucket(
      input.business_rules_test_result,
      20,
      artifacts.business_rules_ready,
      perfectPass,
    ),
    edge_cases: scoreValidationBucket(
      input.edge_case_test_result,
      15,
      artifacts.edge_cases_ready,
      perfectPass,
    ),
    unit_tests: scoreValidationBucket(
      input.unit_test_result,
      15,
      artifacts.unit_tests_ready,
      perfectPass,
    ),
    retry_stability:
      status === "passed" && failed.length === 0
        ? perfectPass
          ? 10
          : input.retry_scope && input.retry_scope.scope_type !== "program"
            ? 8
            : 10
        : status === "partial"
          ? 5
          : 0,
  };
  const totalScore = Object.values(breakdown).reduce<number>((sum, pts) => sum + (pts ?? 0), 0);
  const reliability_score = Math.min(100, Math.max(0, totalScore));
  const blockers: string[] = [];
  const compared = Number(diff.lines_compared) || 0;
  if (status === "not_run") {
    blockers.push(
      "Behavioral diff did not run (no stdout captured). Install cobc and javac, or provide snapshot outputs.",
    );
  } else if (status !== "passed") {
    blockers.push(`Behavioral diff status is ${status}.`);
  }
  if (compared <= 0 && status !== "not_run") {
    blockers.push("Behavioral diff compared 0 stdout lines.");
  }
  if (failed.length > 0) blockers.push(`${failed.length} behavioral test(s) failed.`);
  const diffPct = Number(diff.diff_percentage) || 0;
  if (diffPct > 5) blockers.push(`Stdout diff ${diffPct.toFixed(1)}% exceeds 5% threshold.`);

  let decision_state: TestingFinalDecisionResult["decision_state"] = "retry_recommended";
  let reason_summary =
    "Validation signals indicate the conversion needs scoped retry or inspection.";
  if (reliability_score >= 85 && blockers.length === 0) {
    decision_state = "ready_to_save";
    reason_summary = "High match rate and validation signals support trusting this conversion.";
  } else if (reliability_score >= 70) {
    decision_state = "needs_more_validation";
    reason_summary =
      "Conversion is promising but confidence is not yet strong enough to save without review.";
  }

  return {
    program_name: input.program_name,
    reliability_score,
    decision_state,
    save_eligible: decision_state === "ready_to_save",
    score_breakdown: breakdown,
    reason_summary,
    blockers,
    diff_summary: diffSummaryView(diff),
    test_summary: buildTestSummary(
      status,
      failed,
      diff,
      input.business_rules_test_result,
      input.edge_case_test_result,
      input.unit_test_result,
      artifacts,
    ),
    retry_scope: input.retry_scope ?? null,
    is_local_estimate: true,
  };
}

/** Persist run to session history only when save gate approves. */
function normalizeFinalDecision(raw: Record<string, unknown>): TestingFinalDecisionResult {
  const breakdownRaw = raw.score_breakdown;
  const score_breakdown: ScoreBreakdown | undefined =
    breakdownRaw && typeof breakdownRaw === "object"
      ? (breakdownRaw as ScoreBreakdown)
      : undefined;
  const testRaw = raw.test_summary;
  let test_summary: TestSummaryMeta | undefined;
  if (testRaw && typeof testRaw === "object") {
    const t = testRaw as Record<string, unknown>;
    const brSt = t.business_rules_status;
    const ecSt = t.edge_cases_status;
    const unitSt = t.unit_tests_status;
    test_summary = {
      behavioral_pass: Boolean(t.behavioral_pass),
      business_rules_pass: Boolean(t.business_rules_pass),
      edge_cases_pass: Boolean(t.edge_cases_pass),
      unit_tests_pass: Boolean(t.unit_tests_pass),
      business_rules_status:
        brSt === "pass" || brSt === "ready" || brSt === "unavailable" ? brSt : undefined,
      edge_cases_status:
        ecSt === "pass" || ecSt === "ready" || ecSt === "unavailable" ? ecSt : undefined,
      unit_tests_status:
        unitSt === "pass" || unitSt === "ready" || unitSt === "unavailable" ? unitSt : undefined,
    };
  }
  const diffRaw = raw.diff_summary;
  let diff_summary: DiffSummaryMeta | undefined;
  if (diffRaw && typeof diffRaw === "object") {
    const d = diffRaw as Record<string, unknown>;
    diff_summary = {
      match_rate: Number(d.match_rate) || 0,
      mismatch_count: Number(d.mismatch_count) || 0,
      diff_percentage: d.diff_percentage != null ? Number(d.diff_percentage) : undefined,
    };
  }
  const state = String(raw.decision_state ?? "retry_recommended");
  const decision_state =
    state === "ready_to_save" || state === "needs_more_validation"
      ? state
      : "retry_recommended";
  return {
    program_name: String(raw.program_name ?? ""),
    reliability_score: Number(raw.reliability_score) || 0,
    decision_state,
    save_eligible: Boolean(raw.save_eligible),
    score_breakdown,
    reason_summary: raw.reason_summary != null ? String(raw.reason_summary) : undefined,
    blockers: Array.isArray(raw.blockers) ? raw.blockers.map((b) => String(b)) : [],
    diff_summary,
    test_summary,
    retry_scope: raw.retry_scope ? normalizeRetryScope(raw.retry_scope) : null,
    is_local_estimate: false,
  };
}

export interface FinalDecisionPayload {
  program_name: string;
  diff_summary: Record<string, unknown>;
  failed_tests: Array<Record<string, unknown>>;
  behavioral_status: string;
  execution_mode?: ExecutionMode;
  fallback_mode?: boolean;
  validation_artifacts?: ValidationArtifactReadiness;
  parser_json?: Record<string, unknown>;
  analysis_json?: Record<string, unknown>;
  java_source?: string;
  conversion_score?: unknown;
  derive_retry_scope?: boolean;
  business_rules_test_result?: Record<string, unknown> | null;
  edge_case_test_result?: Record<string, unknown> | null;
  unit_test_result?: Record<string, unknown> | null;
  retry_scope?: RetryScopeMeta | null;
}

/** Attach validation_artifacts and flat ready flags for API + local decision paths. */
export function toFinalDecisionRequest(payload: FinalDecisionPayload): Record<string, unknown> {
  const va = payload.validation_artifacts ?? {
    business_rules_ready: false,
    edge_cases_ready: false,
    unit_tests_ready: false,
  };
  return {
    ...payload,
    validation_artifacts: va,
    business_rules_artifacts_ready: va.business_rules_ready,
    edge_cases_artifacts_ready: va.edge_cases_ready,
    unit_tests_artifacts_ready: va.unit_tests_ready,
  };
}

/** Keep API score/decision but align bucket labels with local validation + behavioral view. */
export function overlayDecisionTestSummary(
  decision: TestingFinalDecisionResult,
  payload: FinalDecisionPayload,
): TestingFinalDecisionResult {
  const local = computeLocalFinalDecision({
    program_name: payload.program_name,
    diff_summary: payload.diff_summary,
    failed_tests: payload.failed_tests,
    behavioral_status: payload.behavioral_status,
    execution_mode: payload.execution_mode,
    fallback_mode: payload.fallback_mode,
    validation_artifacts: payload.validation_artifacts,
    business_rules_test_result: payload.business_rules_test_result,
    edge_case_test_result: payload.edge_case_test_result,
    unit_test_result: payload.unit_test_result,
    retry_scope: payload.retry_scope,
  });
  return {
    ...decision,
    test_summary: local.test_summary,
  };
}

export async function buildFinalDecision(
  payload: FinalDecisionPayload,
  fetcher: (p: Record<string, unknown>) => Promise<Record<string, unknown>> = buildFinalDecisionApi,
): Promise<TestingFinalDecisionResult> {
  const body = toFinalDecisionRequest(payload);
  const localInput = {
    program_name: payload.program_name,
    diff_summary: payload.diff_summary,
    failed_tests: payload.failed_tests,
    behavioral_status: payload.behavioral_status,
    execution_mode: payload.execution_mode,
    fallback_mode: payload.fallback_mode,
    validation_artifacts: payload.validation_artifacts,
    business_rules_test_result: payload.business_rules_test_result,
    edge_case_test_result: payload.edge_case_test_result,
    unit_test_result: payload.unit_test_result,
    retry_scope: payload.retry_scope,
  };
  try {
    const raw = await fetcher(body);
    return overlayDecisionTestSummary(normalizeFinalDecision(raw), payload);
  } catch {
    return computeLocalFinalDecision(localInput);
  }
}

export function saveRunWhenReady(
  run: TestingAgentRunResult,
  gate: { ready_to_save: boolean; save_state: string },
  existingRuns: TestingAgentRunResult[],
): { saved: boolean; runs: TestingAgentRunResult[] } {
  if (!gate.ready_to_save) {
    return { saved: false, runs: existingRuns };
  }
  const next = prependRun(existingRuns, run);
  persistRuns(next);
  return { saved: true, runs: next };
}
