"use client";

import type {
  ExecutionCaptureView,
  RetryScopeMeta,
  TestingAgentRunResult,
} from "@/lib/testingAgentTypes";

function compileDiagnostic(cap: ExecutionCaptureView | undefined, label: string): string | null {
  if (!cap) return null;
  const status = cap.execution_status ?? "";
  if (status !== "compile_failure" && status !== "runtime_failure" && status !== "skipped") {
    if (!cap.error && !cap.compile_stderr?.trim() && !cap.stderr?.trim()) return null;
  }
  const detail = (cap.compile_stderr || cap.stderr || cap.error || "").trim();
  if (!detail && !status) return null;
  const head = status || cap.error || "error";
  return `${label} (${head}): ${detail.slice(0, 600) || "no diagnostic text"}`;
}

export default function TestingFailurePanel({
  run,
  derivedScope,
  scopeLoading,
  retryLoading,
  onRetryScope,
  runValidationLoop,
  onToggleValidationLoop,
}: {
  run: TestingAgentRunResult;
  derivedScope: RetryScopeMeta | null;
  scopeLoading?: boolean;
  retryLoading?: boolean;
  onRetryScope: () => void;
  runValidationLoop?: boolean;
  onToggleValidationLoop?: (value: boolean) => void;
}) {
  const hasFailure = Boolean(run.failure_reason) || run.affected_paragraphs.length > 0;
  const canRetry = hasFailure && Boolean(derivedScope);
  const execDiag =
    run.execution_details?.flatMap((detail) => {
      const sid = detail.scenario_id || "default";
      const rows: string[] = [];
      const cob = compileDiagnostic(detail.cobol_execution, `COBOL ${sid}`);
      const jav = compileDiagnostic(detail.java_execution, `Java ${sid}`);
      if (cob) rows.push(cob);
      if (jav) rows.push(jav);
      return rows;
    }) ?? [];

  const retryLabel = (() => {
    if (!derivedScope) return "Retry this scope";
    const { scope_type, scope_id } = derivedScope;
    if (scope_type === "paragraph") return `Retry paragraph ${scope_id}`;
    if (scope_type === "section") return `Retry section ${scope_id}`;
    if (scope_type === "method") return `Retry method ${scope_id}`;
    if (scope_type === "file") return "Retry this file";
    if (scope_type === "program") return "Retry full program";
    return "Retry this scope";
  })();

  return (
    <section className="glass-card testing-panel">
      <div className="panel-label" style={{ marginBottom: 12 }}>
        Failure analysis
      </div>
      {!hasFailure ? (
        <p className="testing-empty-hint">No failures recorded for this run.</p>
      ) : (
        <>
          {run.failure_reason ? (
            <div className="testing-failure-reason">
              <span className="testing-summary-label">Failure reason</span>
              <p>{run.failure_reason}</p>
            </div>
          ) : null}
          {execDiag.length > 0 ? (
            <div style={{ marginBottom: 10 }}>
              <span className="testing-summary-label">Compile / execution diagnostics</span>
              <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 12, fontFamily: "monospace" }}>
                {execDiag.map((line) => (
                  <li key={line} style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                    {line}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {run.failed_tests.length > 0 ? (
            <div style={{ marginBottom: 10 }}>
              <span className="testing-summary-label">Failing tests</span>
              <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 13 }}>
                {run.failed_tests.map((ft) => (
                  <li key={ft.id}>
                    <code>{ft.id}</code> — {ft.description}
                    {ft.likely_paragraph ? (
                      <span style={{ color: "var(--text-muted)" }}> @ {ft.likely_paragraph}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {run.affected_paragraphs.length > 0 ? (
            <div className="testing-affected-paragraphs">
              <span className="testing-summary-label">Affected paragraphs</span>
              <ul>
                {run.affected_paragraphs.map((para) => (
                  <li key={para}>
                    <code>{para}</code>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {derivedScope ? (
            <div className="testing-retry-scope" style={{ marginBottom: 10 }}>
              <span className="testing-summary-label">Retry scope</span>
              <p style={{ margin: "6px 0", fontSize: 13 }}>
                <strong>{derivedScope.scope_type}</strong> <code>{derivedScope.scope_id}</code>
                <span style={{ color: "var(--text-muted)" }}> ({derivedScope.confidence} confidence)</span>
              </p>
              <p className="testing-panel-hint" style={{ margin: 0 }}>
                {derivedScope.reason}
              </p>
              {derivedScope.affected_methods.length > 0 ? (
                <p className="testing-panel-hint" style={{ marginTop: 6, marginBottom: 0 }}>
                  Methods: {derivedScope.affected_methods.join(", ")}
                </p>
              ) : null}
              <p className="testing-panel-hint" style={{ marginTop: 4, marginBottom: 0 }}>
                Fallback if needed: {derivedScope.fallback_scope}
              </p>
            </div>
          ) : scopeLoading ? (
            <p className="testing-panel-hint">Deriving retry scope…</p>
          ) : run.retry_scope ? (
            <p className="testing-retry-scope">
              <span className="testing-summary-label">Retry scope</span> <code>{run.retry_scope}</code>
            </p>
          ) : null}
        </>
      )}
      <div className="testing-retry-row" style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
        {onToggleValidationLoop ? (
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
            <input
              type="checkbox"
              checked={Boolean(runValidationLoop)}
              onChange={(e) => onToggleValidationLoop(e.target.checked)}
            />
            Run validation loop (regenerate tests)
          </label>
        ) : null}
        <button
          type="button"
          className="action-button primary"
          disabled={!canRetry || retryLoading || scopeLoading}
          onClick={onRetryScope}
        >
          {retryLoading ? "Retrying…" : retryLabel}
        </button>
      </div>
    </section>
  );
}
