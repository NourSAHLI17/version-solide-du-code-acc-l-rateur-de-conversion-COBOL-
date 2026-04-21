export type ParserResult = Record<string, unknown> | null;
export type AnalysisResult = Record<string, unknown> | null;
export type ValidationResult = Record<string, unknown> | null;

export interface BackendStatus {
  api_healthy: boolean;
  parser_backend: string;
  analysis_available: boolean;
  validation_available: boolean;
  llm_configured: boolean;
  conversion_available: boolean;
  llm_model: string;
  prompt_template_available: boolean;
}

export interface PipelineWorkspace {
  sourceCode: string;
  parserResult: ParserResult;
  analysisResult: AnalysisResult;
  javaCode: string;
  validationResult: ValidationResult;
  backendStatus: BackendStatus | null;
  lastError: string | null;
}
