import type { AnalysisResult, ParserResult } from "@/lib/types";
import type { ComplexityLabel, ConversionScoreModel } from "@/lib/conversionScore";
import {
  complexityFromAnalyses,
  complexityFromAnalysis,
  normalizeConversionScore,
  scoreListValue,
} from "@/lib/conversionScore";
import { getApiRoot } from "@/lib/api";
import { isTestingHistoryEntry } from "@/lib/testingHistoryBridge";

export const MAX_HISTORY = 100;

export type HistoryEntryType = "single" | "project";

export interface HistoryEntry {
  id: string;
  type: HistoryEntryType;
  programName: string;
  createdAt: string;
  paragraphCount?: number;
  score: number | null;
  cost: number | null;
  complexityLabel?: ComplexityLabel | null;
  parserOutput: ParserResult;
  analysisOutput: AnalysisResult;
  javaOutput: string | null;
  sourceCode?: string;
  conversionScore?: ConversionScoreModel | null;
  conversionScoreRaw?: unknown;
  projectSnapshot?: ProjectWorkspaceSnapshot;
  /** Behavioral testing reliability score (0–100). */
  reliability_score?: number | null;
  /** Behavioral status for badge display. */
  status?: string | null;
  /** True when the user saved below the auto-save gate. */
  force_save?: boolean;
  /** Durable testing save kind (stable gate vs manual). */
  historyPersistence?: "stable_saved" | "saved";
  /** ISO timestamp when the run was committed to history. */
  savedAt?: string;
  /** Final decision snapshot for reopening saved testing runs. */
  finalDecisionSnapshot?: Record<string, unknown>;
  /** Distinguishes testing-session rows from conversion-only saves. */
  recordKind?: "testing_run" | "conversion" | string;
  /** Full testing run payload for sidebar restore after refresh. */
  testingRun?: Record<string, unknown>;
}

export const TESTING_SIDEBAR_LIMIT = 20;

export interface ProjectWorkspaceSnapshot {
  projectName: string;
  files: Array<{
    filename: string;
    path: string;
    type: string;
    sourceCode: string;
    parserOutput: ParserResult;
    analysisOutput: AnalysisResult;
    javaOutput: string | null;
    parserStatus: string;
    analysisStatus: string;
    conversionStatus: string;
    score?: number | null;
    conversionScore?: ConversionScoreModel | null;
  }>;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getApiRoot()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

function enrichEntry(entry: HistoryEntry): HistoryEntry {
  const e = { ...entry };
  const normalized =
    normalizeConversionScore(e.conversionScore) ??
    normalizeConversionScore(e.conversionScoreRaw) ??
    (typeof e.score === "number"
      ? normalizeConversionScore({
          total_score: e.score,
          structural_score: 0,
          business_rules_score: 0,
          decision: "manual_review",
        })
      : null);
  if (normalized) {
    e.conversionScore = normalized;
    e.score = scoreListValue(normalized);
  }
  if (!e.complexityLabel) {
    if (e.type === "project" && e.projectSnapshot?.files?.length) {
      const analyses = e.projectSnapshot.files
        .filter((f) => f.type === "cbl")
        .map((f) => f.analysisOutput);
      e.complexityLabel = complexityFromAnalyses(analyses);
    } else {
      e.complexityLabel = complexityFromAnalysis(e.analysisOutput);
    }
  }
  return e;
}

export async function getAllAsync(limit = MAX_HISTORY): Promise<HistoryEntry[]> {
  const lim = Math.max(1, Math.min(limit, MAX_HISTORY));
  const data = await request<{ entries: HistoryEntry[] }>(`/history?limit=${lim}`);
  return (data.entries ?? []).map(enrichEntry);
}

/** Testing sidebar: persisted runs with testing metadata (newest first). */
export async function getTestingSidebarAsync(
  limit = TESTING_SIDEBAR_LIMIT,
): Promise<HistoryEntry[]> {
  const entries = await getAllAsync(limit);
  return entries.filter(isTestingHistoryEntry);
}

export async function getByIdAsync(id: string): Promise<HistoryEntry | null> {
  try {
    const entry = await request<HistoryEntry>(`/history/${encodeURIComponent(id)}`);
    return enrichEntry(entry);
  } catch {
    return null;
  }
}

export async function addAsync(entry: HistoryEntry): Promise<void> {
  const payload = enrichEntry(entry);
  await request("/history", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteEntryAsync(id: string): Promise<void> {
  await request(`/history/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function clearAsync(): Promise<void> {
  await request("/history", { method: "DELETE" });
}

/** @deprecated use getAllAsync */
export function getAll(): HistoryEntry[] {
  return [];
}

/** @deprecated use addAsync */
export function add(_entry: HistoryEntry): void {
  void addAsync(_entry).catch(() => {
    /* caller should use addAsync */
  });
}

export function getById(_id: string): HistoryEntry | null {
  return null;
}

export function deleteEntry(id: string): void {
  void deleteEntryAsync(id);
}

export function clear(): void {
  void clearAsync();
}
