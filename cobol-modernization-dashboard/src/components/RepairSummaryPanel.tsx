"use client";

import type { RepairSummary } from "@/lib/repairSummary";
import { formatJavaStageLabel } from "@/lib/repairSummary";
import type { NormalizedConversionScore } from "@/lib/conversionScore";
import { normalizeConversionScore } from "@/lib/conversionScore";
import StatusBadge from "@/components/StatusBadge";

export interface RepairSummaryPanelProps {
  conversionStatus?: "complete" | "partial" | "failed";
  conversionScore?: NormalizedConversionScore | unknown | null;
  repairSummary?: RepairSummary | null;
  /** Raw technical notes (collapsed by default). */
  compileRepairNotes?: string[];
  compact?: boolean;
}

export default function RepairSummaryPanel({
  conversionStatus,
  conversionScore,
  repairSummary,
  compileRepairNotes,
  compact,
}: RepairSummaryPanelProps) {
  const score = normalizeConversionScore(conversionScore);
  const statusLabel = formatJavaStageLabel(conversionStatus);
  const tone =
    conversionStatus === "partial"
      ? "running"
      : conversionStatus === "failed"
        ? "error"
        : "success";

  const auto = repairSummary?.autoRepairs ?? [];
  const manual = repairSummary?.manualReview ?? [];
  const hasRepairs = auto.length > 0 || manual.length > 0;

  if (!score && !hasRepairs && !compileRepairNotes?.length) {
    return null;
  }

  return (
    <div className={`repair-summary-panel${compact ? " repair-summary-panel--compact" : ""}`}>
      <div className="repair-summary-header">
        <span className="repair-summary-java-line">
          <span className="repair-summary-check" aria-hidden>
            ✓
          </span>{" "}
          Java: {statusLabel}
          {score ? (
            <span className="repair-summary-score">
              {" "}
              (Score: {score.total}/100)
            </span>
          ) : null}
        </span>
        <StatusBadge label={statusLabel} tone={tone} compact />
      </div>

      {auto.length > 0 ? (
        <section className="repair-summary-section repair-summary-section--info">
          <h4 className="repair-summary-section-title">
            <span aria-hidden>ℹ️</span> Auto-repairs applied
          </h4>
          <ul className="repair-summary-list">
            {auto.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {manual.length > 0 ? (
        <section className="repair-summary-section repair-summary-section--warn">
          <h4 className="repair-summary-section-title">
            <span aria-hidden>⚠️</span> Manual review needed
          </h4>
          <ul className="repair-summary-list">
            {manual.map((item) => (
              <li key={`${item.line}-${item.message}`}>
                Line {item.line}: {item.message}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {compileRepairNotes && compileRepairNotes.length > 0 && !compact ? (
        <details className="repair-summary-technical">
          <summary>Technical repair log ({compileRepairNotes.length})</summary>
          <ul className="repair-summary-list repair-summary-list--technical">
            {compileRepairNotes.map((note) => (
              <li key={note}>
                <code>{note}</code>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
