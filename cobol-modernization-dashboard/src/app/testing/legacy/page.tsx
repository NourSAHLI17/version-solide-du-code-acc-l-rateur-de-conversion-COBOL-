"use client";

import { useMemo, useState } from "react";

import ActionButton from "@/components/ActionButton";
import AppShell from "@/components/AppShell";
import StatusPill from "@/components/StatusPill";
import { runTests } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";

type TestResult = {
  id: string;
  description: string;
  passed: boolean;
  severity?: "critical" | "high" | "medium" | "low" | string;
  detail?: unknown;
  details?: unknown;
  stdout_diff?: Array<{ line?: number; cobol?: string; java?: string }>;
  assertion_failures?: string[];
  java_stdout?: string;
  java_compile_error?: string;
};

const SUITES = [
  { key: "parser_tests", label: "Parser", stage: "parser", accent: "var(--sky)" },
  { key: "jcl_tests", label: "JCL", stage: "jcl", accent: "var(--orange)" },
  { key: "conversion_tests", label: "Conversion", stage: "java", accent: "var(--emerald)" },
  { key: "behavioral_tests", label: "Behavioral", stage: "tests", accent: "var(--amber)" },
] as const;

function SuiteCard({ label, tests, accent }: { label: string; tests: TestResult[]; accent: string }) {
  const passed = tests.filter((test) => test.passed).length;
  const total = tests.length;
  const allPass = total > 0 && passed === total;

  return (
    <div className="suite-card" style={{ borderColor: allPass ? accent : "rgba(239, 68, 68, 0.65)" }}>
      <strong style={{ color: accent }}>{label}</strong>
      <div className="score" style={{ color: allPass ? accent : "var(--danger)" }}>
        {passed}/{total}
      </div>
      <div className="file-meta">{total === 0 ? "No results yet" : allPass ? "All checks passed" : `${total - passed} failing checks`}</div>
    </div>
  );
}

export default function LegacyTestingPage() {
  const { workspace, hydrated } = useWorkspace();
  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const latestProjectResult = useMemo(
    () => workspace.projectResults.find((result) => typeof result.java_source === "string" && result.java_source),
    [workspace.projectResults],
  );
  const javaSource = workspace.javaCode || String(latestProjectResult?.java_source ?? "");
  const parserOutput = workspace.parserResult || (latestProjectResult?.parser_output as Record<string, unknown> | undefined) || {};
  const analysisOutput = workspace.analysisResult || (latestProjectResult?.analysis_output as Record<string, unknown> | undefined) || {};
  const canRunTests = hydrated && Boolean(javaSource);

  const allTests = useMemo<TestResult[]>(() => {
    if (!report) {
      return [];
    }
    return SUITES.flatMap((suite) => (report[suite.key] as TestResult[] | undefined) ?? []);
  }, [report]);

  const executeTests = async () => {
    setLoading(true);
    try {
      const result = await runTests(parserOutput, analysisOutput, javaSource, workspace.sourceCode || "");
      setReport(result);
    } catch (err) {
      console.error("Test execution failed", err);
      alert("Test suite failed to run. Ensure Java code exists if running full stage.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppShell
      title="Testing Agent (Legacy)"
      subtitle="Original workspace-integrated suite runner. Prefer /testing for the dedicated testing agent UI."
    >
      <div className="toolbar-card glass-card">
        <div>
          <div className="hero-kicker">Stage 9 Verification</div>
          <p className="toolbar-copy">Runs the real backend testing endpoint and visualizes every returned suite.</p>
        </div>
        <ActionButton onClick={executeTests} disabled={loading || !canRunTests}>
          {loading ? "Executing Tests..." : "Run Tests"}
        </ActionButton>
      </div>

      {!hydrated && <div className="error-banner">Loading generated Java from the workspace...</div>}

      {hydrated && !canRunTests && (
        <div className="error-banner">
          Generate Java code first from Single File, Conversion, or Project Upload to enable the full testing suite.
        </div>
      )}

      {report && (
        <div className="cockpit-status-strip glass-card">
          {SUITES.map((suite) => {
            const tests = (report[suite.key] ?? []) as TestResult[];
            const allPass = tests.length > 0 && tests.every((test) => test.passed);
            return (
              <StatusPill
                key={suite.key}
                label={`${suite.label}: ${allPass ? "pass" : "check"}`}
                tone={allPass ? "good" : "warn"}
              />
            );
          })}
          <StatusPill
            label={report["is_pipeline_green"] ? "Pipeline green" : "Pipeline failing"}
            tone={report["is_pipeline_green"] ? "good" : "bad"}
          />
        </div>
      )}

      <section className="suite-grid">
        {SUITES.map((suite) => (
          <SuiteCard
            key={suite.key}
            label={suite.label}
            accent={suite.accent}
            tests={(report?.[suite.key] ?? []) as TestResult[]}
          />
        ))}
      </section>

      <div className="glass-card">
        <div className="panel-label" style={{ marginBottom: 12 }}>
          Test Detail Table
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="results-table">
            <thead className="table-head">
              <tr>
                <th>#</th>
                <th>ID</th>
                <th>Description</th>
                <th>Result</th>
                <th>Severity</th>
              </tr>
            </thead>
            <tbody>
              {allTests.length === 0 && (
                <tr>
                  <td colSpan={5} style={{ padding: 32, textAlign: "center", color: "var(--text-muted)" }}>
                    Run tests to populate the detail table.
                  </td>
                </tr>
              )}
              {allTests.map((test, index) => {
                const detail = test.detail ?? test.details ?? test.java_compile_error;
                const isExpanded = expanded.has(test.id);
                return (
                  <>
                    <tr
                      key={test.id}
                      onClick={() => {
                        const next = new Set(expanded);
                        if (next.has(test.id)) next.delete(test.id);
                        else next.add(test.id);
                        setExpanded(next);
                      }}
                      style={{ cursor: "pointer", background: test.passed ? undefined : "rgba(127, 29, 29, 0.18)" }}
                    >
                      <td className="file-meta">{index + 1}</td>
                      <td className="file-path">{test.id}</td>
                      <td>{test.description}</td>
                      <td style={{ color: test.passed ? "var(--emerald)" : "var(--danger)", fontWeight: 800 }}>
                        {test.passed ? "PASS" : "FAIL"}
                      </td>
                      <td
                        style={{
                          color:
                            test.severity === "critical"
                              ? "var(--danger)"
                              : test.severity === "high"
                                ? "var(--amber)"
                                : "var(--text-muted)",
                        }}
                      >
                        {test.severity ?? "medium"}
                      </td>
                    </tr>
                    {isExpanded && detail ? (
                      <tr key={`${test.id}-detail`}>
                        <td colSpan={5}>
                          <pre className="code-panel" style={{ minHeight: 80 }}>
                            {typeof detail === "string" ? detail : JSON.stringify(detail, null, 2)}
                          </pre>
                        </td>
                      </tr>
                    ) : null}
                  </>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </AppShell>
  );
}
