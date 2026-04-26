# Architecture 05 - Frontend and Backend Interaction

This document explains how the frontend should think about backend pipeline parts.

## Frontend Responsibility

The frontend is not the modernization engine.

Its responsibilities are:

- collect user input
- call real backend endpoints
- display backend artifacts
- preserve workspace state across pages
- let users run stages and inspect outputs
- download backend-generated files

Why this approach:

- backend remains source of truth
- frontend can evolve visually without changing pipeline logic
- API contracts remain testable

## Shared Workspace

The frontend keeps a shared workspace with:

- `sourceCode`
- `parserResult`
- `analysisResult`
- `javaCode`
- `projectResults`
- `jclManifest`
- `validationResult`
- `backendStatus`
- `lastError`
- expected and actual output fields

Why we need it:

- generated Java from one page must be testable on another page
- parser and analysis results are reused by conversion modes
- project upload can feed Testing Agent
- users should not lose work when navigating

Why hydration matters:

- Next.js renders on server and client
- browser `localStorage` exists only on the client
- workspace must not overwrite saved data before hydration finishes

## Single File Page

The Single File page calls:

```text
POST /api/pipeline/run
```

Why use this endpoint:

- supports mode selector
- returns parser, analysis, and Java artifacts depending on mode
- keeps frontend logic simple

## Conversion Page

The Conversion page also uses:

```text
POST /api/pipeline/run
```

Why separate from Single File:

- conversion-focused UX
- shows cost estimates
- lets users test mode behavior around conversion context

## Project Upload Page

The Project Upload page calls:

```text
POST /api/project/upload
POST /api/project/pipeline
POST /api/download/project
```

Why three endpoints:

- upload extracts files from ZIP
- project pipeline processes the extracted files
- download creates a ZIP from result objects

What it should display:

- file explorer
- selected file content
- parser output for selected COBOL file
- analysis output for selected COBOL file
- stage status per file
- download option

## Testing Agent Page

The Testing Agent page calls:

```text
POST /api/test
```

It should use:

- `workspace.javaCode` when available
- latest project result with `java_source` when single-file Java is not available
- parser and analysis output from workspace or project result

Why this approach:

- testing works after both single-file and project conversion
- users do not have to manually copy Java between pages
- the page reflects actual generated backend artifacts

## Health Strip

The health UI calls:

```text
GET /api/status
```

Why we need it:

- tells user whether backend is reachable
- shows LLM readiness
- shows parser backend
- helps diagnose conversion failures caused by missing keys

## Error Display

Backend errors usually return JSON or text from failed requests.

Frontend should:

- show `lastError`
- keep previous successful artifacts where possible
- avoid clearing workspace on page load
- not hide backend errors behind generic UI messages only

Why this approach:

- users can debug endpoint or backend status problems
- generated artifacts are not lost when one stage fails

## Design Principle

Every page should show real pipeline artifacts:

- parser output is backend parser JSON
- analysis output is backend analysis JSON
- Java output is backend conversion text
- testing output is backend test report
- validation output is backend validation report

No page should invent success data just to make the UI look complete.

