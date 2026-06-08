"use client";

import { useState } from "react";
import {
  decisionLabel,
  decisionTone,
  normalizeConversionScore,
  type NormalizedConversionScore,
  type CategoryScore,
  type AnalysisMode,
} from "@/lib/conversionScore";

import ScoreBreakdownTable from "@/components/ScoreBreakdownTable";
import StatusBadge from "@/components/StatusBadge";

function CategoryBar({
  label,
  score,
  max,
  notes,
}: {
  label: string;
  score: number;
  max: number;
  notes: string[];
}) {
  const pct = max > 0 ? Math.round((score / max) * 100) : 0;
  const barColor =
    pct >= 80 ? "var(--color-success, #22c55e)" :
    pct >= 50 ? "var(--color-warning, #f59e0b)" :
    "var(--color-error, #ef4444)";

  return (
    <div className="category-score-row">
      <div className="category-score-label">
        <span className="category-score-name">{label}</span>
        <span className="category-score-value">
          {score} / {max}
        </span>
      </div>
      <div className="category-score-bar-bg">
        <div
          className="category-score-bar-fill"
          style={{ width: `${pct}%`, backgroundColor: barColor }}
        />
      </div>
      {notes.length > 0 && (
        <ul className="category-score-notes">
          {notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function DeterministicFallbackBadge({ mode }: { mode: AnalysisMode }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="deterministic-fallback-banner">
      <button
        type="button"
        className="deterministic-fallback-badge"
        onClick={() => setExpanded(!expanded)}
        title="Click for details"
      >
        <span className="deterministic-fallback-icon">{"\u26A0\uFE0F"}</span>
        <span className="deterministic-fallback-text">
          Deterministic fallback &mdash; LLM analysis unavailable
        </span>
        <span className="deterministic-fallback-chevron">
          {expanded ? "\u25B2" : "\u25BC"}
        </span>
      </button>
      {expanded && (
        <div className="deterministic-fallback-details">
          <div className="deterministic-fallback-detail-row">
            <span className="deterministic-fallback-detail-label">Engine</span>
            <span>{mode.engine}</span>
          </div>
          {mode.fallbackReason && (
            <div className="deterministic-fallback-detail-row">
              <span className="deterministic-fallback-detail-label">Reason</span>
              <span>{mode.fallbackReason}</span>
            </div>
          )}
          <div className="deterministic-fallback-detail-row">
            <span className="deterministic-fallback-detail-label">Score impact</span>
            <span>Analyze score capped at 50% (max 10/20)</span>
          </div>
          <p className="deterministic-fallback-hint">
            Pattern-based rule extraction replaces LLM analysis. Business rule
            coverage may be incomplete. Configure an LLM API key to enable full
            analysis.
          </p>
        </div>
      )}
    </div>
  );
}

function SemanticDetailGrid({
  detail,
}: {
  detail: NonNullable<NormalizedConversionScore["semanticDetail"]>;
}) {
  const items = [
    { label: "Structural fidelity", value: detail.structuralFidelity, max: 10 },
    { label: "Business rule coverage", value: detail.businessRuleCoverage, max: 10 },
    { label: "Code completeness", value: detail.codeCompleteness, max: 10 },
    { label: "Integration readiness", value: detail.integrationReadiness, max: 10 },
  ];

  return (
    <div className="semantic-detail-grid">
      {items.map((item) => {
        const pct = Math.round((item.value / item.max) * 100);
        return (
          <div key={item.label} className="semantic-detail-item">
            <span className="semantic-detail-label">{item.label}</span>
            <span className="semantic-detail-value">
              {item.value}/{item.max}
              <span className="semantic-detail-pct"> ({pct}%)</span>
            </span>
          </div>
        );
      })}
      {detail.rulesTotal > 0 && (
        <div className="semantic-detail-item semantic-detail-rules">
          <span className="semantic-detail-label">Rules matched</span>
          <span className="semantic-detail-value">
            {detail.rulesMatched} / {detail.rulesTotal}
          </span>
        </div>
      )}
    </div>
  );
}

export default function ScoreCard({
  score,
  compact,
  missingMessage = "Score not available for this run. Complete Java conversion to generate a quality score.",
}: {
  score: NormalizedConversionScore | unknown | null;
  compact?: boolean;
  missingMessage?: string;
}) {
  const model = normalizeConversionScore(score);
  if (!model) {
    return (
      <div className="score-card score-card--empty">
        <p className="score-card-missing">{missingMessage}</p>
      </div>
    );
  }

  const tone = decisionTone(model.decision);
  const toneMap = { success: "success", warning: "running", danger: "error", neutral: "neutral" } as const;
  const cats = model.categoryScores;
  const isDeterministic = model.analysisMode?.isDeterministicFallback;

  return (
    <div className={`score-card${compact ? " score-card--compact" : ""}`}>
      <div className="score-card-header">
        <div>
          <span className="score-card-total-value">{model.total}</span>
          <span className="score-card-total-max"> / 100</span>
        </div>
        <StatusBadge label={decisionLabel(model.decision)} tone={toneMap[tone]} />
      </div>

      {isDeterministic && model.analysisMode && (
        <DeterministicFallbackBadge mode={model.analysisMode} />
      )}

      {cats ? (
        <div className="score-card-categories">
          <CategoryBar label="Parse" {...cats.parse} />
          <CategoryBar label="Analyze" {...cats.analyze} />
          <CategoryBar label="Convert" {...cats.convert} />
          <CategoryBar label="Semantic" {...cats.semantic} />
        </div>
      ) : (
        <div className="score-card-metrics">
          <div className="score-metric">
            <span className="score-metric-label">Structural</span>
            <span className="score-metric-value">
              {model.structural}
              <span className="score-metric-max"> / {model.structuralMax}</span>
            </span>
          </div>
          <div className="score-metric">
            <span className="score-metric-label">Business rules</span>
            <span className="score-metric-value">
              {model.businessRules}
              <span className="score-metric-max"> / {model.businessRulesMax}</span>
            </span>
          </div>
        </div>
      )}

      {model.semanticDetail && !compact && (
        <>
          <h3 className="score-section-title">Semantic validation detail</h3>
          <SemanticDetailGrid detail={model.semanticDetail} />
        </>
      )}

      {model.summary ? <p className="score-card-summary">{model.summary}</p> : null}
      {!compact ? (
        <>
          <h3 className="score-section-title">Paragraph breakdown</h3>
          <ScoreBreakdownTable score={model} />
        </>
      ) : null}
    </div>
  );
}
