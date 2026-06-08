"use client";

import dynamic from "next/dynamic";
import { useCallback, useState } from "react";

import type { EdgeCaseTestResult } from "@/lib/testingService";

const MonacoJavaViewer = dynamic(() => import("@/components/MonacoJavaViewer"), {
  ssr: false,
  loading: () => (
    <p className="testing-panel-hint" style={{ margin: 0 }}>
      Loading editor…
    </p>
  ),
});

export default function TestingEdgeCasePanel({
  hydrated,
  result,
  loading,
  error,
  onGenerate,
  canGenerate,
}: {
  /** False until client storage has been read — keeps SSR/first paint markup aligned. */
  hydrated: boolean;
  result: EdgeCaseTestResult | null;
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

  if (!hydrated || !canGenerate) {
    return null;
  }

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
          {open ? "▼" : "▶"} Edge Case Tests
        </button>
        <button
          type="button"
          className="action-button primary"
          disabled={!canGenerate || loading}
          onClick={onGenerate}
        >
          {loading ? "Generating…" : "Generate Edge Case Tests"}
        </button>
        {result ? (
          <span className="testing-panel-hint" style={{ margin: 0 }}>
            {result.edge_cases.length} edge case(s) · {result.test_count} test methods
          </span>
        ) : null}
      </div>

      {open ? (
        <>
          {error ? <p className="testing-panel-hint" style={{ color: "var(--error)" }}>{error}</p> : null}
          {!result && !loading && !error ? (
            <p className="testing-empty-hint">
              Generate JUnit 5 tests from parser structural metadata (loops, OCCURS, exits, EVALUATE).
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
              {result.edge_cases.length > 0 ? (
                <div>
                  <div className="panel-label" style={{ marginBottom: 6 }}>
                    Generated edge cases
                  </div>
                  <ul className="testing-boundary-list" style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                    {result.edge_cases.map((row, i) => (
                      <li key={`${row.type}-${row.field ?? i}`} style={{ marginBottom: 6 }}>
                        <strong>{row.type}</strong>
                        {row.paragraph ? (
                          <span style={{ color: "var(--text-muted)" }}> @ {row.paragraph}</span>
                        ) : null}
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
