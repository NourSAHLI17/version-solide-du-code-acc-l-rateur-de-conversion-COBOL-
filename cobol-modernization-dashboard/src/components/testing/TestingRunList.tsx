"use client";

import ReliabilityScoreBadge from "@/components/ReliabilityScoreBadge";
import type { TestingRunListItem } from "@/lib/testingAgentTypes";
import { reliabilityBadgeForTestingRun } from "@/lib/reliabilityBadge";
import { targetModeLabel } from "@/lib/testingAgentTypes";

export default function TestingRunList({
  runs,
  selectedRunId,
  onSelect,
}: {
  runs: TestingRunListItem[];
  selectedRunId: string | null;
  onSelect: (runId: string) => void;
}) {
  return (
    <div className="testing-run-list">
      <div className="panel-label" style={{ marginBottom: 10 }}>
        Test runs
      </div>
      {runs.length === 0 ? (
        <p className="testing-empty-hint">No test runs yet.</p>
      ) : (
        <ul className="testing-run-list-items">
          {runs.map((run) => {
            const active = run.run_id === selectedRunId;
            return (
              <li key={run.run_id}>
                <button
                  type="button"
                  className={`testing-run-item${active ? " testing-run-item--active" : ""}`}
                  onClick={() => onSelect(run.run_id)}
                >
                  <div className="testing-run-item-top">
                    <strong>{run.program_name}</strong>
                    <ReliabilityScoreBadge
                      score={run.reliability_score}
                      badge={
                        run.badge_display
                          ? {
                              label: run.badge_label ?? run.badge_display,
                              tone: run.badge_tone ?? "neutral",
                              displayText: run.badge_display,
                            }
                          : reliabilityBadgeForTestingRun(
                              run.status,
                              run.reliability_score,
                              run.reliability_score,
                            )
                      }
                      forceSave={run.force_save}
                    />
                  </div>
                  <div className="testing-run-item-meta">
                    {run.persistence_label ? (
                      <span className="testing-run-persistence-label">{run.persistence_label}</span>
                    ) : null}
                    <span>{new Date(run.created_at).toLocaleString()}</span>
                    <span>
                      {run.target_type === "project"
                        ? `${run.scenario_count} files · ${run.failed_count} with issues`
                        : `${run.scenario_count} scenarios · ${run.failed_count} failed`}
                      {run.target_type ? ` · ${targetModeLabel(run.target_type)}` : ""}
                    </span>
                  </div>
                  <code className="testing-run-id">{run.run_id}</code>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
