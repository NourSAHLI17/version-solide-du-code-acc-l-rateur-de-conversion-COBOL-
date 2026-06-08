import type { ConversionScoreModel } from "@/lib/conversionScore";
import type { RepairSummary } from "@/lib/repairSummary";
import type { AnalysisResult, ParserResult } from "@/lib/types";

export const PROJECT_WORKSPACE_KEY = "cobol-project-workspace";

export type ProjectFileType = "cbl" | "cpy" | "jcl" | "other";

export type PipelineStageStatus = "idle" | "running" | "done" | "error" | "partial";

export type ProjectRetryStep = "parser" | "analysis" | "java";

export interface ProjectFileEntry {
  filename: string;
  path: string;
  type: ProjectFileType;
  sourceCode: string;
  parserStatus: PipelineStageStatus;
  analysisStatus: PipelineStageStatus;
  conversionStatus: PipelineStageStatus;
  parserOutput: ParserResult;
  analysisOutput: AnalysisResult;
  javaOutput: string | null;
  score: number | null;
  conversionScore?: ConversionScoreModel | null;
  stageErrors?: {
    parser?: string;
    analysis?: string;
    java?: string;
  };
  /** Set when Java was generated but javac still reports errors after repair. */
  compileErrors?: string[];
  compileRepairNotes?: string[];
  repairSummary?: RepairSummary | null;
}

export interface ProjectWorkspace {
  id: string;
  projectName: string;
  files: ProjectFileEntry[];
  createdAt: string;
  updatedAt: string;
}

export function newProjectWorkspace(name: string, files: ProjectFileEntry[]): ProjectWorkspace {
  const now = new Date().toISOString();
  return {
    id: typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `proj-${Date.now()}`,
    projectName: name,
    files,
    createdAt: now,
    updatedAt: now,
  };
}

export function classifyType(filename: string): ProjectFileType {
  const lower = filename.trim().toLowerCase();
  if (lower.endsWith(".cbl") || lower.endsWith(".cob")) return "cbl";
  if (lower.endsWith(".cpy")) return "cpy";
  if (lower.endsWith(".jcl") || lower.endsWith(".procs")) return "jcl";
  return "other";
}

export function loadProjectWorkspace(): ProjectWorkspace | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(PROJECT_WORKSPACE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as ProjectWorkspace;
  } catch {
    window.localStorage.removeItem(PROJECT_WORKSPACE_KEY);
    return null;
  }
}

export function saveProjectWorkspace(ws: ProjectWorkspace): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(PROJECT_WORKSPACE_KEY, JSON.stringify(ws));
}

export function inferLastFailedStep(f: ProjectFileEntry): ProjectRetryStep | null {
  if (f.conversionStatus === "error" || f.conversionStatus === "partial") return "java";
  if (f.analysisStatus === "error") return "analysis";
  if (f.parserStatus === "error") return "parser";
  return null;
}

export function getFileRetryCapabilities(f: ProjectFileEntry): {
  parser: boolean;
  analysis: boolean;
  java: boolean;
} {
  if (f.type !== "cbl") return { parser: false, analysis: false, java: false };
  return {
    parser: f.parserStatus !== "running",
    analysis: f.parserStatus === "done" && f.analysisStatus !== "running",
    java:
      f.parserStatus === "done" &&
      f.analysisStatus === "done" &&
      f.conversionStatus !== "running",
  };
}

/** Derive COBOL program stem from workspace entry (never from Java class name). */
export function programKeyFromEntry(f: Pick<ProjectFileEntry, "filename" | "path">): string {
  const fromName = f.filename.replace(/\.(cbl|cob)$/i, "");
  if (fromName) return fromName;
  const base = f.path.split(/[/\\]/).pop() ?? f.path;
  return base.replace(/\.(cbl|cob)$/i, "");
}

export function expectedProgramName(filenameOrKey: string): string {
  const base = filenameOrKey.split(/[/\\]/).pop() ?? filenameOrKey;
  return base.replace(/\.(cbl|cob)$/i, "").toUpperCase();
}

/** Warn when parser output program_name does not match the requested COBOL file. */
export function verifyConversionProgram(
  filenameOrPath: string,
  parserOutput: ParserResult | null | undefined,
): void {
  const expected = expectedProgramName(filenameOrPath);
  const got = String((parserOutput as { program_name?: string } | null)?.program_name ?? "").toUpperCase();
  if (got && got !== expected) {
    console.warn(`Program mismatch: requested ${expected}, got ${got}`);
  }
}
