"use client";

interface CodePanelProps {
  title: string;
  code: string;
}

export default function CodePanel({ title, code }: CodePanelProps) {
  return (
    <div className="panel-card">
      <div className="panel-label">{title}</div>
      <pre className="code-panel">
        <code>{code || "// No output yet"}</code>
      </pre>
    </div>
  );
}
