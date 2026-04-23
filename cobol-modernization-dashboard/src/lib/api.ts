import type { AnalysisResult, BackendStatus, ParserResult, ValidationResult } from "@/lib/types";

const API_ROOT = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

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
  return request<AnalysisResult>("/analyze", {
    method: "POST",
    body: JSON.stringify({
      source_code: sourceCode,
      parser_output: parserOutput,
    }),
  });
}

export async function convertCobol(
  sourceCode: string,
  parserOutput: ParserResult,
  analysisOutput: AnalysisResult,
): Promise<string> {
  const payload = await request<{ java_code: string }>("/convert", {
    method: "POST",
    body: JSON.stringify({
      source_code: sourceCode,
      parser_output: parserOutput,
      analysis_output: JSON.stringify(analysisOutput),
    }),
  });

  return payload.java_code;
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

export function runTests(
  parserOutput: any,
  analysisOutput: any,
  javaSource: string,
  cobolSource: string
): Promise<any> {
  return request("/test", {
    method: "POST",
    body: JSON.stringify({
      parser_output: parserOutput,
      analysis_output: analysisOutput,
      java_source: javaSource,
      cobol_source: cobolSource
    }),
  });
}

export async function uploadProject(file: File): Promise<{ files: any[]; total: number }> {
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

  return response.json();
}

export function runProjectPipeline(files: any[], mode: string): Promise<{ results: any[]; total_files: number }> {
  return request("/project/pipeline", {
    method: "POST",
    body: JSON.stringify({ files, mode }),
  });
}

export async function downloadProject(results: any[]): Promise<Blob> {
  const response = await fetch(`${API_ROOT}/download/project`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ results }),
  });
  if (!response.ok) throw new Error("Download failed");
  return response.blob();
}
