"use client";

export type StatusBadgeTone = "idle" | "running" | "success" | "error" | "neutral";

const CLASS: Record<StatusBadgeTone, string> = {
  idle: "status-badge status-badge--idle",
  running: "status-badge status-badge--running",
  success: "status-badge status-badge--success",
  error: "status-badge status-badge--error",
  neutral: "status-badge status-badge--neutral",
};

export default function StatusBadge({
  label,
  tone = "idle",
  compact,
}: {
  label: string;
  tone?: StatusBadgeTone;
  compact?: boolean;
}) {
  return <span className={`${CLASS[tone]}${compact ? " status-badge--compact" : ""}`}>{label}</span>;
}
