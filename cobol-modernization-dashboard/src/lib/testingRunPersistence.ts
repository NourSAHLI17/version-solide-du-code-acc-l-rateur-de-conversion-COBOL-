/**
 * Run persistence states for the testing page (session vs durable history).
 */

import type { HistoryEntry } from "@/services/historyService";

/** In-browser session only — not durable across browsers or server restarts. */
export type TestingRunPersistenceState = "session" | "stable_saved" | "saved";

export type DurableTestingPersistenceState = Exclude<TestingRunPersistenceState, "session">;

export function persistenceStateLabel(state: TestingRunPersistenceState): string {
  switch (state) {
    case "session":
      return "Current session run";
    case "stable_saved":
      return "Stable saved run";
    case "saved":
      return "Saved history run";
    default:
      return "Current session run";
  }
}

export function isDurablePersistence(state: TestingRunPersistenceState | undefined): boolean {
  return state === "stable_saved" || state === "saved";
}

export function persistenceStateFromHistoryEntry(entry: HistoryEntry): DurableTestingPersistenceState {
  if (entry.historyPersistence === "stable_saved" || entry.historyPersistence === "saved") {
    return entry.historyPersistence;
  }
  return entry.force_save ? "saved" : "stable_saved";
}

export function persistenceHintForState(state: TestingRunPersistenceState | undefined): string {
  switch (state) {
    case "session":
      return "Visible for this browser session only. Use Save stable run to history or Save to History to keep it after refresh.";
    case "stable_saved":
      return "Committed to server history (met trust thresholds). Available after refresh and on the History page.";
    case "saved":
      return "Manually saved to server history. Available after refresh and on the History page.";
    default:
      return "";
  }
}
