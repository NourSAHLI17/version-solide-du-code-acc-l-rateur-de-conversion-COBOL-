"use client";

import Editor, { Monaco, BeforeMount } from "@monaco-editor/react";

const cobolBeforeMount: BeforeMount = (monaco: Monaco) => {
  const existing = monaco.languages.getLanguages().some((l: { id: string }) => l.id === "cobol");
  if (existing) return;
  monaco.languages.register({
    id: "cobol",
    extensions: [".cbl", ".cob", ".cpy"],
    aliases: ["COBOL", "cobol"],
  });
  monaco.languages.setMonarchTokensProvider("cobol", {
    tokenizer: {
      root: [
        [/^\s*\*.{0,}$|^\s*\/.{0,}$/, "comment"],
        [/'[^']*'/, "string"],
        [/".*?"/, "string"],
        [
          /\b(PROGRAM-ID|DIVISION|ENVIRONMENT|DATA|PROCEDURE|WORKING-STORAGE|FILE|SECTION|INPUT-OUTPUT|FILE-CONTROL|FD|COPY|IDENTIFICATION|ID)\b/i,
          "keyword",
        ],
        [/\b(IF|ELSE|END-IF|MOVE|PERFORM|THRU|UNTIL|DISPLAY|ACCEPT|STOP|RUN|EVALUATE|WHEN|OTHER|END-EVALUATE|OPEN|CLOSE|READ|WRITE|REWRITE|DELETE|COMPUTE|SUBTRACT|ADD|MULTIPLY|DIVIDE|EXIT|GO|TO|GOBACK)\b/i, "keyword"],
        [/\b\d+\b/, "number"],
      ],
    },
  });
};

interface MonacoCobolEditorProps {
  value: string;
  onChange: (v: string) => void;
  height?: string;
  readOnly?: boolean;
}

export default function MonacoCobolEditor({
  value,
  onChange,
  height = "420px",
  readOnly = false,
}: MonacoCobolEditorProps) {
  return (
    <Editor
      height={height}
      defaultLanguage="cobol"
      language="cobol"
      theme="vs-dark"
      value={value}
      onChange={(v) => onChange(v ?? "")}
      beforeMount={cobolBeforeMount}
      options={{
        readOnly,
        minimap: { enabled: false },
        fontSize: 13,
        fontFamily: "var(--font-mono), monospace",
        wordWrap: "on",
        scrollBeyondLastLine: false,
        automaticLayout: true,
      }}
    />
  );
}
