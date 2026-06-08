/**
 * Normalizes backend `conversion_score` payloads into a stable UI shape.
 * Backend uses snake_case; prompt examples may use camelCase — both are accepted.
 *
 * 4-category scoring model:
 *   PARSE     (20 pts) — parser success / warnings / failure
 *   ANALYZE   (20 pts) — LLM vs deterministic, rule count
 *   CONVERT   (20 pts) — Java produced, compiles, references resolve
 *   SEMANTIC  (40 pts) — business rule coverage, structural fidelity
 */

export type ConversionDecision =
  | "auto_approve"
  | "manual_review_recommended"
  | "reconversion_required"
  | "manual_review"
  | string;

export interface ParagraphBreakdownRow {
  paragraph: string;
  structureScore: number;
  rulesScore: number;
  total: number;
  notes: string;
}

export interface CategoryScore {
  score: number;
  max: number;
  notes: string[];
}

export interface AnalysisMode {
  engine: string;
  isDeterministicFallback: boolean;
  fallbackReason: string | null;
  scoreCapped: boolean;
}

export interface SemanticDetail {
  structuralFidelity: number;
  businessRuleCoverage: number;
  codeCompleteness: number;
  integrationReadiness: number;
  rulesTotal: number;
  rulesMatched: number;
}

export interface NormalizedConversionScore {
  programName: string;
  total: number;
  structural: number;
  structuralMax: number;
  businessRules: number;
  businessRulesMax: number;
  decision: ConversionDecision;
  summary: string;
  breakdown: ParagraphBreakdownRow[];
  /** 4-category score breakdown (new model) */
  categoryScores: {
    parse: CategoryScore;
    analyze: CategoryScore;
    convert: CategoryScore;
    semantic: CategoryScore;
  } | null;
  semanticDetail: SemanticDetail | null;
  analysisMode: AnalysisMode | null;
}

/** @alias NormalizedConversionScore — used across workspace types */
export type ConversionScoreModel = NormalizedConversionScore;

function num(v: unknown, fallback = 0): number {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function str(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}

function strArr(v: unknown): string[] {
  if (Array.isArray(v)) return v.map((x) => String(x));
  return [];
}

function parseCategoryScore(raw: unknown): CategoryScore | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  return {
    score: num(r.score),
    max: num(r.max),
    notes: strArr(r.notes),
  };
}

function parseAnalysisMode(raw: unknown): AnalysisMode | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  const isDet = Boolean(r.is_deterministic_fallback ?? r.isDeterministicFallback);
  if (!isDet && !r.engine) return null;
  return {
    engine: str(r.engine, "unknown"),
    isDeterministicFallback: isDet,
    fallbackReason: r.fallback_reason != null
      ? String(r.fallback_reason ?? r.fallbackReason)
      : (r.fallbackReason != null ? String(r.fallbackReason) : null),
    scoreCapped: Boolean(r.score_capped ?? r.scoreCapped),
  };
}

function parseSemanticDetail(raw: unknown): SemanticDetail | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  return {
    structuralFidelity: num(r.structural_fidelity ?? r.structuralFidelity),
    businessRuleCoverage: num(r.business_rule_coverage ?? r.businessRuleCoverage),
    codeCompleteness: num(r.code_completeness ?? r.codeCompleteness),
    integrationReadiness: num(r.integration_readiness ?? r.integrationReadiness),
    rulesTotal: num(r.rules_total ?? r.rulesTotal),
    rulesMatched: num(r.rules_matched ?? r.rulesMatched),
  };
}

