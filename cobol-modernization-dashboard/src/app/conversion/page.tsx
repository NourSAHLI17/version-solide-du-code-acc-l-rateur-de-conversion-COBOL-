"use client";

import { useMemo, useState } from "react";

import ActionButton from "@/components/ActionButton";
import AppShell from "@/components/AppShell";
import ArtifactPanel from "@/components/ArtifactPanel";
import CodeEditor from "@/components/CodeEditor";
import CodePanel from "@/components/CodePanel";
import HealthStrip from "@/components/HealthStrip";
import MetricCard from "@/components/MetricCard";
import { analyzeCobol, convertCobol, parseCobol } from "@/lib/api";
import { estimateLlmCost } from "@/lib/cost";
import { useBackendStatus } from "@/lib/useBackendStatus";
import { useWorkspace } from "@/lib/workspace";

export default function ConversionPage() {
  const { workspace, actions } = useWorkspace();
  const { status, error, refresh, setStatus } = useBackendStatus(true);
  const [loading, setLoading] = useState(false);

  const estimate = useMemo(
    () =>
      estimateLlmCost({
        sourceCode: workspace.sourceCode,
        parserResult: workspace.parserResult,
        analysisResult: workspace.analysisResult,
        javaCode: workspace.javaCode,
      }),
    [workspace.analysisResult, workspace.javaCode, workspace.parserResult, workspace.sourceCode],
  );

  async function handleConvert() {
    setLoading(true);
    actions.setLastError(null);
    try {
      const nextStatus = await refresh();
      setStatus(nextStatus);
      actions.setBackendStatus(nextStatus);
      const parserResult = workspace.parserResult ?? (await parseCobol(workspace.sourceCode));
      actions.setParserResult(parserResult);
      const analysisResult = workspace.analysisResult ?? (await analyzeCobol(workspace.sourceCode, parserResult));
      actions.setAnalysisResult(analysisResult);
      const javaCode = await convertCobol(workspace.sourceCode, parserResult, analysisResult);
      actions.setJavaCode(javaCode);
    } catch (caught) {
      actions.setLastError(caught instanceof Error ? caught.message : "Conversion failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell
      title="Conversion Agent"
      subtitle="Test Java generation directly, inspect semantic context beside generated code, and review estimated LLM token and cost usage."
    >
      <HealthStrip status={workspace.backendStatus ?? status} lastError={workspace.lastError ?? error} />

      <section className="metrics-grid">
        <MetricCard label="Input Tokens" value={estimate.inputTokens.toLocaleString()} hint="Estimated prompt size" />
        <MetricCard label="Output Tokens" value={estimate.outputTokens.toLocaleString()} hint="Estimated Java response size" />
        <MetricCard
          label="Estimated Cost"
          value={`$${estimate.estimatedCostUsd.toFixed(4)}`}
          hint="Editable heuristic would be easy to add later if you want provider-specific pricing"
        />
      </section>

      <div className="page-grid stacked-panels">
        <CodeEditor label="COBOL Source" value={workspace.sourceCode} onChange={actions.setSourceCode} minHeight={220} />
        <div className="page-grid two-column">
          <ArtifactPanel
            title="Analysis Output"
            data={workspace.analysisResult ?? { message: "Conversion will auto-run parsing and analysis first if needed." }}
          />
          <CodePanel title="Generated Java" code={workspace.javaCode} />
        </div>
      </div>

      <div className="action-row">
        <ActionButton variant="secondary" onClick={actions.reset}>
          Reset Workspace
        </ActionButton>
        <ActionButton onClick={handleConvert} disabled={loading}>
          {loading ? "Converting..." : "Run Conversion"}
        </ActionButton>
      </div>
    </AppShell>
  );
}
