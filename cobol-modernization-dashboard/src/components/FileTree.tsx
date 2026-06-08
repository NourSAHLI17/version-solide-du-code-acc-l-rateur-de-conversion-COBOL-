"use client";

import { complexityTierFromAnalysis, formatScoreCompact, normalizeConversionScore } from "@/lib/conversionScore";
import type { PipelineStageStatus, ProjectFileEntry } from "@/lib/projectWorkspace";
import ComplexityBadge from "@/components/ComplexityBadge";
import StatusBadge from "@/components/StatusBadge";

function stageTone(s: PipelineStageStatus): "idle" | "running" | "success" | "error" {
  if (s === "running") return "running";
  if (s === "partial") return "running";
  if (s === "done") return "success";
  if (s === "error") return "error";
  return "idle";
}

function stageLabel(s: PipelineStageStatus): string {
  if (s === "running") return "Running";
  if (s === "partial") return "Partial";
  if (s === "done") return "Done";
  if (s === "error") return "Failed";
  return "Idle";
}

function fileTypeBadge(type: ProjectFileEntry["type"]) {
  if (type === "cbl") return { label: ".cbl", cls: "stage-badge parser" };
  if (type === "cpy") return { label: ".cpy", cls: "stage-badge copybook" };
  if (type === "jcl") return { label: ".jcl", cls: "stage-badge jcl" };
  return { label: "file", cls: "stage-badge" };
}

export interface FileTreeProps {
  files: ProjectFileEntry[];
  selectedPath: string | null;
  onSelect: (path: string) => void;
  retryBusyPath?: string | null;
  onRetry?: (path: string, step: "parser" | "analysis" | "java") => void;
  retryCapabilities?: (file: ProjectFileEntry) => { parser: boolean; analysis: boolean; java: boolean };
}

export default function FileTree({
  files,
  selectedPath,
  onSelect,
  retryBusyPath,
  onRetry,
  retryCapabilities,
}: FileTreeProps) {
  return (
    <div className="file-list">
      <div className="file-list-header">Files ({files.length})</div>
      {files.map((f) => {
        const active = f.path === selectedPath;
        const typeBadge = fileTypeBadge(f.type);
        const caps = retryCapabilities?.(f);
        const busy = retryBusyPath === f.path;
        const failMsg = f.stageErrors?.java ?? f.stageErrors?.analysis ?? f.stageErrors?.parser ?? null;
        return (
          <div key={f.path} className={`file-item-wrap${active ? " active" : ""}`}>
            <button type="button" className={`file-item${active ? " active" : ""}`} onClick={() => onSelect(f.path)}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div className="file-path">{f.filename}</div>
                <div className="file-tree-meta">
                  {f.type === "cbl" ? (() => {
                    const tierView = complexityTierFromAnalysis(f.analysisOutput);
                    return tierView ? (
                      <ComplexityBadge
                        tier={tierView.tier}
                        ibmRating={tierView.ibmRating}
                        drivers={
                          tierView.drivers.length > 0
                            ? tierView.drivers
                            : Array.isArray(
                                  (f.analysisOutput as { complexity_drivers?: unknown } | null)
                                    ?.complexity_drivers,
                                )
                              ? ((f.analysisOutput as { complexity_drivers: string[] }).complexity_drivers ?? [])
                              : []
                        }
                      />
                    ) : null;
                  })() : null}
                  <span className={`file-type-pill ${typeBadge.cls}`}>{typeBadge.label}</span>
                  {f.type === "cbl" ? (
                    <>
                      <StatusBadge label={`Parse: ${stageLabel(f.parserStatus)}`} tone={stageTone(f.parserStatus)} compact />
                      <StatusBadge label={`Analyze: ${stageLabel(f.analysisStatus)}`} tone={stageTone(f.analysisStatus)} compact />
                      <StatusBadge label={`Java: ${stageLabel(f.conversionStatus)}`} tone={stageTone(f.conversionStatus)} compact />
                    </>
                  ) : null}
                  {(() => {
                    const label = formatScoreCompact(normalizeConversionScore(f.conversionScore));
                    return label !== "—" ? <span className="file-tree-score">{label}</span> : null;
                  })()}
                  {f.repairSummary?.autoRepairs?.length ? (
                    <span className="file-tree-repairs" title="Auto-repairs applied">
                      {f.repairSummary.autoRepairs.length} repair{f.repairSummary.autoRepairs.length === 1 ? "" : "s"}
                    </span>
                  ) : null}
                  {f.repairSummary?.manualReview?.length ? (
                    <span className="file-tree-review-warn" title="Manual review needed">
                      {f.repairSummary.manualReview.length} TODO{f.repairSummary.manualReview.length === 1 ? "" : "s"}
                    </span>
                  ) : null}
                </div>
                {failMsg ? <div className="file-tree-fail">{failMsg}</div> : null}
              </div>
            </button>
            {f.type === "cbl" && onRetry && caps ? (
              <div className="file-tree-row2">
                <button type="button" className="action-button secondary" style={{ padding: "4px 8px", fontSize: 11 }} disabled={!caps.parser || busy} onClick={() => onRetry(f.path, "parser")}>Re-parse</button>
                <button type="button" className="action-button secondary" style={{ padding: "4px 8px", fontSize: 11 }} disabled={!caps.analysis || busy} onClick={() => onRetry(f.path, "analysis")}>Re-analyze</button>
                <button type="button" className="action-button secondary" style={{ padding: "4px 8px", fontSize: 11 }} disabled={!caps.java || busy} onClick={() => onRetry(f.path, "java")}>Re-convert</button>
                {busy ? <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Running…</span> : null}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