export function normalizeConversionScore(raw: unknown): NormalizedConversionScore | null {
  if (raw == null) return null;
  let obj: Record<string, unknown> | null = null;
  if (typeof raw === "object" && !Array.isArray(raw)) {
    obj = raw as Record<string, unknown>;
  } else if (typeof raw === "string") {
    try {
      const parsed = JSON.parse(raw) as unknown;
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) obj = parsed as Record<string, unknown>;
    } catch {
      return null;
    }
  }
  if (!obj) return null;

  const nested = obj.score;
  if (nested && typeof nested === "object" && !Array.isArray(nested)) {
    obj = { ...obj, ...(nested as Record<string, unknown>) };
  }

  const breakdownRaw = (obj.paragraph_breakdown ?? obj.breakdown) as unknown;
  const breakdown: ParagraphBreakdownRow[] = [];
  if (Array.isArray(breakdownRaw)) {
    for (const row of breakdownRaw) {
      if (!row || typeof row !== "object") continue;
      const r = row as Record<string, unknown>;
      breakdown.push({
        paragraph: str(r.paragraph, "—"),
        structureScore: num(r.structure_score ?? r.structureScore),
        rulesScore: num(r.rules_score ?? r.rulesScore),
        total: num(r.total),
        notes: str(r.notes, ""),
      });
    }
  }

  const hasTotal = obj.total_score != null || obj.total != null;
  const hasParts =
    obj.structural_score != null ||
    obj.business_rules_score != null ||
    breakdown.length > 0 ||
    obj.decision != null ||
    obj.summary != null;
  if (!hasTotal && !hasParts) return null;

  // Parse 4-category scores
  const catRaw = (obj.category_scores ?? obj.categoryScores) as Record<string, unknown> | null;
  let categoryScores: NormalizedConversionScore["categoryScores"] = null;
  if (catRaw && typeof catRaw === "object") {
    const parse = parseCategoryScore(catRaw.parse);
    const analyze = parseCategoryScore(catRaw.analyze);
    const convert = parseCategoryScore(catRaw.convert);
    const semantic = parseCategoryScore(catRaw.semantic);
    if (parse && analyze && convert && semantic) {
      categoryScores = { parse, analyze, convert, semantic };
    }
  }

  const semanticDetail = parseSemanticDetail(obj.semantic_detail ?? obj.semanticDetail);
  const analysisMode = parseAnalysisMode(obj.analysis_mode ?? obj.analysisMode);

  return {
    programName: str(obj.program_name ?? obj.programName),
    total: num(obj.total_score ?? obj.total),
    structural: num(obj.structural_score ?? obj.structural),
    structuralMax: num(obj.structural_max ?? obj.structuralMax, 60),
    businessRules: num(obj.business_rules_score ?? obj.businessRules),
    businessRulesMax: num(obj.business_rules_max ?? obj.businessRulesMax, 40),
    decision: str(obj.decision, "manual_review") as ConversionDecision,
    summary: str(obj.summary),
    breakdown,
    categoryScores,
    semanticDetail,
    analysisMode,
  };
}

export function scoreListValue(score: NormalizedConversionScore | null | undefined): number | null {
  if (!score || !Number.isFinite(score.total)) return null;
  return Math.round(score.total);
}

export function formatScoreCompact(score: NormalizedConversionScore | null | undefined): string {
  if (!score || !Number.isFinite(score.total)) return "—";
  return `${Math.round(score.total)}/100`;
}

export function decisionTone(decision: string): "success" | "warning" | "danger" | "neutral" {
  const d = decision.toLowerCase();
  if (d === "auto_approve" || (d.includes("auto") && d.includes("approve"))) return "success";
  if (d === "reconversion_required" || d.includes("reconvert")) return "danger";
  if (d === "manual_review_recommended" || d === "manual_review" || d.includes("manual")) return "warning";
  return "neutral";
}

export function decisionLabel(decision: string): string {
  const d = decision.toLowerCase();
  if (d === "auto_approve") return "Auto approve";
  if (d === "manual_review_recommended") return "Manual review recommended";
  if (d === "manual_review") return "Manual review";
  if (d === "reconversion_required") return "Reconversion required";
  return decision.replace(/_/g, " ");
}

