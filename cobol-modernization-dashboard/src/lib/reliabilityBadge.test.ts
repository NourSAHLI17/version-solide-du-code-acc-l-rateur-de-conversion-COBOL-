import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  reliabilityBadgeFromScore,
  reliabilityBadgeForHistoryEntry,
  reliabilityScoreFromRunStatus,
} from "./reliabilityBadge.ts";
import type { HistoryEntry } from "@/services/historyService";

describe("reliabilityBadge", () => {
  it("maps score thresholds to badge labels", () => {
    assert.equal(reliabilityBadgeFromScore(91).label, "Passed");
    assert.equal(reliabilityBadgeFromScore(91).tone, "success");
    assert.equal(reliabilityBadgeFromScore(70).label, "Needs Review");
    assert.equal(reliabilityBadgeFromScore(40).label, "Failed");
    assert.equal(reliabilityBadgeFromScore(0).label, "Not Run");
    assert.equal(reliabilityBadgeFromScore(null).label, "Not Run");
  });

  it("derives score from run status when needed", () => {
    assert.equal(reliabilityScoreFromRunStatus("passed"), 90);
    assert.equal(reliabilityScoreFromRunStatus("not_run"), 0);
  });

  it("does not use conversion score for testing reliability badge", () => {
    const entry = {
      id: "x",
      type: "single",
      programName: "DEMO",
      createdAt: "2026-01-01T00:00:00.000Z",
      score: 60,
      cost: null,
      parserOutput: {},
      analysisOutput: {},
      javaOutput: null,
      reliability_score: 55,
    } as HistoryEntry;
    const badge = reliabilityBadgeForHistoryEntry(entry);
    assert.equal(badge.label, "Needs Review");
    assert.match(badge.displayText, /55/);
  });

  it("uses reliability_score on history entries", () => {
    const entry = {
      id: "x",
      type: "single",
      programName: "DEMO",
      createdAt: "2026-01-01T00:00:00.000Z",
      score: null,
      cost: null,
      parserOutput: {},
      analysisOutput: {},
      javaOutput: null,
      reliability_score: 88,
      force_save: true,
    } as HistoryEntry;
    const badge = reliabilityBadgeForHistoryEntry(entry);
    assert.equal(badge.label, "Passed");
    assert.match(badge.displayText, /88/);
  });
});
