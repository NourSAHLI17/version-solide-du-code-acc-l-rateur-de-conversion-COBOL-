"use client";

import type { TestingRetryResult } from "@/lib/testingAgentTypes";

function saveStateLabel(state: string): string {
  if (state === "ready_to_save") return "Ready to save";
  if (state === "needs_more_validation") return "Needs more validation";
  return "Retry recommended";
}

export default function TestingRetryOutcomePanel({
  result,
  onSaveToHistory,
  saving,
}: {
  result: TestingRetryResult;
  onSaveToHistory?: () => void;
  saving?: boolean;
}) {
  const scope = result.retry_scope;
  const gate = result.save_gate;
  const requested = result.requested_scope ?? scope.scope_type;
  const actual = result.actual_scope ?? scope.scope_type;

  return (
    <section className="glass-card testing-panel" style={{ marginTop: 10, padding: 14 }}>
      <div className="panel-label" style={{ marginBottom: 10 }}>
        Retry outcome
      </div>
      {result.retry_summary ? (
        <p className="testing-panel-hint" style={{ marginTop: 0 }}>
          {result.retry_summary}
        </p>
      ) : (
        <p className="testing-panel-hint" style={{ marginTop: 0 }}>
          Retried <strong>{scope.scope_type}</strong> <code>{scope.scope_id}</code> — {scope.reason}
        </p>
      )}
      <div
        style={{
          display: "grid",
          gap: 8,
          marginBottom: 10,
          fontSize: 13,
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
        }}
      >
        <div>
          <span className="testing-summary-label">Requested</span>
          <div>
            <strong>{requested}</strong> <code>{scope.scope_id}</code>
          </div>
        </div>
        <div>
          <span className="testing-summary-label">Actual scope used</span>
          <div>
            <strong>{actual}</strong>
            {result.scope_widened ? (
              <span style={{ color: "var(--text-muted)" }}> (widened)</span>
            ) : null}
          </div>
        </div>
        {result.included_paragraphs && result.included_paragraphs.length > 0 ? (
          <div>
            <span className="testing-summary-label">Included paragraphs</span>
            <div style={{ fontFamily: "monospace", fontSize: 12 }}>
              {result.included_paragraphs.join(", ")}
            </div>
          </div>
        ) : null}
      </div>
      {result.scope_widened && result.widen_reason ? (
        <p className="testing-panel-hint" style={{ marginBottom: 10 }}>
          Scope widened: {result.widen_reason}
        </p>
      ) : null}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 10, fontSize: 13 }}>
        {result.reliability_score != null ? (
          <span>
            Reliability: <strong>{result.reliability_score}</strong>
            {result.score_delta != null ? (
              <span style={{ color: result.score_delta >= 0 ? "var(--success)" : "var(--error)" }}>
                {" "}
                ({result.score_delta >= 0 ? "+" : ""}
                {result.score_delta})
              </span>
            ) : null}
          </span>
        ) : null}
        <span>
          Save state: <strong>{saveStateLabel(result.save_state)}</strong>
        </span>
        {result.test_result ? (
          <span>
            Behavioral diff: <strong>{result.test_result.status}</strong>
          </span>
        ) : null}
      </div>
      {gate.blockers.length > 0 ? (
        <ul style={{ margin: "0 0 10px", paddingLeft: 18, fontSize: 13, color: "var(--text-muted)" }}>
          {gate.blockers.map((b) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
      ) : null}
      {gate.reasons.length > 0 ? (
        <ul style={{ margin: "0 0 10px", paddingLeft: 18, fontSize: 13 }}>
          {gate.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      ) : null}
      {result.ready_to_save && onSaveToHistory ? (
        <button
          type="button"
          className="action-button primary"
          disabled={saving}
          onClick={onSaveToHistory}
        >
          {saving ? "Saving…" : "Save stable run to history"}
        </button>
      ) : null}
    </section>
  );
}
