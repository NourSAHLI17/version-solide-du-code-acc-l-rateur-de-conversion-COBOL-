# Architecture 04 - Testing, Validation, and Download Logic

This document explains the quality and output parts of the project.

## Why Testing Is Separate From Conversion

Conversion generates Java, but generated Java still needs checks.

The Testing Agent is separate because:

- conversion can succeed while behavior is wrong
- parser output and Java output can be checked structurally
- Java compilation depends on local tools
- behavioral comparison depends on local COBOL and Java runtimes

Endpoint:

```text
POST /api/test
```

## Testing Agent Approach

The testing agent has three groups:

```text
parser_tests
conversion_tests
behavioral_tests
```

Why this approach:

- parser tests validate structural source extraction
- conversion tests validate Java static rules
- behavioral tests attempt runtime equivalence

## Parser Tests

Parser tests check:

- symbols have `pic` or `kind`
- PERFORM targets exist as paragraphs
- paragraph names are not reserved words
- loop metadata is complete
- conditional calls are registered

Why we need them:

- conversion depends heavily on parser JSON
- bad parser output leads to bad conversion
- test report should show parser quality, not only Java quality

## Conversion Static Tests

Conversion static tests check:

- no do-while loops for PERFORM UNTIL
- no float/double for decimal fields
- BigDecimal usage for decimal fields
- OCCURS array size handling
- string padding comparison hints
- blank checks

Why we need them:

- COBOL numeric semantics are strict
- loop semantics can differ between COBOL and Java
- arrays must preserve OCCURS sizes
- string padding is common in COBOL data

Why regex-based checks:

- lightweight
- no required Java parser dependency
- works even when generated Java is not perfect
- fast enough for UI-triggered tests

## Behavioral Tests

Behavioral tests use subprocess calls:

- `javac -version`
- `cobc --version`
- `javac`
- `java`
- optional compiled COBOL executable

Why we need them:

- behavior matters more than syntax
- stdout comparison can catch semantic drift
- generated Java may compile but produce wrong results

Why this approach:

- uses real compilers when available
- degrades with clear compile/tool errors
- produces stdout diff and assertion failures

## Test Summary

The backend returns:

```json
{
  "summary": {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "critical_failures": 0,
    "high_failures": 0
  },
  "is_pipeline_green": true
}
```

Why we need summary:

- frontend can show quick status
- users can identify severity quickly
- batch project results can include test reports

## Validation Service

Endpoint:

```text
POST /api/validate
```

Validation compares expected and actual output.

Modes:

- JSON structure comparison
- normalized text comparison
- line diff comparison

Why we need it:

- users may have expected output from legacy COBOL
- generated Java output needs equivalence checks
- JSON output should not fail because of formatting
- text output should show exact line differences when needed

Why this approach:

- deterministic
- simple response shape
- independent from LLM and compiler tools

## Download Java

Endpoint:

```text
POST /api/download/java
```

Why we need it:

- users need a real `.java` file
- browser download behavior needs response headers

Why backend streaming:

- source stays exactly as backend generated it
- filename can be controlled with `Content-Disposition`

## Download Project

Endpoint:

```text
POST /api/download/project
```

The ZIP includes:

- Java files
- test report JSON files

Why we need it:

- project upload can generate many Java files
- users need one downloadable artifact
- test reports should be preserved with code

Why this approach:

- backend already has result objects
- backend can build ZIP in memory
- frontend only needs to request and download a blob

## Frontend Testing Agent Dependency

The Testing Agent page needs generated Java from:

- Single File page
- Conversion page
- Project Upload page

Why shared workspace is needed:

- user may generate Java on one page and test it on another
- project upload results must persist across navigation
- Testing Agent should not only depend on single-file `javaCode`

