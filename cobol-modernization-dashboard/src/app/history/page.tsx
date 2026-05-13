"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { PROJECT_BOOTSTRAP_KEY, SINGLE_BOOTSTRAP_KEY } from "@/lib/bootstrapKeys";
import * as historyService from "@/services/historyService";

function formatRelative(iso: string): string {
  const t = new Date(iso).getTime();
  const d = Date.now() - t;
  const sec = Math.floor(d / 1000);
  if (sec < 45) return "just now";
  if (sec < 3600) return `${Math.floor(sec / 60)} min ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} hours ago`;
  if (sec < 604800) return `${Math.floor(sec / 86400)} days ago`;
  return new Date(iso).toLocaleString();
}

export default function HistoryPage() {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState(() => historyService.getAll());

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => r.programName.toLowerCase().includes(q));
  }, [rows, search]);

  const refresh = () => setRows(historyService.getAll());

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: 24 }}>
      <header className="page-hero glass-card">
        <p className="hero-kicker">Phase 1 — Step 1.3</p>
        <h1>Conversion history</h1>
        <p className="hero-copy">Stored locally in your browser (max 50 entries).</p>
      </header>

      <div className="glass-card" style={{ padding: 16, display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
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
          onClick={() => {
            if (!window.confirm("Clear all history?")) return;
            historyService.clear();
            refresh();
          }}
        >
          Clear All
        </button>
      </div>

      <div className="file-list" style={{ borderRadius: 16 }}>
        <div className="file-list-header">Entries ({filtered.length})</div>
        <table className="results-table" style={{ width: "100%" }}>
          <thead>
            <tr>
              <th>Program</th>
              <th>Date</th>
              <th>Paragraphs</th>
              <th>Score</th>
              <th>Cost</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((e) => (
              <tr key={e.id}>
                <td>
                  {e.programName}{" "}
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>({e.type})</span>
                </td>
                <td>{formatRelative(e.createdAt)}</td>
                <td>{e.paragraphCount}</td>
                <td>{e.score === null ? "—" : String(e.score)}</td>
                <td>{e.cost === null ? "—" : String(e.cost)}</td>
                <td>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button
                      type="button"
                      className="action-button secondary"
                      style={{ padding: "6px 10px" }}
                      onClick={() => {
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
                      }}
                    >
                      View
                    </button>
                    <button
                      type="button"
                      className="action-button secondary"
                      style={{ padding: "6px 10px" }}
                      onClick={() => {
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
                      }}
                    >
                      Re-run
                    </button>
                    <button
                      type="button"
                      className="action-button secondary"
                      style={{ padding: "6px 10px" }}
                      onClick={() => {
                        historyService.deleteEntry(e.id);
                        refresh();
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div style={{ padding: 24, color: "var(--text-muted)" }}>No entries match.</div>
        )}
      </div>
    </div>
  );
}
