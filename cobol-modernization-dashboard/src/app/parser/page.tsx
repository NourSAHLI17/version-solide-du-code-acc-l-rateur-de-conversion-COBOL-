"use client";

import { useState } from "react";

import ActionButton from "@/components/ActionButton";
import AppShell from "@/components/AppShell";
import ArtifactPanel from "@/components/ArtifactPanel";
import CodeEditor from "@/components/CodeEditor";
import HealthStrip from "@/components/HealthStrip";
import { parseCobol } from "@/lib/api";
import { useBackendStatus } from "@/lib/useBackendStatus";
import { useWorkspace } from "@/lib/workspace";

export default function ParserPage() {
  const { workspace, actions } = useWorkspace();
  const { status, error, refresh, setStatus } = useBackendStatus(true);
  const [loading, setLoading] = useState(false);

  async function handleParse() {
    setLoading(true);
    actions.setLastError(null);
    try {
      const nextStatus = await refresh();
      setStatus(nextStatus);
      actions.setBackendStatus(nextStatus);
      const result = await parseCobol(workspace.sourceCode);
      actions.setParserResult(result);
    } catch (caught) {
      actions.setLastError(caught instanceof Error ? caught.message : "Parsing failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell
      title="Parser Layer"
      subtitle="Test the deterministic COBOL parser independently and inspect raw structural artifacts before semantic analysis."
    >
      <HealthStrip status={workspace.backendStatus ?? status} lastError={workspace.lastError ?? error} />

      <div className="page-grid two-column">
        <CodeEditor label="COBOL Source" value={workspace.sourceCode} onChange={actions.setSourceCode} minHeight={420} />
        <ArtifactPanel title="Parser Output" data={workspace.parserResult ?? { message: "Run the parser to see divisions, symbols, control flow, and dependencies." }} />
      </div>

      <div className="action-row">
        <ActionButton variant="secondary" onClick={actions.reset}>
          Reset Workspace
        </ActionButton>
        <ActionButton onClick={handleParse} disabled={loading}>
          {loading ? "Parsing..." : "Run Parser"}
        </ActionButton>
      </div>
    </AppShell>
  );
}
