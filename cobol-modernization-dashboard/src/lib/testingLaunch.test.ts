import assert from "node:assert/strict";
import { describe, it, beforeEach } from "node:test";

import { consumeTestingLaunch, queueTestingLaunch } from "./testingLaunch.ts";

describe("testingLaunch", () => {
  beforeEach(() => {
    globalThis.sessionStorage = {
      store: {} as Record<string, string>,
      getItem(k: string) {
        return this.store[k] ?? null;
      },
      setItem(k: string, v: string) {
        this.store[k] = v;
      },
      removeItem(k: string) {
        delete this.store[k];
      },
      clear() {
        this.store = {};
      },
      key: () => null,
      length: 0,
    };
  });

  it("queues and consumes a one-time launch request", () => {
    queueTestingLaunch({ mode: "single_file", autoRun: true });
    const launch = consumeTestingLaunch();
    assert.ok(launch);
    assert.equal(launch.mode, "single_file");
    assert.equal(launch.autoRun, true);
    assert.equal(launch.source, "conversion");
    assert.equal(consumeTestingLaunch(), null);
  });

  it("preserves historyId for history-source launches", () => {
    queueTestingLaunch({
      mode: "single_file",
      autoRun: true,
      source: "history",
      historyId: "entry-42",
    });
    const launch = consumeTestingLaunch();
    assert.ok(launch);
    assert.equal(launch.source, "history");
    assert.equal(launch.historyId, "entry-42");
    assert.equal(launch.autoRun, true);
    assert.equal(consumeTestingLaunch(), null);
  });

  it("defaults source to conversion when not specified", () => {
    queueTestingLaunch({ mode: "project", autoRun: false });
    const launch = consumeTestingLaunch();
    assert.ok(launch);
    assert.equal(launch.source, "conversion");
    assert.equal(launch.mode, "project");
  });
});
