"use client";

import type { NormalizedConversionScore } from "@/lib/conversionScore";

export default function ScoreBreakdownTable({ score }: { score: NormalizedConversionScore }) {
  const rows = score.breakdown ?? [];
  if (rows.length === 0) {
    return <p className="score-breakdown-empty">No paragraph breakdown available.</p>;
  }

  return (
    <div className="score-breakdown-wrap">
      <table className="score-breakdown-table">
        <thead>
          <tr>
            <th>Paragraph</th>
            <th>Structure</th>
            <th>Rules</th>
            <th>Total</th>
            <th>Notes</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.paragraph}>
              <td className="score-breakdown-para">{row.paragraph}</td>
              <td>{row.structureScore}</td>
              <td>{row.rulesScore}</td>
              <td>
                <strong>{row.total}</strong>
              </td>
              <td className="score-breakdown-notes">{row.notes || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="score-breakdown-hint">Sorted weakest paragraphs first.</p>
    </div>
  );
}
