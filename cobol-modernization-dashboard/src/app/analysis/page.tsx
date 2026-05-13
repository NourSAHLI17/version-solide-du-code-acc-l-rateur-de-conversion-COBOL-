"use client";

import { useState } from "react";

import ActionButton from "@/components/ActionButton";
import AppShell from "@/components/AppShell";
import ArtifactPanel from "@/components/ArtifactPanel";
import CodeEditor from "@/components/CodeEditor";
import HealthStrip from "@/components/HealthStrip";
import { analyzeCobol, parseCobol } from "@/lib/api";
import { useBackendStatus } from "@/lib/useBackendStatus";
import { useWorkspace } from "@/lib/workspace";

export default function AnalysisPage() {
  const { workspace, actions } = useWorkspace();
  const { status, error, refresh, setStatus } = useBackendStatus(true);
  const [loading, setLoading] = useState(false);

  async function handleAnalyze() {
    setLoading(true);
    actions.setLastError(null);
    try {
      const nextStatus = await refresh();
      setStatus(nextStatus);
      actions.setBackendStatus(nextStatus);
      const parserResult = await parseCobol(workspace.sourceCode);
      actions.setParserResult(parserResult);
      const analysisResult = await analyzeCobol(workspace.sourceCode, parserResult);
      actions.setAnalysisResult(analysisResult);
    } catch (caught) {
      actions.setLastError(caught instanceof Error ? caught.message : "Analysis failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell
      title="Analysis Agent"
      subtitle="Run semantic interpretation after parsing and inspect grounded purpose, complexity, business rules, risks, and conversion guidance."
    >
      <HealthStrip status={workspace.backendStatus ?? status} lastError={workspace.lastError ?? error} />

      <div className="page-grid stacked-panels">
        <CodeEditor label="COBOL Source" value={workspace.sourceCode} onChange={actions.setSourceCode} minHeight={260} />
        <div className="page-grid two-column">
          <ArtifactPanel
            title="Parser Output"
            data={workspace.parserResult ?? { message: "Parser output will appear here. Analysis will auto-run parsing first if needed." }}
          />
          <ArtifactPanel
            title="Analysis Output"
            data={workspace.analysisResult ?? { message: "Run analysis to inspect semantic summaries and business rules." }}
          />
        </div>
      </div>

      <div className="action-row">
        <ActionButton variant="secondary" onClick={actions.reset}>
          Reset Workspace
        </ActionButton>
        <ActionButton onClick={handleAnalyze} disabled={loading}>
          {loading ? "Analyzing..." : "Run Analysis"}
        </ActionButton>
      </div>
    </AppShell>
  );
}
