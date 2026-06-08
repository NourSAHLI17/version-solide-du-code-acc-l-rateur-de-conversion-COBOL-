"use client";

import type {
  ExecutionMode,
  TestingFinalDecisionResult,
  ValidationBucketStatus,
} from "@/lib/testingAgentTypes";

function decisionLabel(state: string): string {
  if (state === "ready_to_save") return "Ready to save";
  if (state === "needs_more_validation") return "Needs more validation";
  return "Retry recommended";
}

function decisionTone(state: string): string {
  if (state === "ready_to_save") return "var(--success, #22c55e)";
  if (state === "needs_more_validation") return "var(--warning, #eab308)";
  return "var(--error, #ef4444)";
}

function behavioralTestLabel(
  pass: boolean,
  runStatus?: string,
  executionMode?: ExecutionMode,
  linesCompared?: number,
): string {
  if (runStatus === "not_run") {
    const liveRan = executionMode === "live" || executionMode === "mixed";
    const snapshotRan = executionMode === "snapshot" || executionMode === "mixed";
    if ((liveRan || snapshotRan) && (linesCompared ?? 0) > 0) {
      const suffix = snapshotRan && !liveRan ? " (snapshot)" : snapshotRan ? " (mixed)" : "";
      return pass ? `pass${suffix}` : `fail${suffix}`;
    }
    if (liveRan) {
      return "ran live (no stdout compared)";
    }
    if (snapshotRan) {
      return "ran snapshot (no stdout compared)";
    }
    return "not run (execution unavailable)";
  }
  if (runStatus === "failed") {
    return "fail";
  }
  const modeSuffix =
    executionMode === "snapshot"
      ? " (snapshot)"
      : executionMode === "mixed"
        ? " (mixed)"
        : "";
  return pass ? `pass${modeSuffix}` : `fail${modeSuffix}`;
}

function validationBucketLabel(status: ValidationBucketStatus | undefined, pass: boolean): string {
  if (status === "pass" || pass) return "pass";
  if (status === "ready") return "artifacts ready";
  return "not available";
}

function validationBucketTone(status: ValidationBucketStatus | undefined, pass: boolean): string {
  if (status === "pass" || pass) return "var(--success)";
  if (status === "ready") return "var(--warning, #eab308)";
  return "var(--text-muted)";
}

function behavioralLabelTone(
  pass: boolean,
  runStatus?: string,
  executionMode?: ExecutionMode,
  linesCompared?: number,
): string {
  if (runStatus === "not_run") {
    const liveRan = executionMode === "live" || executionMode === "mixed";
    const snapshotRan = executionMode === "snapshot" || executionMode === "mixed";
    if ((liveRan || snapshotRan) && (linesCompared ?? 0) > 0) {
      return pass ? "var(--success)" : "var(--text-muted)";
    }
    if (liveRan || snapshotRan) {
      return "var(--warning, #eab308)";
    }
    return "var(--warning, #eab308)";
  }
  return pass ? "var(--success)" : "var(--text-muted)";
}

