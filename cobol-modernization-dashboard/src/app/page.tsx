"use client";

import { useState } from "react";

import ActionButton from "@/components/ActionButton";
import AppShell from "@/components/AppShell";
import ArtifactPanel from "@/components/ArtifactPanel";
import CodeEditor from "@/components/CodeEditor";
import CodePanel from "@/components/CodePanel";
import HealthStrip from "@/components/HealthStrip";
import PipelineModeSelector from "@/components/PipelineModeSelector";
import PipelineProgress from "@/components/PipelineProgress";
import StageTabs from "@/components/StageTabs";
import { runPipelineMode } from "@/lib/api";
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

export default function HomePage() {
  const { workspace, actions } = useWorkspace();
  const { status, error, refresh, setStatus } = useBackendStatus(true);
  const [mode, setMode] = useState<PipelineMode>("full");
  const [activeTab, setActiveTab] = useState("java");
  const [loading, setLoading] = useState(false);

  async function runPipeline() {
    setLoading(true);
    actions.setLastError(null);
    try {
      const nextStatus = await refresh();
      setStatus(nextStatus);
      actions.setBackendStatus(nextStatus);
      const payload = await runPipelineMode(workspace.sourceCode, mode, workspace.parserResult, workspace.analysisResult);

      if (payload.parser_output) {
        actions.setParserResult(payload.parser_output);
        setActiveTab("parser");
      }
      if (payload.analysis_output) {
        actions.setAnalysisResult(payload.analysis_output);
        setActiveTab("analysis");
      }
      if (payload.java_source) {
        actions.setJavaCode(payload.java_source);
        setActiveTab("java");
      }
    } catch (caught) {
      actions.setLastError(caught instanceof Error ? caught.message : "Pipeline failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell
      title="COBOL Modernizer"
      subtitle="Run a single COBOL source through real backend pipeline modes and inspect every returned artifact."
    >
      <HealthStrip status={workspace.backendStatus ?? status} lastError={workspace.lastError ?? error} />

      <div className="toolbar-card glass-card">
        <PipelineModeSelector value={mode} onChange={setMode} modes={PIPELINE_MODES} />
        <div className="action-row">
          <ActionButton variant="secondary" onClick={actions.reset}>
            Reset
          </ActionButton>
          <ActionButton onClick={runPipeline} disabled={loading}>
            {loading ? "Running Pipeline..." : "Run Pipeline"}
          </ActionButton>
        </div>
      </div>

      <PipelineProgress currentStage={loading ? "Convert" : null} mode={mode} />

      <div className="overhaul-grid">
        <CodeEditor label="COBOL Input (.cbl / .cob)" value={workspace.sourceCode} onChange={actions.setSourceCode} minHeight={460} />
        <div className="output-card">
          <StageTabs tabs={OUTPUT_TABS} activeTab={activeTab} onChange={setActiveTab} />
          <div className="output-card-body">
            {activeTab === "parser" && (
              <ArtifactPanel title="Parser Output" data={workspace.parserResult ?? { message: "Run a parse-capable mode to see parser output." }} />
            )}
            {activeTab === "analysis" && (
              <ArtifactPanel title="Analysis Output" data={workspace.analysisResult ?? { message: "Run analysis-capable mode to see semantic output." }} />
            )}
            {activeTab === "java" && <CodePanel title="Converted Java" code={workspace.javaCode} />}
            {activeTab === "tests" && (
              <ArtifactPanel title="Test Report" data={{ message: "Open Testing Agent to run full backend test reports." }} />
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
