"use client";

import type { DiffSummary, ExecutionMode } from "@/lib/testingAgentTypes";
import { executionModeLabel } from "@/lib/testingAgentTypes";

export default function TestingDiffPanel({
  cobolOutput,
  javaOutput,
  diffSummary,
  executionMode,
  failureReason,
  fallbackMode,
}: {
  cobolOutput: string;
  javaOutput: string;
  diffSummary: DiffSummary;
  executionMode?: ExecutionMode;
  failureReason?: string | null;
  fallbackMode?: boolean;
}) {
  const parityBlocked =
    Boolean(diffSummary.parity_blocked) ||
    diffSummary.comparison_status === "not_comparable" ||
    diffSummary.comparison_status === "execution_failed" ||
    diffSummary.comparison_status === "blocked";
  const notRun = parityBlocked || diffSummary.lines_compared <= 0;
  const snapshotOnly = executionMode === "snapshot";

  let hint = "Side-by-side normalized stdout from the behavioral diff runner.";
  if (parityBlocked) {
    hint =
      failureReason ??
      "Behavioral comparison blocked because COBOL/Java execution did not produce comparable stdout.";
  } else if (snapshotOnly) {
    hint += " Compared snapshot outputs (fallback mode) — not live execution.";
  } else if (executionMode === "live") {
    hint += " Compared live program stdout.";
  } else if (notRun) {
    hint +=
      " No stdout was captured. Install cobc and a JDK on the API host for live runs, or enable snapshot fallback with both snapshot outputs.";
  }

  return (
    <section className="glass-card testing-panel">
      <div className="panel-label" style={{ marginBottom: 12 }}>
        COBOL vs Java diff
      </div>
      {executionMode && executionMode !== "unavailable" ? (
        <p className="testing-panel-hint testing-panel-hint--mode">
          <strong>{executionModeLabel(executionMode)}</strong>
          {fallbackMode && executionMode !== "snapshot" ? " (fallback enabled)" : null}
        </p>
      ) : null}
      {notRun && failureReason ? (
        <p className="testing-panel-hint testing-panel-hint--warn">{failureReason}</p>
      ) : null}
      <p className="testing-panel-hint">
        {hint}
        {!parityBlocked && diffSummary.first_mismatch_index != null
          ? ` First mismatch at line ${diffSummary.first_mismatch_index + 1}.`
          : null}
        {!parityBlocked && diffSummary.diff_percentage != null && diffSummary.lines_compared > 0
          ? ` Diff ${diffSummary.diff_percentage}%.`
          : null}
      </p>
      {!parityBlocked ? (
        <div className="testing-diff-stats">
          <span>
            Compared <strong>{diffSummary.lines_compared}</strong> lines
          </span>
          <span className="testing-diff-stat--match">
            Matched <strong>{diffSummary.lines_matched}</strong>
          </span>
          <span className="testing-diff-stat--drift">
            Diverged <strong>{diffSummary.lines_diverged}</strong>
          </span>
        </div>
      ) : (
        <p className="testing-panel-hint" style={{ marginTop: 8 }}>
          Stdout parity was not scored — fix compile/runtime blockers first.
        </p>
      )}
      {!parityBlocked && diffSummary.highlights.length > 0 && (
        <div className="testing-diff-highlights">
          <div className="panel-label" style={{ marginBottom: 8, fontSize: 12 }}>
            Highlighted differences
          </div>
          {diffSummary.highlights.map((row, idx) => (
            <div key={`${row.line}-${idx}`} className="testing-diff-row">
              <span className="testing-diff-line">L{row.line}</span>
              <span className="testing-diff-cobol">{row.cobol}</span>
              <span className="testing-diff-java">{row.java}</span>
              {row.likely_paragraph ? (
                <span className="testing-diff-para" title={row.failure_kind}>
                  → {row.likely_paragraph}
                </span>
              ) : null}
            </div>
          ))}
        </div>
      )}
      <div className="testing-output-columns">
        <div className="testing-output-col">
          <div className="testing-output-label">COBOL output</div>
          <pre className="code-panel testing-output-pre">{cobolOutput || "(empty)"}</pre>
        </div>
        <div className="testing-output-col">
          <div className="testing-output-label">Java output</div>
          <pre className="code-panel testing-output-pre">{javaOutput || "(empty)"}</pre>
        </div>
      </div>
    </section>
  );
}
