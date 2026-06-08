import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, it } from "node:test";

const PAGE_PATH = join(process.cwd(), "src", "app", "testing", "page.tsx");
const LEGACY_PATH = join(process.cwd(), "src", "app", "testing", "legacy", "page.tsx");

describe("/testing route module", () => {
  it("exports API-backed testing page with loading and error states", () => {
    const source = readFileSync(PAGE_PATH, "utf8");
    assert.match(source, /export default function TestingAgentPage/);
    assert.match(source, /runBehavioralTestForMode/);
    assert.match(source, /loadTestingTargetMode/);
    assert.match(source, /persistTestingTargetMode/);
    assert.match(source, /single_file.*project/s);
    assert.match(source, /resolveDisplayRun/);
    assert.match(source, /getTestingSidebarAsync/);
    assert.match(source, /historyService/);
    assert.match(source, /loadPersistedTestingSession/);
    assert.match(source, /persistTestingSession/);
    assert.match(source, /persistenceByRunId/);
    assert.match(source, /historyPersistence/);
    assert.doesNotMatch(source, /persistRunToApi\(hydrated\)\.catch/);
    assert.match(source, /loadMockRuns/);
    assert.match(source, /Running diff/);
    assert.match(source, /error-banner/);
    assert.match(source, /TestingRunList/);
    assert.match(source, /TestingFailurePanel/);
    assert.doesNotMatch(source, /getMockTestingRuns\(\)/);
  });

  it("wires section components for scenarios, diff, failures, and retry", () => {
    const source = readFileSync(PAGE_PATH, "utf8");
    assert.match(source, /TestingScenarioPanel/);
    assert.match(source, /TestingDiffPanel/);
    assert.match(source, /TestingFailedTestsPanel/);
    assert.match(source, /TestingSummaryBar/);
    assert.match(source, /TestingBusinessRulesPanel/);
    assert.match(source, /generateBusinessRulesTests/);
    assert.match(source, /TestingEdgeCasePanel/);
    assert.match(source, /generateEdgeCaseTests/);
    assert.match(source, /TestingUnitTestPanel/);
    assert.match(source, /generateUnitTests/);
    assert.match(source, /retryConversionScope/);
    assert.match(source, /deriveRetryScope/);
    assert.match(source, /TestingRetryOutcomePanel/);
    assert.match(source, /TestingDecisionPanel/);
    assert.match(source, /buildFinalDecision/);
    assert.match(source, /consumeTestingLaunch/);
  });
});

describe("/testing/legacy route", () => {
  it("remains the workspace-integrated legacy runner", () => {
    const source = readFileSync(LEGACY_PATH, "utf8");
    assert.match(source, /runTests/);
    assert.match(source, /AppShell/);
    assert.doesNotMatch(source, /fetchBehavioralDiff/);
  });
});
