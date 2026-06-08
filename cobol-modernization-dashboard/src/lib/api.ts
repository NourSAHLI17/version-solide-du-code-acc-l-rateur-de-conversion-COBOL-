import type { NormalizedConversionScore } from "@/lib/conversionScore";
import { normalizeConversionScore } from "@/lib/conversionScore";
import type { RepairSummary } from "@/lib/repairSummary";
import { normalizeRepairSummary } from "@/lib/repairSummary";
import type { AnalysisResult, BackendStatus, ParserResult, ValidationResult } from "@/lib/types";

const API_ROOT = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8010/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_ROOT}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch (err) {
    const hint =
      err instanceof TypeError && /fetch/i.test(err.message)
        ? `Cannot reach the API at ${API_ROOT}. Start the backend (port 8010) and refresh.`
        : err instanceof Error
          ? err.message
          : "Network request failed.";
    throw new Error(hint);
  }

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with status ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function getApiRoot(): string {
  return API_ROOT;
}

export function fetchBackendStatus(): Promise<BackendStatus> {
  return request<BackendStatus>("/status", { method: "GET" });
}

export function parseCobol(sourceCode: string): Promise<ParserResult> {
  return request<ParserResult>("/parse", {
    method: "POST",
    body: JSON.stringify({ source_code: sourceCode }),
  });
}

export function analyzeCobol(sourceCode: string, parserOutput: ParserResult): Promise<AnalysisResult> {
  const parserPayload =
    parserOutput && typeof parserOutput === "object" && !Array.isArray(parserOutput)
      ? parserOutput
      : {};
  return request<AnalysisResult>("/analyze", {
    method: "POST",
    body: JSON.stringify({
      source_code: sourceCode,
      parser_output: parserPayload,
    }),
  });
}

export interface ConvertCobolResult {
  javaCode: string;
  conversionScore: NormalizedConversionScore | null;
  conversionStatus?: "complete" | "partial" | "failed";
  compileErrors?: string[];
  compileStderr?: string;
  compileRepairNotes?: string[];
  repairSummary?: RepairSummary | null;
  mappingNotes?: string;
  smokeTest?: unknown;
}

export async function convertCobol(
  sourceCode: string,
  parserOutput: ParserResult,
  analysisOutput: AnalysisResult,
): Promise<ConvertCobolResult> {
  const payload = await request<{
    java_code?: string;
    java_source?: string;
    conversion_score?: unknown;
    conversion_status?: string;
    compile_errors?: string[];
    compile_stderr?: string;
    compile_repair_notes?: string[];
    repair_summary?: unknown;
    mapping_notes?: string;
    smoke_test?: unknown;
    conversion_failed?: boolean;
    error?: string;
  }>("/convert", {
    method: "POST",
    body: JSON.stringify({
      source_code: sourceCode,
      parser_output: parserOutput,
      analysis_output: JSON.stringify(analysisOutput),
    }),
  });

  if (payload.conversion_failed) {
    throw new Error(payload.error ?? "Conversion failed.");
  }

  return {
    javaCode: payload.java_code ?? payload.java_source ?? "",
    conversionScore: normalizeConversionScore(payload.conversion_score),
    conversionStatus:
      payload.conversion_status === "partial"
        ? "partial"
        : payload.conversion_status === "complete"
          ? "complete"
          : undefined,
    compileErrors: payload.compile_errors,
    compileStderr: payload.compile_stderr,
    compileRepairNotes: payload.compile_repair_notes,
    repairSummary: normalizeRepairSummary(payload.repair_summary),
    mappingNotes: payload.mapping_notes,
    smokeTest: payload.smoke_test ?? undefined,
  };
}

export function validateOutputs(expectedOutput: string, actualOutput: string): Promise<ValidationResult> {
  return request<ValidationResult>("/validate", {
    method: "POST",
    body: JSON.stringify({
      expected_output: expectedOutput,
      actual_output: actualOutput,
    }),
  });
}

