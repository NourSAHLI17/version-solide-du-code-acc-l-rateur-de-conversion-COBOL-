"use client";



import {

  complexityBadgeTone,

  formatScoreCompact,

  normalizeConversionScore,

  type ComplexityLabel,

} from "@/lib/conversionScore";

import type { HistoryEntry } from "@/services/historyService";

import ReliabilityScoreBadge from "@/components/ReliabilityScoreBadge";

import StatusBadge from "@/components/StatusBadge";

import { isTestingHistoryEntry } from "@/lib/testingHistoryBridge";

import { persistenceStateFromHistoryEntry, persistenceStateLabel } from "@/lib/testingRunPersistence";

import { reliabilityBadgeForHistoryEntry } from "@/lib/reliabilityBadge";



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



function complexityForEntry(e: HistoryEntry): ComplexityLabel | null {

  if (e.complexityLabel) return e.complexityLabel;

  return null;

}



export default function HistoryList({

  rows,

  selectedId,

  onSelect,

  onView,

  onRerun,

  onRunTesting,

  canRunTesting,

  onDelete,

}: {

  rows: HistoryEntry[];

  selectedId: string | null;

  onSelect: (id: string) => void;

  onView: (e: HistoryEntry) => void;

  onRerun: (e: HistoryEntry) => void;

  onRunTesting: (e: HistoryEntry) => void;

  canRunTesting: (e: HistoryEntry) => boolean;

  onDelete: (id: string) => void;

}) {

  if (rows.length === 0) {

    return <div className="history-list-empty">No history entries yet.</div>;

  }



  return (

    <div className="file-list" style={{ borderRadius: 16 }}>

      <div className="file-list-header">Entries ({rows.length})</div>

      <table className="results-table" style={{ width: "100%" }}>

        <thead>

          <tr>

            <th>Program</th>

            <th>Date</th>

            <th>Complexity</th>

            <th>Testing / conversion</th>

            <th>Actions</th>

          </tr>

        </thead>

        <tbody>

          {rows.map((e) => {

            const cx = complexityForEntry(e);

            const active = e.id === selectedId;

            return (

              <tr

                key={e.id}

                className={active ? "history-row-active" : undefined}

                style={{ cursor: "pointer" }}

                onClick={() => onSelect(e.id)}

              >

                <td>

                  {e.programName}{" "}

                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>({e.type})</span>

                  {isTestingHistoryEntry(e) ? (

                    <span style={{ display: "block", fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>

                      {persistenceStateLabel(persistenceStateFromHistoryEntry(e))}

                    </span>

                  ) : null}

                </td>

                <td>{formatRelative(e.createdAt)}</td>

                <td>

                  {cx ? <StatusBadge label={cx} tone={complexityBadgeTone(cx)} compact /> : "—"}

                </td>

                <td>

                  {e.reliability_score != null ? (

                    <ReliabilityScoreBadge

                      badge={reliabilityBadgeForHistoryEntry(e)}

                      forceSave={Boolean(e.force_save)}

                    />

                  ) : null}

                  {normalizeConversionScore(e.conversionScore) ||

                  (typeof e.score === "number" && e.reliability_score == null) ? (

                    <span

                      style={{

                        display: "block",

                        fontSize: 10,

                        color: "var(--text-muted)",

                        marginTop: e.reliability_score != null ? 4 : 0,

                      }}

                    >

                      Conversion:{" "}

                      {formatScoreCompact(

                        normalizeConversionScore(e.conversionScore) ??

                          (typeof e.score === "number"

                            ? normalizeConversionScore({ total_score: e.score })

                            : null),

                      )}

                    </span>

                  ) : e.reliability_score == null ? (

                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>—</span>

                  ) : null}

                </td>

                <td onClick={(ev) => ev.stopPropagation()}>

                  <div className="history-actions">

                    <button type="button" className="action-button secondary" style={{ padding: "6px 10px" }} onClick={() => onView(e)}>View</button>

                    {canRunTesting(e) ? (

                      <button

                        type="button"

                        className="action-button primary"

                        style={{ padding: "6px 10px" }}

                        onClick={() => onRunTesting(e)}

                      >

                        Run Testing

                      </button>

                    ) : null}

                    <button type="button" className="action-button secondary" style={{ padding: "6px 10px" }} onClick={() => onRerun(e)}>Re-run</button>

                    <button type="button" className="action-button secondary" style={{ padding: "6px 10px" }} onClick={() => onDelete(e.id)}>Delete</button>

                  </div>

                </td>

              </tr>

            );

          })}

        </tbody>

      </table>

    </div>

  );

}