export default function TestingDecisionPanel({
  decision,
  behavioralRunStatus,
  behavioralExecutionMode,
  behavioralLinesCompared,
  layeredQscore,
  loading,
  error,
  placeholder,
  onSaveToHistory,
  onManualSaveToHistory,
  saving,
}: {
  decision: TestingFinalDecisionResult | null;
  behavioralRunStatus?: string;
  behavioralExecutionMode?: ExecutionMode;
  behavioralLinesCompared?: number;
  layeredQscore?: number | null;
  loading?: boolean;
  error?: string | null;
  placeholder?: string;
  onSaveToHistory?: () => void;
  onManualSaveToHistory?: () => void;
  saving?: boolean;
}) {
  const showPlaceholder = !decision && !loading;
  const primaryScore =
    layeredQscore != null && !Number.isNaN(Number(layeredQscore))
      ? Math.round(Number(layeredQscore))
      : decision?.reliability_score;
  const primaryScoreTone =
    primaryScore != null && primaryScore >= 85
      ? "var(--success, #22c55e)"
      : primaryScore != null && primaryScore >= 55
        ? "var(--warning, #eab308)"
        : decision
          ? decisionTone(decision.decision_state)
          : "var(--text-muted)";

  return (
    <section
      className="glass-card testing-panel testing-decision-panel"
      style={{
        padding: 18,
        borderColor: decision ? decisionTone(decision.decision_state) : "var(--border)",
        borderWidth: 2,
      }}
    >
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", gap: 16 }}>
          <div style={{ flex: "1 1 200px" }}>
          <p className="hero-kicker" style={{ margin: "0 0 4px" }}>
            Can I trust this conversion?
          </p>
          <div className="panel-label">Reliability decision</div>
        </div>
        {decision ? (
          <div
            style={{
              fontSize: 42,
              fontWeight: 700,
              lineHeight: 1,
              color: primaryScoreTone,
            }}
          >
            {primaryScore ?? "—"}
          </div>
        ) : null}
      </div>

      {loading ? (
        <p className="testing-panel-hint" style={{ marginTop: 12 }}>
          Computing reliability score…
        </p>
      ) : null}

      {error ? (
        <p className="testing-panel-hint" style={{ marginTop: 12, color: "var(--warning, #eab308)" }}>
          {error}
        </p>
      ) : null}

      {decision?.is_local_estimate ? (
        <p className="testing-panel-hint" style={{ marginTop: 8, marginBottom: 0 }}>
          Showing estimated score from run data (final-decision API unavailable).
        </p>
      ) : null}

      {decision ? (
        <DecisionBody
          decision={decision}
          behavioralRunStatus={behavioralRunStatus}
          behavioralExecutionMode={behavioralExecutionMode}
          behavioralLinesCompared={behavioralLinesCompared}
          layeredQscore={layeredQscore}
          onSaveToHistory={onSaveToHistory}
          onManualSaveToHistory={onManualSaveToHistory}
          saving={saving}
        />
      ) : showPlaceholder ? (
        <p className="testing-empty-hint" style={{ marginTop: 12 }}>
          {placeholder ?? "No reliability decision available yet."}
        </p>
      ) : null}
    </section>
  );
}

