"use client";

import { useCallback, useState } from "react";

import type {
  TestingAgentRunResult,
  TestingFinalDecisionResult,
} from "@/lib/testingAgentTypes";
import {
  buildProjectTestingPdfReportModel,
  downloadProjectTestingPdf,
} from "@/lib/testingProjectPdfReport";

export interface TestingExportProjectPdfButtonProps {
  run: TestingAgentRunResult;
  decision: TestingFinalDecisionResult | null;
  disabled?: boolean;
}

export default function TestingExportProjectPdfButton({
  run,
  decision,
  disabled = false,
}: TestingExportProjectPdfButtonProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDownloadPdf = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const model = buildProjectTestingPdfReportModel(run, decision);
      await downloadProjectTestingPdf(model);
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
        className="action-button primary"
        disabled={disabled || busy}
        onClick={() => void handleDownloadPdf()}
        aria-busy={busy}
      >
        {busy ? "Generating PDF…" : "⬇ Download PDF"}
      </button>
      {error ? (
        <p className="testing-panel-hint" style={{ color: "var(--error)", marginTop: 8 }}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
