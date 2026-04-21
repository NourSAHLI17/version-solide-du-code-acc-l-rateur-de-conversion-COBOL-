import type { AnalysisResult, ParserResult } from "@/lib/types";

export interface CostEstimateInput {
  sourceCode: string;
  parserResult: ParserResult;
  analysisResult: AnalysisResult;
  javaCode: string;
  inputRatePerMillion?: number;
  outputRatePerMillion?: number;
}

export interface CostEstimate {
  inputTokens: number;
  outputTokens: number;
  estimatedCostUsd: number;
}

function estimateTokens(value: string): number {
  return Math.ceil(value.length / 4);
}

export function estimateLlmCost({
  sourceCode,
  parserResult,
  analysisResult,
  javaCode,
  inputRatePerMillion = 0.1,
  outputRatePerMillion = 0.4,
}: CostEstimateInput): CostEstimate {
  const promptPayload = [
    sourceCode,
    JSON.stringify(parserResult ?? {}, null, 2),
    JSON.stringify(analysisResult ?? {}, null, 2),
  ].join("\n");

  const inputTokens = estimateTokens(promptPayload);
  const outputTokens = estimateTokens(javaCode);
  const estimatedCostUsd =
    (inputTokens / 1_000_000) * inputRatePerMillion +
    (outputTokens / 1_000_000) * outputRatePerMillion;

  return {
    inputTokens,
    outputTokens,
    estimatedCostUsd,
  };
}
