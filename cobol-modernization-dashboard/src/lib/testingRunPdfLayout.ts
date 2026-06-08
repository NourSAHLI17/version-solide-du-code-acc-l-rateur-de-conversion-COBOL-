/**
 * Consulting-style PDF layout helpers (EY-branded testing report).
 */

import type { jsPDF } from "jspdf";
import type { UserOptions } from "jspdf-autotable";

/** EY charcoal */
export const COLOR_INK: [number, number, number] = [46, 46, 56];
/** Muted label text */
export const COLOR_MUTED: [number, number, number] = [116, 116, 128];
/** EY yellow accent */
export const COLOR_ACCENT: [number, number, number] = [255, 230, 0];
/** Table header background */
export const COLOR_HEADER_BG: [number, number, number] = [46, 46, 56];
/** Zebra stripe */
export const COLOR_ROW_ALT: [number, number, number] = [246, 246, 250];

export const PAGE_WIDTH_PT = 595.28;
export const PAGE_HEIGHT_PT = 841.89;
export const MARGIN_X_PT = 48;
export const MARGIN_TOP_PT = 48;
export const FOOTER_RESERVE_PT = 48;
export const CONTENT_WIDTH_PT = PAGE_WIDTH_PT - MARGIN_X_PT * 2;

/** Primary EY logo (user-provided); served from public/brand. */
export const EY_LOGO_JPEG_PATH = "/brand/ey_logo_icon_171166.jpg";
const EY_LOGO_SVG_FALLBACK_PATH = "/brand/ey-logo.svg";

const LOGO_MAX_WIDTH_PT = 88;
const LOGO_MAX_HEIGHT_PT = 36;
const LOGO_FALLBACK_WIDTH_PT = 72;
const LOGO_FALLBACK_HEIGHT_PT = 29;

export type EyLogoPdfAsset = {
  dataUrl: string;
  format: "JPEG" | "PNG";
  widthPt: number;
  heightPt: number;
};

let cachedLogo: EyLogoPdfAsset | null | undefined;

export type AutoTableModule = typeof import("jspdf-autotable");

function fitLogoDimensions(
  naturalW: number,
  naturalH: number,
  maxW: number,
  maxH: number,
): { widthPt: number; heightPt: number } {
  if (naturalW <= 0 || naturalH <= 0) {
    return { widthPt: maxW, heightPt: maxH };
  }
  const scale = Math.min(maxW / naturalW, maxH / naturalH, 1);
  return { widthPt: naturalW * scale, heightPt: naturalH * scale };
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("read failed"));
    reader.readAsDataURL(blob);
  });
}

function loadImageElement(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("image load failed"));
    img.src = src;
  });
}

