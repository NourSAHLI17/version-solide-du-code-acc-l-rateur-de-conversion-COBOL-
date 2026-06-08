import {
  saveProjectWorkspace,
  type ProjectWorkspace,
} from "@/lib/projectWorkspace";
import { saveSingleWorkspace, type SingleFileWorkspace } from "@/lib/singleFileWorkspace";
import type { TestingTargetType } from "@/lib/testingAgentTypes";

const TESTING_REPLAY_KEY = "cobol-testing-replay-workspace";

export type TestingReplayWorkspace =
  | { mode: "single_file"; workspace: SingleFileWorkspace }
  | { mode: "project"; workspace: ProjectWorkspace };

/** Persist the exact workspace snapshot used when Run Testing was clicked. */
export function persistTestingReplayWorkspace(payload: TestingReplayWorkspace): void {
  const storage = launchStorage();
  if (!storage) return;
  storage.setItem(TESTING_REPLAY_KEY, JSON.stringify(payload));
}

/** Apply handoff workspace to localStorage (returns mode if applied). */
export function applyTestingReplayWorkspace(): TestingTargetType | null {
  const replay = consumeTestingReplayWorkspace();
  if (!replay) return null;
  if (replay.mode === "project") {
    saveProjectWorkspace(replay.workspace);
    return "project";
  }
  saveSingleWorkspace(replay.workspace);
  return "single_file";
}

/** Load replay workspace and clear the one-shot handoff. */
export function consumeTestingReplayWorkspace(): TestingReplayWorkspace | null {
  const storage = launchStorage();
  if (!storage) return null;
  try {
    const raw = storage.getItem(TESTING_REPLAY_KEY);
    if (!raw) return null;
    storage.removeItem(TESTING_REPLAY_KEY);
    const parsed = JSON.parse(raw) as Partial<TestingReplayWorkspace>;
    if (parsed.mode === "project" && parsed.workspace && typeof parsed.workspace === "object") {
      return { mode: "project", workspace: parsed.workspace as ProjectWorkspace };
    }
    if (parsed.mode === "single_file" && parsed.workspace && typeof parsed.workspace === "object") {
      return { mode: "single_file", workspace: parsed.workspace as SingleFileWorkspace };
    }
    return null;
  } catch {
    storage.removeItem(TESTING_REPLAY_KEY);
    return null;
  }
}

function launchStorage(): Storage | null {
  if (typeof window !== "undefined") return window.sessionStorage;
  const g = globalThis as { sessionStorage?: Storage };
  return g.sessionStorage ?? null;
}
