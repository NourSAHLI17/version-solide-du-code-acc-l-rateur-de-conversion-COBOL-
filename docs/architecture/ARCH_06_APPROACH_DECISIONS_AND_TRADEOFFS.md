# Architecture 06 - Approach Decisions and Tradeoffs

This document explains why the project uses its current approaches. It is written as a decision guide for future developers.

## Decision 1: Use A Staged Pipeline Instead Of One Big Prompt

Approach:

```text
COPY/JCL context -> parser -> analysis -> conversion -> testing -> validation
```

Why we need it:

- COBOL behavior depends on data declarations, file bindings, COPY books, and paragraph flow.
- One large prompt can hide missing information and make failures hard to debug.
- Users need to inspect parser and analysis output before trusting generated Java.

Why this approach:

- Each stage has an output that can be shown in the frontend.
- Each stage can be tested independently.
- Conversion can compare multiple context modes.
- Bugs become easier to locate because the failed stage is visible.

Tradeoff:

- More code and more endpoints are required.
- The user may need to understand pipeline stages.
- The benefit is much better traceability and safer conversion.

## Decision 2: Keep Deterministic Components Before LLM Components

Approach:

Use deterministic services for parsing, copybook resolution, segmentation, aggregation, testing, and validation. Use the LLM provider only for Java generation.

Why we need it:

- Parser output must be stable.
- COPY expansion must not invent source.
- Test and validation reports must be repeatable.
- Backend tests need to run without an LLM key.

Why this approach:

- Deterministic services create reliable evidence.
- The LLM receives explicit context instead of guessing everything.
- Local development still works through stub fallback behavior.

Tradeoff:

- Deterministic parsers may be less complete than a full commercial COBOL parser.
- The benefit is predictable behavior and easier debugging.

## Decision 3: Always Include Raw COBOL In Conversion

Approach:

The conversion prompt receives the raw COBOL source in every mode. Parser output and analysis output are optional context layers.

Why we need it:

- Parser output can omit formatting or exact source details.
- Analysis output can summarize behavior but not replace source code.
- Conversion must always have the original evidence.

Why this approach:

- Raw source remains the ground truth.
- Mode-specific context can be added or removed without removing source evidence.
- The LLM is told what context exists and what context is missing.

Tradeoff:

- Prompts can become longer.
- The benefit is safer Java generation with fewer missing-source mistakes.

## Decision 4: Support Multiple Pipeline Modes

Approach:

The backend supports modes such as `full`, `parse_only`, `parse_analyse`, `analyse_only`, `convert_only`, and `no_parse`.

Why we need it:

- Developers need to test conversion with parser context only.
- Developers need to test conversion with analysis context only.
- Users may want a fast raw conversion.
- Debugging requires isolating the effect of each context layer.

Why this approach:

- One API endpoint can drive the frontend selector.
- The same mental model works for single-file and project-upload workflows.
- Context differences are explicit instead of hidden in frontend logic.

Tradeoff:

- Mode names must stay clear and documented.
- The benefit is controlled experimentation and easier bug reports.

## Decision 5: Process Project Uploads In Memory

Approach:

The project upload endpoint reads ZIP contents and returns file records to the frontend. The project pipeline receives those records back and processes them without permanent server storage.

Why we need it:

- Users need to upload multi-file COBOL projects.
- Copybooks included in the ZIP must be available during parsing.
- The frontend needs a file explorer and file preview.

Why this approach:

- No persistent project database is required.
- Uploaded projects remain self-contained.
- Batch conversion can be repeated from the same frontend state.

Tradeoff:

- Very large projects may need future streaming or storage support.
- The benefit is simple local development and a clear API contract.

## Decision 6: Return Parser And Analysis For Every COBOL File In Project Upload

Approach:

Project results include `parser_output` and `analysis_output` per COBOL file whenever those artifacts are generated.

Why we need it:

- Users want to inspect every `.cbl` file, not only the generated Java.
- The Testing Agent can reuse project parser output.
- Batch failures should be diagnosable file by file.

Why this approach:

- The project page can show stage badges and artifact panels.
- One failed file does not hide successful output from other files.
- Parser and analysis become first-class project artifacts.

Tradeoff:

- Response payloads are larger.
- The benefit is much better visibility for real projects.

## Decision 7: Use A Shared Frontend Workspace

Approach:

The frontend stores source, parser output, analysis output, Java output, project results, validation output, backend status, and errors in a shared workspace.

Why we need it:

- Users generate Java on one page and test it on another page.
- Project upload should feed the Testing Agent.
- Navigation should not clear successful pipeline artifacts.

Why this approach:

- Pages stay focused on their own UX while sharing artifacts.
- The Testing Agent can find generated Java from single-file or project workflows.
- Hydration guards prevent client storage from being overwritten during startup.

Tradeoff:

- Workspace state must be carefully synchronized.
- The benefit is a smoother multi-page workflow.

## Decision 8: Keep Backend As The Source Of Truth

Approach:

The frontend displays real backend artifacts and should not invent parser, analysis, Java, or test results.

Why we need it:

- Modernization output must be trustworthy.
- Mock data can hide integration bugs.
- Tests and downloads should match what the backend produced.

Why this approach:

- UI state maps directly to API responses.
- Backend tests validate contracts used by the frontend.
- Users see real failures instead of decorative success states.

Tradeoff:

- The UI can look empty when backend data is missing.
- The benefit is honest debugging and reliable user feedback.

## Decision 9: Use Lightweight Static Testing Before Runtime Behavioral Testing

Approach:

The Testing Agent starts with parser and Java static checks, then attempts runtime behavior only when Java and COBOL tools are available.

Why we need it:

- Runtime tools may not exist on every developer machine.
- Static checks can catch common semantic risks quickly.
- Runtime checks are still valuable when the environment supports them.

Why this approach:

- The test report degrades gracefully.
- Users get useful feedback even without every compiler installed.
- Behavioral failures can show stdout diffs when execution is possible.

Tradeoff:

- Static checks cannot prove full semantic equivalence.
- The benefit is immediate quality feedback in more environments.

## Decision 10: Keep Downloads Backend-Generated

Approach:

The backend streams single Java files and project ZIP files.

Why we need it:

- The backend owns generated Java and test reports.
- Project ZIP downloads must include multiple Java files and report JSON.
- Browser code should not duplicate ZIP assembly rules.

Why this approach:

- Download behavior is consistent.
- File naming can be controlled in one place.
- Frontend only handles the response blob.

Tradeoff:

- Backend must build archives in memory.
- The benefit is simpler frontend code and consistent artifacts.

## Extension Checklist

Use this checklist when adding a new project part:

- Identify whether the part is deterministic or LLM-driven.
- Add or update the backend service first.
- Expose the service through a typed route model.
- Return a visible artifact that the frontend can display.
- Store reusable artifacts in shared workspace when another page needs them.
- Add tests for the service or route contract.
- Update the architecture docs with what the part does, why it exists, and why the approach was chosen.

## Practical Rule

If a future feature cannot explain its input, output, and reason for existing, it probably belongs behind a clearer pipeline stage before it reaches conversion.
