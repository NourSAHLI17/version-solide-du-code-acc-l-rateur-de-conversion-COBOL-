/**
 * Deterministic PDF report builder for a single testing run (consulting / audit style).
 */

import type { AnalysisResult } from "./types.ts";
import type {
  LayerScores,
  TestingAgentRunResult,
  TestingFinalDecisionResult,
  TestSummaryMeta,
} from "./testingAgentTypes.ts";
import { formatFailureLayer, statusLabel } from "./testingAgentTypes.ts";
import {
  drawDecisionBlock,
  drawPageFooters,
  drawReportHeader,
  renderTable,
} from "./testingRunPdfLayout.ts";

function collectBusinessRulesFromAnalysis(
  analysis: Record<string, unknown> | null | undefined,
): string[] {
  if (!analysis || typeof analysis !== "object") return [];
  const rules: string[] = [];
  const top = analysis.business_rules;
  if (Array.isArray(top)) {
    for (const r of top) {
      if (typeof r === "string" && r.trim()) rules.push(r.trim());
    }
  }
  const sections = analysis.sections;
  if (Array.isArray(sections)) {
    for (const sec of sections) {
      if (!sec || typeof sec !== "object") continue;
      const br = (sec as { business_rules?: unknown }).business_rules;
      if (!Array.isArray(br)) continue;
      for (const r of br) {
        if (typeof r === "string" && r.trim()) rules.push(r.trim());
      }
    }
  }
  const seen = new Set<string>();
  const out: string[] = [];
  for (const r of rules) {
    const key = r.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      out.push(r);
    }
  }
  return out.sort((a, b) => a.localeCompare(b));
}

export type TestingRunPdfExportSource = "history" | "session";

export type PdfTableRow = [string, string];
export type PdfTableRow3 = [string, string, string];

export interface TestingRunPdfReportModel {
  program_name: string;
  run_id: string;
  created_at: string;
  created_at_display: string;
  export_source: TestingRunPdfExportSource;
  export_source_note: string;
  reliability_score: string;
  behavioral_status: string;
  behavioral_summary: string;
  decision_label: string;
  decision_state: string;
  save_eligible: string;
  reason_summary: string;
  blockers: string[];
  failure_reason: string | null;
  is_local_estimate: boolean;
  /** Structured tables for PDF layout */
  metadata_rows: PdfTableRow[];
  executive_rows: PdfTableRow[];
  score_breakdown_rows: PdfTableRow[];
  layer_rows: PdfTableRow[];
  diff_rows: PdfTableRow[];
  analysis_rows: PdfTableRow[];
  validation_rows: PdfTableRow3[];
  /** Legacy line arrays (tests / compatibility) */
  layer_summary_lines: string[];
  analysis_summary_lines: string[];
  validation_summary_lines: string[];
  score_breakdown_lines: string[];
  diff_summary_lines: string[];
}

