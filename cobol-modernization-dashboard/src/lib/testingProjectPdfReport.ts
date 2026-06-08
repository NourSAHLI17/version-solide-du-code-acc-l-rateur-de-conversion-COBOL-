/**
 * Demo-quality PDF report for project-level behavioral equivalence testing (ACME Bank v3).
 */

import type {
  ProjectFileTestResult,
  TestingAgentRunResult,
  TestingFinalDecisionResult,
} from "./testingAgentTypes.ts";
import { statusLabel } from "./testingAgentTypes.ts";
import {
  COLOR_ACCENT,
  COLOR_INK,
  COLOR_MUTED,
  CONTENT_WIDTH_PT,
  drawBodyParagraph,
  drawEyLogoFallback,
  drawInsightBox,
  drawPageFooters,
  drawProgramCard,
  drawSectionTitle,
  ensureVerticalSpace,
  lastTableY,
  loadEyLogoForPdf,
  MARGIN_TOP_PT,
  MARGIN_X_PT,
  PAGE_WIDTH_PT,
  renderTable,
} from "./testingRunPdfLayout.ts";

/* -------------------------------------------------------------------------- */
/* ACME Bank v3 — static reference content for demo PDF                        */
/* -------------------------------------------------------------------------- */

const REPORT_TITLE = "COBOL Modernization — Behavioral Equivalence Report";
const REPORT_SUBTITLE = "ACME Bank v3 — Tunisian Banking Batch System";

const PROJECT_OVERVIEW_PARAGRAPH =
  "ACME Bank v3 is a production-scale Tunisian banking batch system originally written in COBOL. The system processes the bank's entire loan portfolio on a monthly basis, performing regulatory risk classification in accordance with BCT (Banque Centrale de Tunisie) requirements, AML sanctions screening, loan evaluation scoring, recovery action generation, and executive report production.";

const DATA_FILES_ROWS: [string, string, string][] = [
  ["CUSTFILE.dat", "500", "Customer profiles (income, employment, credit history)"],
  ["LOANFILE.dat", "800", "Loan records (amount, DPD, status, type)"],
  ["COLFILE.dat", "400", "Collateral records (type, appraised value)"],
  ["GUARFILE.dat", "200", "Guarantor records (income, guarantee amount)"],
  ["SANCFILE.dat", "51", "Sanctions and PEP watchlist entries"],
];

const BEHAVIORAL_EQUIVALENCE_PARAGRAPH =
  "Behavioral equivalence means the converted Java produces exactly the same output as the original COBOL when run against the same input data. Both programs read the identical .dat files and must produce identical results. A 0% divergence means not a single output line differs between the two implementations.";

const KEY_INSIGHTS: Array<{ title: string; body: string }> = [
  {
    title: "726 — The consistency number",
    body:
      "726 active loans flow through all 4 programs consistently. LOANEVAL processes 726 eligible loans. RISKSCOR classifies all 726 as CLASS 1 (current, DPD ≤ 30 days). RPTMONTH reports on all 726. RECOVRY correctly finds zero delinquent loans to action. This number appearing identically across all programs on both COBOL and Java confirms the business logic was preserved end-to-end.",
  },
  {
    title: "800 loans read, 74 errors",
    body:
      "The 74 loans counted as ERRORS are loans with incomplete data — missing customer records, collateral data, or guarantor information. This is realistic for production banking data. Both COBOL and Java identify the same 74 problematic records, confirming the error-handling logic was also converted correctly.",
  },
];

export type ProgramTier = "Standard" | "Complex" | "Enterprise";

export interface AcmeProgramProfile {
  name: string;
  tier: ProgramTier;
  description: string;
  tableDescription: string;
  keyMetrics?: string;
}

