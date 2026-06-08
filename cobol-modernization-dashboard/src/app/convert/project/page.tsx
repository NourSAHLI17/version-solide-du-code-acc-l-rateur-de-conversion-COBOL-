"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import JSZip from "jszip";

import FileTree from "@/components/FileTree";
import JsonTreeViewer from "@/components/JsonTreeViewer";
import MonacoCobolEditor from "@/components/MonacoCobolEditor";
import MonacoJavaViewer from "@/components/MonacoJavaViewer";
import RepairSummaryPanel from "@/components/RepairSummaryPanel";
import ScoreCard from "@/components/ScoreCard";
import SmokeTestPanel from "@/components/SmokeTestPanel";
import { pipelineToConversionStatus } from "@/lib/repairSummary";
import { complexityFromAnalyses, normalizeConversionScore, scoreListValue } from "@/lib/conversionScore";
import { PROJECT_BOOTSTRAP_KEY } from "@/lib/bootstrapKeys";
import { expandCopybooks } from "@/lib/projectCopybooks";
import {
  PROJECT_WORKSPACE_KEY,
  classifyType,
  getFileRetryCapabilities,
  loadProjectWorkspace,
  newProjectWorkspace,
  programKeyFromEntry,
  saveProjectWorkspace,
  verifyConversionProgram,
  type ProjectRetryStep,
  type PipelineStageStatus,
  type ProjectFileEntry,
  type ProjectWorkspace,
} from "@/lib/projectWorkspace";
import { extractProgramId } from "@/lib/programId";
import { isParserOk } from "@/lib/singleFileWorkspace";
import { analyzeCobol, convertCobol, parseCobol } from "@/lib/api";
import { queueTestingLaunch } from "@/lib/testingLaunch";
import { persistTestingReplayWorkspace } from "@/lib/testingReplayHandoff";
import { persistTestingTargetMode } from "@/lib/testingService";
import * as historyService from "@/services/historyService";
import type { ProjectWorkspaceSnapshot } from "@/services/historyService";

type TabKey = "parser" | "analysis" | "java" | "score";

