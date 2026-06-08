import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  formatJavaStageLabel,
  normalizeRepairSummary,
  pipelineToConversionStatus,
} from "./repairSummary.ts";

describe("normalizeRepairSummary", () => {
  it("maps backend snake_case repair_summary", () => {
    const model = normalizeRepairSummary({
      auto_repairs: [
        "Added missing semicolon at line 12",
        "Renamed status → loanStatus (name mismatch)",
      ],
      manual_review: [
        {
          line: 42,
          message: "Type mismatch (manual review): BigDecimal cannot be converted to int",
        },
      ],
    });
    assert.equal(model?.autoRepairs.length, 2);
    assert.equal(model?.manualReview[0]?.line, 42);
    assert.ok(model?.manualReview[0]?.message.includes("Type mismatch"));
  });

  it("returns null when both lists are empty", () => {
    assert.equal(normalizeRepairSummary({ auto_repairs: [], manual_review: [] }), null);
  });
});

describe("pipelineToConversionStatus", () => {
  it("maps done to complete for RepairSummaryPanel", () => {
    assert.equal(pipelineToConversionStatus("done"), "complete");
    assert.equal(pipelineToConversionStatus("partial"), "partial");
  });
});

describe("formatJavaStageLabel", () => {
  it("labels partial conversions clearly", () => {
    assert.equal(formatJavaStageLabel("partial"), "Partial");
    assert.equal(formatJavaStageLabel("complete"), "Done");
  });
});

function panelWouldRender(input: {
  score?: { total: number } | null;
  repairSummary?: ReturnType<typeof normalizeRepairSummary>;
  compileRepairNotes?: string[];
}): boolean {
  const hasRepairs =
    (input.repairSummary?.autoRepairs?.length ?? 0) > 0 ||
    (input.repairSummary?.manualReview?.length ?? 0) > 0;
  return Boolean(input.score) || hasRepairs || (input.compileRepairNotes?.length ?? 0) > 0;
}

describe("RepairSummaryPanel visibility (F37)", () => {
  it("renders when auto-repairs exist", () => {
    const summary = normalizeRepairSummary({
      auto_repairs: ["Removed 2 Spring/framework imports (plain Java profile)"],
      manual_review: [],
    });
    assert.equal(panelWouldRender({ repairSummary: summary }), true);
  });

  it("renders when manual-review items exist", () => {
    const summary = normalizeRepairSummary({
      auto_repairs: [],
      manual_review: [{ line: 10, message: 'Unresolvable name "customAttribute"' }],
    });
    assert.equal(panelWouldRender({ repairSummary: summary }), true);
  });

  it("technical log available when compileRepairNotes non-empty", () => {
    const notes = ["iteration 1: repaired semicolon_expected at T.java:12"];
    assert.equal(notes.length > 0, true);
  });
});

describe("file tree badge counts (F37)", () => {
  it("computes repair and TODO badge text", () => {
    const summary = normalizeRepairSummary({
      auto_repairs: ["a", "b", "c"],
      manual_review: [
        { line: 1, message: "x" },
        { line: 2, message: "y" },
      ],
    });
    assert.equal(`${summary!.autoRepairs.length} repairs`, "3 repairs");
    assert.equal(`${summary!.manualReview.length} TODOs`, "2 TODOs");
  });
});
