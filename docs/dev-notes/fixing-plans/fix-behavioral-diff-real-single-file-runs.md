# Cursor Prompt — Fix Behavioral Diff Replay for Real Single-File Runs

## Context

We are working in the COBOL modernization service:
`C:\Users\LENOVO\Desktop\cobol1\cobol\cobol-modernization-service`

I have a single-file example where the COBOL input and Java output are both valid, but the Testing page still reports:
- Reliability decision: 54
- Retry recommended
- Behavioral diff: 100% match
- Behavioral: not run / fail
- Compared 0 lines
- COBOL output empty
- Java output empty
- Retry scope: program low confidence

This means the conversion output is probably fine, but the behavioral replay / diff layer is not running correctly.

## Goal

Fix the testing agent so that a real single-file conversion run uses the actual COBOL input, Java output, and behavioral scenario when the user clicks **Run Testing**.

The testing dashboard must not show placeholder or empty diff data when a real conversion exists.

## What must happen

For a real single-file run like `TEMPCNVT`:
1. The conversion page produces COBOL source, parser JSON, analysis JSON, and Java output.
2. The user clicks **Run Testing**.
3. The testing page receives the real run context.
4. The behavioral diff runner compares real stdout or real scenario output.
5. The diff panel shows actual compared lines and outputs.
6. The reliability score is computed from the real result.
7. The decision panel shows a trustworthy state.
8. Retry scope is derived from the actual failure attribution if any.

## Current bug symptoms

The current output suggests one or more of these problems:
- the testing page is using fallback/default scenario data,
- the behavioral diff runner is not receiving the real payload,
- stdout capture is empty,
- the launch handoff is not restoring the selected run correctly,
- the failed behavioral state is being reported even when the diff did not truly run.

## What to inspect

### 1. Testing launch handoff
Check the conversion-to-testing handoff logic.
Make sure the following are passed or persisted correctly:
- `source`
- `runId` or `historyId`
- `program_name`
- `parser_json`
- `analysis_json`
- `java_source`
- `scriptedInput` or behavioral scenario input if present

### 2. Real data loading on `/testing`
The testing page must load the real conversion workspace and not a stale project from localStorage.
If a real run exists, it should restore that run and run the replay from that state.

### 3. Behavioral diff runner input
Verify the diff runner gets non-empty real inputs for both COBOL and Java.
It should not compare empty strings or placeholder outputs.

### 4. Run status logic
If the diff has not actually executed, do not label the behavioral section as failed.
Use a distinct status such as:
- `not_run`
- `waiting_for_input`
- `missing_artifacts`
Only mark it as failed when the replay actually ran and failed.

### 5. Retry scope derivation
If there is no real paragraph attribution, do not force a bogus program-low-confidence failure unless the replay really failed.
The retry scope should come from actual failure metadata when available.

## Required UI behavior

For real conversion runs:
- show the actual behavioral diff output,
- show real compared line counts,
- show real stdout excerpts,
- show the proper failure reason if it fails,
- show the final score based on the real execution.

For fallback runs:
- explicitly label them as fallback or sample data,
- do not mix them with real replay results.

## Acceptance criteria

This fix is done when:
- TEMPCNVT and other real single-file runs replay with real inputs,
- the diff panel no longer shows empty stdout when it should not,
- the behavioral section no longer says `not run / fail` incorrectly,
- the score reflects the actual replay result,
- the retry scope is attributed from real data when possible.

## Suggested implementation direction

- Make the launch handoff persist the selected run before navigating.
- Make the testing page rehydrate the exact run from the handoff.
- Make the diff runner require real inputs and return a clear `not_run` state if inputs are missing.
- Separate real replay results from fallback/sample results in the UI.

## Final mental model

**Conversion result exists → testing page restores it → behavioral diff runs on real data → score + decision are computed from actual replay**
