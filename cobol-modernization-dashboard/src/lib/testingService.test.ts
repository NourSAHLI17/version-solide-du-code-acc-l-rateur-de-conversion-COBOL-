import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  findRunById,
  normalizeBehavioralDiffResponse,
  prependRun,
  resolveDisplayRun,
  resolveEffectiveBehavioralStatus,
  hydrateRunForDisplay,
  runResultToListItem,
  runsToListItems,
} from "./testingResponseMapper.ts";

const API_SAMPLE: Record<string, unknown> = {
  run_id: "live-run-1",
  program_name: "DEMO",
  created_at: "2026-05-17T12:00:00.000Z",
  status: "partial",
  input_set: {
    id: "set-1",
    name: "Test set",
    scenarios: [{ id: "scn-1", label: "Smoke", inputs: { CHOICE: "1" } }],
  },
  cobol_output: "line A\nline B\n",
  java_output: "line A\nline WRONG\n",
  diff_summary: {
    lines_compared: 2,
    lines_matched: 1,
    lines_diverged: 1,
    diff_percentage: 50,
    first_mismatch_index: 1,
    highlights: [
      {
        line: 2,
        cobol: "line B",
        java: "line WRONG",
        likely_paragraph: "2000-VALIDATE",
        failure_kind: "content_mismatch",
      },
    ],
  },
  failed_tests: [
    {
      id: "BEH_scn-1",
      scenario_id: "scn-1",
      description: "Stdout mismatch",
      severity: "high",
      likely_paragraph: "2000-VALIDATE",
    },
  ],
  failure_reason: "Behavioral drift at line 2 (likely paragraph 2000-VALIDATE).",
  affected_paragraphs: ["2000-VALIDATE"],
  retry_scope: "2000-VALIDATE",
  failure_mapping: { scenarios_mapped: 1, primary_retry_scope: "2000-VALIDATE" },
};

