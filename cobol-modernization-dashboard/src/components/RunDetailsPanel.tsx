"use client";

import { useState } from "react";

import JsonTreeViewer from "@/components/JsonTreeViewer";
import MonacoJavaViewer from "@/components/MonacoJavaViewer";
import ScoreCard from "@/components/ScoreCard";
import SmokeTestPanel from "@/components/SmokeTestPanel";
import { normalizeConversionScore } from "@/lib/conversionScore";
import type { HistoryEntry } from "@/services/historyService";

type Tab = "parser" | "analysis" | "java" | "score";

export default function RunDetailsPanel({ entry }: { entry: HistoryEntry | null }) {
  const [tab, setTab] = useState<Tab>("parser");

  if (!entry) {
    return (
      <div className="glass-card" style={{ padding: 24, color: "var(--text-muted)" }}>
        Select a history entry to preview outputs and score.
      </div>
    );
  }

  const score =
    normalizeConversionScore(entry.conversionScore) ??
    normalizeConversionScore(entry.conversionScoreRaw) ??
    (typeof entry.score === "number"
      ? normalizeConversionScore({
          total_score: entry.score,
          structural_score: 0,
          business_rules_score: 0,
          decision: "manual_review",
        })
      : null);

  return (
    <div className="output-card">
      <div className="panel-label">{entry.programName}</div>
      <div className="stage-tabs" style={{ marginBottom: 12 }}>
        {(
          [
            ["parser", "Parser"],
            ["analysis", "Analysis"],
            ["java", "Java"],
            ["score", "Quality score"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`stage-tab ${tab === id ? "active" : ""}`}
            data-stage={id === "parser" ? "parser" : id === "analysis" ? "analysis" : id === "java" ? "java" : "tests"}
            style={{ border: "none", cursor: "pointer" }}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "parser" && <JsonTreeViewer data={entry.parserOutput} emptyMessage="No parser output stored." />}
      {tab === "analysis" && <JsonTreeViewer data={entry.analysisOutput} emptyMessage="No analysis output stored." />}
      {tab === "java" && (
        entry.type === "single" && typeof entry.javaOutput === "string" ? (
          <MonacoJavaViewer value={entry.javaOutput} height="360px" />
        ) : (
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Open in Project view for multi-file Java outputs.</p>
        )
      )}
      {tab === "score" && (
        <div className="run-details-score">
          <ScoreCard score={score} />
          <SmokeTestPanel smokeTest={(entry as Record<string, unknown>).smokeTest ?? null} />
        </div>
      )}
    </div>
  );
}
