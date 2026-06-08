/** Reliability score badge labels and tones (testing + history lists). */

import type { StatusBadgeTone } from "@/components/StatusBadge";
import type { HistoryEntry } from "@/services/historyService";
import type { TestingRunStatus } from "@/lib/testingAgentTypes";

export type ReliabilityBadgeTone = StatusBadgeTone;

export type ReliabilityBadgeInfo = {
  label: string;
  tone: ReliabilityBadgeTone;
  /** Primary badge text, e.g. "Passed · 91" */
  displayText: string;
};

export function reliabilityBadgeFromScore(
  score: number | null | undefined,
): ReliabilityBadgeInfo {
  if (score == null || Number.isNaN(Number(score))) {
    return { label: "Not Run", tone: "neutral", displayText: "Not Run" };
  }
  const s = Math.round(Number(score));
  if (s <= 0) {
    return { label: "Not Run", tone: "neutral", displayText: "Not Run" };
  }
  if (s >= 85) {
    return { label: "Passed", tone: "success", displayText: `Passed · ${s}` };
  }
  if (s >= 55) {
    return { label: "Needs Review", tone: "running", displayText: `Needs Review · ${s}` };
  }
  return { label: "Failed", tone: "error", displayText: `Failed · ${s}` };
}

/** Map behavioral run status to a display score when reliability_score is absent. */
export function reliabilityScoreFromRunStatus(
  status: TestingRunStatus | string | undefined,
  qscore?: number | null,
): number | null {
  if (qscore != null && !Number.isNaN(Number(qscore))) {
    return Math.round(Number(qscore));
  }
  if (status === "passed") return 90;
  if (status === "partial") return 70;
  if (status === "failed") return 40;
  if (status === "not_run") return 0;
  return null;
}

export function reliabilityBadgeForHistoryEntry(entry: HistoryEntry): ReliabilityBadgeInfo {
  if (entry.reliability_score != null) {
    return reliabilityBadgeFromScore(entry.reliability_score);
  }
  if (entry.status != null) {
    return reliabilityBadgeFromScore(reliabilityScoreFromRunStatus(entry.status));
  }
  return reliabilityBadgeFromScore(null);
}

export function reliabilityBadgeForTestingRun(
  status: TestingRunStatus | string | undefined,
  reliabilityScore?: number | null,
  qscore?: number | null,
): ReliabilityBadgeInfo {
  const score =
    reliabilityScore != null
      ? reliabilityScore
      : reliabilityScoreFromRunStatus(status, qscore);
  return reliabilityBadgeFromScore(score);
}
