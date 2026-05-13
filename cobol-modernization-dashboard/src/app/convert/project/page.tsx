"use client";

import { useCallback, useEffect, useState } from "react";
import JSZip from "jszip";

import JsonTreeViewer from "@/components/JsonTreeViewer";
import MonacoCobolEditor from "@/components/MonacoCobolEditor";
import MonacoJavaViewer from "@/components/MonacoJavaViewer";
import { PROJECT_BOOTSTRAP_KEY } from "@/lib/bootstrapKeys";
import { expandCopybooks, topologicalCobolOrder } from "@/lib/projectCopybooks";
import {
  PROJECT_WORKSPACE_KEY,
  classifyType,
  loadProjectWorkspace,
  newProjectWorkspace,
  saveProjectWorkspace,
  type PipelineStageStatus,
  type ProjectFileEntry,
  type ProjectWorkspace,
} from "@/lib/projectWorkspace";
import { extractProgramId } from "@/lib/programId";
import { isParserOk } from "@/lib/singleFileWorkspace";
import { analyzeCobol, convertCobol, parseCobol } from "@/lib/api";
import * as historyService from "@/services/historyService";
import type { ProjectWorkspaceSnapshot } from "@/services/historyService";

type TabKey = "parser" | "analysis" | "java";

function downloadText(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function badgeClass(type: ProjectFileEntry["type"]) {
  if (type === "cbl") return { label: ".cbl", bg: "rgba(14, 165, 233, 0.25)", color: "#7dd3fc" };
  if (type === "jcl") return { label: ".jcl", bg: "rgba(251, 146, 60, 0.25)", color: "#fdba74" };
  if (type === "cpy") return { label: ".cpy", bg: "rgba(244, 114, 182, 0.25)", color: "#f9a8d4" };
  return { label: "file", bg: "rgba(148, 163, 184, 0.2)", color: "#cbd5e1" };
}

function statusGlyph(s: PipelineStageStatus) {
  if (s === "idle") return "—";
  if (s === "running") return "⏳";
  if (s === "done") return "✅";
  return "❌";
}

function normalizeProjectPath(p: string): string {
  return p.replace(/\\/g, "/");
}

export default function ProjectConvertPage() {
  const [workspace, setWorkspace] = useState<ProjectWorkspace | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [detailTab, setDetailTab] = useState<TabKey>("parser");
  const [runBusy, setRunBusy] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const id = window.setTimeout(() => {
      const boot = sessionStorage.getItem(PROJECT_BOOTSTRAP_KEY);
      if (boot) {
        try {
          const snap = JSON.parse(boot) as ProjectWorkspaceSnapshot;
          sessionStorage.removeItem(PROJECT_BOOTSTRAP_KEY);
          const files: ProjectFileEntry[] = snap.files.map((f) => ({
            filename: f.filename,
            path: f.path,
            type: f.type as ProjectFileEntry["type"],
            sourceCode: f.sourceCode,
            parserStatus: f.parserStatus as PipelineStageStatus,
            analysisStatus: f.analysisStatus as PipelineStageStatus,
            conversionStatus: f.conversionStatus as PipelineStageStatus,
            parserOutput: f.parserOutput,
            analysisOutput: f.analysisOutput,
            javaOutput: f.javaOutput,
            score: null,
          }));
          const ws = newProjectWorkspace(snap.projectName, files);
          setWorkspace(ws);
          saveProjectWorkspace(ws);
          const firstCbl = files.find((f) => f.type === "cbl");
          setSelectedPath(firstCbl?.path ?? files[0]?.path ?? null);
        } catch {
          sessionStorage.removeItem(PROJECT_BOOTSTRAP_KEY);
        }
      } else {
        const w = loadProjectWorkspace();
        if (w) {
          setWorkspace(w);
          setSelectedPath(w.files[0]?.path ?? null);
        }
      }
      setHydrated(true);
    }, 0);
    return () => clearTimeout(id);
  }, []);

  useEffect(() => {
    if (hydrated && workspace) saveProjectWorkspace(workspace);
  }, [workspace, hydrated]);

  const selected = workspace?.files.find((f) => f.path === selectedPath) ?? null;
  const selectedCblProgramStub =
    selected?.type === "cbl"
      ? extractProgramId(selected.sourceCode) || selected.filename.replace(/\.(cbl|cob)$/i, "") || "Program"
      : "";

  const ingestZip = useCallback(async (file: File) => {
    const buf = await file.arrayBuffer();
    const zip = await JSZip.loadAsync(buf);
    const files: ProjectFileEntry[] = [];
    const entries = Object.keys(zip.files);
    for (const path of entries.sort()) {
      const zf = zip.files[path];
      if (zf.dir) continue;
      const sourceCode = await zf.async("string");
      const posixPath = String(path).replace(/\\/g, "/").replace(/\/+$/u, "");
      const filename = (posixPath.split("/").pop() ?? posixPath).trim();
      const type = classifyType(filename);
      files.push({
        filename,
        path: posixPath,
        type,
        sourceCode,
        parserStatus: "idle",
        analysisStatus: "idle",
        conversionStatus: "idle",
        parserOutput: null,
        analysisOutput: null,
        javaOutput: null,
        score: null,
      });
    }
    const baseName = file.name.replace(/\.zip$/i, "") || "Project";
    const ws = newProjectWorkspace(baseName, files);
    setWorkspace(ws);
    saveProjectWorkspace(ws);
    const firstCbl = files.find((f) => f.type === "cbl");
    setSelectedPath(firstCbl?.path ?? files[0]?.path ?? null);
  }, []);

  const runAll = async () => {
    const snap = workspace;
    if (!snap) return;
    setRunBusy(true);
    try {
      const fileMapSnapshot = new Map<string, string>();
      for (const f of snap.files) {
        const p = normalizeProjectPath(f.path);
        fileMapSnapshot.set(p, f.sourceCode);
        fileMapSnapshot.set(f.filename, f.sourceCode);
      }

      /** Plain snapshot: no shared refs with React state rows — loop is stable across setWorkspace. */
      const cobolSnapshots = snap.files
        .filter((f) => f.type === "cbl")
        .map((f) => ({
          path: normalizeProjectPath(f.path),
          filename: f.filename,
          sourceCode: f.sourceCode,
        }));
      const ordered = topologicalCobolOrder(cobolSnapshots);

      const updateFile = (pathKey: string, partial: Partial<ProjectFileEntry>) => {
        const key = normalizeProjectPath(pathKey);
        setWorkspace((w) => {
          if (!w) return w;
          return {
            ...w,
            updatedAt: new Date().toISOString(),
            files: w.files.map((f) =>
              normalizeProjectPath(f.path) === key ? { ...f, ...partial } : f,
            ),
          };
        });
      };

      for (let i = 0; i < ordered.length; i++) {
        const file = ordered[i];
        const path = file.path;
        const expanded = expandCopybooks(file.sourceCode, fileMapSnapshot);

        updateFile(path, { parserStatus: "running", stageErrors: undefined });
        try {
          const parserOutput = await parseCobol(expanded);
          if (!isParserOk(parserOutput)) {
            const errs = (parserOutput as { preflight_errors?: string[] })?.preflight_errors ?? [];
            updateFile(path, {
              parserStatus: "error",
              parserOutput,
              stageErrors: { parser: errs.join("; ") },
            });
            continue;
          }
          updateFile(path, { parserStatus: "done", parserOutput });

          updateFile(path, { analysisStatus: "running" });
          let analysisOutput;
          try {
            analysisOutput = await analyzeCobol(expanded, parserOutput);
          } catch (e) {
            updateFile(path, {
              analysisStatus: "error",
              stageErrors: { analysis: e instanceof Error ? e.message : "analysis failed" },
            });
            continue;
          }
          const halted =
            analysisOutput &&
            typeof analysisOutput === "object" &&
            (analysisOutput as { analysis_engine?: string }).analysis_engine === "n/a";
          if (halted) {
            updateFile(path, {
              analysisOutput,
              analysisStatus: "error",
              stageErrors: { analysis: "Analysis halted" },
            });
            continue;
          }
          updateFile(path, { analysisStatus: "done", analysisOutput });

          updateFile(path, { conversionStatus: "running" });
          try {
            const java = await convertCobol(expanded, parserOutput, analysisOutput);
            updateFile(path, { conversionStatus: "done", javaOutput: java });
          } catch (e) {
            updateFile(path, {
              conversionStatus: "error",
              stageErrors: { java: e instanceof Error ? e.message : "convert failed" },
            });
          }
        } catch (e) {
          updateFile(path, {
            parserStatus: "error",
            stageErrors: { parser: e instanceof Error ? e.message : "parse failed" },
          });
        }
      }
    } finally {
      setRunBusy(false);
    }
  };

  const resetProject = () => {
    if (!window.confirm("Reset project? All outputs and statuses will be cleared.")) return;
    if (!workspace) return;
    window.localStorage.removeItem(PROJECT_WORKSPACE_KEY);
    const cleared: ProjectWorkspace = {
      ...workspace,
      updatedAt: new Date().toISOString(),
      files: workspace.files.map((f) => ({
        ...f,
        parserStatus: "idle",
        analysisStatus: "idle",
        conversionStatus: "idle",
        parserOutput: null,
        analysisOutput: null,
        javaOutput: null,
        stageErrors: undefined,
        score: null,
      })),
    };
    setWorkspace(cleared);
    saveProjectWorkspace(cleared);
    setDetailTab("parser");
  };

  const downloadAllJava = async () => {
    if (!workspace) return;
    const zip = new JSZip();
    for (const f of workspace.files) {
      if (f.type !== "cbl" || !f.javaOutput) continue;
      const stub = f.filename.replace(/\.(cbl|cob)$/i, "") || "Program";
      zip.file(`${stub}.java`, f.javaOutput);
    }
    const blob = await zip.generateAsync({ type: "blob" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${workspace.projectName}-java.zip`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const saveFileToHistory = () => {
    if (!selected || selected.type !== "cbl") return;
    const paragraphs = (selected.parserOutput as { paragraphs?: unknown[] } | null)?.paragraphs;
    const paragraphCount = Array.isArray(paragraphs) ? paragraphs.length : 0;
    historyService.add({
      id: crypto.randomUUID(),
      type: "single",
      programName: extractProgramId(selected.sourceCode),
      createdAt: new Date().toISOString(),
      paragraphCount,
      score: null,
      cost: null,
      parserOutput: selected.parserOutput,
      analysisOutput: selected.analysisOutput,
      javaOutput: selected.javaOutput,
      sourceCode: selected.sourceCode,
    });
    alert("Saved to History.");
  };

  return (
    <div style={{ maxWidth: 1400, margin: "0 auto", padding: 24, display: "flex", flexDirection: "column", gap: 18 }}>
      <header className="page-hero glass-card">
        <p className="hero-kicker">Phase 1 — Step 1.2</p>
        <h1>Project conversion</h1>
        <p className="hero-copy">Upload a ZIP of COBOL sources. COPYbooks are expanded client-side before calling the API.</p>
      </header>

      <div className="glass-card" style={{ padding: 16, display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        <label className="action-button secondary" style={{ cursor: "pointer", margin: 0 }}>
          📂 Load Existing / Upload ZIP
          <input
            type="file"
            accept=".zip"
            className="app-file-input"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void ingestZip(f);
              e.target.value = "";
            }}
          />
        </label>
        <span style={{ color: "var(--text-muted)", fontSize: 13 }}>
          Sample: <a href="/usecase3-demo.zip" download style={{ color: "var(--sky)" }}>usecase3-demo.zip</a>
        </span>
        <button
          type="button"
          className="action-button primary"
          disabled={!workspace || runBusy}
          onClick={() => void runAll()}
        >
          ▶ Run All
        </button>
        <button type="button" className="action-button secondary" disabled={!workspace} onClick={() => void downloadAllJava()}>
          ⬇ Download All Java
        </button>
        <button type="button" className="action-button secondary" disabled={!workspace} onClick={resetProject}>
          🔄 Reset
        </button>
      </div>

      {!workspace && (
        <div className="glass-card" style={{ padding: 24, color: "var(--text-muted)" }}>
          Upload a project ZIP to begin. A sample Use Case 3 archive ships with the dashboard:{" "}
          <a href="/usecase3-demo.zip" download style={{ color: "var(--sky)", fontWeight: 700 }}>
            usecase3-demo.zip
          </a>{" "}
          (3 .cbl, 4 .cpy, 1 .jcl when extracted).
        </div>
      )}

      {workspace && (
        <div className="project-layout">
          <div className="file-list">
            <div className="file-list-header">{workspace.projectName}</div>
            {workspace.files.map((f) => {
              const b = badgeClass(f.type);
              const active = f.path === selectedPath;
              return (
                <button
                  key={f.path}
                  type="button"
                  className={`file-item ${active ? "active" : ""}`}
                  onClick={() => setSelectedPath(f.path)}
                >
                  <div style={{ minWidth: 0 }}>
                    <div className="file-path">{f.filename}</div>
                    <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap", alignItems: "center" }}>
                      <span className="stage-badge" style={{ background: b.bg, color: b.color, borderColor: b.color }}>
                        {b.label}
                      </span>
                      <span className="stage-badge parser" style={{ fontSize: 10, padding: "4px 8px" }}>
                        Parse {statusGlyph(f.parserStatus)}
                      </span>
                      <span className="stage-badge analysis" style={{ fontSize: 10, padding: "4px 8px" }}>
                        Analyze {statusGlyph(f.analysisStatus)}
                      </span>
                      <span className="stage-badge java" style={{ fontSize: 10, padding: "4px 8px" }}>
                        Convert {statusGlyph(f.conversionStatus)}
                      </span>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="output-card">
            {!selected && <p style={{ color: "var(--text-muted)" }}>Select a file.</p>}
            {selected && (
              <>
                <div className="panel-label">{selected.filename}</div>
                {selected.type === "cbl" ? (
                  <div key={selected.path}>
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
                          className={`stage-tab ${detailTab === id ? "active" : ""}`}
                          data-stage={id === "parser" ? "parser" : id === "analysis" ? "analysis" : "java"}
                          style={{ border: "none", cursor: "pointer" }}
                          onClick={() => setDetailTab(id)}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    {detailTab === "parser" && (
                      <div>
                        <JsonTreeViewer data={selected.parserOutput} emptyMessage="Run pipeline to see output." />
                        <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
                          <button
                            type="button"
                            className="action-button secondary"
                            disabled={!selected.parserOutput}
                            onClick={() =>
                              selected.parserOutput &&
                              downloadText(
                                `${selectedCblProgramStub}-parser.json`,
                                JSON.stringify(selected.parserOutput, null, 2),
                                "application/json",
                              )
                            }
                          >
                            Download JSON
                          </button>
                        </div>
                      </div>
                    )}
                    {detailTab === "analysis" && (
                      <div>
                        <JsonTreeViewer data={selected.analysisOutput} emptyMessage="Run pipeline to see output." />
                        <div style={{ marginTop: 12 }}>
                          <button
                            type="button"
                            className="action-button secondary"
                            disabled={!selected.analysisOutput}
                            onClick={() =>
                              selected.analysisOutput &&
                              downloadText(
                                `${selectedCblProgramStub}-analysis.json`,
                                JSON.stringify(selected.analysisOutput, null, 2),
                                "application/json",
                              )
                            }
                          >
                            Download JSON
                          </button>
                        </div>
                      </div>
                    )}
                    {detailTab === "java" && (
                      <div>
                        <MonacoJavaViewer value={selected.javaOutput ?? ""} height="400px" />
                        <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
                          <button
                            type="button"
                            className="action-button secondary"
                            disabled={!selected.javaOutput}
                            onClick={() => selected.javaOutput && void navigator.clipboard.writeText(selected.javaOutput)}
                          >
                            Copy Java
                          </button>
                          <button
                            type="button"
                            className="action-button secondary"
                            disabled={!selected.javaOutput}
                            onClick={() =>
                              selected.javaOutput &&
                              downloadText(`${selectedCblProgramStub}.java`, selected.javaOutput, "text/x-java-source")
                            }
                          >
                            Download .java
                          </button>
                        </div>
                      </div>
                    )}
                    <div style={{ marginTop: 12 }}>
                      <button type="button" className="action-button primary" onClick={saveFileToHistory}>
                        💾 Save to History
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <MonacoCobolEditor value={selected.sourceCode} onChange={() => {}} height="360px" readOnly />
                    <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>Pipeline runs on .cbl files only.</p>
                  </>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
