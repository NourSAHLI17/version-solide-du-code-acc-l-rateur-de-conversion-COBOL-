"use client";

import { useMemo, useState } from "react";

import ActionButton from "@/components/ActionButton";
import AppShell from "@/components/AppShell";
import ArtifactPanel from "@/components/ArtifactPanel";
import CodeEditor from "@/components/CodeEditor";
import CodePanel from "@/components/CodePanel";
import HealthStrip from "@/components/HealthStrip";
import MetricCard from "@/components/MetricCard";
import StatusPill from "@/components/StatusPill";
import { analyzeCobol, convertCobol, parseCobol, validateOutputs } from "@/lib/api";
import { estimateLlmCost } from "@/lib/cost";
import { useBackendStatus } from "@/lib/useBackendStatus";
import { useWorkspace } from "@/lib/workspace";

export default function CockpitPage() {
  const { workspace, actions } = useWorkspace();
  const { status, error, refresh, setStatus } = useBackendStatus(true);
  const [loadingStep, setLoadingStep] = useState<string | null>(null);
  const [lastConversionWorked, setLastConversionWorked] = useState<boolean | null>(null);

  const cost = useMemo(
    () =>
      estimateLlmCost({
        sourceCode: workspace.sourceCode,
        parserResult: workspace.parserResult,
        analysisResult: workspace.analysisResult,
        javaCode: workspace.javaCode,
      }),
    [workspace.analysisResult, workspace.javaCode, workspace.parserResult, workspace.sourceCode],
  );

  async function runStatus() {
    const nextStatus = await refresh();
    setStatus(nextStatus);
    actions.setBackendStatus(nextStatus);
    return nextStatus;
  }

  async function runParse() {
    setLoadingStep("parse");
    actions.setLastError(null);
    try {
      await runStatus();
      const parserResult = await parseCobol(workspace.sourceCode);
      actions.setParserResult(parserResult);
    } catch (caught) {
      actions.setLastError(caught instanceof Error ? caught.message : "Parser step failed.");
    } finally {
      setLoadingStep(null);
    }
  }

  async function runAnalysis() {
    setLoadingStep("analysis");
    actions.setLastError(null);
    try {
      await runStatus();
      const parserResult = await parseCobol(workspace.sourceCode);
      actions.setParserResult(parserResult);
      const analysisResult = await analyzeCobol(workspace.sourceCode, parserResult);
      actions.setAnalysisResult(analysisResult);
    } catch (caught) {
      actions.setLastError(caught instanceof Error ? caught.message : "Analysis step failed.");
    } finally {
      setLoadingStep(null);
    }
  }

  async function runConversion() {
    setLoadingStep("conversion");
    actions.setLastError(null);
    try {
      await runStatus();
      const parserResult = workspace.parserResult ?? (await parseCobol(workspace.sourceCode));
      actions.setParserResult(parserResult);
      const analysisResult = workspace.analysisResult ?? (await analyzeCobol(workspace.sourceCode, parserResult));
      actions.setAnalysisResult(analysisResult);
      const javaCode = await convertCobol(workspace.sourceCode, parserResult, analysisResult);
      actions.setJavaCode(javaCode);
      setLastConversionWorked(true);
    } catch (caught) {
      setLastConversionWorked(false);
      actions.setLastError(caught instanceof Error ? caught.message : "Conversion step failed.");
    } finally {
      setLoadingStep(null);
    }
  }

  async function runValidation() {
    setLoadingStep("validation");
    actions.setLastError(null);
    try {
      await runStatus();
      const validationResult = await validateOutputs(workspace.expectedOutput, workspace.actualOutput);
      actions.setValidationResult(validationResult);
    } catch (caught) {
      actions.setLastError(caught instanceof Error ? caught.message : "Validation step failed.");
    } finally {
      setLoadingStep(null);
    }
  }

  async function runAll() {
    setLoadingStep("all");
    actions.setLastError(null);
    try {
      await runStatus();
      const parserResult = await parseCobol(workspace.sourceCode);
      actions.setParserResult(parserResult);
      const analysisResult = await analyzeCobol(workspace.sourceCode, parserResult);
      actions.setAnalysisResult(analysisResult);
      const javaCode = await convertCobol(workspace.sourceCode, parserResult, analysisResult);
      actions.setJavaCode(javaCode);
      const validationResult = await validateOutputs(workspace.expectedOutput, workspace.actualOutput);
      actions.setValidationResult(validationResult);
      setLastConversionWorked(true);
    } catch (caught) {
      setLastConversionWorked(false);
      actions.setLastError(caught instanceof Error ? caught.message : "Full pipeline failed.");
    } finally {
      setLoadingStep(null);
    }
  }

  return (
    <AppShell
      title="Full Pipeline Cockpit"
      subtitle="Test every backend step from its own control, inspect all artifacts, and monitor backend health, LLM readiness, and estimated conversion cost in one page."
    >
      <HealthStrip status={workspace.backendStatus ?? status} lastError={workspace.lastError ?? error} />

      <section className="metrics-grid">
        <MetricCard label="API Health" value={status?.api_healthy ? "Online" : "Unknown"} hint="Based on /api/status" />
        <MetricCard
          label="LLM API"
          value={
            status?.llm_configured
              ? lastConversionWorked === false
                ? "Configured, last conversion failed"
                : "Configured"
              : "Not configured"
          }
          hint={status?.llm_model ?? "No model available"}
        />
        <MetricCard label="Estimated Cost" value={`$${cost.estimatedCostUsd.toFixed(4)}`} hint="Heuristic token-based estimate" />
      </section>

      <div className="cockpit-status-strip glass-card">
        <StatusPill label={workspace.parserResult ? "Parser done" : "Parser idle"} tone={workspace.parserResult ? "good" : "neutral"} />
        <StatusPill label={workspace.analysisResult ? "Analysis done" : "Analysis idle"} tone={workspace.analysisResult ? "good" : "neutral"} />
        <StatusPill label={workspace.javaCode ? "Conversion done" : "Conversion idle"} tone={workspace.javaCode ? "good" : "neutral"} />
        <StatusPill
          label={workspace.validationResult ? "Validation done" : "Validation idle"}
          tone={workspace.validationResult ? "good" : "neutral"}
        />
      </div>

      <CodeEditor label="COBOL Source" value={workspace.sourceCode} onChange={actions.setSourceCode} minHeight={180} />

      <div className="action-row wrap">
        <ActionButton variant="secondary" onClick={actions.reset}>
          Reset Workspace
        </ActionButton>
        <ActionButton variant="secondary" onClick={runParse} disabled={loadingStep !== null}>
          {loadingStep === "parse" ? "Parsing..." : "Run Parser"}
        </ActionButton>
        <ActionButton variant="secondary" onClick={runAnalysis} disabled={loadingStep !== null}>
          {loadingStep === "analysis" ? "Analyzing..." : "Run Analysis"}
        </ActionButton>
        <ActionButton variant="secondary" onClick={runConversion} disabled={loadingStep !== null}>
          {loadingStep === "conversion" ? "Converting..." : "Run Conversion"}
        </ActionButton>
        <ActionButton variant="secondary" onClick={runValidation} disabled={loadingStep !== null}>
          {loadingStep === "validation" ? "Validating..." : "Run Validation"}
        </ActionButton>
        <ActionButton onClick={runAll} disabled={loadingStep !== null}>
          {loadingStep === "all" ? "Running Full Pipeline..." : "Run Full Pipeline"}
        </ActionButton>
      </div>

      <div className="page-grid cockpit-grid">
        <ArtifactPanel
          title="Parser Output"
          data={workspace.parserResult ?? { message: "Parser artifacts will appear here." }}
        />
        <ArtifactPanel
          title="Analysis Output"
          data={workspace.analysisResult ?? { message: "Analysis output will appear here." }}
        />
        <CodePanel title="Generated Java" code={workspace.javaCode} />
        <ArtifactPanel
          title="Validation Report"
          data={workspace.validationResult ?? { message: "Validation results will appear here." }}
        />
      </div>
    </AppShell>
  );
}
