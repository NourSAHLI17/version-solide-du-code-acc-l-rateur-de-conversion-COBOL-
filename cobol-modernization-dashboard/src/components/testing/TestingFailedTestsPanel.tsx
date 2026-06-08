"use client";

import StatusBadge from "@/components/StatusBadge";
import type { FailedTest } from "@/lib/testingAgentTypes";

function severityTone(severity: FailedTest["severity"]): "error" | "running" | "neutral" {
  if (severity === "critical" || severity === "high") return "error";
  if (severity === "medium") return "running";
  return "neutral";
}

export default function TestingFailedTestsPanel({ failedTests }: { failedTests: FailedTest[] }) {
  return (
    <section className="glass-card testing-panel">
      <div className="panel-label" style={{ marginBottom: 12 }}>
        Failed tests
      </div>
      {failedTests.length === 0 ? (
        <p className="testing-empty-hint">All scenarios passed for this run.</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="results-table testing-failed-table">
            <thead className="table-head">
              <tr>
                <th>ID</th>
                <th>Scenario</th>
                <th>Description</th>
                <th>Severity</th>
              </tr>
            </thead>
            <tbody>
              {failedTests.map((test) => (
                <tr key={test.id}>
                  <td className="file-path">{test.id}</td>
                  <td>
                    <code>{test.scenario_id}</code>
                  </td>
                  <td>{test.description}</td>
                  <td>
                    <StatusBadge label={test.severity} tone={severityTone(test.severity)} compact />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