async function tryLoadEyLogoJpeg(): Promise<EyLogoPdfAsset | null> {
  const res = await fetch(EY_LOGO_JPEG_PATH);
  if (!res.ok) return null;
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  try {
    const img = await loadImageElement(objectUrl);
    const { widthPt, heightPt } = fitLogoDimensions(
      img.naturalWidth,
      img.naturalHeight,
      LOGO_MAX_WIDTH_PT,
      LOGO_MAX_HEIGHT_PT,
    );
    const dataUrl = await blobToDataUrl(blob);
    const format: EyLogoPdfAsset["format"] =
      blob.type.includes("png") ? "PNG" : "JPEG";
    return { dataUrl, format, widthPt, heightPt };
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

async function tryLoadEyLogoSvg(): Promise<EyLogoPdfAsset | null> {
  const res = await fetch(EY_LOGO_SVG_FALLBACK_PATH);
  if (!res.ok) return null;
  const svgText = await res.text();
  const blob = new Blob([svgText], { type: "image/svg+xml;charset=utf-8" });
  const objectUrl = URL.createObjectURL(blob);
  try {
    const img = await loadImageElement(objectUrl);
    const scale = 3;
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(LOGO_FALLBACK_WIDTH_PT * scale);
    canvas.height = Math.round(LOGO_FALLBACK_HEIGHT_PT * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.scale(scale, scale);
    ctx.drawImage(img, 0, 0, LOGO_FALLBACK_WIDTH_PT, LOGO_FALLBACK_HEIGHT_PT);
    return {
      dataUrl: canvas.toDataURL("image/png"),
      format: "PNG",
      widthPt: LOGO_FALLBACK_WIDTH_PT,
      heightPt: LOGO_FALLBACK_HEIGHT_PT,
    };
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

/** Load EY logo for PDF header (JPEG preferred, SVG then text fallback). */
export async function loadEyLogoForPdf(): Promise<EyLogoPdfAsset | null> {
  if (cachedLogo !== undefined) {
    return cachedLogo;
  }
  if (typeof document === "undefined" || typeof fetch === "undefined") {
    cachedLogo = null;
    return null;
  }
  try {
    cachedLogo = (await tryLoadEyLogoJpeg()) ?? (await tryLoadEyLogoSvg());
  } catch {
    cachedLogo = null;
  }
  return cachedLogo;
}

/** @deprecated Use loadEyLogoForPdf — returns data URL only when logo loaded. */
export async function loadEyLogoDataUrl(): Promise<string | null> {
  const logo = await loadEyLogoForPdf();
  return logo?.dataUrl ?? null;
}

export function drawEyLogoFallback(doc: jsPDF, x: number, y: number): number {
  doc.setFont("helvetica", "bold");
  doc.setFontSize(22);
  doc.setTextColor(...COLOR_INK);
  doc.text("EY", x, y + 18);
  doc.setFillColor(...COLOR_ACCENT);
  doc.rect(x, y + 22, 36, 3, "F");
  doc.setTextColor(0, 0, 0);
  return y + LOGO_FALLBACK_HEIGHT_PT;
}

export async function drawReportHeader(
  doc: jsPDF,
  opts: {
    programName: string;
    reportTitle: string;
    runId: string;
    runTimestamp: string;
  },
): Promise<number> {
  let y = MARGIN_TOP_PT;
  const logo = await loadEyLogoForPdf();
  if (logo) {
    doc.addImage(logo.dataUrl, logo.format, MARGIN_X_PT, y, logo.widthPt, logo.heightPt);
    y += logo.heightPt + 14;
  } else {
    y = drawEyLogoFallback(doc, MARGIN_X_PT, y) + 14;
  }

  doc.setDrawColor(...COLOR_ACCENT);
  doc.setLineWidth(2);
  doc.line(MARGIN_X_PT, y, PAGE_WIDTH_PT - MARGIN_X_PT, y);
  y += 18;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(16);
  doc.setTextColor(...COLOR_INK);
  doc.text(opts.reportTitle, MARGIN_X_PT, y);
  y += 20;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(11);
  doc.setTextColor(...COLOR_INK);
  doc.text(opts.programName, MARGIN_X_PT, y);
  y += 14;

  doc.setFontSize(9);
  doc.setTextColor(...COLOR_MUTED);
  doc.text(`Run ID: ${opts.runId}`, MARGIN_X_PT, y);
  y += 12;
  doc.text(`Run completed: ${opts.runTimestamp}`, MARGIN_X_PT, y);
  y += 20;

  doc.setTextColor(0, 0, 0);
  return y;
}

export function baseTableOptions(
  startY: number,
  head: string[],
  body: string[][],
  overrides?: Partial<UserOptions>,
): UserOptions {
  const colCount = head.length;
  const columnStyles: Record<number, { cellWidth: number | "auto"; fontStyle?: string }> = {};
  if (colCount === 2) {
    columnStyles[0] = { cellWidth: 155, fontStyle: "bold" };
    columnStyles[1] = { cellWidth: "auto" };
  } else if (colCount === 3) {
    columnStyles[0] = { cellWidth: 140, fontStyle: "bold" };
    columnStyles[1] = { cellWidth: 100 };
    columnStyles[2] = { cellWidth: "auto" };
  }

  return {
    startY,
    margin: { left: MARGIN_X_PT, right: MARGIN_X_PT, bottom: FOOTER_RESERVE_PT },
    tableWidth: CONTENT_WIDTH_PT,
    head: [head],
    body,
    theme: "grid",
    styles: {
      font: "helvetica",
      fontSize: 9,
      cellPadding: 6,
      lineColor: [220, 220, 228] as [number, number, number],
      lineWidth: 0.5,
      textColor: COLOR_INK,
      overflow: "linebreak",
    },
    headStyles: {
      fillColor: COLOR_HEADER_BG,
      textColor: [255, 255, 255] as [number, number, number],
      fontStyle: "bold",
      halign: "left",
    },
    alternateRowStyles: {
      fillColor: COLOR_ROW_ALT,
    },
    columnStyles,
    ...overrides,
  };
}

export function ensureVerticalSpace(doc: jsPDF, y: number, needed: number): number {
  const pageBottom = PAGE_HEIGHT_PT - FOOTER_RESERVE_PT;
  if (y + needed > pageBottom) {
    doc.addPage();
    return MARGIN_TOP_PT;
  }
  return y;
}

export function drawBodyParagraph(
  doc: jsPDF,
  y: number,
  text: string,
  opts?: { fontSize?: number; lineHeight?: number },
): number {
  const fontSize = opts?.fontSize ?? 9;
  const lineHeight = opts?.lineHeight ?? 12;
  const lines = doc.splitTextToSize(text, CONTENT_WIDTH_PT) as string[];
  const blockH = lines.length * lineHeight + 8;
  y = ensureVerticalSpace(doc, y, blockH);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(fontSize);
  doc.setTextColor(...COLOR_INK);
  doc.text(lines, MARGIN_X_PT, y);
  doc.setTextColor(0, 0, 0);
  return y + lines.length * lineHeight + 10;
}

export function drawInsightBox(
  doc: jsPDF,
  y: number,
  title: string,
  body: string,
): number {
  const pad = 12;
  const innerW = CONTENT_WIDTH_PT - pad * 2;
  const bodyLines = doc.splitTextToSize(body, innerW) as string[];
  const boxH = 28 + bodyLines.length * 11;
  y = ensureVerticalSpace(doc, y, boxH + 8);

  doc.setFillColor(252, 252, 248);
  doc.setDrawColor(220, 220, 228);
  doc.roundedRect(MARGIN_X_PT, y, CONTENT_WIDTH_PT, boxH, 3, 3, "FD");

  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.setTextColor(...COLOR_INK);
  doc.text(title, MARGIN_X_PT + pad, y + 16);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(8.5);
  doc.setTextColor(...COLOR_MUTED);
  doc.text(bodyLines, MARGIN_X_PT + pad, y + 30);
  doc.setTextColor(0, 0, 0);
  return y + boxH + 14;
}

export function drawProgramCard(
  doc: jsPDF,
  y: number,
  programName: string,
  tier: string,
  description: string,
  keyMetrics?: string,
): number {
  const pad = 12;
  const innerW = CONTENT_WIDTH_PT - pad * 2;
  const descLines = doc.splitTextToSize(description, innerW) as string[];
  const metricsLines = keyMetrics
    ? (doc.splitTextToSize(keyMetrics, innerW) as string[])
    : [];
  const boxH = 36 + descLines.length * 11 + metricsLines.length * 10;
  y = ensureVerticalSpace(doc, y, boxH + 6);

  doc.setFillColor(252, 252, 255);
  doc.setDrawColor(...COLOR_ACCENT);
  doc.setLineWidth(1);
  doc.roundedRect(MARGIN_X_PT, y, CONTENT_WIDTH_PT, boxH, 2, 2, "FD");

  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.setTextColor(...COLOR_INK);
  doc.text(`${programName} (${tier})`, MARGIN_X_PT + pad, y + 16);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(8.5);
  doc.setTextColor(...COLOR_INK);
  let by = y + 30;
  doc.text(descLines, MARGIN_X_PT + pad, by);
  by += descLines.length * 11;

  if (metricsLines.length > 0) {
    doc.setFont("helvetica", "italic");
    doc.setTextColor(...COLOR_MUTED);
    doc.text(metricsLines, MARGIN_X_PT + pad, by);
  }

  doc.setTextColor(0, 0, 0);
  return y + boxH + 10;
}

export function drawSectionTitle(doc: jsPDF, title: string, y: number): number {
  const pageBottom = PAGE_HEIGHT_PT - FOOTER_RESERVE_PT;
  if (y + 36 > pageBottom) {
    doc.addPage();
    y = MARGIN_TOP_PT;
  }
  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  doc.setTextColor(...COLOR_INK);
  doc.text(title, MARGIN_X_PT, y);
  doc.setDrawColor(...COLOR_MUTED);
  doc.setLineWidth(0.5);
  doc.line(MARGIN_X_PT, y + 4, MARGIN_X_PT + CONTENT_WIDTH_PT, y + 4);
  doc.setTextColor(0, 0, 0);
  return y + 16;
}

export function lastTableY(doc: jsPDF): number {
  const t = doc as jsPDF & { lastAutoTable?: { finalY: number } };
  return t.lastAutoTable?.finalY ?? MARGIN_TOP_PT;
}

export async function renderTable(
  autoTable: AutoTableModule["default"],
  doc: jsPDF,
  startY: number,
  sectionTitle: string,
  head: string[],
  body: string[][],
  overrides?: Partial<UserOptions>,
): Promise<number> {
  let y = drawSectionTitle(doc, sectionTitle, startY);
  if (body.length === 0) {
    body = [["—", "No data recorded"]];
  }
  autoTable(doc, baseTableOptions(y, head, body, overrides));
  return lastTableY(doc) + 14;
}

export function drawDecisionBlock(
  doc: jsPDF,
  y: number,
  decision: string,
  saveEligible: string,
  reason: string,
  blockers: string[],
): number {
  const pageBottom = PAGE_HEIGHT_PT - FOOTER_RESERVE_PT;
  if (y + 80 > pageBottom) {
    doc.addPage();
    y = MARGIN_TOP_PT;
  }
  y = drawSectionTitle(doc, "Final decision", y);

  const pad = 12;
  const innerW = CONTENT_WIDTH_PT - pad * 2;
  const reasonLines = doc.splitTextToSize(reason || "—", innerW) as string[];
  let blockersH = 0;
  const blockerLineGroups: string[][] = [];
  if (blockers.length > 0) {
    blockersH = 14;
    for (const b of blockers) {
      const bl = doc.splitTextToSize(`• ${b}`, innerW - 8) as string[];
      blockerLineGroups.push(bl);
      blockersH += bl.length * 11;
    }
  }
  const boxH = 52 + reasonLines.length * 11 + blockersH;

  doc.setFillColor(248, 248, 252);
  doc.setDrawColor(220, 220, 228);
  doc.roundedRect(MARGIN_X_PT, y, CONTENT_WIDTH_PT, boxH, 3, 3, "FD");

  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  doc.setTextColor(...COLOR_INK);
  doc.text(decision, MARGIN_X_PT + pad, y + 18);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(...COLOR_MUTED);
  doc.text(`Save eligible: ${saveEligible}`, MARGIN_X_PT + pad, y + 32);

  let by = y + 46;
  doc.text(reasonLines, MARGIN_X_PT + pad, by);
  by += reasonLines.length * 11;

  if (blockers.length > 0) {
    doc.setFont("helvetica", "bold");
    doc.setTextColor(...COLOR_INK);
    doc.text("Blockers:", MARGIN_X_PT + pad, by + 4);
    by += 14;
    doc.setFont("helvetica", "normal");
    for (const bl of blockerLineGroups) {
      doc.text(bl, MARGIN_X_PT + pad + 4, by);
      by += bl.length * 11;
    }
  }

  doc.setTextColor(0, 0, 0);
  return y + boxH + 16;
}

export function drawPageFooters(
  doc: jsPDF,
  opts: {
    programName: string;
    runId: string;
    generatedAt: string;
    sourceNote: string;
  },
): void {
  const pageCount = doc.getNumberOfPages();
  for (let p = 1; p <= pageCount; p++) {
    doc.setPage(p);
    const footerY = PAGE_HEIGHT_PT - 28;
    doc.setDrawColor(...COLOR_ACCENT);
    doc.setLineWidth(1);
    doc.line(MARGIN_X_PT, footerY - 10, PAGE_WIDTH_PT - MARGIN_X_PT, footerY - 10);
    doc.setFontSize(7);
    doc.setTextColor(...COLOR_MUTED);
    doc.text(
      `Generated ${opts.generatedAt} · ${opts.programName} · Run ${opts.runId.slice(0, 8)}… · Page ${p} of ${pageCount}`,
      MARGIN_X_PT,
      footerY,
    );
    doc.text(opts.sourceNote, MARGIN_X_PT, footerY + 10, {
      maxWidth: CONTENT_WIDTH_PT,
    });
    doc.setTextColor(0, 0, 0);
  }
}
