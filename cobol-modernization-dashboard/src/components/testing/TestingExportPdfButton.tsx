"use client";

import { useCallback, useState } from "react";

import type {
  TestingAgentRunResult,
  TestingFinalDecisionResult,
} from "@/lib/testingAgentTypes";
import {
  buildTestingRunReportModel,
  downloadTestingRunPdf,
  type TestingRunPdfExportSource,
} from "@/lib/testingRunPdfReport";
import { loadSingleWorkspace } from "@/lib/singleFileWorkspace";
import { isTestingHistoryEntry } from "@/lib/testingHistoryBridge";
import * as historyService from "@/services/historyService";
import type { AnalysisResult } from "@/lib/types";

export interface TestingExportPdfButtonProps {
  run: TestingAgentRunResult;
  decision: TestingFinalDecisionResult | null;
  disabled?: boolean;
}

async function resolveExportSource(run: TestingAgentRunResult): Promise<{
  source: TestingRunPdfExportSource;
  analysis_output: AnalysisResult | Record<string, unknown> | null;
}> {
  try {
    const entry = await historyService.getByIdAsync(run.run_id);
    if (entry && isTestingHistoryEntry(entry) && entry.testingRun) {
      return {
        source: "history",
        analysis_output: entry.analysisOutput ?? null,
      };
    }
  } catch {
    /* fall through to session */
  }
  const ws = loadSingleWorkspace();
  const sameProgram =
    ws?.programName &&
    run.program_name &&
    ws.programName.toUpperCase() === run.program_name.toUpperCase();
  return {
    source: "session",
    analysis_output: sameProgram ? ws?.analysisOutput ?? null : null,
  };
}

export default function TestingExportPdfButton({
  run,
  decision,
  disabled = false,
}: TestingExportPdfButtonProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleExport = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const { source, analysis_output } = await resolveExportSource(run);
      const model = buildTestingRunReportModel({
        run,
        decision,
        export_source: source,
        analysis_output,
      });
      await downloadTestingRunPdf(model);
    } catch (err) {
      setError(err instanceof Error ? err.message : "PDF export failed");
    } finally {
      setBusy(false);
    }
  }, [run, decision]);

  return (
    <div className="testing-export-pdf-wrap">
      <button
        type="button"
        className="action-button secondary"
        disabled={disabled || busy}
        onClick={() => void handleExport()}
        aria-busy={busy}
      >
        {busy ? "Generating PDF…" : "Download PDF Report"}
      </button>
      {error ? (
        <p className="testing-panel-hint" style={{ color: "var(--error)", marginTop: 8 }}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
