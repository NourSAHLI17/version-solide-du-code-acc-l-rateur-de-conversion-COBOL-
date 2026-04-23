"use client";

import { useMemo, useState } from "react";

import ActionButton from "@/components/ActionButton";
import AppShell from "@/components/AppShell";
import ArtifactPanel from "@/components/ArtifactPanel";
import CodeEditor from "@/components/CodeEditor";
import CodePanel from "@/components/CodePanel";
import HealthStrip from "@/components/HealthStrip";
import MetricCard from "@/components/MetricCard";
import PipelineModeSelector from "@/components/PipelineModeSelector";
import PipelineProgress from "@/components/PipelineProgress";
import StageTabs from "@/components/StageTabs";
import { runPipelineMode } from "@/lib/api";
import { estimateLlmCost } from "@/lib/cost";
import type { PipelineMode } from "@/lib/pipelineModes";
import { PIPELINE_MODES } from "@/lib/pipelineModes";
import { useBackendStatus } from "@/lib/useBackendStatus";
import { useWorkspace } from "@/lib/workspace";

const OUTPUT_TABS = [
  { id: "parser", label: "Parser Output", stage: "parser" as const },
  { id: "analysis", label: "Analysis", stage: "analysis" as const },
  { id: "java", label: "Java Output", stage: "java" as const },
  { id: "tests", label: "Test Report", stage: "tests" as const },
];

export default function ConversionPage() {
  const { workspace, actions } = useWorkspace();
  const { status, error, refresh, setStatus } = useBackendStatus(true);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<PipelineMode>("full");
  const [activeTab, setActiveTab] = useState("java");

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
      
      const payload = await runPipelineMode(
        workspace.sourceCode, 
        mode,
        workspace.parserResult,
        workspace.analysisResult
      );
      
      if (payload.parser_output) actions.setParserResult(payload.parser_output);
      if (payload.analysis_output) actions.setAnalysisResult(payload.analysis_output);
      if (payload.java_source) actions.setJavaCode(payload.java_source);
      if (payload.java_source) {
        setActiveTab("java");
      } else if (payload.analysis_output) {
        setActiveTab("analysis");
      } else if (payload.parser_output) {
        setActiveTab("parser");
      }
      
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

      <div className="toolbar-card glass-card">
        <PipelineModeSelector value={mode} onChange={setMode} modes={PIPELINE_MODES} />
        <div className="toolbar-copy">
          Choose how much context the backend should build before conversion. Every mode calls the real
          <strong> /api/pipeline/run</strong> endpoint.
        </div>
      </div>

      <PipelineProgress currentStage={loading ? "Convert" : null} mode={mode} />

      <div className="overhaul-grid">
        <CodeEditor label="COBOL Source" value={workspace.sourceCode} onChange={actions.setSourceCode} minHeight={220} />
        <div className="output-card">
          <StageTabs tabs={OUTPUT_TABS} activeTab={activeTab} onChange={setActiveTab} />
          <div className="output-card-body">
            {activeTab === "parser" && (
              <ArtifactPanel title="Parser Output" data={workspace.parserResult ?? { message: "Run parse-capable mode to inspect parser artifacts." }} />
            )}
            {activeTab === "analysis" && (
              <ArtifactPanel
                title="Analysis Output"
                data={workspace.analysisResult ?? { message: "Analysis context will appear for full, parse + analyse, or analyse-only modes." }}
              />
            )}
            {activeTab === "java" && <CodePanel title="Generated Java" code={workspace.javaCode} />}
            {activeTab === "tests" && (
              <ArtifactPanel title="Test Report" data={workspace.validationResult ?? { message: "Run the testing page for full Stage 9 report." }} />
            )}
          </div>
        </div>
      </div>


      <div className="action-row mt-6">
        <ActionButton variant="secondary" onClick={actions.reset}>
          Reset Workspace
        </ActionButton>
        <ActionButton onClick={handleConvert} disabled={loading}>
          {loading ? "Running Pipeline..." : "Execute Mode"}
        </ActionButton>
      </div>
    </AppShell>
  );
}