/** @deprecated use decisionLabel */
export const formatDecisionLabel = decisionLabel;
/** @deprecated use decisionTone */
export function decisionBadgeTone(
  decision: string,
): "success" | "running" | "error" | "neutral" {
  const t = decisionTone(decision);
  if (t === "success") return "success";
  if (t === "warning") return "running";
  if (t === "danger") return "error";
  return "neutral";
}

export type ComplexityLabel = "Simple" | "Medium" | "Complex" | "Mixed" | "Unknown";

export type ComplexityTierLabel = "Standard" | "Complex" | "Enterprise";

export interface ComplexityTierView {
  tier: ComplexityTierLabel;
  ibmRating: string;
  drivers: string[];
}

/** Drop line-count entries from complexity tooltip drivers (e.g. "1126 lines"). */
export function filterComplexityDriversForTooltip(drivers: string[]): string[] {
  return drivers.filter((d) => !/\blines\b/i.test(String(d).trim()));
}

const RANK: Record<string, number> = { low: 1, simple: 1, medium: 2, med: 2, high: 3, complex: 3 };

function normalizeComplexityToken(v: unknown): string | null {
  if (v == null) return null;
  const s = String(v).trim().toLowerCase();
  if (!s || s === "n/a" || s === "unknown") return null;
  return s;
}

export function complexityFromAnalysis(analysis: unknown): ComplexityLabel {
  const token = normalizeComplexityToken(
    analysis && typeof analysis === "object" ? (analysis as { complexity?: unknown }).complexity : null,
  );
  if (!token) return "Unknown";
  if (token.includes("mix")) return "Mixed";
  const rank = RANK[token];
  if (rank === 1) return "Simple";
  if (rank === 2) return "Medium";
  if (rank === 3) return "Complex";
  return "Unknown";
}

export function complexityFromAnalyses(analyses: unknown[]): ComplexityLabel {
  const ranks = new Set<number>();
  for (const a of analyses) {
    const token = normalizeComplexityToken(
      a && typeof a === "object" ? (a as { complexity?: unknown }).complexity : null,
    );
    if (!token) continue;
    if (token.includes("mix")) return "Mixed";
    const r = RANK[token];
    if (r) ranks.add(r);
  }
  if (ranks.size === 0) return "Unknown";
  if (ranks.size > 1) return "Mixed";
  const only = [...ranks][0];
  if (only === 1) return "Simple";
  if (only === 2) return "Medium";
  return "Complex";
}

export function complexityBadgeTone(
  label: ComplexityLabel | null | undefined,
): "success" | "running" | "error" | "idle" | "neutral" {
  if (!label || label === "Unknown") return "idle";
  if (label === "Simple") return "success";
  if (label === "Medium") return "running";
  if (label === "Complex" || label === "Mixed") return "error";
  return "neutral";
}

export function complexityTierFromAnalysis(analysis: unknown): ComplexityTierView | null {
  if (!analysis || typeof analysis !== "object") return null;
  const raw = (analysis as { complexity_tier?: unknown }).complexity_tier;
  if (raw && typeof raw === "object") {
    const tierObj = raw as Record<string, unknown>;
    const tier = String(tierObj.tier || "");
    if (tier === "Standard" || tier === "Complex" || tier === "Enterprise") {
      return {
        tier,
        ibmRating: String(tierObj.ibm_rating_equivalent ?? tierObj.ibmRating ?? ""),
        drivers: filterComplexityDriversForTooltip(
          Array.isArray(tierObj.drivers) ? tierObj.drivers.map(String) : [],
        ),
      };
    }
  }

  const legacy = complexityFromAnalysis(analysis);
  if (legacy === "Simple") {
    return { tier: "Standard", ibmRating: "0-3", drivers: [] };
  }
  if (legacy === "Medium" || legacy === "Mixed") {
    return { tier: "Complex", ibmRating: "4-6", drivers: [] };
  }
  if (legacy === "Complex") {
    return { tier: "Enterprise", ibmRating: "7-9", drivers: [] };
  }
  return null;
}
