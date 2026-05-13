"use client";

import { useCallback, useEffect, useRef, useState, type DragEventHandler } from "react";

import JsonTreeViewer from "@/components/JsonTreeViewer";
import MonacoCobolEditor from "@/components/MonacoCobolEditor";
import MonacoJavaViewer from "@/components/MonacoJavaViewer";
import { SINGLE_BOOTSTRAP_KEY } from "@/lib/bootstrapKeys";
import { extractProgramId } from "@/lib/programId";
import {
  isParserOk,
  loadSingleWorkspace,
  newSingleWorkspace,
  saveSingleWorkspace,
  type SingleFileWorkspace,
} from "@/lib/singleFileWorkspace";
import type { AnalysisResult, ParserResult } from "@/lib/types";
import { analyzeCobol, convertCobol, parseCobol } from "@/lib/api";
import * as historyService from "@/services/historyService";

type Stage = "parser" | "analysis" | "java";
type UiStatus = "idle" | "loading" | "success" | "error";

function downloadText(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function StageButton({
  label,
  status,
  disabled,
  onClick,
}: {
  label: string;
  status: UiStatus;
  disabled: boolean;
  onClick: () => void;
}) {
  const icon =
    status === "loading" ? (
      <span className="progress-spinner" style={{ width: 14, height: 14 }} />
    ) : status === "success" ? (
      "✅"
    ) : status === "error" ? (
      "❌"
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

export default function SingleConvertPage() {
  const [ws, setWs] = useState<SingleFileWorkspace>(() => newSingleWorkspace(""));
  const [hydrated, setHydrated] = useState(false);
  const [activeTab, setActiveTab] = useState<"parser" | "analysis" | "java">("parser");
  const [parserUi, setParserUi] = useState<UiStatus>("idle");
  const [analysisUi, setAnalysisUi] = useState<UiStatus>("idle");
  const [javaUi, setJavaUi] = useState<UiStatus>("idle");
  const [errorOpen, setErrorOpen] = useState(false);
  const [lastErrorStage, setLastErrorStage] = useState<Stage | null>(null);
  const [lastErrorMsg, setLastErrorMsg] = useState("");
  const skipNextSourcePersist = useRef(false);
  const wsRef = useRef(ws);

  useEffect(() => {
    wsRef.current = ws;
  }, [ws]);

  const persist = useCallback((next: SingleFileWorkspace) => {
    setWs(next);
    saveSingleWorkspace({ ...next, updatedAt: new Date().toISOString() });
  }, []);

  useEffect(() => {
    const id = window.setTimeout(() => {
      const boot = sessionStorage.getItem(SINGLE_BOOTSTRAP_KEY);
      if (boot) {
        try {
          const b = JSON.parse(boot) as {
            sourceCode?: string;
            programName?: string;
            parserOutput?: ParserResult;
            analysisOutput?: AnalysisResult;
            javaOutput?: string | null;
            clearOutputs?: boolean;
          };
          sessionStorage.removeItem(SINGLE_BOOTSTRAP_KEY);
          const base = newSingleWorkspace(b.sourceCode ?? "");
          const merged: SingleFileWorkspace = {
            ...base,
            programName: b.programName ?? extractProgramId(b.sourceCode ?? ""),
            sourceCode: b.sourceCode ?? "",
            parserOutput: b.clearOutputs ? null : (b.parserOutput ?? null),
            analysisOutput: b.clearOutputs ? null : (b.analysisOutput ?? null),
            javaOutput: b.clearOutputs ? null : (b.javaOutput ?? null),
            pipelineErrors: b.clearOutputs ? undefined : base.pipelineErrors,
          };
          skipNextSourcePersist.current = true;
          setWs(merged);
          saveSingleWorkspace(merged);
          setParserUi(
            merged.parserOutput && isParserOk(merged.parserOutput)
              ? "success"
              : merged.pipelineErrors?.parser
                ? "error"
                : "idle",
          );
          setAnalysisUi(
            merged.analysisOutput && merged.analysisOutput !== null && !merged.pipelineErrors?.analysis
              ? "success"
              : merged.pipelineErrors?.analysis
                ? "error"
                : "idle",
          );
          setJavaUi(
            merged.javaOutput
              ? "success"
              : merged.pipelineErrors?.java
                ? "error"
                : "idle",
          );
        } catch {
          sessionStorage.removeItem(SINGLE_BOOTSTRAP_KEY);
        }
      } else {
        const stored = loadSingleWorkspace();
        if (stored) {
          setWs(stored);
          setParserUi(
            stored.parserOutput && isParserOk(stored.parserOutput)
              ? "success"
              : stored.pipelineErrors?.parser
                ? "error"
                : "idle",
          );
          const analysisOk =
            stored.analysisOutput &&
            typeof stored.analysisOutput === "object" &&
            (stored.analysisOutput as { analysis_engine?: string }).analysis_engine !== "n/a";
          setAnalysisUi(
            analysisOk && !stored.pipelineErrors?.analysis ? "success" : stored.pipelineErrors?.analysis ? "error" : "idle",
          );
          setJavaUi(stored.javaOutput ? "success" : stored.pipelineErrors?.java ? "error" : "idle");
        }
      }
      setHydrated(true);
    }, 0);
    return () => clearTimeout(id);
  }, []);

  useEffect(() => {
    if (!hydrated || skipNextSourcePersist.current) {
      skipNextSourcePersist.current = false;
      return;
    }
    saveSingleWorkspace({ ...ws, updatedAt: new Date().toISOString() });
  }, [ws, hydrated]);

  const onSourceChange = useCallback((sourceCode: string) => {
    const programName = extractProgramId(sourceCode);
    setWs((prev) => {
      const next: SingleFileWorkspace = {
        ...prev,
        sourceCode,
        programName,
        parserOutput: null,
        analysisOutput: null,
        javaOutput: null,
        pipelineErrors: undefined,
        updatedAt: new Date().toISOString(),
      };
      saveSingleWorkspace(next);
      return next;
    });
    setParserUi("idle");
    setAnalysisUi("idle");
    setJavaUi("idle");
    setErrorOpen(false);
    setLastErrorStage(null);
    setLastErrorMsg("");
  }, []);

  const setError = (stage: Stage, msg: string) => {
    setLastErrorStage(stage);
    setLastErrorMsg(msg);
    setErrorOpen(true);
    if (stage === "parser") setParserUi("error");
    if (stage === "analysis") setAnalysisUi("error");
    if (stage === "java") setJavaUi("error");
  };

  const runParser = async () => {
    const cur = wsRef.current;
    setParserUi("loading");
    setAnalysisUi("idle");
    setJavaUi("idle");
    const cleared: SingleFileWorkspace = {
      ...cur,
      parserOutput: null,
      analysisOutput: null,
      javaOutput: null,
      pipelineErrors: undefined,
      updatedAt: new Date().toISOString(),
    };
    persist(cleared);
    try {
      const parserOutput = await parseCobol(cur.sourceCode);
      const ok = isParserOk(parserOutput);
      const updated: SingleFileWorkspace = {
        ...cleared,
        parserOutput,
        updatedAt: new Date().toISOString(),
      };
      if (!ok) {
        const errs = (parserOutput as { preflight_errors?: string[] })?.preflight_errors ?? [];
        setError("parser", errs.join("\n") || "Parser reported preflight errors.");
        persist({
          ...updated,
          pipelineErrors: { parser: errs.join("; ") },
        });
        return;
      }
      setParserUi("success");
      persist(updated);
      setActiveTab("parser");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Parse failed.";
      setError("parser", msg);
      persist({
        ...cleared,
        pipelineErrors: { parser: msg },
        updatedAt: new Date().toISOString(),
      });
    }
  };

  const runAnalysis = async () => {
    const cur = wsRef.current;
    if (!cur.parserOutput || !isParserOk(cur.parserOutput)) return;
    setAnalysisUi("loading");
    try {
      const analysisOutput = await analyzeCobol(cur.sourceCode, cur.parserOutput);
      const halted =
        analysisOutput &&
        typeof analysisOutput === "object" &&
        (analysisOutput as { analysis_engine?: string }).analysis_engine === "n/a";
      if (halted) {
        const msg = "Analysis halted (preflight or engine n/a).";
        setError("analysis", msg);
        persist({
          ...cur,
          analysisOutput,
          pipelineErrors: { ...cur.pipelineErrors, analysis: msg },
          updatedAt: new Date().toISOString(),
        });
        return;
      }
      setAnalysisUi("success");
      persist({
        ...cur,
        analysisOutput,
        pipelineErrors: { ...cur.pipelineErrors, analysis: undefined },
        updatedAt: new Date().toISOString(),
      });
      setActiveTab("analysis");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Analysis failed.";
      setError("analysis", msg);
      persist({
        ...cur,
        pipelineErrors: { ...cur.pipelineErrors, analysis: msg },
        updatedAt: new Date().toISOString(),
      });
    }
  };

  const runJava = async () => {
    const cur = wsRef.current;
    if (!cur.parserOutput || !cur.analysisOutput) return;
    setJavaUi("loading");
    try {
      const java = await convertCobol(cur.sourceCode, cur.parserOutput, cur.analysisOutput);
      setJavaUi("success");
      persist({
        ...cur,
        javaOutput: java,
        pipelineErrors: { ...cur.pipelineErrors, java: undefined },
        updatedAt: new Date().toISOString(),
      });
      setActiveTab("java");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Conversion failed.";
      setError("java", msg);
      persist({
        ...cur,
        pipelineErrors: { ...cur.pipelineErrors, java: msg },
        updatedAt: new Date().toISOString(),
      });
    }
  };

  const retry = () => {
    setErrorOpen(false);
    if (lastErrorStage === "parser") void runParser();
    else if (lastErrorStage === "analysis") void runAnalysis();
    else if (lastErrorStage === "java") void runJava();
  };

  const resetAll = () => {
    if (!window.confirm("Reset all outputs and editor state for this page?")) return;
    const fresh = newSingleWorkspace("");
    persist(fresh);
    setParserUi("idle");
    setAnalysisUi("idle");
    setJavaUi("idle");
    setErrorOpen(false);
    setActiveTab("parser");
  };

  const saveHistory = () => {
    const w = wsRef.current;
    const paragraphs = (w.parserOutput as { paragraphs?: unknown[] } | null)?.paragraphs;
    const paragraphCount = Array.isArray(paragraphs) ? paragraphs.length : 0;
    historyService.add({
      id: typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `h-${Date.now()}`,
      type: "single",
      programName: w.programName,
      createdAt: new Date().toISOString(),
      paragraphCount,
      score: null,
      cost: null,
      parserOutput: w.parserOutput,
      analysisOutput: w.analysisOutput,
      javaOutput: w.javaOutput,
      sourceCode: w.sourceCode,
    });
    alert("Saved to History.");
  };

  const parserEnabled = ws.sourceCode.trim().length > 0;
  const analysisEnabled = parserUi === "success" && isParserOk(ws.parserOutput);
  const javaEnabled = analysisUi === "success" && ws.analysisOutput != null;

  const onDrop: DragEventHandler<HTMLDivElement> = (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (!f || !/\.(cbl|cob|cpy)$/i.test(f.name)) return;
    const reader = new FileReader();
    reader.onload = () => onSourceChange(String(reader.result ?? ""));
    reader.readAsText(f);
  };

  return (
    <div style={{ maxWidth: 1400, margin: "0 auto", padding: "24px", display: "flex", flexDirection: "column", gap: 18 }}>
      <header className="page-hero glass-card">
        <p className="hero-kicker">Phase 1 — Step 1.1</p>
        <h1>Single file conversion</h1>
        <p className="hero-copy">Parse, analyze, and convert one COBOL program. State is stored in your browser.</p>
      </header>

      <div
        className="glass-card"
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
        style={{ padding: 18 }}
      >
        <div className="panel-label" style={{ marginBottom: 8 }}>
          Program: <strong style={{ color: "#e5e7eb" }}>{ws.programName}</strong>
        </div>
        <MonacoCobolEditor value={ws.sourceCode} onChange={onSourceChange} height="380px" />
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>Drag and drop a .cbl / .cob file to load.</p>
      </div>

      <div className="glass-card" style={{ padding: 18, display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
        <StageButton label="Run Parser" status={parserUi} disabled={!parserEnabled} onClick={() => void runParser()} />
        <StageButton
          label="Run Analysis"
          status={analysisUi}
          disabled={!analysisEnabled}
          onClick={() => void runAnalysis()}
        />
        <StageButton label="Convert to Java" status={javaUi} disabled={!javaEnabled} onClick={() => void runJava()} />
      </div>

      {errorOpen && (
        <div className="glass-card" style={{ padding: 0, overflow: "hidden" }}>
          <button
            type="button"
            onClick={() => setErrorOpen((o) => !o)}
            style={{
              width: "100%",
              textAlign: "left",
              padding: 12,
              background: "rgba(127,29,29,0.25)",
              border: "none",
              color: "#fecaca",
              cursor: "pointer",
              fontWeight: 700,
            }}
          >
            Error ({lastErrorStage}) ▼
          </button>
          <div style={{ padding: 14, borderTop: "1px solid var(--border)" }}>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: 13, marginBottom: 12 }}>{lastErrorMsg}</pre>
            <button type="button" className="action-button secondary" onClick={retry}>
              Retry
            </button>
          </div>
        </div>
      )}

      <div className="glass-card" style={{ padding: 18 }}>
        <div className="stage-tabs" style={{ marginBottom: 12 }}>
          {(
            [
              ["parser", "Parser Output"],
              ["analysis", "Analysis Output"],
              ["java", "Java Output"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={`stage-tab ${activeTab === id ? "active" : ""}`}
              data-stage={id === "parser" ? "parser" : id === "analysis" ? "analysis" : "java"}
              style={{ border: "none", cursor: "pointer" }}
              onClick={() => setActiveTab(id)}
            >
              {label}
            </button>
          ))}
        </div>

        {activeTab === "parser" && (
          <div>
            <JsonTreeViewer data={ws.parserOutput} emptyMessage="Run parser to see JSON." />
            <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
              <button
                type="button"
                className="action-button secondary"
                disabled={!ws.parserOutput}
                onClick={() =>
                  ws.parserOutput && downloadText(`${ws.programName}-parser.json`, JSON.stringify(ws.parserOutput, null, 2), "application/json")
                }
              >
                Download JSON
              </button>
            </div>
          </div>
        )}

        {activeTab === "analysis" && (
          <div>
            <JsonTreeViewer data={ws.analysisOutput} emptyMessage="Run analysis to see JSON." />
            <div style={{ marginTop: 12 }}>
              <button
                type="button"
                className="action-button secondary"
                disabled={!ws.analysisOutput}
                onClick={() =>
                  ws.analysisOutput &&
                  downloadText(`${ws.programName}-analysis.json`, JSON.stringify(ws.analysisOutput, null, 2), "application/json")
                }
              >
                Download JSON
              </button>
            </div>
          </div>
        )}

        {activeTab === "java" && (
          <div>
            <MonacoJavaViewer value={ws.javaOutput ?? ""} height="440px" />
            <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
              <button
                type="button"
                className="action-button secondary"
                disabled={!ws.javaOutput}
                onClick={() => ws.javaOutput && void navigator.clipboard.writeText(ws.javaOutput)}
              >
                Copy Java
              </button>
              <button
                type="button"
                className="action-button secondary"
                disabled={!ws.javaOutput}
                onClick={() => ws.javaOutput && downloadText(`${ws.programName}.java`, ws.javaOutput, "text/x-java-source")}
              >
                Download .java
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="action-row wrap" style={{ paddingBottom: 32 }}>
        <button type="button" className="action-button primary" onClick={saveHistory}>
          💾 Save to History
        </button>
        <button type="button" className="action-button secondary" onClick={resetAll}>
          🔄 Reset
        </button>
      </div>
    </div>
  );
}