function DecisionBody({
  decision,
  behavioralRunStatus,
  behavioralExecutionMode,
  behavioralLinesCompared,
  layeredQscore,
  onSaveToHistory,
  onManualSaveToHistory,
  saving,
}: {
  decision: TestingFinalDecisionResult;
  behavioralRunStatus?: string;
  behavioralExecutionMode?: ExecutionMode;
  behavioralLinesCompared?: number;
  layeredQscore?: number | null;
  onSaveToHistory?: () => void;
  onManualSaveToHistory?: () => void;
  saving?: boolean;
}) {
  const linesCompared = behavioralLinesCompared ?? 0;
  const showMatchRate =
    linesCompared > 0 &&
    behavioralRunStatus !== "failed" &&
    behavioralRunStatus !== "not_run";
  const matchLabel = showMatchRate
    ? `${decision.diff_summary?.match_rate ?? 0}% match`
    : "N/A (no comparable stdout)";
  return (
    <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
        <span
          className="testing-summary-pill"
          style={{
            borderColor: decisionTone(decision.decision_state),
            color: decisionTone(decision.decision_state),
          }}
        >
          {decisionLabel(decision.decision_state)}
        </span>
        <span className="testing-summary-label">
          Save eligible:{" "}
          <strong style={{ color: decision.save_eligible ? "var(--success)" : "var(--text-muted)" }}>
            {decision.save_eligible ? "Yes" : "No"}
          </strong>
        </span>
      </div>

      <p style={{ margin: 0, fontSize: 14, color: "var(--text-muted)" }}>
        {decision.save_eligible
          ? "This conversion meets trust thresholds — you may save to history."
          : "Review blockers or run a scoped retry before saving."}
      </p>

      {decision.reason_summary ? (
        <p className="testing-panel-hint" style={{ margin: 0 }}>
          {decision.reason_summary}
        </p>
      ) : null}

      {decision.diff_summary ? (
        <div>
          <span className="testing-summary-label">Behavioral diff</span>
          <p style={{ margin: "4px 0 0", fontSize: 14 }}>
            <strong>{matchLabel}</strong>
            {showMatchRate && decision.diff_summary.mismatch_count > 0
              ? ` · ${decision.diff_summary.mismatch_count} line(s) diverged`
              : ""}
          </p>
          {layeredQscore != null ? (
            <p className="testing-panel-hint" style={{ margin: "4px 0 0" }}>
              Layered diagnostic qscore: <strong>{Math.round(Number(layeredQscore))}</strong>
              {decision.reliability_score != null &&
              Math.round(Number(layeredQscore)) !== decision.reliability_score
                ? ` · reliability rollup ${decision.reliability_score}`
                : ""}
            </p>
          ) : null}
        </div>
      ) : null}

      {decision.test_summary ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, fontSize: 13 }}>
          {(
            [
              {
                label: "Behavioral",
                pass: decision.test_summary.behavioral_pass,
                status: undefined as ValidationBucketStatus | undefined,
              },
              {
                label: "Business rules",
                pass: decision.test_summary.business_rules_pass,
                status: decision.test_summary.business_rules_status,
              },
              {
                label: "Edge cases",
                pass: decision.test_summary.edge_cases_pass,
                status: decision.test_summary.edge_cases_status,
              },
              {
                label: "Unit tests",
                pass: decision.test_summary.unit_tests_pass,
                status: decision.test_summary.unit_tests_status,
              },
            ] as const
          ).map(({ label, pass, status }) => (
            <span
              key={label}
              style={{
                color:
                  label === "Behavioral"
                    ? behavioralLabelTone(
                        pass,
                        behavioralRunStatus,
                        behavioralExecutionMode,
                        behavioralLinesCompared,
                      )
                    : validationBucketTone(status, pass),
              }}
            >
              {label}:{" "}
              {label === "Behavioral"
                ? behavioralTestLabel(
                    pass,
                    behavioralRunStatus,
                    behavioralExecutionMode,
                    behavioralLinesCompared,
                  )
                : validationBucketLabel(status, pass)}
            </span>
          ))}
        </div>
      ) : null}

      {decision.score_breakdown ? (
        <div>
          <span className="testing-summary-label">Score breakdown</span>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 13 }}>
            {Object.entries(decision.score_breakdown).map(([key, val]) => (
              <li key={key}>
                {key.replace(/_/g, " ")}: <strong>{val}</strong>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div>
        <span className="testing-summary-label">Retry recommendation</span>
        {decision.decision_state === "retry_recommended" || decision.retry_scope ? (
          decision.retry_scope ? (
            <p className="testing-panel-hint" style={{ margin: "6px 0 0" }}>
              Retry <strong>{decision.retry_scope.scope_type}</strong>{" "}
              <code>{decision.retry_scope.scope_id}</code>
              {decision.retry_scope.confidence
                ? ` (${decision.retry_scope.confidence} confidence)`
                : ""}
            </p>
          ) : (
            <p className="testing-panel-hint" style={{ margin: "6px 0 0" }}>
              Scoped retry recommended — use the failure panel below.
            </p>
          )
        ) : (
          <p className="testing-panel-hint" style={{ margin: "6px 0 0" }}>
            None — no scoped retry needed.
          </p>
        )}
      </div>

      {decision.blockers.length > 0 ? (
        <div>
          <span className="testing-summary-label">Blockers</span>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 13, color: "var(--text-muted)" }}>
            {decision.blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
        {decision.save_eligible && onSaveToHistory ? (
          <button
            type="button"
            className="action-button primary"
            disabled={saving}
            onClick={onSaveToHistory}
          >
            {saving ? "Saving…" : "Save stable run to history"}
          </button>
        ) : null}
        {!decision.save_eligible && onManualSaveToHistory ? (
          <button
            type="button"
            className="action-button secondary"
            disabled={saving}
            onClick={onManualSaveToHistory}
          >
            {saving ? "Saving…" : "Save to History"}
          </button>
        ) : null}
      </div>
    </div>
  );
}
