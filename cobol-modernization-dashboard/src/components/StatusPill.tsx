"use client";

interface StatusPillProps {
  label: string;
  tone?: "good" | "warn" | "bad" | "neutral";
}

export default function StatusPill({ label, tone = "neutral" }: StatusPillProps) {
  return <span className={`status-pill ${tone}`}>{label}</span>;
}
