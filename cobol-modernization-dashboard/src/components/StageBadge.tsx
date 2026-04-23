"use client";

interface StageBadgeProps {
  label: string;
  stage: "parser" | "jcl" | "copybook" | "analysis" | "java" | "tests";
}

export default function StageBadge({ label, stage }: StageBadgeProps) {
  return <span className={`stage-badge ${stage}`}>{label}</span>;
}
