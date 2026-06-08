# COBOL Modernization App — End-to-End Workflow Overview

## Goal

The app should behave like a conversion reliability platform, not just a converter. The user should be able to convert COBOL to Java, validate the output, see a reliability score, decide whether the conversion is trustworthy, retry only the affected scope if needed, and save to history only when the result is stable.

---

## Core Principle

Conversion is not finished when Java is produced. Conversion is finished when the output is validated and judged reliable.

---

## Main User Journey

1. User selects or uploads COBOL.
2. User runs parser, analysis, and conversion.
3. The app generates behavioral diff and tests.
4. The app computes a reliability score.
5. The UI shows a decision such as:
   - reliable enough to save,
   - needs more validation,
   - retry recommended.
6. If needed, the user manually retries only the affected scope.
7. Stable results are saved to history.

---

## What the Reliability Score Means

The reliability score answers one question:

**Can I trust this conversion?**

A high score means:
- the converted Java matches the COBOL behavior well enough,
- the tests pass,
- the diff is small.

A low score means:
- something is still off,
- the user should retry a narrower scope or inspect failures before saving.

---

## Decision States

### Ready to save
- score high,
- tests pass,
- diff acceptable.

### Needs more validation
- score borderline,
- result potentially good,
- but confidence is not yet strong enough.

### Retry recommended
- tests fail,
- diff too large,
- or the scope suggests unresolved issues.

---

## Retry Loop

The retry loop should sit inside the testing phase, not after the user already accepted the conversion.

Flow:
- Convert.
- Test.
- Score.
- If the score is not good enough, retry the affected scope.
- Re-test.
- Re-score.
- Only then save to history.

The retry action must be manual. The app suggests the scope, but the user clicks retry.

---

## Save Gating

History should only store stable outputs.

A run should be saveable only when:
- the score is high enough,
- the diff is acceptable,
- all required tests pass,
- no unresolved retry scope remains.

---

## Mental Model

**Convert → Test → Score → Decide → Retry if needed → Save when reliable**
