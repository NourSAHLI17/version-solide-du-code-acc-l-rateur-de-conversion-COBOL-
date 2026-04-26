# Architecture 03 - Project Upload and Batch Flow

This document explains the project-upload pipeline and why it is different from single-file conversion.

## Project Upload Goal

Project upload handles a ZIP containing multiple files, such as:

- `.cbl`
- `.cob`
- `.cobol`
- `.cpy`
- `.copy`
- `.cpb`
- `.jcl`
- `.proc`
- other supporting files

Why we need it:

- real COBOL systems are multi-file
- COPY books are often separate from source programs
- project context matters for conversion
- users need batch conversion and download

## Upload Approach

Endpoint:

```text
POST /api/project/upload
```

The backend reads the ZIP and returns a file tree:

```json
{
  "files": [
    {
      "path": "src/PROGRAM.cbl",
      "type": "cobol",
      "size": 1234,
      "content": "..."
    }
  ],
  "total": 1
}
```

Why this approach:

- frontend can show an IDE-style file explorer
- backend does not need to store uploaded files permanently
- users can inspect file content before running conversion
- project pipeline can receive the exact file list back as JSON

## File Type Classification

The backend classifies files by extension:

- COBOL source: `.cbl`, `.cob`, `.cobol`
- JCL: `.jcl`, `.proc`
- copybook: `.cpy`, `.copy`, `.cpb`
- other: everything else

Why we need it:

- only COBOL files are converted
- copybooks are used for inline COPY resolution
- JCL/proc files are useful context even when not directly converted
- other files should remain visible but skipped

## Project Pipeline Approach

Endpoint:

```text
POST /api/project/pipeline
```

Input:

```json
{
  "files": [],
  "mode": "full"
}
```

Output:

```json
{
  "results": [],
  "total_files": 0
}
```

The backend processes only files with:

```python
f.get("type") == "cobol"
```

Why this approach:

- copybooks and JCL are context, not Java conversion targets
- each COBOL file gets its own result object
- failures are isolated per file

## In-Memory COPY Resolution For Project Files

`run_project_pipeline()` builds a copybook library:

```python
copybook_lib = {
    Path(f["path"]).stem.upper(): f["content"]
    for f in copybook_files
}
```

Then it replaces `COPY X.` patterns from uploaded copybooks.

Why we need it:

- project ZIP may include copybooks not present on disk
- users should not need to configure server copybook folders for uploaded projects
- parser output should include copied declarations where possible

Why this approach:

- simple in-memory resolution for uploaded ZIP content
- avoids persistent temp project state
- keeps batch run self-contained

## Per-COBOL Result Contract

Each COBOL file result can contain:

- `file`
- `errors`
- `parser_output`
- `analysis_output`
- `java_source`
- `test_report`

Why parser and analysis are always returned:

- users want to inspect parser output for each `.cbl`
- users want to inspect analysis output for each `.cbl`
- testing and debugging need stage artifacts
- frontend can feed the Testing Agent from project results

## Project Pipeline Modes

Modes match single-file modes:

- `full`
- `parse_only`
- `parse_analyse`
- `analyse_only`
- `convert_only`
- `no_parse`

Why use the same modes:

- frontend selector stays consistent
- user mental model is the same across single-file and project workflows
- conversion prompt context can be compared across modes

## Project Testing Behavior

When mode is `full` and Java is generated, the backend also attaches:

```json
{
  "test_report": {}
}
```

Why only full mode:

- testing is the most expensive and environment-dependent part
- parser-only or analysis-only style modes should not force testing
- full mode means the user requested the complete pipeline

## Download Approach

Endpoint:

```text
POST /api/download/project
```

The backend streams a ZIP with:

- converted Java files under `src/main/java/`
- test reports under `reports/`

Why this approach:

- frontend does not need to zip files itself
- backend uses the same result objects it generated
- test reports travel with converted Java

## Frontend Project Page Role

The project page should:

- upload ZIP
- show project files
- preview selected file content
- run project pipeline
- show parser and analysis outputs for selected `.cbl`
- show stage badges per file
- store first generated Java result in shared workspace for Testing Agent

Why we need this:

- users need visibility into every file
- batch conversion should not hide parser/analysis details
- Testing Agent should work after project generation, not only single-file generation

