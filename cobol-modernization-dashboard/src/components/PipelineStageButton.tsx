"use client";

export type PipelineUiStatus = "idle" | "loading" | "success" | "error" | "partial";

export default function PipelineStageButton({
  label,
  status,
  disabled,
  onClick,
}: {
  label: string;
  status: PipelineUiStatus;
  disabled?: boolean;
  onClick: () => void;
}) {
  const icon =
    status === "loading" ? (
      <span className="progress-spinner" style={{ width: 14, height: 14 }} />
    ) : status === "success" ? (
      "✅"
    ) : status === "error" ? (
      "❌"
    ) : status === "partial" ? (
      "⚠️"
    ) : (
      "▶"
    );

  return (
    <button
      type="button"
      className="action-button primary"
      disabled={disabled || status === "loading"}
      onClick={(e) => {
        e.preventDefault();
        if (!disabled && status !== "loading") onClick();
      }}
      style={{ display: "inline-flex", alignItems: "center", gap: 8 }}
    >
      {icon} {label}
    </button>
  );
}
