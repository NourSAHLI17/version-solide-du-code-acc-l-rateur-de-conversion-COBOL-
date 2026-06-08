import { extractProgramId } from "@/lib/programId";
import type { ConversionScoreModel } from "@/lib/conversionScore";
import type { RepairSummary } from "@/lib/repairSummary";
import type { SmokeTestResult } from "@/components/SmokeTestPanel";
import type { AnalysisResult, ParserResult } from "@/lib/types";

export const SINGLE_WORKSPACE_KEY = "cobol-single-workspace";

export interface SingleFileWorkspace {
  id: string;
  programName: string;
  sourceCode: string;
  parserOutput: ParserResult;
  analysisOutput: AnalysisResult;
  javaOutput: string | null;
  score: number | null;
  cost: number | null;
  conversionScore?: ConversionScoreModel | null;
  conversionStatus?: "complete" | "partial" | "failed";
  compileRepairNotes?: string[];
  repairSummary?: RepairSummary | null;
  smokeTest?: SmokeTestResult | null;
  createdAt: string;
  updatedAt: string;
  /** Persist stage error messages across navigation (optional). */
  pipelineErrors?: {
    parser?: string;
    analysis?: string;
    java?: string;
  };
}

export function newSingleWorkspace(sourceCode = ""): SingleFileWorkspace {
  const now = new Date().toISOString();
  const name = extractProgramId(sourceCode);
  return {
    id: typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `ws-${Date.now()}`,
    programName: name,
    sourceCode,
    parserOutput: null,
    analysisOutput: null,
    javaOutput: null,
    score: null,
    cost: null,
    createdAt: now,
    updatedAt: now,
    pipelineErrors: undefined,
  };
}

export function loadSingleWorkspace(): SingleFileWorkspace | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(SINGLE_WORKSPACE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SingleFileWorkspace;
  } catch {
    window.localStorage.removeItem(SINGLE_WORKSPACE_KEY);
    return null;
  }
}

export function saveSingleWorkspace(ws: SingleFileWorkspace): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(SINGLE_WORKSPACE_KEY, JSON.stringify(ws));
}

export function isParserOk(parserOutput: ParserResult): boolean {
  if (!parserOutput || typeof parserOutput !== "object") return false;
  const errs = (parserOutput as { preflight_errors?: unknown }).preflight_errors;
  return Array.isArray(errs) && errs.length === 0;
}
