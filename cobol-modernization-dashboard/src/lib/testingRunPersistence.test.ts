import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  isDurablePersistence,
  persistenceHintForState,
  persistenceStateFromHistoryEntry,
  persistenceStateLabel,
} from "./testingRunPersistence.ts";
import type { HistoryEntry } from "../services/historyService.ts";

describe("testingRunPersistence", () => {
  it("labels session vs durable states", () => {
    assert.equal(persistenceStateLabel("session"), "Current session run");
    assert.equal(persistenceStateLabel("stable_saved"), "Stable saved run");
    assert.equal(persistenceStateLabel("saved"), "Saved history run");
  });

  it("detects durable persistence", () => {
    assert.equal(isDurablePersistence("session"), false);
    assert.equal(isDurablePersistence("stable_saved"), true);
    assert.equal(isDurablePersistence("saved"), true);
  });

  it("maps history entries to stable vs manual save", () => {
    const stable: HistoryEntry = {
      id: "a",
      type: "single",
      programName: "P",
      createdAt: "2026-01-01T00:00:00Z",
      score: null,
      cost: null,
      parserOutput: {} as HistoryEntry["parserOutput"],
      analysisOutput: {} as HistoryEntry["analysisOutput"],
      javaOutput: null,
      historyPersistence: "stable_saved",
      recordKind: "testing_run",
    };
    const manual: HistoryEntry = { ...stable, id: "b", force_save: true, historyPersistence: "saved" };
    assert.equal(persistenceStateFromHistoryEntry(stable), "stable_saved");
    assert.equal(persistenceStateFromHistoryEntry(manual), "saved");
  });

  it("session hint mentions explicit save", () => {
    assert.match(persistenceHintForState("session"), /Save stable run/i);
  });
});
