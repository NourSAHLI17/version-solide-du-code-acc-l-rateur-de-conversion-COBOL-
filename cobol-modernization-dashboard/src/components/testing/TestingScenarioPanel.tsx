"use client";

import type { TestInputSet } from "@/lib/testingAgentTypes";

export default function TestingScenarioPanel({ inputSet }: { inputSet: TestInputSet }) {
  return (
    <section className="glass-card testing-panel">
      <div className="panel-label" style={{ marginBottom: 12 }}>
        Input scenarios — {inputSet.name}
      </div>
      <p className="testing-panel-hint">
        {inputSet.scenarios.length > 0 && inputSet.scenarios.some((s) => Object.keys(s.inputs).length > 0)
          ? "Scripted inputs used for this behavioral comparison run."
          : inputSet.scenarios.length > 0
            ? "Default workspace scenario (stdin) used for live COBOL vs Java execution."
            : "No scenario metadata on this run."}
      </p>
      <div className="testing-scenario-list">
        {inputSet.scenarios.map((scenario) => (
          <article key={scenario.id} className="testing-scenario-card">
            <div className="testing-scenario-header">
              <strong>{scenario.label}</strong>
              <code className="testing-scenario-id">{scenario.id}</code>
            </div>
            <table className="testing-input-table">
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Value</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(scenario.inputs).map(([field, value]) => (
                  <tr key={field}>
                    <td className="testing-input-field">{field}</td>
                    <td>
                      <code>{value}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </article>
        ))}
      </div>
    </section>
  );
}
