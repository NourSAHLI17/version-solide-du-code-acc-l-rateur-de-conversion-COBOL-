"use client";

import { useState } from "react";
import AppShell from "@/components/AppShell";
import ActionButton from "@/components/ActionButton";
import { uploadProject, runProjectPipeline, downloadProject } from "@/lib/api";
import StatusPill from "@/components/StatusPill";
import ArtifactPanel from "@/components/ArtifactPanel";
import CodePanel from "@/components/CodePanel";
import PipelineModeSelector from "@/components/PipelineModeSelector";
import PipelineProgress from "@/components/PipelineProgress";
import StageBadge from "@/components/StageBadge";
import type { PipelineMode } from "@/lib/pipelineModes";
import { PROJECT_PIPELINE_MODES } from "@/lib/pipelineModes";
import { useWorkspace } from "@/lib/workspace";

interface ProjectFile {
    path: string;
    content: string;
    type: "cobol" | "copybook" | "jcl" | "other";
    size: number;
    status: "idle" | "processing" | "success" | "failed";
    error?: string;
    javaCode?: string;
}

export default function ProjectCockpitPage() {
    const { actions } = useWorkspace();
    const [projectName, setProjectName] = useState("MyCobolProject");
    const [files, setFiles] = useState<ProjectFile[]>([]);
    const [selectedFile, setSelectedFile] = useState<ProjectFile | null>(null);
    const [isUploading, setIsUploading] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);
    const [mode, setMode] = useState<PipelineMode>("full");
    const [projectResults, setProjectResults] = useState<any[]>([]);
    const selectedResult = selectedFile ? projectResults.find((r: any) => r.file === selectedFile.path) : null;

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        if (!e.target.files || e.target.files.length === 0) return;
        
        const file = e.target.files[0];
        if (!file.name.endsWith(".zip")) {
            alert("Please upload a .zip file containing your COBOL project.");
            return;
        }

        setIsUploading(true);
        // Clear old state
        setFiles([]);
        setProjectResults([]);
        setSelectedFile(null);
        
        try {
            const res = await uploadProject(file);
            console.log("Upload result:", res);
            const nextFiles = res.files.map((f: any) => ({
                ...f,
                status: "idle"
            }));
            setFiles(nextFiles);
            setSelectedFile(nextFiles[0] ?? null);
            // Guess a project name from the file name
            setProjectName(file.name.replace(/\.zip$/i, ""));
        } catch (err) {
            console.error(err);
            alert("Failed to upload/parse ZIP. Check console.");
        } finally {
            setIsUploading(false);
            // Reset the input so the user can select the same file again if they want
            e.target.value = '';
        }
    };

    const runModernization = async () => {
        setIsProcessing(true);
        // Set all cobol files to processing
        setFiles(prev => prev.map(f => f.type === "cobol" ? { ...f, status: "processing" } : f));
        
        try {
            const payloadFiles = files.map(f => ({
                path: f.path,
                content: f.content,
                type: f.type
            }));
            
            const response = await runProjectPipeline(payloadFiles, mode);
            setProjectResults(response.results);
            actions.setProjectResults(response.results);

            const firstConverted = response.results.find((r: any) => r.java_source);
            const firstSourceFile = firstConverted ? files.find((f) => f.path === firstConverted.file) : null;
            if (firstConverted && firstSourceFile) {
                actions.setActiveArtifact(
                    firstSourceFile.content,
                    firstConverted.parser_output ?? null,
                    firstConverted.analysis_output ?? null,
                    firstConverted.java_source ?? ""
                );
            }
            
            // Update local file status based on the results array
            setFiles(prev => prev.map(f => {
                const res = response.results.find((r: any) => r.file === f.path);
                if (res) {
                    const hasError = res.errors && res.errors.length > 0;
                    return { 
                        ...f, 
                        status: hasError ? "failed" : "success", 
                        error: hasError ? res.errors[0] : undefined, 
                        javaCode: res.java_source 
                    };
                }
                return f;
            }));
        } catch (err) {
            console.error("Project modernization failed", err);
            alert("Modernization batch failed. Check console.");
        } finally {
            setIsProcessing(false);
        }
    };

    const handleDownload = async () => {
        if (projectResults.length === 0) return;
        try {
            const blob = await downloadProject(projectResults);
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `${projectName}_modernized_${mode}.zip`;
            a.click();
        } catch (err) {
            console.error(err);
            alert("Download failed.");
        }
    };

    const cobolCount = files.filter(f => f.type === "cobol").length;

    return (
        <AppShell
            title="Project Modernization Cockpit" 
            subtitle="Upload full COBOL projects (.zip containing source, copybooks, JCL) and batch-transform them using robust pipeline features."
        >
            <div className="glass-card">
                <div className="page-grid two-column">
                    <div>
                        <label className="mode-select-label" htmlFor="project-name">Project Name</label>
                        <input
                            id="project-name"
                            type="text"
                            value={projectName}
                            onChange={(e) => setProjectName(e.target.value)}
                            className="app-input"
                            disabled={isProcessing}
                        />
                    </div>
                    <div>
                        <label className="mode-select-label" htmlFor="project-zip">Upload Project (.zip)</label>
                        <input
                            id="project-zip"
                            type="file"
                            accept=".zip"
                            onChange={handleFileUpload}
                            disabled={isProcessing || isUploading}
                            className="app-file-input"
                        />
                    </div>
                </div>

                <div style={{ marginTop: 18 }}>
                    <PipelineModeSelector value={mode} onChange={setMode} modes={PROJECT_PIPELINE_MODES} compact />
                </div>

                <div className="action-row wrap" style={{ marginTop: 18 }}>
                    <ActionButton 
                        onClick={runModernization} 
                        disabled={cobolCount === 0 || isProcessing || isUploading}
                    >
                        {isProcessing ? "Processing Project Batch..." : `Run Pipeline on ${cobolCount} files`}
                    </ActionButton>
                    
                    {projectResults.length > 0 && (
                        <ActionButton variant="secondary" onClick={handleDownload}>
                            Download Results (.zip)
                        </ActionButton>
                    )}
                    
                    <ActionButton variant="secondary" onClick={() => { setFiles([]); setProjectResults([]); setSelectedFile(null); }} disabled={isProcessing || files.length === 0}>
                        Clear All
                    </ActionButton>
                </div>
            </div>

            <PipelineProgress currentStage={isProcessing ? "Convert" : null} mode={mode} />

            <div className="project-layout">
                <div className="file-list">
                    <div className="file-list-header">Project Explorer</div>
                    {files.length === 0 ? (
                        <div style={{ padding: 24, color: "var(--text-muted)", fontSize: 14 }}>
                            Upload a ZIP to inspect COBOL, COPY, and JCL files.
                        </div>
                    ) : (
                        files.map((file) => (
                            <button
                                key={file.path}
                                type="button"
                                className={`file-item ${selectedFile?.path === file.path ? "active" : ""}`}
                                onClick={() => setSelectedFile(file)}
                            >
                                <span>
                                    <span className="file-path">{file.path}</span>
                                    <span className="file-meta">{(file.size / 1024).toFixed(1)} KB</span>
                                </span>
                                <StageBadge
                                    label={file.type}
                                    stage={file.type === "copybook" ? "copybook" : file.type === "jcl" ? "jcl" : file.type === "cobol" ? "parser" : "tests"}
                                />
                            </button>
                        ))
                    )}
                </div>
                <CodePanel title={selectedFile ? selectedFile.path : "Selected File"} code={selectedFile?.content ?? "// Select a project file to preview its content"} />
            </div>

            {selectedFile?.type === "cobol" && (
                <div className="page-grid two-column">
                    <ArtifactPanel
                        title={`Parser Output: ${selectedFile.path}`}
                        data={selectedResult?.parser_output ?? { message: "Run the project pipeline to see parser output for this COBOL file." }}
                    />
                    <ArtifactPanel
                        title={`Analysis Output: ${selectedFile.path}`}
                        data={selectedResult?.analysis_output ?? { message: "Run the project pipeline to see analysis output for this COBOL file." }}
                    />
                </div>
            )}

            <div className="glass-card">
                <table className="results-table">
                    <thead className="table-head">
                        <tr>
                            <th>File</th>
                            <th>Status</th>
                            <th>Parser</th>
                            <th>Analysis</th>
                            <th>Java</th>
                            <th>Tests</th>
                            <th>Result</th>
                        </tr>
                    </thead>
                    <tbody>
                        {files.length === 0 && (
                            <tr>
                                <td colSpan={7} style={{ padding: 48, textAlign: "center", color: "var(--text-muted)" }}>
                                    Upload a .ZIP file containing your COBOL sources, copybooks, and JCL to begin a batch run.
                                </td>
                            </tr>
                        )}
                        {files.map((file, i) => {
                            const rowResult = projectResults.find((r: any) => r.file === file.path);
                            return (
                            <tr key={i}>
                                <td className="file-path" title={file.path}>
                                    {file.path}
                                </td>
                                <td>
                                    {file.type === "cobol" ? (
                                        <StatusPill 
                                            label={file.status} 
                                            tone={file.status === "success" ? "good" : file.status === "failed" ? "bad" : "neutral"} 
                                        />
                                    ) : (
                                        <span className="file-meta">Context</span>
                                    )}
                                </td>
                                <td><StageBadge label={rowResult?.parser_output ? "done" : "--"} stage="parser" /></td>
                                <td><StageBadge label={rowResult?.analysis_output ? "done" : "--"} stage="analysis" /></td>
                                <td><StageBadge label={rowResult?.java_source ? "done" : "--"} stage="java" /></td>
                                <td><StageBadge label={rowResult?.test_report ? "done" : "--"} stage="tests" /></td>
                                <td>
                                    {file.javaCode ? (
                                        <span style={{ color: "var(--emerald)" }}>Successfully converted</span>
                                    ) : file.error ? (
                                        <span style={{ color: "var(--danger)" }} title={file.error}>{file.error.substring(0, 54)}...</span>
                                    ) : (
                                        <span className="file-meta">--</span>
                                    )}
                                </td>
                            </tr>
                        )})}
                    </tbody>
                </table>
            </div>
        </AppShell>
    );
}
