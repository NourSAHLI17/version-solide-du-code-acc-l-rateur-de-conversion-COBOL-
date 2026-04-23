export type PipelineMode = "full" | "parse_only" | "parse_analyse" | "analyse_only" | "convert_only" | "no_parse";

export interface PipelineModeOption {
  value: PipelineMode;
  label: string;
  description: string;
  color: "violet" | "sky" | "pink" | "emerald";
}

export const PIPELINE_MODES: PipelineModeOption[] = [
  {
    value: "full",
    label: "Full Pipeline",
    color: "violet",
    description: "Parse, analyse, convert, and test when available",
  },
  {
    value: "parse_only",
    label: "Parser Context Convert",
    color: "sky",
    description: "Convert Java with COBOL source plus parser output only",
  },
  {
    value: "parse_analyse",
    label: "Parser + Analysis Convert",
    color: "pink",
    description: "Convert Java with both parser and analysis context",
  },
  {
    value: "analyse_only",
    label: "Analysis Context Convert",
    color: "violet",
    description: "Convert Java with COBOL source plus analysis output only",
  },
  {
    value: "no_parse",
    label: "Direct Convert",
    color: "emerald",
    description: "Send raw COBOL to conversion without parser context",
  },
];

export const PROJECT_PIPELINE_MODES: PipelineModeOption[] = [
  ...PIPELINE_MODES,
  {
    value: "convert_only",
    label: "Convert Only",
    color: "emerald",
    description: "Use existing project context and generate Java output",
  },
];

export const STAGES_FOR_MODE: Record<PipelineMode, string[]> = {
  full: ["Copy", "Parse", "Analyse", "Convert", "Test"],
  parse_only: ["Copy", "Parse"],
  parse_analyse: ["Copy", "Parse", "Analyse"],
  analyse_only: ["Analyse", "Convert"],
  convert_only: ["Convert"],
  no_parse: ["Convert"],
};
