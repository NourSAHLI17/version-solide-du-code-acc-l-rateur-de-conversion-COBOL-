/** Normalized compile-and-repair summary for the dashboard. */

export interface ManualReviewItem {
  line: number;
  message: string;
}

export interface RepairSummary {
  autoRepairs: string[];
  manualReview: ManualReviewItem[];
}

export function normalizeRepairSummary(raw: unknown): RepairSummary | null {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const autoRaw = obj.auto_repairs ?? obj.autoRepairs;
  const manualRaw = obj.manual_review ?? obj.manualReview;

  const autoRepairs = Array.isArray(autoRaw)
    ? autoRaw.filter((x): x is string => typeof x === "string" && x.trim().length > 0)
    : [];

  const manualReview: ManualReviewItem[] = [];
  if (Array.isArray(manualRaw)) {
    for (const item of manualRaw) {
      if (!item || typeof item !== "object") continue;
      const row = item as Record<string, unknown>;
      const line = typeof row.line === "number" ? row.line : Number(row.line);
      const message = typeof row.message === "string" ? row.message : "";
      if (Number.isFinite(line) && line > 0 && message) {
        manualReview.push({ line, message });
      }
    }
  }

  if (!autoRepairs.length && !manualReview.length) return null;
  return { autoRepairs, manualReview };
}

/** Map dashboard pipeline stage status to API conversion_status. */
export function pipelineToConversionStatus(
  status?: string,
): "complete" | "partial" | "failed" | undefined {
  if (status === "done") return "complete";
  if (status === "partial") return "partial";
  if (status === "error") return "failed";
  if (status === "complete") return "complete";
  return undefined;
}

export function formatJavaStageLabel(
  conversionStatus?: "complete" | "partial" | "failed",
): string {
  if (conversionStatus === "partial") return "Partial";
  if (conversionStatus === "complete") return "Done";
  if (conversionStatus === "failed") return "Failed";
  return "Done";
}