function downloadText(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function normalizeProjectPath(p: string): string {
  return p.replace(/\\/g, "/");
}

export default function ProjectConvertPage() {
  const router = useRouter();
  const [workspace, setWorkspace] = useState<ProjectWorkspace | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [detailTab, setDetailTab] = useState<TabKey>("parser");
  const [runBusy, setRunBusy] = useState(false);
  const [retryBusyPath, setRetryBusyPath] = useState<string | null>(null);
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
            score:
              scoreListValue(normalizeConversionScore(f.conversionScore)) ??
              f.score ??
              null,
            conversionScore: normalizeConversionScore(f.conversionScore) ?? null,
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
          const files = w.files.map((f) => {
            const normalizedScore = normalizeConversionScore(f.conversionScore);
            return {
              ...f,
              conversionScore: normalizedScore,
              score: scoreListValue(normalizedScore) ?? f.score ?? null,
            };
          });
          setWorkspace({ ...w, files });
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

  const canRunTesting = Boolean(
    workspace?.files.some((f) => f.type === "cbl" && f.javaOutput?.trim()),
  );

  const goToTesting = useCallback(() => {
    if (workspace) {
      saveProjectWorkspace(workspace);
      persistTestingReplayWorkspace({ mode: "project", workspace });
    }
    queueTestingLaunch({ mode: "project", autoRun: true, source: "conversion" });
    persistTestingTargetMode("project");
    router.push("/testing");
  }, [router, workspace]);

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
          parserOutput: f.parserOutput,
          analysisOutput: f.analysisOutput,
        }));

      const RUN_ALL_ORDER = [
        "CALCFEE.cbl",
        "CHKAML.cbl",
        "LOANEVAL.cbl",
        "RISKSCOR.cbl",
        "RPTMONTH.cbl",
        "RECOVRY.cbl",
      ];
      const sorted = [...cobolSnapshots].sort((a, b) => {
        const ai = RUN_ALL_ORDER.indexOf(a.filename);
        const bi = RUN_ALL_ORDER.indexOf(b.filename);
        return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
      });

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

      const convertOneFile = async (file: (typeof sorted)[number]) => {
        const path = file.path;
        const expanded = expandCopybooks(file.sourceCode, fileMapSnapshot);

        try {
          let parserOutput = file.parserOutput;
          if (parserOutput && isParserOk(parserOutput)) {
            updateFile(path, { parserStatus: "done", parserOutput, stageErrors: undefined });
          } else {
            updateFile(path, { parserStatus: "running", stageErrors: undefined });
            parserOutput = await parseCobol(expanded);
            if (!isParserOk(parserOutput)) {
              const errs =
                (parserOutput as { preflight_errors?: string[] })?.preflight_errors ?? [];
              updateFile(path, {
                parserStatus: "error",
                parserOutput,
                stageErrors: { parser: errs.join("; ") },
              });
              return;
            }
            updateFile(path, { parserStatus: "done", parserOutput });
          }

          const reusedAnalysis =
            file.analysisOutput &&
            typeof file.analysisOutput === "object" &&
            (file.analysisOutput as { analysis_engine?: string }).analysis_engine !== "n/a";
          let analysisOutput = file.analysisOutput;
          if (reusedAnalysis) {
            updateFile(path, { analysisStatus: "done", analysisOutput });
          } else {
          updateFile(path, { analysisStatus: "running" });
          try {
            analysisOutput = await analyzeCobol(expanded, parserOutput);
          } catch (e) {
            updateFile(path, {
              analysisStatus: "error",
              stageErrors: { analysis: e instanceof Error ? e.message : "analysis failed" },
            });
            return;
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
            return;
          }
          updateFile(path, { analysisStatus: "done", analysisOutput });
          }

          updateFile(path, { conversionStatus: "running" });
          try {
            const {
              javaCode,
              conversionScore,
              conversionStatus,
              compileErrors,
              compileStderr,
              compileRepairNotes,
              repairSummary,
            } = await convertCobol(expanded, parserOutput, analysisOutput);
            verifyConversionProgram(file.filename, parserOutput);
            const isPartial = conversionStatus === "partial";
            const compileMsg =
              isPartial && compileErrors?.length
                ? compileErrors.join("\n")
                : isPartial && compileStderr
                  ? compileStderr.slice(0, 2000)
                  : undefined;
            updateFile(path, {
              conversionStatus: isPartial ? "partial" : "done",
              javaOutput: javaCode,
              conversionScore,
              score: scoreListValue(conversionScore),
              compileRepairNotes: compileRepairNotes?.length ? compileRepairNotes : undefined,
              repairSummary: repairSummary ?? undefined,
              compileErrors: compileErrors?.length ? compileErrors : undefined,
              stageErrors: compileMsg ? { java: compileMsg } : undefined,
            });
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
      };

      // All programs in parallel — wall clock = slowest single program (~LOANEVAL), not sum of groups.
      const toRun = sorted.filter((p) => p.filename.endsWith(".cbl"));
      await Promise.allSettled(toRun.map((p) => convertOneFile(p)));
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
        conversionScore: null,
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
      const programName = programKeyFromEntry(f);
      zip.file(`${programName}.java`, f.javaOutput);
    }
    const blob = await zip.generateAsync({ type: "blob" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${workspace.projectName}-java.zip`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const buildProjectSnapshot = (): ProjectWorkspaceSnapshot | null => {
    if (!workspace) return null;
    return {
      projectName: workspace.projectName,
      files: workspace.files.map((f) => ({
        filename: f.filename,
        path: f.path,
        type: f.type,
        sourceCode: f.sourceCode,
        parserOutput: f.parserOutput,
        analysisOutput: f.analysisOutput,
        javaOutput: f.javaOutput,
        parserStatus: f.parserStatus,
        analysisStatus: f.analysisStatus,
        conversionStatus: f.conversionStatus,
        score: f.score,
        conversionScore: f.conversionScore ?? null,
      })),
    };
  };

  const saveProjectToHistory = () => {
    if (!workspace) return;
    const snap = buildProjectSnapshot();
    if (!snap) return;
    const cbl = workspace.files.filter((f) => f.type === "cbl");
    const scores = cbl.map((f) => f.score).filter((s): s is number => typeof s === "number");
    const avgScore = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null;
    void historyService
      .addAsync({
        id: crypto.randomUUID(),
        type: "project",
        programName: workspace.projectName,
        createdAt: new Date().toISOString(),
        score: avgScore,
        cost: null,
        parserOutput: cbl[0]?.parserOutput ?? null,
        analysisOutput: cbl[0]?.analysisOutput ?? null,
        javaOutput: null,
        complexityLabel: complexityFromAnalyses(cbl.map((f) => f.analysisOutput)),
        projectSnapshot: snap,
        conversionScoreRaw: cbl[0]?.conversionScore ?? null,
      })
      .then(() => alert("Project saved to History (database)."))
      .catch((err) => alert(err instanceof Error ? err.message : "Failed to save history"));
  };

  const retryFileStep = async (path: string, step: ProjectRetryStep) => {
    if (!workspace || runBusy || retryBusyPath) return;
    const file = workspace.files.find((f) => normalizeProjectPath(f.path) === normalizeProjectPath(path));
    if (!file || file.type !== "cbl") return;

    setRetryBusyPath(path);
    const fileMapSnapshot = new Map<string, string>();
    for (const f of workspace.files) {
      fileMapSnapshot.set(normalizeProjectPath(f.path), f.sourceCode);
      fileMapSnapshot.set(f.filename, f.sourceCode);
    }
    const expanded = expandCopybooks(file.sourceCode, fileMapSnapshot);
    const pathKey = normalizeProjectPath(path);

    const patch = (partial: Partial<ProjectFileEntry>) => {
      setWorkspace((w) => {
        if (!w) return w;
        return {
          ...w,
          updatedAt: new Date().toISOString(),
          files: w.files.map((f) =>
            normalizeProjectPath(f.path) === pathKey ? { ...f, ...partial } : f,
          ),
        };
      });
    };

    try {
      if (step === "parser") {
        patch({
          parserStatus: "running",
          analysisStatus: "idle",
          conversionStatus: "idle",
          parserOutput: null,
          analysisOutput: null,
          javaOutput: null,
          conversionScore: null,
          score: null,
          stageErrors: undefined,
        });
        const parserOutput = await parseCobol(expanded);
        if (!isParserOk(parserOutput)) {
          const errs = (parserOutput as { preflight_errors?: string[] })?.preflight_errors ?? [];
          patch({ parserStatus: "error", parserOutput, stageErrors: { parser: errs.join("; ") } });
          return;
        }
        patch({ parserStatus: "done", parserOutput });
        return;
      }

      if (step === "analysis") {
        if (!file.parserOutput || !isParserOk(file.parserOutput)) return;
        patch({
          analysisStatus: "running",
          conversionStatus: "idle",
          analysisOutput: null,
          javaOutput: null,
          conversionScore: null,
          score: null,
          stageErrors: { ...file.stageErrors, analysis: undefined, java: undefined },
        });
        const analysisOutput = await analyzeCobol(expanded, file.parserOutput);
        const halted =
          analysisOutput &&
          typeof analysisOutput === "object" &&
          (analysisOutput as { analysis_engine?: string }).analysis_engine === "n/a";
        if (halted) {
          patch({
            analysisOutput,
            analysisStatus: "error",
            stageErrors: { analysis: "Analysis halted" },
          });
          return;
        }
        patch({ analysisStatus: "done", analysisOutput });
        return;
      }

      if (step === "java") {
        if (!file.parserOutput || !file.analysisOutput) return;
        patch({
          conversionStatus: "running",
          javaOutput: null,
          conversionScore: null,
          score: null,
          stageErrors: { ...file.stageErrors, java: undefined },
        });
        const {
          javaCode,
          conversionScore,
          conversionStatus,
          compileErrors,
          compileStderr,
          compileRepairNotes,
          repairSummary,
        } = await convertCobol(expanded, file.parserOutput, file.analysisOutput);
        verifyConversionProgram(file.filename, file.parserOutput);
        const isPartial = conversionStatus === "partial";
        const compileMsg =
          isPartial && compileErrors?.length
            ? compileErrors.join("\n")
            : isPartial && compileStderr
              ? compileStderr.slice(0, 2000)
              : undefined;
        patch({
          conversionStatus: isPartial ? "partial" : "done",
          javaOutput: javaCode,
          conversionScore,
          score: scoreListValue(conversionScore),
          compileRepairNotes: compileRepairNotes?.length ? compileRepairNotes : undefined,
          repairSummary: repairSummary ?? undefined,
          compileErrors: compileErrors?.length ? compileErrors : undefined,
          stageErrors: compileMsg ? { java: compileMsg } : undefined,
        });
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Stage failed";
      if (step === "parser") patch({ parserStatus: "error", stageErrors: { parser: msg } });
      if (step === "analysis") patch({ analysisStatus: "error", stageErrors: { analysis: msg } });
      if (step === "java") patch({ conversionStatus: "error", stageErrors: { java: msg } });
    } finally {
      setRetryBusyPath(null);
    }
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
          disabled={!workspace || runBusy || !!retryBusyPath}
          onClick={() => void runAll()}
        >
          ▶ Run All
        </button>
        {canRunTesting ? (
          <button type="button" className="action-button primary" disabled={runBusy} onClick={goToTesting}>
            Run Testing
          </button>
        ) : null}
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
          <FileTree
            files={workspace.files}
            selectedPath={selectedPath}
            onSelect={setSelectedPath}
            retryBusyPath={retryBusyPath}
            onRetry={(path, step) => void retryFileStep(path, step)}
            retryCapabilities={getFileRetryCapabilities}
          />

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
                          ["score", "Quality Score"],
                        ] as const
                      ).map(([id, label]) => (
                        <button
                          key={id}
                          type="button"
                          className={`stage-tab ${detailTab === id ? "active" : ""}`}
                          data-stage={
                            id === "parser" ? "parser" : id === "analysis" ? "analysis" : id === "java" ? "java" : "tests"
                          }
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
                    {detailTab === "score" && (
                      <div className="score-tab-stack">
                        <RepairSummaryPanel
                          conversionStatus={pipelineToConversionStatus(selected.conversionStatus)}
                          conversionScore={selected.conversionScore}
                          repairSummary={selected.repairSummary}
                          compileRepairNotes={selected.compileRepairNotes}
                        />
                        <ScoreCard score={selected.conversionScore ?? null} />
                        <SmokeTestPanel smokeTest={(selected as Record<string, unknown>).smokeTest ?? null} />
                      </div>
                    )}

                    {detailTab === "java" && (
                      <div>
                        {(selected.repairSummary || selected.compileRepairNotes?.length) ? (
                          <RepairSummaryPanel
                            conversionStatus={pipelineToConversionStatus(selected.conversionStatus)}
                            conversionScore={selected.conversionScore}
                            repairSummary={selected.repairSummary}
                            compileRepairNotes={selected.compileRepairNotes}
                            compact
                          />
                        ) : null}
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
                      <button type="button" className="action-button primary" onClick={saveProjectToHistory}>
                        💾 Save project to History
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
