# Architecture 00 - System Logic and Big Picture

This document explains the project architecture at a practical level: what each part does, why it exists, and why the current approach is useful for COBOL-to-Java modernization.

## What This Project Is

The project is a COBOL modernization platform with:

- a FastAPI backend in `cobol-modernization-service`
- a Next.js frontend in `cobol-modernization-dashboard`
- deterministic parsing, JCL parsing, COPY resolution, segmentation, analysis, conversion, testing, validation, upload, and download flows

The backend exposes all public endpoints under:

```text
/api
```

The frontend calls those real API endpoints. It is not intended to fake pipeline results in the UI.

## Main Architecture Idea

The system separates modernization into stages instead of sending raw COBOL directly to an LLM every time.

The high-level flow is:

```text
COBOL/JCL/project files
  -> JCL parse
  -> COPY resolve
  -> COBOL parse
  -> analysis
  -> conversion
  -> testing
  -> validation/download
```

Not every user path runs every stage. The platform supports mode-based execution so users can test one part at a time or run an end-to-end project batch.

## Why We Need Stages

COBOL modernization is risky because old COBOL programs often depend on:

- fixed-format columns
- COPY books
- JCL file bindings
- paragraph-level control flow
- global working-storage state
- file I/O behavior
- numeric PIC semantics
- loops, GO TO, PERFORM, EVALUATE, and external calls

If the project uses one large raw LLM prompt, the model can miss these details. The staged approach gives the conversion step structured evidence.

## Why FastAPI

FastAPI is used because it gives:

- typed request models through Pydantic
- automatic OpenAPI docs
- straightforward route structure
- easy frontend integration through JSON endpoints
- simple file upload and streaming download support

This fits the project because every pipeline stage can be exposed independently.

## Why a Central `PipelineService`

`PipelineService` is the backend orchestration layer. It keeps route functions thin and moves pipeline logic into one place.

Why this is useful:

- route handlers stay simple
- tests can call service methods directly
- pipeline modes are centralized
- frontend behavior maps to one backend source of truth
- future changes to stage order do not require rewriting every route

## Why Deterministic Components Before LLM Components

The parser, JCL parser, COPY resolver, segmenter, aggregator, validation service, and testing agent are deterministic. They do not rely on LLM guesses.

This matters because:

- parser output must be stable
- file bindings must not be invented
- COPY expansion must be traceable
- risk flags and control flow need reproducible behavior
- tests should not depend on model randomness

The LLM conversion agent is used only when Java generation is needed. It receives raw COBOL plus structured context.

## Why the Frontend Has Multiple Pages

The frontend separates user workflows:

- Single File page: quick pipeline run on one COBOL source
- Conversion page: selective mode-based conversion
- Project Upload page: ZIP upload, file explorer, project pipeline, downloads
- Testing Agent page: run backend test report on generated Java
- Cockpit: manual step-by-step backend operation
- Parser, Analysis, Validation pages: isolated debugging for each stage

This makes the system easier to debug because users can see which stage failed.

## Backend Endpoint Groups

Core transformation:

- `POST /api/parse`
- `POST /api/analyze`
- `POST /api/convert`
- `POST /api/pipeline/run`
- `POST /api/smart-convert`

Project workflow:

- `POST /api/project/upload`
- `POST /api/project/pipeline`

Segmentation and assembly:

- `POST /api/segment`
- `POST /api/aggregate`

Quality and output:

- `POST /api/test`
- `POST /api/validate`
- `POST /api/download/java`
- `POST /api/download/project`
- `GET /api/status`

## Key Design Principle

The project tries to keep generated Java traceable to source evidence:

- COBOL source remains in every conversion prompt
- parser context can be included
- analysis context can be included
- project upload returns parser and analysis output per COBOL file
- test reports are stored alongside project conversion results

This is why the system supports different context modes instead of only one conversion path.

## When To Use Each Workflow

Use Single File when:

- testing a small COBOL program
- checking parser/analysis/conversion quickly
- debugging one source file

Use Project Upload when:

- working with many `.cbl` files
- COPY books are included in a ZIP
- JCL or project context files are present
- the user wants a ZIP of converted Java files

Use Testing Agent when:

- Java has already been generated
- parser output and Java output need static checks
- behavioral checks should be attempted with local Java/COBOL tools

Use Parser/Analysis/Validation pages when:

- debugging one stage in isolation
- checking exact JSON contracts
- comparing outputs manually

