"use client";

interface CodeEditorProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  minHeight?: number;
}

export default function CodeEditor({ label, value, onChange, minHeight = 280 }: CodeEditorProps) {
  return (
    <div className="panel-card">
      <div className="panel-label">{label}</div>
      <textarea
        className="editor-textarea"
        style={{ minHeight }}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}
