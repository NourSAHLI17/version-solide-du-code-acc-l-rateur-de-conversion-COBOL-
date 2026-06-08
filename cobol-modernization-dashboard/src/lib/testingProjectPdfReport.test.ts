import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  ACME_PROGRAM_PROFILES,
  buildLineComparisonRows,
  buildProjectTestingPdfReportModel,
} from "./testingProjectPdfReport.ts";
import type { TestingAgentRunResult } from "./testingAgentTypes.ts";

function sampleRun(): TestingAgentRunResult {
  return {
    run_id: "run-demo-001",
    program_name: "ACME Bank v3",
    created_at: "2026-06-01T12:00:00.000Z",
    status: "passed",
    qscore: 100,
    cobol_output: "",
    java_output: "",
    file_results: [
      {
        path: "LOANEVAL.cbl",
        program_name: "LOANEVAL",
        status: "passed",
        cobol_output:
          "LOANEVAL COMPLETED.\n  READ        : 00000800\n  APPROVED    : 00000454\n",
        java_output:
          "LOANEVAL COMPLETED.\n  READ        : 00000800\n  APPROVED    : 00000454\n",
        diff_summary: { diff_percentage: 0, lines_diverged: 0, highlights: [] },
      },
    ],
    project_summary: {
      project_name: "ACME Bank v3",
      files_tested: 6,
      files_passed: 6,
      file_summaries: ACME_PROGRAM_PROFILES.map((p) => ({
        path: `${p.name}.cbl`,
        program_name: p.name,
        status: "passed",
        diff_percentage: 0,
      })),
    },
  } as TestingAgentRunResult;
}

describe("testingProjectPdfReport", () => {
  it("buildLineComparisonRows marks matching lines", () => {
    const cobol = "LOANEVAL COMPLETED.\n  READ        : 00000800\n";
    const java = "LOANEVAL COMPLETED.\n  READ        : 00000800\n";
    const rows = buildLineComparisonRows(cobol, java);
    assert.ok(rows.length >= 2);
    assert.equal(rows[0][3], "✓");
    assert.equal(rows[1][3], "✓");
  });

  it("buildProjectTestingPdfReportModel includes all six programs", () => {
    const model = buildProjectTestingPdfReportModel(sampleRun(), null);
    assert.equal(model.program_rows.length, 6);
    assert.equal(model.overall_score, "100/100");
    assert.equal(model.overall_status, "PASSED");
    assert.ok(model.side_by_side_sections.some((s) => s.title.includes("LOANEVAL")));
  });
});
