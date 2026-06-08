"use client";

function downloadText(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function DownloadButton({
  filename,
  content,
  mime,
  label = "Download",
  disabled,
}: {
  filename: string;
  content: string;
  mime: string;
  label?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      className="action-button secondary"
      disabled={disabled || !content}
      onClick={() => downloadText(filename, content, mime)}
    >
      {label}
    </button>
  );
}
