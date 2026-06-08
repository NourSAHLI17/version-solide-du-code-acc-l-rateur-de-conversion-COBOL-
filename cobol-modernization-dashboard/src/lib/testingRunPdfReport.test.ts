import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  buildTestingRunReportModel,
  formatTestingRunPdfFilename,
} from "./testingRunPdfReport.ts";
import { EY_LOGO_JPEG_PATH } from "./testingRunPdfLayout.ts";
import type { TestingAgentRunResult, TestingRunStatus } from "./testingAgentTypes.ts";

const SAMPLE_RUN: TestingAgentRunResult = {
  run_id: "ba674212-8bd3-4223-842a-6413111b6317",
  program_name: "AUTOPREM",
  created_at: "2026-05-23T16:46:16.000Z",
  status: "passed" as TestingRunStatus,
  input_set: { id: "default", name: "Default", scenarios: [] },
  cobol_output: "COBOL\n",
  java_output: "COBOL\n",
  diff_summary: {
    lines_compared: 42,
    lines_matched: 42,
    lines_diverged: 0,
    diff_percentage: 0,
    highlights: [],
  },
  failed_tests: [],
  failure_reason: null,
  affected_paragraphs: [],
  retry_scope: "",
  layer_scores: {
    compile_health: 100,
    runtime_health: 100,
    behavioral_parity: 100,
    retry_stability: 100,
    attribution_confidence: 95,
  },
  qscore: 100,
};

describe("testingRunPdfReport", () => {
  it("pdf logo path points at user-provided JPEG in public/brand", () => {
    assert.equal(EY_LOGO_JPEG_PATH, "/brand/ey_logo_icon_171166.jpg");
  });

  it("formatTestingRunPdfFilename uses program and run id", () => {
    const name = formatTestingRunPdfFilename(
      "AUTOPREM",
      "ba674212-8bd3-4223-842a-6413111b6317",
      "2026-05-23T16:46:16.000Z",
    );
    assert.match(name, /^AUTOPREM-testing-run-ba674212/);
    assert.ok(name.endsWith(".pdf"));
    assert.ok(name.includes("2026-05-23"));
  });

  it("buildTestingRunReportModel is deterministic", () => {
    const decision = {
      program_name: "AUTOPREM",
      reliability_score: 100,
      decision_state: "ready_to_save" as const,
      save_eligible: true,
      reason_summary: "High match rate.",
      blockers: [],
      score_breakdown: {
        behavioral_diff: 40,
        business_rules: 20,
        edge_cases: 15,
        unit_tests: 15,
        retry_stability: 10,
      },
      test_summary: {
        behavioral_pass: true,
        business_rules_pass: true,
        edge_cases_pass: true,
        unit_tests_pass: true,
        business_rules_status: "pass" as const,
        edge_cases_status: "ready" as const,
        unit_tests_status: "ready" as const,
      },
      diff_summary: { match_rate: 100, mismatch_count: 0 },
    };
    const input = {
      run: SAMPLE_RUN,
      decision,
      export_source: "history" as const,
      analysis_output: {
        global_purpose: "Rate auto insurance premiums.",
        complexity: "high",
        business_rules: ["Minimum premium 250"],
      },
    };
    const a = buildTestingRunReportModel(input);
    const b = buildTestingRunReportModel(input);
    assert.deepEqual(a, b);
    assert.equal(a.reliability_score, "100");
    assert.equal(a.behavioral_status, "Passed");
    assert.ok(a.decision_label.includes("pass"));
    assert.ok(a.export_source_note.includes("history"));
    assert.ok(a.layer_rows.some(([k]) => k.includes("Compile health")));
    assert.ok(a.analysis_rows.some(([, v]) => v.includes("Rate auto insurance")));
    assert.ok(a.validation_rows.some(([k]) => k.includes("Business rules")));
    assert.ok(a.metadata_rows.some(([k]) => k === "Program"));
    assert.equal(a.executive_rows[0][0], "Reliability score");
  });

  it("session export note differs from history", () => {
    const model = buildTestingRunReportModel({
      run: SAMPLE_RUN,
      decision: null,
      export_source: "session",
    });
    assert.ok(model.export_source_note.includes("current session"));
    assert.ok(model.export_source_note.includes("may not be persisted"));
  });
});
