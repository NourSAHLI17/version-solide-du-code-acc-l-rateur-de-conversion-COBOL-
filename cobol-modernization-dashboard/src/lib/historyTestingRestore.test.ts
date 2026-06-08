import assert from "node:assert/strict";
import { describe, it, beforeEach } from "node:test";

import { canRunTestingFromHistory, restoreWorkspaceFromHistory } from "./historyTestingRestore.ts";
import { loadProjectWorkspace, PROJECT_WORKSPACE_KEY } from "./projectWorkspace.ts";
import { loadSingleWorkspace, SINGLE_WORKSPACE_KEY } from "./singleFileWorkspace.ts";

describe("historyTestingRestore", () => {
  beforeEach(() => {
    const store: Record<string, string> = {};
    globalThis.localStorage = {
      store,
      getItem(k: string) {
        return store[k] ?? null;
      },
      setItem(k: string, v: string) {
        store[k] = v;
      },
      removeItem(k: string) {
        delete store[k];
      },
      clear() {
        for (const key of Object.keys(store)) delete store[key];
      },
      key: () => null,
      length: 0,
    };
  });

  it("detects testable single-file history", () => {
    assert.equal(
      canRunTestingFromHistory({
        id: "1",
        type: "single",
        programName: "HELLO",
        createdAt: new Date().toISOString(),
        score: 80,
        cost: null,
        parserOutput: {},
        analysisOutput: {},
        javaOutput: "class X {}",
        sourceCode: "       PROGRAM-ID. HELLO.",
      }),
      true,
    );
  });

  it("restores single-file workspace to localStorage", () => {
    const result = restoreWorkspaceFromHistory({
      id: "1",
      type: "single",
      programName: "HELLO",
      createdAt: new Date().toISOString(),
      score: 80,
      cost: null,
      parserOutput: { ok: true },
      analysisOutput: { ok: true },
      javaOutput: "public class Hello {}",
      sourceCode: "       PROGRAM-ID. HELLO.",
    });
    assert.deepEqual(result, { mode: "single_file" });
    const ws = loadSingleWorkspace();
    assert.ok(ws?.javaOutput?.includes("Hello"));
    assert.ok(localStorage.getItem(SINGLE_WORKSPACE_KEY));
  });

  it("restores project workspace with converted cbl files", () => {
    const result = restoreWorkspaceFromHistory({
      id: "p1",
      type: "project",
      programName: "Demo",
      createdAt: new Date().toISOString(),
      score: 70,
      cost: null,
      parserOutput: {},
      analysisOutput: {},
      javaOutput: null,
      projectSnapshot: {
        projectName: "Demo",
        files: [
          {
            filename: "pay.cbl",
            path: "pay.cbl",
            type: "cbl",
            sourceCode: "       PROGRAM-ID. PAY.",
            parserOutput: {},
            analysisOutput: {},
            javaOutput: "class Pay {}",
            parserStatus: "done",
            analysisStatus: "done",
            conversionStatus: "done",
          },
        ],
      },
    });
    assert.deepEqual(result, { mode: "project" });
    const ws = loadProjectWorkspace();
    assert.equal(ws?.files.filter((f) => f.javaOutput).length, 1);
    assert.ok(localStorage.getItem(PROJECT_WORKSPACE_KEY));
  });
});
