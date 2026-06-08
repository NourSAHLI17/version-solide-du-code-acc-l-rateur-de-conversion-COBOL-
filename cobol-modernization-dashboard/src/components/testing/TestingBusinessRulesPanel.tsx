"use client";

import { useCallback, useState } from "react";

import MonacoJavaViewer from "@/components/MonacoJavaViewer";
import type { BusinessRulesTestResult } from "@/lib/testingService";

export default function TestingBusinessRulesPanel({
  result,
  loading,
  error,
  onGenerate,
  canGenerate,
}: {
  result: BusinessRulesTestResult | null;
  loading: boolean;
  error: string | null;
  onGenerate: () => void;
  canGenerate: boolean;
}) {
  const [open, setOpen] = useState(true);

  const downloadJava = useCallback(() => {
    if (!result?.test_source) return;
    const blob = new Blob([result.test_source], { type: "text/x-java-source" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${result.test_class_name}.java`;
    a.click();
    URL.revokeObjectURL(url);
  }, [result]);

  const copySource = useCallback(() => {
    if (!result?.test_source) return;
    void navigator.clipboard.writeText(result.test_source);
  }, [result]);

  return (
    <div className="glass-card testing-panel" style={{ padding: 14 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginBottom: 10 }}>
        <button
          type="button"
          className="action-button secondary"
          style={{ padding: "4px 10px" }}
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          {open ? "▼" : "▶"} Business Rules Tests
        </button>
        <button
          type="button"
          className="action-button primary"
          disabled={!canGenerate || loading}
          onClick={onGenerate}
        >
          {loading ? "Generating…" : "Generate Business Rules Tests"}
        </button>
        {result ? (
          <span className="testing-panel-hint" style={{ margin: 0 }}>
            {result.rules_covered}/{result.rules_total} rules covered · {result.test_count} test methods
          </span>
        ) : null}
      </div>

      {open ? (
        <>
          {error ? <p className="testing-panel-hint" style={{ color: "var(--error)" }}>{error}</p> : null}
          {!result && !loading && !error ? (
            <p className="testing-empty-hint">
              Generate JUnit 5 tests from workspace business rules and Java output.
            </p>
          ) : null}
          {result ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                <button type="button" className="action-button secondary" onClick={copySource}>
                  Copy source
                </button>
                <button type="button" className="action-button secondary" onClick={downloadJava}>
                  Download .java
                </button>
              </div>
              {result.boundary_inputs.length > 0 ? (
                <div>
                  <div className="panel-label" style={{ marginBottom: 6 }}>
                    Boundary inputs
                  </div>
                  <ul className="testing-boundary-list" style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                    {result.boundary_inputs.map((row) => (
                      <li key={`${row.rule}-${row.pattern}`} style={{ marginBottom: 6 }}>
                        <strong>{row.rule}</strong>
                        <span style={{ color: "var(--text-muted)" }}> ({row.pattern})</span>
                        {": "}
                        {JSON.stringify(row.values)}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <MonacoJavaViewer value={result.test_source} height="320px" />
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
