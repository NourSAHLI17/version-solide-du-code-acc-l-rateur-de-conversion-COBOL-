import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { getDefaultMockRunId, getMockTestingRunById, getMockTestingRuns } from "./testingAgentMock.ts";

const REQUIRED_RUN_KEYS = [
  "run_id",
  "program_name",
  "input_set",
  "cobol_output",
  "java_output",
  "diff_summary",
  "failed_tests",
  "failure_reason",
  "affected_paragraphs",
  "retry_scope",
  "status",
] as const;

describe("testingAgentMock contract", () => {
  it("exposes mock run history", () => {
    const list = getMockTestingRuns();
    assert.ok(list.length >= 3);
    assert.ok(list[0]?.run_id);
    assert.match(list[0]!.status, /^(passed|partial|failed)$/);
  });

  it("returns full run payloads with required fields", () => {
    const run = getMockTestingRunById(getDefaultMockRunId());
    assert.ok(run);
    for (const key of REQUIRED_RUN_KEYS) {
      assert.ok(key in run!);
    }
    assert.ok(run!.input_set.scenarios.length > 0);
    assert.equal(typeof run!.diff_summary.lines_compared, "number");
  });
});