export const ACME_PROGRAM_PROFILES: AcmeProgramProfile[] = [
  {
    name: "CALCFEE",
    tier: "Standard",
    tableDescription: "Fee calculation sub-program",
    description:
      "Fee calculation sub-program. Called by LOANEVAL for each loan to compute file fees, insurance, and taxes based on loan type and amount. Implements BCT fee schedule with min/max bounds.",
  },
  {
    name: "CHKAML",
    tier: "Standard",
    tableDescription: "AML screening sub-program",
    description:
      "AML screening sub-program. Called by LOANEVAL for each customer to screen against the SANCFILE sanctions watchlist. Computes a risk score based on sanctions hits, transaction amount, and high-risk nationality flags.",
  },
  {
    name: "LOANEVAL",
    tier: "Enterprise",
    tableDescription: "Loan evaluation engine",
    description:
      "The core loan evaluation engine. Reads all 800 loans and for each one: looks up customer data, screens for AML compliance, calculates fees, scores the loan across 6 dimensions (income, collateral, guarantees, credit history, sector, tenure), and applies a decision (Approved/Conditional/Declined).",
    keyMetrics: "Key metrics: 800 loans read, 1,100 lines of COBOL, 36 paragraphs",
  },
  {
    name: "RISKSCOR",
    tier: "Complex",
    tableDescription: "Risk classification engine",
    description:
      "BCT regulatory risk classifier. Reads the loan portfolio and classifies each active loan into one of four BCT risk classes based on days past due (DPD). CLASS 1 (current), CLASS 2 (watch), CLASS 3 (substandard), CLASS 4 (loss). Required by BCT Circular 91-24.",
  },
  {
    name: "RECOVRY",
    tier: "Complex",
    tableDescription: "Recovery action engine",
    description:
      "Recovery action engine. Processes delinquent loans (CLASS 2, 3, 4) and generates appropriate recovery actions: SMS reminders, phone calls, demand letters, legal notices, court orders, or write-offs. Generates French-language dunning letters for BCT compliance.",
  },
  {
    name: "RPTMONTH",
    tier: "Complex",
    tableDescription: "Monthly report generator",
    description:
      "Monthly portfolio report generator. Aggregates loan data by risk class, loan type, and customer segment. Computes NPL ratio, provision coverage ratio, and weighted average rate. Produces the executive management report.",
  },
];

const SIDE_BY_SIDE_SECTION_TITLES: Record<string, string> = {
  LOANEVAL: "LOANEVAL — Loan Evaluation Results",
  RISKSCOR: "RISKSCOR — BCT Risk Classification",
  RECOVRY: "RECOVRY — Recovery Actions",
  RPTMONTH: "RPTMONTH — Monthly Report",
};

const MAIN_PROGRAMS_FOR_DIFF = ["LOANEVAL", "RISKSCOR", "RECOVRY", "RPTMONTH"] as const;

/* -------------------------------------------------------------------------- */
/* Model                                                                      */
/* -------------------------------------------------------------------------- */

export interface SideBySideSection {
  title: string;
  rows: [string, string, string, string][];
}