describe("testingResponseMapper", () => {
  it("maps optional layered scoring fields from API", () => {
    const run = normalizeBehavioralDiffResponse({
      ...API_SAMPLE,
      qscore: 72,
      layer_scores: {
        compile_health: 100,
        runtime_health: 100,
        behavioral_parity: 25,
        retry_stability: 55,
        attribution_confidence: 80,
      },
      primary_failure_layer: "behavioral_parity",
      run_diagnostics: {
        behavioral_status: "partial",
        execution_mode: "snapshot",
        lines_compared: 2,
        lines_matched: 1,
        lines_diverged: 1,
      },
    });
    assert.equal(run.qscore, 72);
    assert.equal(run.layer_scores?.behavioral_parity, 25);
    assert.equal(run.primary_failure_layer, "behavioral_parity");
    assert.equal(run.run_diagnostics?.behavioral_status, "partial");
  });

  it("normalizes API payload into UI run result", () => {
    const run = normalizeBehavioralDiffResponse(API_SAMPLE);
    assert.equal(run.run_id, "live-run-1");
    assert.equal(run.status, "partial");
    assert.equal(run.retry_scope, "2000-VALIDATE");
    assert.equal(run.affected_paragraphs[0], "2000-VALIDATE");
    assert.equal(run.diff_summary.diff_percentage, 50);
    assert.equal(run.diff_summary.first_mismatch_index, 1);
    assert.equal(run.diff_summary.highlights[0]?.likely_paragraph, "2000-VALIDATE");
    assert.equal(run.failure_reason?.includes("2000-VALIDATE"), true);
  });

  it("successful API fetch path maps via normalize (injected fetcher)", async () => {
    const raw = await (async () => API_SAMPLE)();
    const run = normalizeBehavioralDiffResponse(raw);
    assert.equal(run.program_name, "DEMO");
    const item = runResultToListItem(run);
    assert.equal(item.failed_count, 1);
    assert.equal(item.status, "partial");
  });

  it("empty identical result has no failure fields", () => {
    const run = normalizeBehavioralDiffResponse({
      ...API_SAMPLE,
      status: "passed",
      failed_tests: [],
      failure_reason: null,
      affected_paragraphs: [],
      retry_scope: "",
      diff_summary: {
        lines_compared: 2,
        lines_matched: 2,
        lines_diverged: 0,
        highlights: [],
      },
      cobol_output: "a\nb\n",
      java_output: "a\nb\n",
    });
    assert.equal(run.status, "passed");
    assert.equal(run.failed_tests.length, 0);
    assert.equal(run.retry_scope, "");
  });

  it("prependRun places newest run first", () => {
    const a = normalizeBehavioralDiffResponse({ ...API_SAMPLE, run_id: "a" });
    const b = normalizeBehavioralDiffResponse({ ...API_SAMPLE, run_id: "b" });
    const next = prependRun([a], b);
    assert.equal(next[0]?.run_id, "b");
    assert.equal(next.length, 2);
  });

  it("findRunById returns matching run", () => {
    const a = normalizeBehavioralDiffResponse({ ...API_SAMPLE, run_id: "a" });
    assert.equal(findRunById([a], "a")?.run_id, "a");
    assert.equal(findRunById([a], null), null);
  });

  it("runsToListItems maps list shape", () => {
    const run = normalizeBehavioralDiffResponse(API_SAMPLE);
    const items = runsToListItems([run]);
    assert.equal(items[0]?.scenario_count, 1);
    assert.equal(items[0]?.failed_count, 1);
  });

  it("normalizes project mode with file_results and project_summary", () => {
    const run = normalizeBehavioralDiffResponse({
      ...API_SAMPLE,
      target_type: "project",
      target_id: "proj-1",
      project_id: "proj-1",
      program_name: "MY-PROJECT",
      file_results: [{ ...API_SAMPLE, path: "a.cbl", filename: "a.cbl" }],
      project_summary: {
        project_name: "MY-PROJECT",
        files_total: 2,
        files_tested: 1,
        files_passed: 0,
        files_partial: 1,
        files_failed: 0,
        files_skipped: 1,
        file_summaries: [
          {
            path: "a.cbl",
            filename: "a.cbl",
            program_name: "DEMO",
            status: "partial",
            diff_percentage: 50,
          },
        ],
      },
    });
    assert.equal(run.target_type, "project");
    assert.equal(run.project_summary?.files_skipped, 1);
    assert.equal(run.file_results?.[0]?.path, "a.cbl");
    const item = runResultToListItem(run);
    assert.equal(item.target_type, "project");
    assert.equal(item.scenario_count, 1);
  });

  it("resolveDisplayRun returns per-file slice when path selected", () => {
    const project = normalizeBehavioralDiffResponse({
      ...API_SAMPLE,
      target_type: "project",
      program_name: "PROJ",
      file_results: [
        { ...API_SAMPLE, run_id: "f1", program_name: "FILE-A", path: "a.cbl", filename: "a.cbl" },
      ],
      project_summary: {
        project_name: "PROJ",
        files_total: 1,
        files_tested: 1,
        files_passed: 0,
        files_partial: 1,
        files_failed: 0,
        files_skipped: 0,
        file_summaries: [],
      },
    });
    const slice = resolveDisplayRun(project, "a.cbl");
    assert.match(slice.program_name, /FILE-A/);
    assert.equal(slice.run_id, "f1");
  });

  it("resolveEffectiveBehavioralStatus promotes snapshot not_run with stdout", () => {
    const status = resolveEffectiveBehavioralStatus("not_run", {
      execution_mode: "snapshot",
      lines_compared: 12,
      lines_diverged: 0,
      failed_count: 0,
    });
    assert.equal(status, "passed");
  });

  it("resolveEffectiveBehavioralStatus promotes not_run when stdout compared but mode unavailable", () => {
    const status = resolveEffectiveBehavioralStatus("not_run", {
      execution_mode: "unavailable",
      lines_compared: 8,
      lines_diverged: 0,
      failed_count: 0,
    });
    assert.equal(status, "passed");
  });

  it("hydrateRunForDisplay promotes root and per-file status for project runs", () => {
    const run = hydrateRunForDisplay({
      target_type: "project",
      run_id: "p1",
      program_name: "PROJ",
      created_at: new Date().toISOString(),
      status: "not_run",
      execution_mode: "unavailable",
      input_set: { id: "s", name: "S", scenarios: [] },
      cobol_output: "",
      java_output: "",
      diff_summary: {
        lines_compared: 10,
        lines_matched: 10,
        lines_diverged: 0,
        diff_percentage: 0,
        highlights: [],
      },
      failed_tests: [],
      failure_reason: null,
      affected_paragraphs: [],
      retry_scope: "",
      file_results: [
        {
          path: "a.cbl",
          program_name: "A",
          status: "not_run",
          execution_mode: "unavailable",
          cobol_output: "",
          java_output: "",
          diff_summary: {
            lines_compared: 4,
            lines_matched: 4,
            lines_diverged: 0,
            diff_percentage: 0,
            highlights: [],
          },
          failed_tests: [],
          failure_reason: null,
          affected_paragraphs: [],
          retry_scope: "",
        },
      ],
    });
    assert.equal(run.status, "passed");
    assert.equal(run.execution_mode, "live");
    assert.equal(run.file_results?.[0]?.status, "passed");
  });
});
