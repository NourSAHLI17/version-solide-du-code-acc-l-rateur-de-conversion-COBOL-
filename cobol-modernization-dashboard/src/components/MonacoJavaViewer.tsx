"use client";

import Editor from "@monaco-editor/react";

interface MonacoJavaViewerProps {
  value: string;
  height?: string;
}

export default function MonacoJavaViewer({ value, height = "420px" }: MonacoJavaViewerProps) {
  return (
    <Editor
      height={height}
      defaultLanguage="java"
      language="java"
      theme="vs-dark"
      value={value}
      options={{
        readOnly: true,
        minimap: { enabled: false },
        fontSize: 13,
        wordWrap: "on",
        scrollBeyondLastLine: false,
        automaticLayout: true,
      }}
    />
  );
}
