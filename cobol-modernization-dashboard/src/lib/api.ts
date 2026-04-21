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
