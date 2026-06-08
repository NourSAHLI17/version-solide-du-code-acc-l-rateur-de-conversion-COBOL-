"use client";

import { useState } from "react";
import StatusBadge from "@/components/StatusBadge";

export interface SmokeTestCase {
  name: string;
  passed: boolean;
  exit_code: number;
  stdout: string;
  stderr: string;
  duration_ms: number;
  baseline_compared: boolean;
  baseline_match: boolean;
  diff: string;
  error: string | null;
}

export interface SmokeTestResult {
  program_name: string;
  passed: boolean;
  compiled: boolean;
  compile_stderr: string;
  test_cases: SmokeTestCase[];
  data_files_staged: string[];
  wrapper_generated: boolean;
  pass_count: number;
  fail_count: number;
  error: string | null;
}

export function normalizeSmokeTest(raw: unknown): SmokeTestResult | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  if (r.program_name == null && r.compiled == null) return null;

  const cases = Array.isArray(r.test_cases)
    ? (r.test_cases as Record<string, unknown>[]).map((tc) => ({
        name: String(tc.name ?? "main"),
        passed: Boolean(tc.passed),
        exit_code: Number(tc.exit_code ?? -1),
        stdout: String(tc.stdout ?? ""),
        stderr: String(tc.stderr ?? ""),
        duration_ms: Number(tc.duration_ms ?? 0),
        baseline_compared: Boolean(tc.baseline_compared),
        baseline_match: Boolean(tc.baseline_match),
        diff: String(tc.diff ?? ""),
        error: tc.error ? String(tc.error) : null,
      }))
    : [];

  return {
    program_name: String(r.program_name ?? ""),
    passed: Boolean(r.passed),
    compiled: Boolean(r.compiled),
    compile_stderr: String(r.compile_stderr ?? ""),
    test_cases: cases,
    data_files_staged: Array.isArray(r.data_files_staged)
      ? (r.data_files_staged as string[])
      : [],
    wrapper_generated: Boolean(r.wrapper_generated),
    pass_count: Number(r.pass_count ?? 0),
    fail_count: Number(r.fail_count ?? 0),
    error: r.error ? String(r.error) : null,
  };
}

function OutputBlock({ label, text }: { label: string; text: string }) {
  const [expanded, setExpanded] = useState(false);
  if (!text.trim()) return null;
  const lines = text.split("\n");
  const preview = lines.slice(0, 5).join("\n");
  const hasMore = lines.length > 5;

  return (
    <div className="smoke-output-block">
      <div className="smoke-output-label">{label}</div>
      <pre className="smoke-output-pre">
        {expanded ? text : preview}
        {hasMore && !expanded && "\n..."}
      </pre>
      {hasMore && (
        <button
          className="smoke-output-toggle"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? "Show less" : `Show all (${lines.length} lines)`}
        </button>
      )}
    </div>
  );
}

export default function SmokeTestPanel({
  smokeTest,
  compact,
}: {
  smokeTest: SmokeTestResult | unknown | null;
  compact?: boolean;
}) {
  const model = normalizeSmokeTest(smokeTest);
  if (!model) return null;

  const overallTone = model.passed
    ? "success"
    : model.compiled
      ? "error"
      : "neutral";
  const overallLabel = model.passed
    ? "Smoke test passed"
    : model.error
      ? `Smoke test failed: ${model.error}`
      : "Smoke test failed";

  return (
    <div className="smoke-test-panel">
      <div className="smoke-test-header">
        <h3 className="smoke-test-title">Smoke Test</h3>
        <StatusBadge
          label={overallLabel}
          tone={overallTone as "success" | "error" | "neutral"}
        />
      </div>

      {!model.compiled && model.compile_stderr && (
        <OutputBlock label="Compile errors" text={model.compile_stderr} />
      )}

      {model.data_files_staged.length > 0 && !compact && (
        <div className="smoke-data-files">
          <span className="smoke-data-label">Data files staged:</span>
          {model.data_files_staged.map((f) => (
            <span key={f} className="smoke-data-tag">{f}</span>
          ))}
        </div>
      )}

      {model.wrapper_generated && !compact && (
        <div className="smoke-wrapper-note">
          Auto-generated test wrapper (no main() in converted code)
        </div>
      )}

      {model.test_cases.map((tc, i) => (
        <div
          key={tc.name + i}
          className={`smoke-test-case ${tc.passed ? "smoke-case-pass" : "smoke-case-fail"}`}
        >
          <div className="smoke-case-header">
            <span className="smoke-case-icon">{tc.passed ? "\u2713" : "\u2717"}</span>
            <span className="smoke-case-name">{tc.name}</span>
            <span className="smoke-case-meta">
              exit={tc.exit_code} &middot; {tc.duration_ms.toFixed(0)}ms
            </span>
            {tc.baseline_compared && (
              <StatusBadge
                label={tc.baseline_match ? "Baseline match" : "Baseline diff"}
                tone={tc.baseline_match ? "success" : "running"}
              />
            )}
          </div>

          {!compact && (
            <>
              <OutputBlock label="stdout" text={tc.stdout} />
              <OutputBlock label="stderr" text={tc.stderr} />
              {tc.diff && <OutputBlock label="Baseline diff" text={tc.diff} />}
              {tc.error && (
                <div className="smoke-case-error">{tc.error}</div>
              )}
            </>
          )}
        </div>
      ))}
    </div>
  );
}
