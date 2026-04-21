"use client";

import JsonViewer from "@/components/JsonViewer";

interface ArtifactPanelProps {
  title: string;
  data: unknown;
}

export default function ArtifactPanel({ title, data }: ArtifactPanelProps) {
  return (
    <div className="panel-card artifact-card">
      <div className="panel-label">{title}</div>
      <div className="artifact-body">
        <JsonViewer data={data} />
      </div>
    </div>
  );
}
