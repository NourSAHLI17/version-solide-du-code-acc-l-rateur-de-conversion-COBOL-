import type { TestingTargetType } from "@/lib/testingAgentTypes";

const TESTING_LAUNCH_KEY = "cobol-testing-launch";

export type TestingLaunchSource = "conversion" | "history";

export interface TestingLaunchRequest {
  mode: TestingTargetType;
  autoRun: boolean;
  source?: TestingLaunchSource;
  historyId?: string;
  scriptedInput?: string;
}

function launchStorage(): Storage | null {
  if (typeof window !== "undefined") return window.sessionStorage;
  const g = globalThis as { sessionStorage?: Storage };
  return g.sessionStorage ?? null;
}

/** Queue an automatic behavioral comparison when the testing page loads. */
export function queueTestingLaunch(request: TestingLaunchRequest): void {
  const storage = launchStorage();
  if (!storage) return;
  storage.setItem(TESTING_LAUNCH_KEY, JSON.stringify(request));
}

/** Read and clear a pending launch request (one-time). */
export function consumeTestingLaunch(): TestingLaunchRequest | null {
  const storage = launchStorage();
  if (!storage) return null;
  try {
    const raw = storage.getItem(TESTING_LAUNCH_KEY);
    if (!raw) return null;
    storage.removeItem(TESTING_LAUNCH_KEY);
    const parsed = JSON.parse(raw) as Partial<TestingLaunchRequest>;
    const mode = parsed.mode === "project" ? "project" : "single_file";
    const source = parsed.source === "history" ? "history" : "conversion";
    return {
      mode,
      autoRun: Boolean(parsed.autoRun),
      source,
      historyId: typeof parsed.historyId === "string" ? parsed.historyId : undefined,
      scriptedInput: typeof parsed.scriptedInput === "string" ? parsed.scriptedInput : undefined,
    };
  } catch {
    storage.removeItem(TESTING_LAUNCH_KEY);
    return null;
  }
}
