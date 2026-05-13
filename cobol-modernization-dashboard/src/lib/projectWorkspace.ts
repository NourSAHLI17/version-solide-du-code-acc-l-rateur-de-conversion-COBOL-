import type { AnalysisResult, ParserResult } from "@/lib/types";

export const PROJECT_WORKSPACE_KEY = "cobol-project-workspace";

export type ProjectFileType = "cbl" | "cpy" | "jcl" | "other";

export type PipelineStageStatus = "idle" | "running" | "done" | "error";

export interface ProjectFileEntry {
  filename: string;
  /** Path inside ZIP (posix-style). */
  path: string;
  type: ProjectFileType;
  sourceCode: string;
  parserStatus: PipelineStageStatus;
  analysisStatus: PipelineStageStatus;
  conversionStatus: PipelineStageStatus;
  parserOutput: ParserResult;
  analysisOutput: AnalysisResult;
  javaOutput: string | null;
  score: null;
  stageErrors?: {
    parser?: string;
    analysis?: string;
    java?: string;
  };
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
  const base = filename.trim();
  const lower = base.toLowerCase();
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
