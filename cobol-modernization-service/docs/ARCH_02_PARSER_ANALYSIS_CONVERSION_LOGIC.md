# Architecture 02 - Parser, Analysis, and Conversion Logic

This document explains why parser, analysis, and conversion are separate stages.

## Parser Stage

The parser is deterministic. Its job is not to understand business meaning. Its job is to extract structure.

It produces:

- `program_name`
- `source_format`
- `divisions`
- `sections`
- `paragraphs`
- `symbol_table`
- `control_flow`
- `operations`
- `dependencies`
- `risk_flags`
- `warnings`

Why we need it:

- COBOL syntax is old and context-heavy
- source format can be fixed or free
- data declarations drive Java types
- control flow drives method and loop conversion
- dependencies drive I/O and external-call conversion

Why this approach:

- deterministic parser output is stable
- output is easy to inspect in UI
- parser warnings help identify risky areas before LLM conversion
- parser output can be used without analysis or conversion

## Preflight Validation Inside Parser

Before full parse results are trusted, the parser checks for blocking structural problems.

Examples:

- duplicate data names
- selected files without matching FD entries
- undeclared `PERFORM VARYING` indexes
- reserved words used as paragraph names

Why we need it:

- downstream stages should not reason over broken source
- conversion should not continue blindly when structural evidence is unsafe

Why this approach:

- fail early for structural issues
- return the same parser contract with `preflight_errors`
- let analysis choose a halted strategy

## Analysis Stage

The analysis agent turns parser structure and source text into semantic context.

It produces:

- `global_purpose`
- `complexity`
- `complexity_drivers`
- `sections`
- `business_rules`
- `file_io_paragraphs`
- `loop_paragraphs`
- `risk_points`
- `risk_flags`
- `conversion_guidance`
- `data_flow_summary`
- `warnings`

Why we need it:

- parser tells what exists
- analysis explains why it matters
- conversion needs business rules, risks, and guidance

Why this approach:

- analysis remains grounded in parser output and source text
- business rules are extracted from structural evidence
- it avoids inventing rules when evidence is absent
- complexity and risk guide conversion strategy

## Segment-Based Analysis

`AnalysisAgent` uses `CobolSegmenter`.

The segmenter gives paragraph-focused context:

- source lines
- symbol reads/writes
- file I/O presence
- loop presence
- branch presence
- GO TO presence

Why we need it:

- COBOL programs are paragraph-oriented
- business behavior is often localized in paragraphs
- conversion needs paragraph-to-method mapping

Why this approach:

- paragraph analysis is easier to explain
- risk and business rules can be mapped to named COBOL sections
- generated Java can preserve traceability to COBOL paragraphs

## Conversion Stage

The conversion agent builds a prompt with:

- raw COBOL source
- context mode
- parser output JSON
- analysis output JSON
- conversion configuration JSON

Why raw COBOL is always included:

- parser and analysis may omit syntax details
- conversion still needs exact source lines
- missing context should not remove source evidence

Why context modes exist:

- `COBOL source only` helps fallback conversion
- `COBOL + parser` tests structural conversion without semantic analysis
- `COBOL + analysis` tests business-guided conversion without parser constraints
- `COBOL + parser + analysis` gives maximum context

Why this approach:

- prompt tells the LLM exactly which context exists
- prompt explicitly says not to invent missing parser or analysis facts
- mode comparison helps debug bad conversions

## Conversion Configuration

The conversion agent derives config from parser and analysis:

- target language: Java
- Java version: 17
- package name from program name
- decimal strategy: BigDecimal
- I/O strategy based on file dependencies
- complexity hint from analysis

Why we need it:

- Java generation needs consistent conventions
- numeric behavior is critical in COBOL
- file programs need different Java structure from in-memory programs

Why this approach:

- config is generated from backend evidence
- prompt stays consistent across providers
- provider-specific code does not change conversion rules

## LLM Provider Abstraction

`ConversionAgent` supports:

- Google
- OpenAI
- OpenRouter
- stub fallback

Why we need it:

- users may have different API keys
- local dev should not crash without an LLM key
- frontend can still show conversion availability status

Why this approach:

- provider selection is environment-driven
- runtime status reports model and readiness
- stub response keeps the backend usable in demos and tests

