import type { AnalysisResult, ParserResult } from "@/lib/types";

export const HISTORY_STORAGE_KEY = "cobol-conversion-history";
export const MAX_HISTORY = 50;

export type HistoryEntryType = "single" | "project";

export interface HistoryEntry {
  id: string;
  type: HistoryEntryType;
  programName: string;
  createdAt: string;
  paragraphCount: number;
  score: null;
  cost: null;
  parserOutput: ParserResult;
  analysisOutput: AnalysisResult;
  /** For single: Java source string. For project: JSON string map filename → java. */
  javaOutput: string | null;
  /** Optional: single-file COBOL source for Re-run / View. */
  sourceCode?: string;
  /** Project-only payload for restoring multi-file workspace. */
  projectSnapshot?: ProjectWorkspaceSnapshot;
}

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
  }>;
}

function readRaw(): HistoryEntry[] {
  if (typeof window === "undefined") return [];
  const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as HistoryEntry[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    window.localStorage.removeItem(HISTORY_STORAGE_KEY);
    return [];
  }
}

function writeAll(entries: HistoryEntry[]) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(entries));
}

export function getAll(): HistoryEntry[] {
  return readRaw().sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
}

export function add(entry: HistoryEntry): void {
  const list = readRaw();
  const next = [entry, ...list.filter((e) => e.id !== entry.id)];
  const trimmed = next.slice(0, MAX_HISTORY);
  writeAll(trimmed);
}

export function getById(id: string): HistoryEntry | null {
  return readRaw().find((e) => e.id === id) ?? null;
}

export function deleteEntry(id: string): void {
  writeAll(readRaw().filter((e) => e.id !== id));
}

export function clear(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(HISTORY_STORAGE_KEY);
}
