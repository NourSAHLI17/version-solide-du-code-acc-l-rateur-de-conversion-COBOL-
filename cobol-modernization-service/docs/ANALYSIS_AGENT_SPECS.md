# Analysis Agent: Semantic Aggregator & Profiler

## 1. Purpose

The Analysis Agent represents the **Semantic Aggregator**. It consumes the structural output of the Parser and the paragraph slices of the Segmenter to build a high-level, human-readable profile of the program.

## 2. Methodology: Paragraph-to-Program Induction

The agent operates in three stages:

### Stage A: Segment-Level Analysis
For each paragraph, the agent induces:
- **Role Classification**: Is this an "Entry Point", an "Orchestrator", a "Data Processor", or a "Termination" block?
- **Business Rule Extraction**: Identifying logic like "Apply 10% discount if item is taxable".
- **Local Risks**: Identifying loops, complex branches, or risky constructs like `REDEFINES`.

### Stage B: Relationship Analysis
The agent tracks the "reachability" of paragraphs:
- **Called By**: Which paragraphs invoke this one?
- **Calls**: Which paragraphs does this one invoke?
- **Dead Code Detection**: Paragraphs that are neither entry points nor called by anyone else are flagged as unreachable.

### Stage C: Program Aggregation
The individual paragraph profiles are aggregated into a global summary:
- **Global Purpose**: A 1-sentence summary of the program's business goal.
- **Complexity Assessment**: Driving a "Simple", "Medium", or "High" score based on branch density, file I/O, and control-flow patterns.
- **Conversion Guidance**: Providing the downstream LLM with specific hints on how to handle the code (e.g., "This program is monolithic and should be chunked").

## 3. Grounding Principle: No Invented Rules

The Analysis Agent is strictly forbidden from "inventing" business rules (e.g., adding user-confirmation steps that don't exist in COBOL). All extracted rules must be verifiable in the source code or AST.

## 4. Complexity Drivers

The agent tracks specific "drivers" that increase cognitive load for modernization:
- **Unstructured Control Flow**: Use of `GO TO` or `PERFORM THRU`.
- **Figurative Constants**: Use of `SPACES`, `ZEROS`, etc.
- **External Dependencies**: Use of `COPY` blocks or external `CALL` statements.
- **Dense Logic**: High number of nested `IF` or `EVALUATE` statements.
