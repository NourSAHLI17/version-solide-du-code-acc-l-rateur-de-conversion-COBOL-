"use client";

import { useState } from "react";

import ActionButton from "@/components/ActionButton";
import AppShell from "@/components/AppShell";
import ArtifactPanel from "@/components/ArtifactPanel";
import CodeEditor from "@/components/CodeEditor";
import HealthStrip from "@/components/HealthStrip";
import { validateOutputs } from "@/lib/api";
import { useBackendStatus } from "@/lib/useBackendStatus";
import { useWorkspace } from "@/lib/workspace";

export default function ValidationPage() {
  const { workspace, actions } = useWorkspace();
  const { status, error, refresh, setStatus } = useBackendStatus(true);
  const [loading, setLoading] = useState(false);

  async function handleValidate() {
    setLoading(true);
    actions.setLastError(null);
    try {
      const nextStatus = await refresh();
      setStatus(nextStatus);
      actions.setBackendStatus(nextStatus);
      const validationResult = await validateOutputs(workspace.expectedOutput, workspace.actualOutput);
      actions.setValidationResult(validationResult);
    } catch (caught) {
      actions.setLastError(caught instanceof Error ? caught.message : "Validation failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell
      title="Validation Layer"
      subtitle="Test validation separately with expected and actual outputs, including JSON-aware comparisons and line-level differences."
    >
      <HealthStrip status={workspace.backendStatus ?? status} lastError={workspace.lastError ?? error} />

      <div className="page-grid two-column">
        <CodeEditor label="Expected Output" value={workspace.expectedOutput} onChange={actions.setExpectedOutput} minHeight={260} />
        <CodeEditor label="Actual Output" value={workspace.actualOutput} onChange={actions.setActualOutput} minHeight={260} />
      </div>

      <ArtifactPanel
        title="Validation Report"
        data={workspace.validationResult ?? { message: "Run validation to inspect comparison mode, differences, and warnings." }}
      />

      <div className="action-row">
        <ActionButton variant="secondary" onClick={actions.reset}>
          Reset Workspace
        </ActionButton>
        <ActionButton onClick={handleValidate} disabled={loading}>
          {loading ? "Validating..." : "Run Validation"}
        </ActionButton>
      </div>
    </AppShell>
  );
}
