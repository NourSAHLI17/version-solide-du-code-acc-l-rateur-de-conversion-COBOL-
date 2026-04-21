"use client";

interface MetricCardProps {
  label: string;
  value: string;
  hint?: string;
}

export default function MetricCard({ label, value, hint }: MetricCardProps) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {hint ? <div className="metric-hint">{hint}</div> : null}
    </div>
  );
}