export interface BuildTestingRunPdfReportInput {
  run: TestingAgentRunResult;
  decision: TestingFinalDecisionResult | null;
  export_source: TestingRunPdfExportSource;
  analysis_output?: AnalysisResult | Record<string, unknown> | null;
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso || "—";
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function decisionDisplayLabel(state: string | undefined): string {
  if (state === "ready_to_save") return "Ready to save (pass)";
  if (state === "needs_more_validation") return "Needs more validation";
  if (state === "retry_recommended") return "Retry recommended (fail)";
  return state || "Unknown";
}

function validationStatus(
  summary: TestSummaryMeta | undefined,
  passKey: keyof TestSummaryMeta,
  statusKey: "business_rules_status" | "edge_cases_status" | "unit_tests_status",
): string {
  const pass = Boolean(summary?.[passKey]);
  const status = summary?.[statusKey];
  if (status === "pass" || pass) return "Pass";
  if (status === "ready") return "Artifacts ready";
  return "Not available";
}

function buildLayerRows(run: TestingAgentRunResult): PdfTableRow[] {
  const rows: PdfTableRow[] = [];
  const layers = run.layer_scores;
  const diag = run.run_diagnostics;

  if (layers) {
    const entries: Array<[keyof LayerScores, string]> = [
      ["compile_health", "Compile health"],
      ["runtime_health", "Runtime health"],
      ["behavioral_parity", "Behavioral parity"],
      ["retry_stability", "Retry stability"],
      ["attribution_confidence", "Attribution confidence"],
    ];
    for (const [key, label] of entries) {
      const v = layers[key];
      rows.push([label, v != null ? `${v} / 100` : "N/A"]);
    }
  } else if (diag) {
    rows.push(["COBOL compile", String(diag.cobol_compile_status ?? "—")]);
    rows.push(["Java compile", String(diag.java_compile_status ?? "—")]);
    rows.push(["COBOL runtime", String(diag.cobol_runtime_status ?? "—")]);
    rows.push(["Java runtime", String(diag.java_runtime_status ?? "—")]);
    rows.push(["Stdout diff %", String(diag.stdout_diff_percentage ?? 0)]);
  } else {
    rows.push(["Diagnostics", "Not recorded on this run"]);
  }

  if (run.primary_failure_layer) {
    rows.push(["Primary failure layer", formatFailureLayer(run.primary_failure_layer)]);
  }
  if (run.qscore != null) {
    rows.push(["Layered qscore", `${Math.round(Number(run.qscore))} / 100`]);
  }
  return rows;
}

function buildAnalysisRows(
  analysis: AnalysisResult | Record<string, unknown> | null | undefined,
): PdfTableRow[] {
  if (!analysis || typeof analysis !== "object") {
    return [["Analysis", "Not available on this run record"]];
  }
  const rows: PdfTableRow[] = [];
  const gp = (analysis as { global_purpose?: unknown }).global_purpose;
  if (typeof gp === "string" && gp.trim()) {
    rows.push(["Program purpose", gp.trim()]);
  }
  const complexity = (analysis as { complexity?: unknown }).complexity;
  if (complexity) rows.push(["Complexity", String(complexity)]);
  const engine = (analysis as { analysis_engine?: unknown }).analysis_engine;
  if (engine) rows.push(["Analysis engine", String(engine)]);
  const rules = collectBusinessRulesFromAnalysis(analysis);
  rows.push(["Business rules (count)", String(rules.length)]);
  const sections = (analysis as { sections?: unknown }).sections;
  if (Array.isArray(sections)) {
    rows.push(["Paragraph sections", String(sections.length)]);
  }
  if (rules.length > 0) {
    const preview = rules.slice(0, 8);
    for (let i = 0; i < preview.length; i++) {
      rows.push([i === 0 ? "Sample business rules" : "", preview[i]]);
    }
    if (rules.length > 8) {
      rows.push(["", `… and ${rules.length - 8} additional rules`]);
    }
  }
  if (rows.length === 0) {
    rows.push(["Analysis", "Present but no summary fields extracted"]);
  }
  return rows;
}

function buildDiffRows(
  run: TestingAgentRunResult,
  decision: TestingFinalDecisionResult | null,
): PdfTableRow[] {
  const diff = run.diff_summary;
  const rows: PdfTableRow[] = [
    ["Lines compared", String(diff.lines_compared ?? 0)],
    ["Lines matched", String(diff.lines_matched ?? 0)],
    ["Lines diverged", String(diff.lines_diverged ?? 0)],
    ["Diff percentage", `${diff.diff_percentage ?? 0}%`],
  ];
  if (decision?.diff_summary?.match_rate != null) {
    rows.push(["Match rate", `${decision.diff_summary.match_rate}%`]);
  }
  if (run.execution_mode) {
    rows.push(["Execution mode", run.execution_mode]);
  }
  if (run.fallback_mode) {
    rows.push(["Fallback mode", "Yes (snapshot / offline artifacts)"]);
  }
  return rows;
}

function rowsToLines(rows: PdfTableRow[]): string[] {
  return rows.map(([a, b]) => `${a}: ${b}`);
}

function validationRowsToLines(rows: PdfTableRow3[]): string[] {
  return rows.map(([a, b, c]) => `${a}: ${b}${c ? ` · ${c}` : ""}`);
}

/** Map run + decision into deterministic report sections (no PDF). */
export function buildTestingRunReportModel(
  input: BuildTestingRunPdfReportInput,
): TestingRunPdfReportModel {
  const { run, decision, export_source, analysis_output } = input;
  const breakdown = decision?.score_breakdown;
  const summary = decision?.test_summary;

  const reliability =
    decision?.reliability_score != null
      ? String(Math.round(decision.reliability_score))
      : run.qscore != null
        ? String(Math.round(Number(run.qscore)))
        : "—";

  const behavioralStatus = statusLabel(run.status);
  const behavioralSummary = summary?.behavioral_pass
    ? "Behavioral COBOL vs Java stdout comparison passed."
    : run.status === "not_run"
      ? "Behavioral comparison did not run or produced no comparable stdout."
      : `Behavioral status: ${behavioralStatus}. Failed tests: ${run.failed_tests?.length ?? 0}.`;

  const export_source_note =
    export_source === "history"
      ? "Report source: saved history record (authoritative)."
      : "Report source: current session view (run may not be persisted in history).";

  const metadata_rows: PdfTableRow[] = [
    ["Program", run.program_name || "Program"],
    ["Run ID", run.run_id],
    ["Run completed", formatTimestamp(run.created_at)],
    ["Export source", export_source === "history" ? "History (saved)" : "Session (transient)"],
    ["Target mode", run.target_type === "project" ? "Project" : "Single file"],
  ];
  if (decision?.is_local_estimate) {
    metadata_rows.push([
      "Score note",
      "Reliability score estimated locally (API unavailable at decision time).",
    ]);
  }

  const executive_rows: PdfTableRow[] = [
    ["Reliability score", `${reliability} / 100`],
    ["Behavioral status", behavioralStatus],
    ["Behavioral summary", behavioralSummary],
    ["Final decision", decisionDisplayLabel(decision?.decision_state)],
    ["Save eligible", decision?.save_eligible ? "Yes" : decision ? "No" : "—"],
    ["Decision rationale", decision?.reason_summary?.trim() || "—"],
  ];

  const score_breakdown_rows: PdfTableRow[] = [];
  if (breakdown) {
    const keys = Object.keys(breakdown).sort();
    for (const k of keys) {
      const v = breakdown[k];
      if (v != null) {
        score_breakdown_rows.push([
          k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
          String(v),
        ]);
      }
    }
  } else {
    score_breakdown_rows.push(["Breakdown", "Not available"]);
  }

  const layer_rows = buildLayerRows(run);
  const diff_rows = buildDiffRows(run, decision);
  const analysis_rows = buildAnalysisRows(analysis_output);

  const validation_rows: PdfTableRow3[] = [
    [
      "Business rules",
      validationStatus(summary, "business_rules_pass", "business_rules_status"),
      breakdown?.business_rules != null ? `${breakdown.business_rules} pts` : "—",
    ],
    [
      "Edge cases",
      validationStatus(summary, "edge_cases_pass", "edge_cases_status"),
      breakdown?.edge_cases != null ? `${breakdown.edge_cases} pts` : "—",
    ],
    [
      "Unit tests",
      validationStatus(summary, "unit_tests_pass", "unit_tests_status"),
      breakdown?.unit_tests != null ? `${breakdown.unit_tests} pts` : "—",
    ],
  ];

  return {
    program_name: run.program_name || "Program",
    run_id: run.run_id,
    created_at: run.created_at,
    created_at_display: formatTimestamp(run.created_at),
    export_source,
    export_source_note,
    reliability_score: reliability,
    behavioral_status: behavioralStatus,
    behavioral_summary: behavioralSummary,
    decision_label: decisionDisplayLabel(decision?.decision_state),
    decision_state: decision?.decision_state ?? "—",
    save_eligible: decision?.save_eligible ? "Yes" : decision ? "No" : "—",
    reason_summary: decision?.reason_summary?.trim() || "—",
    blockers: decision?.blockers?.length ? [...decision.blockers] : [],
    failure_reason: run.failure_reason,
    is_local_estimate: Boolean(decision?.is_local_estimate),
    metadata_rows,
    executive_rows,
    score_breakdown_rows,
    layer_rows,
    diff_rows,
    analysis_rows,
    validation_rows,
    layer_summary_lines: rowsToLines(layer_rows),
    analysis_summary_lines: rowsToLines(analysis_rows),
    validation_summary_lines: validationRowsToLines(validation_rows),
    score_breakdown_lines: rowsToLines(score_breakdown_rows),
    diff_summary_lines: rowsToLines(diff_rows),
  };
}

/** Meaningful download file name for a testing run PDF. */
export function formatTestingRunPdfFilename(
  programName: string,
  runId: string,
  createdAt?: string,
): string {
  const safeProgram = (programName || "program")
    .replace(/[^\w.-]+/g, "_")
    .replace(/_+/g, "_")
    .slice(0, 48);
  const shortId = (runId || "run").slice(0, 8);
  let stamp = "";
  if (createdAt) {
    const d = new Date(createdAt);
    if (!Number.isNaN(d.getTime())) {
      stamp = `-${d.toISOString().slice(0, 10)}`;
    }
  }
  return `${safeProgram}-testing-run-${shortId}${stamp}.pdf`;
}

/** Render report model to PDF bytes (browser). */
export async function renderTestingRunPdfBlob(model: TestingRunPdfReportModel): Promise<Blob> {
  const { jsPDF } = await import("jspdf");
  const autoTable = (await import("jspdf-autotable")).default;

  const doc = new jsPDF({ unit: "pt", format: "a4" });
  const reportTitle = "COBOL Modernization — Behavioral Testing Report";

  let y = await drawReportHeader(doc, {
    programName: model.program_name,
    reportTitle,
    runId: model.run_id,
    runTimestamp: model.created_at_display,
  });

  y = await renderTable(
    autoTable,
    doc,
    y,
    "Executive summary",
    ["Metric", "Value"],
    model.executive_rows,
    { styles: { fontSize: 10, cellPadding: 7 } },
  );

  y = await renderTable(autoTable, doc, y, "Run metadata", ["Field", "Value"], model.metadata_rows);

  y = await renderTable(
    autoTable,
    doc,
    y,
    "Reliability score breakdown",
    ["Component", "Points"],
    model.score_breakdown_rows,
  );

  y = await renderTable(
    autoTable,
    doc,
    y,
    "Layer diagnostics (compile / runtime / parity / retry / attribution)",
    ["Layer", "Score / status"],
    model.layer_rows,
  );

  y = await renderTable(
    autoTable,
    doc,
    y,
    "Behavioral diff summary",
    ["Measure", "Value"],
    model.diff_rows,
  );

  y = await renderTable(
    autoTable,
    doc,
    y,
    "Analysis summary",
    ["Attribute", "Detail"],
    model.analysis_rows,
  );

  y = await renderTable(
    autoTable,
    doc,
    y,
    "Generated tests (business rules / edge cases / unit tests)",
    ["Category", "Status", "Score contribution"],
    model.validation_rows,
  );

  y = drawDecisionBlock(
    doc,
    y,
    model.decision_label,
    model.save_eligible,
    model.reason_summary,
    model.blockers,
  );

  if (model.failure_reason) {
    y = await renderTable(
      autoTable,
      doc,
      y,
      "Failure reason",
      ["Detail", "Description"],
      [["Failure", model.failure_reason]],
    );
  }

  const generatedAt = formatTimestamp(new Date().toISOString());
  drawPageFooters(doc, {
    programName: model.program_name,
    runId: model.run_id,
    generatedAt,
    sourceNote: model.export_source_note,
  });

  return doc.output("blob");
}

/** Build PDF from run record and trigger browser download. */
export async function downloadTestingRunPdf(
  model: TestingRunPdfReportModel,
): Promise<void> {
  const blob = await renderTestingRunPdfBlob(model);
  const filename = formatTestingRunPdfFilename(
    model.program_name,
    model.run_id,
    model.created_at,
  );
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.rel = "noopener";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
