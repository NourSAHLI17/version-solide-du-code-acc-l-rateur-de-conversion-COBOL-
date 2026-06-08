"use client";

import type { LayerScores, RunDiagnostics, TestingAgentRunResult } from "@/lib/testingAgentTypes";
import { formatFailureLayer, hasLayeredScoring } from "@/lib/testingAgentTypes";

const LAYER_ROWS: { key: keyof LayerScores; label: string }[] = [
  { key: "compile_health", label: "Compile" },
  { key: "runtime_health", label: "Runtime" },
  { key: "behavioral_parity", label: "Parity" },
  { key: "retry_stability", label: "Retry" },
  { key: "attribution_confidence", label: "Attribution" },
];

function scoreTone(score: number | null | undefined): string {
  if (score == null) return "var(--text-muted)";
  if (score >= 80) return "var(--success, #22c55e)";
  if (score >= 50) return "var(--warning, #eab308)";
  return "var(--error, #ef4444)";
}

function formatScore(score: number | null | undefined): string {
  if (score == null) return "N/A";
  return String(score);
}

function DiagnosticsDetails({ diagnostics }: { diagnostics: RunDiagnostics }) {
  const rows: { label: string; value: string }[] = [];
  const push = (label: string, value: string | number | null | undefined) => {
    if (value == null || value === "") return;
    rows.push({ label, value: String(value) });
  };

  push("Behavioral status", diagnostics.behavioral_status);
  push("Execution mode", diagnostics.execution_mode);
  push("COBOL execution", diagnostics.cobol_execution_status);
  push("Java execution", diagnostics.java_execution_status);
  push("COBOL compile", diagnostics.cobol_compile_status);
  push("Java compile", diagnostics.java_compile_status);
  push("COBOL runtime", diagnostics.cobol_runtime_status);
  push("Java runtime", diagnostics.java_runtime_status);
  if (diagnostics.stdout_diff_percentage != null) {
    push("Stdout diff %", `${diagnostics.stdout_diff_percentage}%`);
  }
  if (diagnostics.first_mismatch_line != null) {
    push("First mismatch line", diagnostics.first_mismatch_line + 1);
  }
  if (diagnostics.lines_compared != null) {
    push(
      "Lines compared / matched / diverged",
      `${diagnostics.lines_compared} / ${diagnostics.lines_matched ?? 0} / ${diagnostics.lines_diverged ?? 0}`,
    );
  }
  if (diagnostics.infrastructure_blocker) {
    push("Infrastructure blocker", "yes");
  }
  if (diagnostics.retry_scope) {
    push("Retry scope", diagnostics.retry_scope);
  }
  if (diagnostics.failure_reason) {
    push("Failure reason", diagnostics.failure_reason);
  }

  if (rows.length === 0) {
    return <p className="testing-layered-diagnostics-empty">No diagnostic details available.</p>;
  }

  return (
    <dl className="testing-layered-diagnostics-grid">
      {rows.map((row) => (
        <div key={row.label} className="testing-layered-diagnostics-row">
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function TestingLayeredScoringPanel({ run }: { run: TestingAgentRunResult }) {
  if (!hasLayeredScoring(run)) {
    return null;
  }

  const layerScores = run.layer_scores;
  const qscore = run.qscore;

  return (
    <section className="glass-card testing-layered-panel" aria-label="Layered diagnostic scoring">
      <div className="testing-layered-header">
        <div>
          <div className="panel-label">Diagnostic score</div>
          <p className="testing-layered-subtitle">
            Weighted quality score across compile, runtime, parity, retry, and attribution layers.
          </p>
        </div>
        {qscore != null ? (
          <div className="testing-layered-qscore" style={{ color: scoreTone(qscore) }}>
            <span className="testing-layered-qscore-value">{qscore}</span>
            <span className="testing-layered-qscore-label">qscore</span>
          </div>
        ) : (
          <span className="testing-layered-qscore-missing">Score unavailable</span>
        )}
      </div>

      {run.primary_failure_layer ? (
        <p className="testing-layered-blocker">
          <span className="testing-layered-blocker-label">Primary blocker</span>
          <strong>{formatFailureLayer(run.primary_failure_layer)}</strong>
        </p>
      ) : null}

      {layerScores ? (
        <div className="testing-layered-breakdown">
          <div className="panel-label">Layer breakdown</div>
          <ul className="testing-layered-layers">
            {LAYER_ROWS.map(({ key, label }) => {
              const score = layerScores[key];
              const applicable = run.run_diagnostics?.layers_applicable?.[key];
              const na = score == null && applicable === false;
              return (
                <li key={key} className="testing-layered-layer">
                  <span className="testing-layered-layer-name">{label}</span>
                  <span
                    className="testing-layered-layer-score"
                    style={{ color: scoreTone(score) }}
                    title={na ? "Not applicable for this run" : undefined}
                  >
                    {formatScore(score)}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {run.run_diagnostics ? (
        <details className="testing-layered-details">
          <summary>Run diagnostics</summary>
          <div className="testing-layered-details-body">
            <DiagnosticsDetails diagnostics={run.run_diagnostics} />
          </div>
        </details>
      ) : null}
    </section>
  );
}
