"use client";

import { useCallback, useMemo, useState } from "react";

function isObject(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

function TreeRow({
  label,
  value,
  depth,
}: {
  label: string;
  value: unknown;
  depth: number;
}) {
  const [open, setOpen] = useState(depth < 2);

  if (value === null || value === undefined) {
    return (
      <div style={{ paddingLeft: depth * 14, fontFamily: "var(--font-mono)", fontSize: 12 }}>
        <span style={{ color: "#93c5fd" }}>{label}</span>
        <span style={{ color: "#9ca3af" }}>: </span>
        <span style={{ color: "#f9a8d4" }}>{String(value)}</span>
      </div>
    );
  }

  if (Array.isArray(value)) {
    return (
      <div style={{ paddingLeft: depth * 14 }}>
        <button
          type="button"
          onClick={() => setOpen(!open)}
          style={{
            background: "none",
            border: "none",
            color: "#e5e7eb",
            cursor: "pointer",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            padding: "2px 0",
          }}
        >
          {open ? "▼" : "▶"} <span style={{ color: "#93c5fd" }}>{label}</span>
          <span style={{ color: "#9ca3af" }}> [{value.length}]</span>
        </button>
        {open &&
          value.map((item, i) => (
            <TreeRow key={i} label={`[${i}]`} value={item} depth={depth + 1} />
          ))}
      </div>
    );
  }

  if (isObject(value)) {
    const keys = Object.keys(value);
    return (
      <div style={{ paddingLeft: depth * 14 }}>
        <button
          type="button"
          onClick={() => setOpen(!open)}
          style={{
            background: "none",
            border: "none",
            color: "#e5e7eb",
            cursor: "pointer",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            padding: "2px 0",
          }}
        >
          {open ? "▼" : "▶"} <span style={{ color: "#93c5fd" }}>{label}</span>
          <span style={{ color: "#9ca3af" }}> {"{" + keys.length + " keys}"}</span>
        </button>
        {open &&
          keys.map((k) => (
            <TreeRow key={k} label={k} value={value[k]} depth={depth + 1} />
          ))}
      </div>
    );
  }

  const text =
    typeof value === "string"
      ? JSON.stringify(value)
      : typeof value === "number" || typeof value === "boolean"
        ? String(value)
        : JSON.stringify(value);

  return (
    <div style={{ paddingLeft: depth * 14, fontFamily: "var(--font-mono)", fontSize: 12 }}>
      <span style={{ color: "#93c5fd" }}>{label}</span>
      <span style={{ color: "#9ca3af" }}>: </span>
      <span style={{ color: "#a5d6ff" }}>{text}</span>
    </div>
  );
}

interface JsonTreeViewerProps {
  data: unknown;
  emptyMessage?: string;
}

export default function JsonTreeViewer({ data, emptyMessage = "No data yet." }: JsonTreeViewerProps) {
  const body = useMemo(() => {
    if (data === null || data === undefined) {
      return <div style={{ color: "var(--text-muted)", padding: 16 }}>{emptyMessage}</div>;
    }
    return <TreeRow label="root" value={data} depth={0} />;
  }, [data, emptyMessage]);

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
    } catch {
      /* ignore */
    }
  }, [data]);

  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: 12,
        background: "#020617",
        minHeight: 280,
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          padding: "8px 12px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          justifyContent: "flex-end",
        }}
      >
        <button type="button" className="action-button secondary" style={{ padding: "8px 14px" }} onClick={copy}>
          Copy JSON
        </button>
      </div>
      <div style={{ padding: 12, overflow: "auto", maxHeight: 480, flex: 1 }}>{body}</div>
    </div>
  );
}