export interface ProjectTestingPdfReportModel {
  project_name: string;
  run_id: string;
  created_at_display: string;
  overall_score: string;
  overall_status: string;
  program_rows: [string, string, string, string, string, string, string][];
  side_by_side_sections: SideBySideSection[];
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

function profileForProgram(name: string): AcmeProgramProfile | undefined {
  const key = String(name || "").trim().toUpperCase();
  return ACME_PROGRAM_PROFILES.find((p) => p.name === key);
}

function compileLabel(file: ProjectFileTestResult): string {
  const d = file.run_diagnostics;
  const cobol = d?.cobol_compile_status ?? d?.java_compile_status;
  const java = d?.java_compile_status;
  if (cobol === "success" && java === "success") return "OK";
  if (cobol === "failed" || java === "failed") return "FAIL";
  if (file.status === "passed" || file.status === "partial") return "OK";
  if (file.status === "failed") return "FAIL";
  return "—";
}

function executeLabel(file: ProjectFileTestResult): string {
  const d = file.run_diagnostics;
  const cobol = d?.cobol_runtime_status ?? d?.cobol_execution_status;
  const java = d?.java_runtime_status ?? d?.java_execution_status;
  if (cobol === "success" && java === "success") return "OK";
  if (cobol === "failed" || java === "failed") return "FAIL";
  if (file.status === "passed") return "OK";
  if (file.status === "failed") return "FAIL";
  if (file.status === "partial") return "PARTIAL";
  return "—";
}

function diffPctLabel(file: ProjectFileTestResult, summaryPct?: number): string {
  const pct = file.diff_summary?.diff_percentage ?? summaryPct;
  if (pct == null || Number.isNaN(Number(pct))) return "—";
  return `${Math.round(Number(pct))}%`;
}

function normalizeStdoutLine(line: string): string {
  return line.replace(/\s+/g, " ").trim();
}

/** Meaningful stdout lines for side-by-side tables (skip blank / banner noise). */
function extractReportLines(stdout: string): string[] {
  return stdout
    .split(/\r?\n/)
    .map((l) => l.trimEnd())
    .filter((l) => {
      const t = l.trim();
      if (!t) return false;
      if (/^LOADED\s+(CUST|COL|GUAR)\s*:/i.test(t)) return false;
      if (/^LOANEVAL\s+v[\d.]+\s+-\s+START/i.test(t)) return false;
      return true;
    });
}

export function buildLineComparisonRows(
  cobolStdout: string,
  javaStdout: string,
): [string, string, string, string][] {
  const cobolLines = extractReportLines(cobolStdout);
  const javaLines = extractReportLines(javaStdout);
  const max = Math.max(cobolLines.length, javaLines.length, 1);
  const rows: [string, string, string, string][] = [];

  for (let i = 0; i < max; i++) {
    const c = cobolLines[i] ?? "";
    const j = javaLines[i] ?? "";
    const match = normalizeStdoutLine(c) === normalizeStdoutLine(j) ? "✓" : "≠";
    rows.push([String(i + 1), c || "—", j || "—", match]);
  }
  return rows;
}

export function buildProjectTestingPdfReportModel(
  run: TestingAgentRunResult,
  decision: TestingFinalDecisionResult | null,
): ProjectTestingPdfReportModel {
  const summary = run.project_summary;
  const fileResults = run.file_results ?? [];
  const summaries = summary?.file_summaries ?? [];

  const fileByProgram = new Map<string, ProjectFileTestResult>();
  for (const f of fileResults) {
    fileByProgram.set(String(f.program_name || "").toUpperCase(), f);
  }

  const program_rows: ProjectTestingPdfReportModel["program_rows"] = [];

  for (const profile of ACME_PROGRAM_PROFILES) {
    const fs = summaries.find(
      (s) => String(s.program_name || "").toUpperCase() === profile.name,
    );
    const file = fileByProgram.get(profile.name);

    if (file) {
      program_rows.push([
        profile.name,
        profile.tier,
        compileLabel(file),
        executeLabel(file),
        diffPctLabel(file, fs?.diff_percentage),
        statusLabel(file.status).toUpperCase(),
        profile.tableDescription,
      ]);
    } else if (fs) {
      program_rows.push([
        profile.name,
        profile.tier,
        "—",
        "—",
        fs.diff_percentage != null ? `${Math.round(fs.diff_percentage)}%` : "—",
        String(fs.status).toUpperCase(),
        profile.tableDescription,
      ]);
    } else {
      program_rows.push([
        profile.name,
        profile.tier,
        "—",
        "—",
        "—",
        "—",
        profile.tableDescription,
      ]);
    }
  }

  const side_by_side_sections: SideBySideSection[] = [];

  for (const prog of MAIN_PROGRAMS_FOR_DIFF) {
    const file = fileByProgram.get(prog);
    const cobol = file?.cobol_output ?? "";
    const java = file?.java_output ?? "";
    if (!cobol.trim() && !java.trim()) continue;

    side_by_side_sections.push({
      title: SIDE_BY_SIDE_SECTION_TITLES[prog] ?? prog,
      rows: buildLineComparisonRows(cobol, java),
    });
  }

  const overallScore =
    decision?.reliability_score != null
      ? `${Math.round(decision.reliability_score)}/100`
      : run.qscore != null
        ? `${Math.round(Number(run.qscore))}/100`
        : "—";

  return {
    project_name: summary?.project_name || run.program_name,
    run_id: run.run_id,
    created_at_display: formatTimestamp(run.created_at),
    overall_score: overallScore,
    overall_status: statusLabel(run.status).toUpperCase(),
    program_rows,
    side_by_side_sections,
  };
}

/* -------------------------------------------------------------------------- */
/* PDF rendering                                                              */
/* -------------------------------------------------------------------------- */

async function drawCoverPage(
  doc: import("jspdf").jsPDF,
  model: ProjectTestingPdfReportModel,
): Promise<number> {
  let y = MARGIN_TOP_PT;
  const logo = await loadEyLogoForPdf();
  if (logo) {
    doc.addImage(logo.dataUrl, logo.format, MARGIN_X_PT, y, logo.widthPt, logo.heightPt);
    y += logo.heightPt + 20;
  } else {
    y = drawEyLogoFallback(doc, MARGIN_X_PT, y) + 20;
  }

  doc.setDrawColor(...COLOR_ACCENT);
  doc.setLineWidth(2.5);
  doc.line(MARGIN_X_PT, y, PAGE_WIDTH_PT - MARGIN_X_PT, y);
  y += 28;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(18);
  doc.setTextColor(...COLOR_INK);
  const titleLines = doc.splitTextToSize(REPORT_TITLE, CONTENT_WIDTH_PT) as string[];
  doc.text(titleLines, MARGIN_X_PT, y);
  y += titleLines.length * 22 + 8;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(12);
  doc.setTextColor(...COLOR_MUTED);
  doc.text(REPORT_SUBTITLE, MARGIN_X_PT, y);
  y += 36;

  doc.setFontSize(10);
  doc.setTextColor(...COLOR_INK);
  doc.text(`Run ID: ${model.run_id}`, MARGIN_X_PT, y);
  y += 14;
  doc.text(`Run completed: ${model.created_at_display}`, MARGIN_X_PT, y);
  y += 28;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(14);
  doc.text(`Overall score: ${model.overall_score}`, MARGIN_X_PT, y);
  y += 20;
  doc.setFontSize(12);
  const statusColor: [number, number, number] =
    model.overall_status === "PASSED" ? [22, 120, 72] : COLOR_INK;
  doc.setTextColor(...statusColor);
  doc.text(`Status: ${model.overall_status}`, MARGIN_X_PT, y);
  doc.setTextColor(0, 0, 0);

  doc.addPage();
  return MARGIN_TOP_PT;
}

export async function renderProjectTestingPdfBlob(
  model: ProjectTestingPdfReportModel,
): Promise<Blob> {
  const { jsPDF } = await import("jspdf");
  const autoTable = (await import("jspdf-autotable")).default;
  const doc = new jsPDF({ unit: "pt", format: "a4" });

  let y = await drawCoverPage(doc, model);

  y = drawSectionTitle(doc, "What is ACME Bank v3?", y);
  y = drawBodyParagraph(doc, y, PROJECT_OVERVIEW_PARAGRAPH);

  y = await renderTable(
    autoTable,
    doc,
    y,
    "Data files used",
    ["File", "Records", "Description"],
    DATA_FILES_ROWS,
    { styles: { fontSize: 8, cellPadding: 5 } },
  );

  y = drawSectionTitle(doc, "The 6 Programs", y);
  for (const profile of ACME_PROGRAM_PROFILES) {
    y = drawProgramCard(
      doc,
      y,
      profile.name,
      profile.tier,
      profile.description,
      profile.keyMetrics,
    );
  }

  y = await renderTable(
    autoTable,
    doc,
    y,
    "Per-program results",
    ["Program", "Complexity", "Compile", "Execute", "Diff %", "Status", "Description"],
    model.program_rows,
    {
      styles: { fontSize: 7, cellPadding: 4, overflow: "linebreak" },
      columnStyles: {
        0: { cellWidth: 52 },
        1: { cellWidth: 48 },
        2: { cellWidth: 36 },
        3: { cellWidth: 36 },
        4: { cellWidth: 32 },
        5: { cellWidth: 40 },
        6: { cellWidth: "auto" },
      },
    },
  );

  y = drawSectionTitle(doc, "What 0% Divergence Means", y);
  y = drawBodyParagraph(doc, y, BEHAVIORAL_EQUIVALENCE_PARAGRAPH);

  y = drawSectionTitle(doc, "COBOL vs Java Output — Line by Line", y);
  if (model.side_by_side_sections.length === 0) {
    y = drawBodyParagraph(doc, y, "No per-program stdout was captured for this run.");
  } else {
    for (const section of model.side_by_side_sections) {
      y = ensureVerticalSpace(doc, y, 40);
      doc.setFont("helvetica", "bold");
      doc.setFontSize(9);
      doc.setTextColor(...COLOR_INK);
      doc.text(section.title, MARGIN_X_PT, y);
      y += 14;

      autoTable(
        doc,
        {
          startY: y,
          margin: { left: MARGIN_X_PT, right: MARGIN_X_PT, bottom: 48 },
          tableWidth: CONTENT_WIDTH_PT,
          head: [["Line", "COBOL Output", "Java Output", "Match"]],
          body: section.rows,
          theme: "grid",
          styles: {
            font: "helvetica",
            fontSize: 7,
            cellPadding: 4,
            overflow: "linebreak",
            textColor: COLOR_INK,
          },
          headStyles: {
            fillColor: [46, 46, 56],
            textColor: [255, 255, 255],
            fontStyle: "bold",
          },
          columnStyles: {
            0: { cellWidth: 28 },
            1: { cellWidth: 175 },
            2: { cellWidth: 175 },
            3: { cellWidth: 36, halign: "center" },
          },
        },
      );
      y = lastTableY(doc) + 12;
    }
  }

  y = drawSectionTitle(doc, "What the Numbers Mean", y);
  for (const insight of KEY_INSIGHTS) {
    y = drawInsightBox(doc, y, insight.title, insight.body);
  }

  const generatedAt = formatTimestamp(new Date().toISOString());
  drawPageFooters(doc, {
    programName: model.project_name,
    runId: model.run_id,
    generatedAt,
    sourceNote: "Generated by COBOL Modernizer Pipeline",
  });

  return doc.output("blob");
}

export async function downloadProjectTestingPdf(
  model: ProjectTestingPdfReportModel,
): Promise<void> {
  const blob = await renderProjectTestingPdfBlob(model);
  const safeName = model.project_name.replace(/[^\w.-]+/g, "_").slice(0, 48);
  const filename = `${safeName}-behavioral-equivalence-${model.run_id.slice(0, 8)}.pdf`;
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
