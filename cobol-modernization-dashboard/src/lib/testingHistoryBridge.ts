import { scoreListValue } from "@/lib/conversionScore";
import type { TestingAgentRunResult, TestingRunListItem } from "@/lib/testingAgentTypes";
import { reliabilityBadgeForTestingRun } from "@/lib/reliabilityBadge";
import {
  persistenceStateFromHistoryEntry,
  persistenceStateLabel,
  type DurableTestingPersistenceState,
  type TestingRunPersistenceState,
} from "@/lib/testingRunPersistence";
import { normalizeBehavioralDiffResponse } from "@/lib/testingResponseMapper";
import type { HistoryEntry } from "@/services/historyService";
import type { TestingFinalDecisionResult } from "@/lib/testingAgentTypes";

export const TESTING_SIDEBAR_HISTORY_LIMIT = 20;

export function isTestingHistoryEntry(entry: HistoryEntry): boolean {
  return Boolean(
    entry.testingRun ||
      entry.reliability_score != null ||
      entry.status != null ||
      entry.recordKind === "testing_run",
  );
}

export function historyEntryToTestingRun(entry: HistoryEntry): TestingAgentRunResult | null {
  if (!entry.testingRun || typeof entry.testingRun !== "object") {
    return null;
  }
  try {
    return normalizeBehavioralDiffResponse(entry.testingRun as Record<string, unknown>);
  } catch {
    return null;
  }
}

export function buildHistoryEntryFromTestingRun(
  run: TestingAgentRunResult,
  options: {
    reliability_score?: number | null;
    force_save?: boolean;
    historyPersistence?: DurableTestingPersistenceState;
    savedAt?: string;
    finalDecision?: TestingFinalDecisionResult | null;
    parserOutput?: HistoryEntry["parserOutput"];
    analysisOutput?: HistoryEntry["analysisOutput"];
    javaOutput?: string | null;
    sourceCode?: string;
    conversionScore?: HistoryEntry["conversionScore"];
  } = {},
): HistoryEntry {
  const reliability_score =
    options.reliability_score != null
      ? options.reliability_score
      : run.qscore != null
        ? Math.round(Number(run.qscore))
        : null;
  const conversionScore = options.conversionScore ?? null;
  const conversionListScore = conversionScore ? scoreListValue(conversionScore) : null;

  return {
    id: run.run_id,
    type: run.target_type === "project" ? "project" : "single",
    programName: run.program_name,
    createdAt: run.created_at || new Date().toISOString(),
    score: conversionListScore,
    cost: null,
    conversionScore,
    reliability_score,
    status: run.status,
    force_save: Boolean(options.force_save),
    historyPersistence: options.historyPersistence ?? (options.force_save ? "saved" : "stable_saved"),
    savedAt: options.savedAt ?? new Date().toISOString(),
    finalDecisionSnapshot: options.finalDecision
      ? (options.finalDecision as unknown as Record<string, unknown>)
      : undefined,
    recordKind: "testing_run",
    parserOutput: options.parserOutput ?? ({} as HistoryEntry["parserOutput"]),
    analysisOutput: options.analysisOutput ?? ({} as HistoryEntry["analysisOutput"]),
    javaOutput: options.javaOutput ?? null,
    sourceCode: options.sourceCode,
    testingRun: run as unknown as Record<string, unknown>,
  };
}

export function persistenceMapFromHistoryEntries(
  entries: HistoryEntry[],
): Record<string, TestingRunPersistenceState> {
  const out: Record<string, TestingRunPersistenceState> = {};
  for (const entry of entries) {
    if (!isTestingHistoryEntry(entry)) continue;
    out[entry.id] = persistenceStateFromHistoryEntry(entry);
  }
  return out;
}

export function testingRunToListItem(
  run: TestingAgentRunResult,
  extras?: {
    reliability_score?: number | null;
    force_save?: boolean;
    persistence_state?: TestingRunPersistenceState;
  },
): TestingRunListItem {
  const failed_count =
    run.target_type === "project"
      ? (run.file_results?.filter((f) => f.status !== "passed").length ?? 0)
      : (run.failed_tests?.length ?? 0);
  const reliability_score =
    extras?.reliability_score != null
      ? extras.reliability_score
      : run.qscore != null
        ? Math.round(Number(run.qscore))
        : undefined;

  const badge = reliabilityBadgeForTestingRun(run.status, reliability_score, run.qscore);

  const persistence_state = extras?.persistence_state ?? "session";

  return {
    run_id: run.run_id,
    program_name: run.program_name,
    created_at: run.created_at,
    status: run.status,
    scenario_count:
      run.target_type === "project"
        ? run.project_summary?.file_summaries.length ?? run.file_results?.length ?? 0
        : run.input_set?.length ?? 0,
    failed_count,
    target_type: run.target_type,
    reliability_score,
    force_save: extras?.force_save,
    persistence_state,
    persistence_label: persistenceStateLabel(persistence_state),
    badge_label: badge.label,
    badge_display: badge.displayText,
    badge_tone: badge.tone,
  };
}

export function mergeRunsByRecency(
  primary: TestingAgentRunResult[],
  secondary: TestingAgentRunResult[],
): TestingAgentRunResult[] {
  const seen = new Set<string>();
  const out: TestingAgentRunResult[] = [];
  for (const run of [...primary, ...secondary]) {
    if (!run?.run_id || seen.has(run.run_id)) continue;
    seen.add(run.run_id);
    out.push(run);
  }
  return out.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).slice(0, TESTING_SIDEBAR_HISTORY_LIMIT);
}