// Replaced by runPipelineMode, kept for fallback mapping
export async function smartConvert(
  sourceCode: string,
  parserOutput?: ParserResult,
  analysisOutput?: AnalysisResult,
): Promise<{ java_code: string; parser_output: ParserResult; analysis_output: AnalysisResult }> {
  return request("/smart-convert", {
    method: "POST",
    body: JSON.stringify({
      source_code: sourceCode,
      parser_output: parserOutput,
      analysis_output: analysisOutput ? JSON.stringify(analysisOutput) : undefined,
    }),
  });
}

export async function runPipelineMode(
  sourceCode: string,
  mode: string,
  parserOutput?: ParserResult,
  analysisOutput?: AnalysisResult
): Promise<{ java_source?: string; parser_output?: ParserResult; analysis_output?: AnalysisResult }> {
  return request("/pipeline/run", {
    method: "POST",
    body: JSON.stringify({
      cobol_source: sourceCode,
      mode: mode,
      parser_output: parserOutput,
      analysis_output: analysisOutput ? JSON.stringify(analysisOutput) : undefined,
    }),
  });
}

/** Run behavioral diff via the dedicated testing agent (Testing page contract). */
export function runBehavioralDiff(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/testing/behavioral-diff", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface FetchToolchainStatusParams {
  fallbackMode?: boolean;
  snapshotsAvailable?: boolean;
  executionMode?: string;
  /** Re-probe the API host (use after installing cobc or restarting the backend). */
  forceRefresh?: boolean;
}

/** Toolchain probe and banner guidance for the Testing page. */
export function fetchTestingToolchainStatus(
  params: FetchToolchainStatusParams = {},
): Promise<Record<string, unknown>> {
  const q = new URLSearchParams();
  if (params.fallbackMode) q.set("fallback_mode", "true");
  if (params.snapshotsAvailable) q.set("snapshots_available", "true");
  if (params.executionMode) q.set("execution_mode", params.executionMode);
  if (params.forceRefresh) q.set("force_refresh", "true");
  const query = q.toString();
  return request<Record<string, unknown>>(`/testing/toolchain-status${query ? `?${query}` : ""}`, {
    method: "GET",
  });
}

/** Generate JUnit 5 tests from business rules (Phase 4.2). */
export function generateBusinessRulesTestsApi(
  payload: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/testing/generate-business-rules-tests", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Generate JUnit 5 edge-case tests from parser metadata (Phase 4.3). */
export function generateEdgeCaseTestsApi(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/testing/generate-edge-case-tests", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Generate JUnit 5 unit tests from converted Java (Phase 4.4). */
export function generateUnitTestsApi(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/testing/generate-unit-tests", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Derive smallest safe retry scope from failures (testing retry loop). */
export function deriveRetryScopeApi(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/testing/derive-retry-scope", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Re-convert a narrowed scope and re-run behavioral validation. */
export function retryConversionScopeApi(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/testing/retry-conversion-scope", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Compute final reliability score and trust decision. */
export function buildFinalDecisionApi(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/testing/final-decision", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function runTests(
  parserOutput: Record<string, unknown>,
  analysisOutput: Record<string, unknown>,
  javaSource: string,
  cobolSource: string,
): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/test", {
    method: "POST",
    body: JSON.stringify({
      parser_output: parserOutput,
      analysis_output: analysisOutput,
      java_source: javaSource,
      cobol_source: cobolSource,
    }),
  });
}

export async function uploadProject(file: File): Promise<{ files: Array<Record<string, unknown>>; total: number }> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_ROOT}/project/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Upload failed");
  }

  return response.json() as Promise<{ files: Array<Record<string, unknown>>; total: number }>;
}

export function runProjectPipeline(
  files: Array<Record<string, unknown>>,
  mode: string,
): Promise<{ results: Array<Record<string, unknown>>; total_files: number }> {
  return request<{ results: Array<Record<string, unknown>>; total_files: number }>("/project/pipeline", {
    method: "POST",
    body: JSON.stringify({ files, mode }),
  });
}

export async function downloadProject(results: Array<Record<string, unknown>>): Promise<Blob> {
  const response = await fetch(`${API_ROOT}/download/project`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ results }),
  });
  if (!response.ok) throw new Error("Download failed");
  return response.blob();
}
