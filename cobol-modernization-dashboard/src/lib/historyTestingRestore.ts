import { normalizeConversionScore, scoreListValue } from "@/lib/conversionScore";
import { extractProgramId } from "@/lib/programId";
import {
  classifyType,
  newProjectWorkspace,
  saveProjectWorkspace,
  type PipelineStageStatus,
  type ProjectFileEntry,
} from "@/lib/projectWorkspace";
import { newSingleWorkspace, saveSingleWorkspace, type SingleFileWorkspace } from "@/lib/singleFileWorkspace";
import type { HistoryEntry } from "@/services/historyService";

export function canRunTestingFromHistory(entry: HistoryEntry): boolean {
  if (entry.type === "single") {
    return Boolean(entry.sourceCode?.trim() && entry.javaOutput?.trim());
  }
  if (entry.type === "project" && entry.projectSnapshot?.files?.length) {
    return entry.projectSnapshot.files.some(
      (f) => f.type === "cbl" && f.sourceCode?.trim() && f.javaOutput?.trim(),
    );
  }
  return false;
}

function stageStatus(raw: string | undefined, hasArtifact: boolean): PipelineStageStatus {
  if (raw === "running" || raw === "done" || raw === "error" || raw === "idle") return raw;
  return hasArtifact ? "done" : "idle";
}

/** Write a history entry into the active conversion workspace (localStorage). */
export function restoreWorkspaceFromHistory(
  entry: HistoryEntry,
): { mode: "single_file" | "project" } | { error: string } {
  if (entry.type === "project") {
    const snap = entry.projectSnapshot;
    if (!snap?.files?.length) {
      return { error: "This history entry has no project snapshot to replay." };
    }
    const files: ProjectFileEntry[] = snap.files.map((f) => {
      const hasParser = Boolean(f.parserOutput);
      const hasAnalysis = Boolean(f.analysisOutput);
      const hasJava = Boolean(f.javaOutput?.trim());
      const normalizedScore = normalizeConversionScore(f.conversionScore);
      return {
        filename: f.filename,
        path: f.path,
        type: classifyType(f.filename),
        sourceCode: f.sourceCode ?? "",
        parserStatus: stageStatus(f.parserStatus, hasParser),
        analysisStatus: stageStatus(f.analysisStatus, hasAnalysis),
        conversionStatus: stageStatus(f.conversionStatus, hasJava),
        parserOutput: f.parserOutput ?? null,
        analysisOutput: f.analysisOutput ?? null,
        javaOutput: f.javaOutput ?? null,
        score: scoreListValue(normalizedScore) ?? f.score ?? null,
        conversionScore: normalizedScore ?? null,
      };
    });
    const ws = newProjectWorkspace(snap.projectName || entry.programName, files);
    saveProjectWorkspace(ws);
    if (!canRunTestingFromHistory(entry)) {
      return { error: "No converted programs with Java output in this saved project." };
    }
    return { mode: "project" };
  }

  if (!entry.sourceCode?.trim()) {
    return { error: "This history entry has no COBOL source to replay." };
  }
  if (!entry.javaOutput?.trim()) {
    return { error: "This history entry has no Java output to replay." };
  }

  const base = newSingleWorkspace(entry.sourceCode);
  const merged: SingleFileWorkspace = {
    ...base,
    programName: entry.programName || extractProgramId(entry.sourceCode),
    sourceCode: entry.sourceCode,
    parserOutput: entry.parserOutput ?? null,
    analysisOutput: entry.analysisOutput ?? null,
    javaOutput: entry.javaOutput ?? null,
    conversionScore: normalizeConversionScore(entry.conversionScore) ?? null,
    score:
      scoreListValue(normalizeConversionScore(entry.conversionScore)) ??
      (typeof entry.score === "number" ? entry.score : null),
  };
  saveSingleWorkspace(merged);
  return { mode: "single_file" };
}
