"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { PROJECT_BOOTSTRAP_KEY, SINGLE_BOOTSTRAP_KEY } from "@/lib/bootstrapKeys";
import * as historyService from "@/services/historyService";
import type { HistoryEntry } from "@/services/historyService";
import HistoryList from "@/components/HistoryList";
import { canRunTestingFromHistory, restoreWorkspaceFromHistory } from "@/lib/historyTestingRestore";
import { queueTestingLaunch } from "@/lib/testingLaunch";
import { persistTestingTargetMode } from "@/lib/testingService";

export default function HistoryPage() {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const entries = await historyService.getAllAsync(100);
      console.log(`[History] loaded ${entries.length} entries from backend`);
      setRows(entries);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error("[History] failed to load:", msg);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    const result = rows.filter((r) => r.programName.toLowerCase().includes(q));
    if (result.length !== rows.length) {
      console.log(`[History] search filter: ${rows.length} total → ${result.length} shown (query="${q}")`);
    }
    return result;
  }, [rows, search]);

  const handleView = useCallback(
    (e: HistoryEntry) => {
      if (e.type === "project" && e.projectSnapshot) {
        sessionStorage.setItem(PROJECT_BOOTSTRAP_KEY, JSON.stringify(e.projectSnapshot));
        router.push("/convert/project");
        return;
      }
      sessionStorage.setItem(
        SINGLE_BOOTSTRAP_KEY,
        JSON.stringify({
          sourceCode: e.sourceCode ?? "",
          programName: e.programName,
          parserOutput: e.parserOutput,
          analysisOutput: e.analysisOutput,
          javaOutput: e.javaOutput,
        }),
      );
      router.push("/convert/single");
    },
    [router],
  );

  const handleRerun = useCallback(
    (e: HistoryEntry) => {
      if (e.type === "project" && e.projectSnapshot) {
        const cleared = {
          ...e.projectSnapshot,
          files: e.projectSnapshot.files.map((f) => ({
            ...f,
            parserOutput: null,
            analysisOutput: null,
            javaOutput: null,
            parserStatus: "idle",
            analysisStatus: "idle",
            conversionStatus: "idle",
          })),
        };
        sessionStorage.setItem(PROJECT_BOOTSTRAP_KEY, JSON.stringify(cleared));
        router.push("/convert/project");
        return;
      }
      sessionStorage.setItem(
        SINGLE_BOOTSTRAP_KEY,
        JSON.stringify({
          sourceCode: e.sourceCode ?? "",
          programName: e.programName,
          clearOutputs: true,
        }),
      );
      router.push("/convert/single");
    },
    [router],
  );

  const handleRunTesting = useCallback(
    (e: HistoryEntry) => {
      const restored = restoreWorkspaceFromHistory(e);
      if ("error" in restored) {
        console.error("[History] cannot run testing:", restored.error);
        return;
      }
      queueTestingLaunch({
        mode: restored.mode,
        autoRun: true,
        source: "history",
        historyId: e.id,
      });
      persistTestingTargetMode(restored.mode);
      router.push("/testing");
    },
    [router],
  );

  const canRunTesting = useCallback(
    (e: HistoryEntry) => canRunTestingFromHistory(e),
    [],
  );

  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await historyService.deleteEntryAsync(id);
        setRows((prev) => prev.filter((r) => r.id !== id));
      } catch (err) {
        console.error("[History] delete failed:", err);
      }
    },
    [],
  );

  const handleClearAll = useCallback(async () => {
    if (!window.confirm("Clear all history?")) return;
    try {
      await historyService.clearAsync();
      setRows([]);
    } catch (err) {
      console.error("[History] clear failed:", err);
    }
  }, []);

  const [selectedId, setSelectedId] = useState<string | null>(null);

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: 24 }}>
      <header className="page-hero glass-card">
        <p className="hero-kicker">Phase 1 — Step 1.3</p>
        <h1>Conversion history</h1>
        <p className="hero-copy">
          All runs persisted in the backend database ({rows.length} entries).
        </p>
      </header>

      <div
        className="glass-card"
        style={{ padding: 16, display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}
      >
        <input
          type="search"
          className="app-input"
          placeholder="Search program name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ minWidth: 240, flex: "1 1 200px" }}
        />
        <button
          type="button"
          className="action-button secondary"
          onClick={() => void loadHistory()}
        >
          Refresh
        </button>
        <button type="button" className="action-button secondary" onClick={handleClearAll}>
          Clear All
        </button>
      </div>

      {loading ? (
        <div className="glass-card" style={{ padding: 32, textAlign: "center", color: "var(--text-muted)" }}>
          Loading history…
        </div>
      ) : error ? (
        <div className="glass-card" style={{ padding: 32, textAlign: "center", color: "#e74c3c" }}>
          Failed to load history: {error}
          <div style={{ marginTop: 12 }}>
            <button type="button" className="action-button primary" onClick={() => void loadHistory()}>
              Retry
            </button>
          </div>
        </div>
      ) : (
        <HistoryList
          rows={filtered}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onView={handleView}
          onRerun={handleRerun}
          onRunTesting={handleRunTesting}
          canRunTesting={canRunTesting}
          onDelete={(id) => void handleDelete(id)}
        />
      )}
    </div>
  );
}
