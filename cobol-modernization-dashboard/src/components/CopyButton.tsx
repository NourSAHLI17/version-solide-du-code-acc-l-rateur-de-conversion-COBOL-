"use client";

export default function CopyButton({
  text,
  label = "Copy",
  disabled,
}: {
  text: string;
  label?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      className="action-button secondary"
      disabled={disabled || !text}
      onClick={() => void navigator.clipboard.writeText(text)}
    >
      {label}
    </button>
  );
}
